"""Ollama provider: local models, structured output through the `format` JSON schema."""

from __future__ import annotations

import contextlib
import json
import logging
import re
import socket
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import httpx

from ..config import settings
from .base import AnswerCut, ContextOverflow, Generation, ProviderError, failed_call

log = logging.getLogger(__name__)

# How long health waits for the endpoint's list of models: a probe, which a running server answers at once.
HEALTH_PROBE_TIMEOUT_S = 5.0

# When this process last heard the model answer (time.monotonic), whether to a question or a wake-up; None until then.
# Read by application/wake_model.py to leave a model that is still awake alone.
_last_answer: float | None = None
_clock = time.monotonic


# Hops a request may take on the endpoint's own host (Modal's 303 to the waiting URL is one).
MAX_REDIRECTS = 5

# Sent with every request to the chat model, a wake-up included, so a wake-up and an answer load it the same way. A prompt larger
# than the context window is refused, never cut. Left to its default the server drops text to make room and answers
# anyway: asked for a notice period stated at the start of a prompt of 20,695 tokens, it evaluated 8,194 of them and
# answered "30 days" where the text said 47, with nothing in the response to say so (measured against Ollama 0.35.0,
# 2026-10-02). `shift` is the same rule for the answer: it may not push the prompt out of the window while it is being
# written. Both are also load settings: on 0.40.7 a request without them started llama-server with --context-shift, and
# the next answer loaded the model again (2026-10-21).
NEVER_CUT = {"truncate": False, "shift": False}

# The most a reply may hold. An answer fills at most the context window (16,384 tokens, under 100 KB of JSON) and the list
# of models is a few KB; an endpoint that sends without end was read without end, in time and in memory (stress test,
# 2026-10-30, model transport 3).
MAX_REPLY_BYTES = 8 * 1024 * 1024
# Statuses a refusal for size has come with: llama-server's 400, and the Go runner's wording at 500.
SIZE_REFUSAL_STATUSES = (400, 413, 500)

# The clock each call's deadline is kept on, and how a deadline is enforced on a reply already arriving: a timer that cuts
# its connection (both replaceable in tests).
_monotonic = time.monotonic


class _Timer(Protocol):
    def start(self) -> None: ...
    def cancel(self) -> None: ...


def _timer(seconds: float, action: Callable[[], None]) -> _Timer:
    timer = threading.Timer(seconds, action)
    timer.daemon = True
    return timer


_arm: Callable[[float, Callable[[], None]], _Timer] = _timer


def last_answer() -> float | None:
    return _last_answer


def _heard() -> None:
    global _last_answer
    _last_answer = _clock()


class _Deadline:
    """One call's whole time, on the monotonic clock. httpx's timeout bounds each connect, read, write and pool wait, not
    the request: a reply sent a byte at a time, under the read timeout, held the one admission slot for as long as it
    lasted (with a 1 s timeout, a 15 s drip succeeded and the next caller waited 15 s), and each redirect hop had a fresh
    budget (stress test, 2026-10-30, model transport 3). stale_after_seconds (application/recover_runs.py) counts one
    model timeout per call; every request a call makes, every hop of each, and every byte of each reply share it."""

    def __init__(self, seconds: float) -> None:
        self.at = _monotonic() + seconds

    def left(self) -> float:
        return self.at - _monotonic()


def _out_of_time(request: httpx.Request) -> httpx.ReadTimeout:
    return httpx.ReadTimeout("the call's time ran out", request=request)


def _cut(response: httpx.Response) -> None:
    """End a reply that is still arriving at its call's deadline: its connection is shut and closed, so a read blocked on
    it returns now rather than after its own timeout. Both, because each platform wakes on one: on Linux a shutdown wakes
    the blocked read and a close does not; on Windows a read waiting with a timeout (httpx's) wakes only on the close
    (measured 2026-10-30: after a shutdown it waited out its 10 s; after a close it returned in 0.3 s). The call is not
    abandoned: it ends here, with its connection, before the admission slot is given to the next request (abandoned, its
    answer would still share the server's one slot)."""
    stream = response.extensions.get("network_stream")
    connection = stream.get_extra_info("socket") if stream is not None else None
    if isinstance(connection, socket.socket):
        with contextlib.suppress(OSError):  # already shut: nothing is waiting on it
            connection.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            connection.close()


def _whole(response: httpx.Response, deadline: _Deadline) -> bytes:
    """The reply's body, every chunk read within the deadline and within MAX_REPLY_BYTES."""
    timer = _arm(max(0.0, deadline.left()), lambda: _cut(response))
    timer.start()
    chunks: list[bytes] = []
    size = 0
    try:
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_REPLY_BYTES:
                raise ProviderError(f"the model endpoint sent a reply larger than any answer (over {MAX_REPLY_BYTES // (1024 * 1024)} MiB); it was not read")
            chunks.append(chunk)
            if deadline.left() <= 0:
                raise _out_of_time(response.request)
    except httpx.TimeoutException:
        raise
    except httpx.HTTPError as error:
        if deadline.left() <= 0:  # the timer cut the connection
            raise _out_of_time(response.request) from error
        raise
    finally:
        timer.cancel()
    return b"".join(chunks)


def _overflow(response: httpx.Response, limit: int) -> ContextOverflow | None:
    """A refusal for size, read from the server's fields first and its words second. llama-server sends a typed body
    (type exceed_context_size_error, n_prompt_tokens, n_ctx), nested as a string inside Ollama's {"error": ...}; the Go
    runner words it ("the input length exceeds the context length") and has sent it as a 500, which was retried as an
    ordinary failure (stress test, 2026-10-30, model transport 4)."""
    if response.status_code not in SIZE_REFUSAL_STATUSES:
        return None
    text = response.text
    fields = _error_fields(text)
    typed = fields.get("type") == "exceed_context_size_error"
    lowered = text.lower()
    worded = ("exceed" in lowered and "context" in lowered) or "longer than the context" in lowered
    if not (typed or worded):
        return None
    prompt = fields.get("n_prompt_tokens")
    if not isinstance(prompt, int):
        found = re.search(r"\((\d+) tokens\)", text)
        prompt = int(found.group(1)) if found else None
    window = fields.get("n_ctx")
    return ContextOverflow(_overflow_message(prompt, window if isinstance(window, int) else limit))


def _error_fields(text: str) -> dict[str, Any]:
    """The innermost error object of a refusal, through the JSON strings Ollama wraps llama-server's in."""
    found: Any = text
    for _ in range(4):
        if isinstance(found, str):
            try:
                found = json.loads(found)
            except ValueError:
                return {}
        if isinstance(found, dict) and "error" in found:
            found = found["error"]
            continue
        break
    return found if isinstance(found, dict) else {}


def _overflow_message(prompt_tokens: int | None, limit: int) -> str:
    """What the server said, as a sentence a person can act on. The token count is the server's own."""
    size = f"{prompt_tokens:,} tokens" if prompt_tokens else "more tokens than the model can hold"
    return (
        f"The prompt's instructions, the question, the guidance, the contract's file name and the sections handed to the model come to "
        f"{size}; its context window holds {limit:,}. "
        "The request was refused rather than answered from a cut prompt. Shorten the guidance or the question and ask again."
    )


def _answer_cut(body: Mapping[str, Any], limit: int) -> AnswerCut:
    """A reply the server stopped short (done_reason "length"), in words a person can act on. Read as the model's invalid
    JSON, it was asked again with a longer prompt, which at temperature 0 is cut sooner (stress test, 2026-10-30, model
    transport 4)."""
    prompt, answer = body.get("prompt_eval_count"), body.get("eval_count")
    if isinstance(prompt, int) and isinstance(answer, int) and prompt + answer >= limit:
        return AnswerCut(
            f"The model's answer was cut where the prompt and the answer filled its {limit:,}-token context window (the prompt "
            f"used {prompt:,}, the answer {answer:,} when it was stopped). A cut answer is not read. Shorten the guidance or the question "
            "and ask again."
        )
    written = f" after {answer:,} tokens" if isinstance(answer, int) else ""
    return AnswerCut(f"The model server stopped the answer{written}, before it was complete. A cut answer is not read; ask again.")


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


class OllamaProvider:
    name = "ollama"

    def __init__(
        self, model: str | None = None, base_url: str | None = None, timeout_s: float | None = None, decoding: Mapping[str, Any] | None = None
    ) -> None:
        self.model = model or settings.model
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.timeout_s = timeout_s or settings.model_timeout_s
        self._decoding = dict(decoding) if decoding is not None else None

    def options(self) -> dict[str, Any]:
        """The decoding settings of this provider: the ones it was bound to, or the process's defaults."""
        defaults = {"temperature": settings.temperature, "seed": settings.seed, "num_ctx": settings.num_ctx}
        return defaults if self._decoding is None else {name: self._decoding.get(name, default) for name, default in defaults.items()}

    def with_options(self, options: Mapping[str, Any]) -> OllamaProvider:
        """This provider bound to the model and decoding settings a run recorded when it was created, so the call is
        made with those and not with whatever the process's settings have since become."""
        return OllamaProvider(model=str(options.get("model") or self.model), base_url=self.base_url, timeout_s=self.timeout_s, decoding=options)

    def _exchange(self, method: str, url: str, deadline: _Deadline, payload: dict[str, Any] | None) -> httpx.Response:
        """One request, its reply read whole within the call's deadline. Each wait inside it (connect, write, the first
        byte) is bounded by what is left of the deadline; the body is read chunk by chunk against it."""
        left = deadline.left()
        if left <= 0:
            raise _out_of_time(httpx.Request(method, url))
        with httpx.stream(method, url, json=payload, timeout=httpx.Timeout(left), headers=settings.ollama_headers, follow_redirects=False) as response:
            body = _whole(response, deadline)
            # The body is decoded already: the reply is handed on without the headers that described its transfer.
            headers = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
            return httpx.Response(response.status_code, headers=headers, content=body, request=response.request)

    def _send(self, method: str, url: str, deadline: _Deadline | float, payload: dict[str, Any] | None = None) -> httpx.Response:
        """One request to the endpoint, following its redirects only on its own scheme and host: the credentials
        (WORKBENCH_OLLAMA_HEADERS) go with every hop, and httpx keeps custom headers across hosts, so a redirect
        elsewhere is refused rather than followed (security review, 2026-10-13). A 303 is followed with a GET, as
        Modal's redirect to the URL that waits for a long answer requires. Every hop shares the one deadline."""
        deadline = deadline if isinstance(deadline, _Deadline) else _Deadline(deadline)
        own = httpx.URL(self.base_url)
        for _ in range(MAX_REDIRECTS + 1):
            response = self._exchange(method, url, deadline, payload if method != "GET" else None)
            location = response.headers.get("location") if response.is_redirect else None
            if location is None:
                return response
            target = response.url.join(location)
            if (target.scheme, target.host, target.port) != (own.scheme, own.host, own.port):
                raise ProviderError("the model endpoint redirected to another host; its credentials are not sent there")
            if response.status_code == 303 or (response.status_code in (301, 302) and method == "POST"):
                method, payload = "GET", None
            url = str(target)
        raise ProviderError("the model endpoint redirected too many times")

    def _tags(self, deadline: _Deadline | float) -> list[dict[str, Any]]:
        response = self._send("GET", f"{self.base_url}/api/tags", deadline)
        response.raise_for_status()
        models: list[dict[str, Any]] = response.json().get("models", [])
        return models

    def _digest(self, models: list[dict[str, Any]]) -> str:
        found = next((m for m in models if m.get("name") in (self.model, f"{self.model}:latest")), None)
        return str((found or {}).get("digest", "")).lower()

    def _build_problem(self, models: list[dict[str, Any]]) -> str | None:
        """Why the endpoint's tag is not the build the deployment pinned (settings.model_digest), or None."""
        pinned = settings.model_digest
        if not pinned:
            return None
        digest = self._digest(models)
        if not digest.startswith(pinned):
            return f"the model endpoint serves {self.model} build {digest[:12] or 'unknown'}, not the pinned build {pinned[:12]}"
        return None

    def healthy(self) -> tuple[bool, str]:
        try:
            models = self._tags(HEALTH_PROBE_TIMEOUT_S)
        except (httpx.HTTPError, ValueError, ProviderError) as error:  # ProviderError: a redirect refused (_send)
            # The endpoint's address stays in the server log; /api/health is public and never names it.
            log.warning("model endpoint %s not reachable: %s", self.base_url, type(error).__name__)
            return False, "the model endpoint is not reachable"
        names = [m.get("name", "") for m in models]
        if self.model not in names and f"{self.model}:latest" not in names:
            # What else the server holds is the operator's to read, in the log; health is answered to every visitor.
            log.warning("model %s is not pulled; the endpoint has: %s", self.model, ", ".join(names) or "none")
            return False, f"model {self.model} is not pulled"
        problem = self._build_problem(models)
        if problem:
            return False, problem
        return True, f"{self.model} ready"

    def describe_build(self) -> str:
        """The server's version and the model's build, logged at start: Ollama updates itself, and an update or a pull
        changed answers with no line in Verity's log saying so (ops audit, 2026-10-19)."""
        try:
            version = self._send("GET", f"{self.base_url}/api/version", HEALTH_PROBE_TIMEOUT_S).json().get("version", "unknown")
            models = self._tags(HEALTH_PROBE_TIMEOUT_S)
        except (httpx.HTTPError, ValueError, ProviderError) as error:
            return f"model endpoint not reachable at start ({type(error).__name__})"
        build = self._digest(models)[:12] or "not pulled"
        return f"server_version={version} model={self.model} build={build}"

    def _check_build(self, deadline: _Deadline | None = None) -> str | None:
        """Before an answer, when a build is pinned: the endpoint can change under a long-lived process (a serverless
        container replaced, a tag pulled again), so it is asked each time, not once. Returns the digest it served, or
        None when nothing is pinned."""
        if not settings.model_digest:
            return None
        try:
            # The answer's own budget, not health's: a serverless endpoint that has scaled to zero answers this first
            # request only once a container has started, a minute or more on Modal (cloud readiness review, 2026-10-12).
            models = self._tags(deadline or _Deadline(self.timeout_s))
        except (httpx.HTTPError, ValueError) as error:
            log.warning("model build check failed: %s", type(error).__name__)
            raise ProviderError("the model endpoint could not confirm its build") from error
        problem = self._build_problem(models)
        if problem:
            raise ProviderError(problem)
        return self._digest(models)

    def _clean_start_payload(self) -> dict[str, Any]:
        """The one request this provider sends the chat model that is not an answer (see _start_clean)."""
        return {"model": self.model, "prompt": "x", "raw": True, "stream": False, **NEVER_CUT, "options": {**self.options(), "num_predict": 1}}

    def chat_request(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """The one builder of an answer's request."""
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "think": False,
            **NEVER_CUT,
            "options": self.options(),
        }

    def wake(self) -> None:
        """Load the model on the endpoint before a question arrives, with the decoding settings an answer uses: the
        context window is part of what Ollama loads, so a model woken with any other would be loaded again by the first
        answer. It sends exactly the clean start an answer sends: raw, one token. It was a templated prompt ("ok"),
        which opens with the chat template's first token, the answer's own: sent outside the admission slot, it could
        land between an answer's clean start and the answer, which then started from token 1 (stress test, 2026-10-30,
        model transport 2: 18 of 40 races on a cold host). Now it shares no token with any answer, wherever it lands."""
        deadline = _Deadline(self.timeout_s)
        self._check_build(deadline)  # starts a sleeping endpoint, and confirms the pinned build as an answer would
        try:
            self._post_clean_start(deadline)
        except httpx.HTTPError as error:
            raise ProviderError(failed_call("The model could not be woken", error)) from error
        _heard()

    def _post_clean_start(self, deadline: _Deadline) -> None:
        response = self._send("POST", f"{self.base_url}/api/generate", deadline, self._clean_start_payload())
        response.raise_for_status()

    def _start_clean(self, deadline: _Deadline | None = None) -> None:
        """Leave the server's one slot holding a prompt that shares no token with the next, so the answer that follows is
        computed from its own first token. The server starts a prompt from the longest prefix it already holds, and one
        recorded input gave two answers by what was asked before it: on Ollama 0.40.7 the convenience question gave 3
        quotes from token 0 and 1 quote from token 620 (docs/CASEBOOK.md, case 6). Raw, so no chat template opens it, and
        sent with the answer's own load settings, or the server would load the model again. It works only with the
        server's host-RAM prompt cache off (LLAMA_ARG_CACHE_RAM=0), which would otherwise restore the prefix, and with the one
        slot the server runs by default (OLLAMA_NUM_PARALLEL=1) used by one request at a time (WORKBENCH_MODEL_CONCURRENCY=1,
        the admission slot this call and the answer share): with two slots the answer is given the one whose prompt is
        most like its own."""
        try:
            self._post_clean_start(deadline or _Deadline(self.timeout_s))
        except httpx.HTTPError as error:
            raise ProviderError(failed_call("The model could not be prepared for the answer", error)) from error

    def _answered_by(self, body: Mapping[str, Any]) -> str:
        """The model the reply names, when it is the one asked for (its ":latest" form either way). A reply naming another
        was recorded as the run's model, under the identity of the one asked for (stress test, 2026-10-30, model
        transport 1)."""
        named = str(body.get("model") or self.model)
        if named not in (self.model, f"{self.model}:latest", self.model.removesuffix(":latest")):
            raise ProviderError(f"the model endpoint answered as {named}, not the {self.model} asked for; the answer was not kept")
        return named

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        payload = self.chat_request(system, user, schema)
        limit = int(self.options()["num_ctx"])
        deadline = _Deadline(self.timeout_s)  # the build check, the clean start and the answer together
        before = self._check_build(deadline)
        # Timed from the clean start: when the model is not loaded, that call is the one that loads it.
        started = time.perf_counter()
        self._start_clean(deadline)
        try:
            # Modal answers a request still running after 150 s with a 303 to a URL that waits for the result; following
            # it is how that platform's documented contract is kept (cloud readiness review, 2026-10-12). A server on the
            # same machine never redirects.
            response = self._send("POST", f"{self.base_url}/api/chat", deadline, payload)
            refused = _overflow(response, limit)
            if refused is not None:
                raise refused
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as error:
            log.warning("model call failed: %s", error)
            raise ProviderError(failed_call("The model could not answer", error)) from error
        except ValueError as error:
            raise ProviderError("Ollama returned a non-JSON response") from error
        latency_ms = (time.perf_counter() - started) * 1000
        _heard()
        answered_by = self._answered_by(body)
        content = (body.get("message") or {}).get("content", "")
        if body.get("done_reason") == "length" and not _is_json(content):
            raise _answer_cut(body, limit)
        if not content:
            raise ProviderError("Ollama returned an empty message")
        if before is not None:
            # Asked again once the answer is in: a build swapped while it was computed answered under the checked one's
            # name (stress test, 2026-10-30, model transport 1). What is left of the call's time, and at least a probe's.
            after = self._check_build(_Deadline(max(deadline.left(), HEALTH_PROBE_TIMEOUT_S)))
            if after != before:
                swapped = f"{before[:12]} before, {(after or 'none')[:12]} after"
                raise ProviderError(f"the model endpoint's build changed while it answered ({swapped}); the answer was not kept")
        return Generation(
            text=content,
            input_tokens=body.get("prompt_eval_count"),
            output_tokens=body.get("eval_count"),
            latency_ms=latency_ms,
            model=answered_by,
        )
