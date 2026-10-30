"""The model boundary: one deadline per call, fields not words, nothing but its own clean start before an answer, and an
answer kept only from the model and build asked (stress test, 2026-10-30, model transport 1 to 4).

- A call had no overall deadline: httpx's timeout bounds each read, so a reply sent a byte at a time under it, an
  endless chunked body, or redirect hops each under it held the one admission slot for as long as they lasted (with a
  1 s timeout, 15 s, 31 s, 8.7 s).
- The provider read the server's words: a reply cut at the context window (done_reason "length") was taken for the
  model's invalid JSON and asked again with a longer prompt, and a refusal for size worded otherwise, or sent as a 500,
  was retried.
- The wake-up sent a templated prompt, which opens with the chat template's first token, the answer's own: landing
  between an answer's clean start and the answer, it moved the answer's start to token 1 (18 of 40 races on a cold host).
- A reply naming another model was kept, recorded as the run's model; a build swapped while it answered was kept under
  the checked one's name; and a run made under one pinned build was handed back after the pin moved.

The endpoint is scripted in process: replies are real httpx responses whose bodies arrive chunk by chunk, each chunk
moving a fake monotonic clock, so nothing sleeps and no socket is opened (one socket pair, for the cut).
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.analysis.schema import ANALYSIS_SCHEMA
from app.analysis.service import analyze, load_prompt
from app.application.start_run import run_options
from app.providers import ollama as ollama_module
from app.providers.admission import AdmissionController, AdmittedProvider
from app.providers.base import AnswerCut, ContextOverflow, ProviderError
from app.providers.ollama import OllamaProvider
from tests.support import CONTRACT

PINNED = "500a1f067a9f"
URL = "https://model.example.invalid"
GOOD = '{"insufficient_evidence": true, "findings": []}'


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Chunks(httpx.SyncByteStream):
    """A body that arrives a chunk at a time, `gap` seconds of the fake clock before each."""

    def __init__(self, chunks: Iterable[bytes], clock: Clock, gap: float, then: Callable[[], None] | None = None) -> None:
        self.chunks, self.clock, self.gap, self.then = chunks, clock, gap, then

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.chunks:
            self.clock.advance(self.gap)
            yield chunk
        if self.then is not None:
            self.then()


def _drip(data: bytes) -> Iterator[bytes]:
    yield from (data[i : i + 1] for i in range(len(data)))


def _forever() -> Iterator[bytes]:
    while True:
        yield b" "


Reply = Callable[[str, str, dict[str, Any] | None], httpx.Response]


class Endpoint:
    """httpx.stream scripted per path. `reply(method, path, body)` makes each response; requests are recorded."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.sent: list[tuple[str, str, dict[str, Any] | None, float]] = []
        self.digest = PINNED + "deadbeef"
        self.chat: dict[str, Any] = {"model": "qwen3:8b", "message": {"content": GOOD}, "done_reason": "stop", "prompt_eval_count": 900, "eval_count": 20}
        self.chat_status = 200
        self.chat_text: str | None = None
        self.slow: dict[str, tuple[Iterable[bytes] | None, float]] = {}  # path -> (chunks or None for the whole body, gap)
        self.redirects: list[str] = []
        self.on_chat: Callable[[], None] | None = None

    def _body(self, path: str) -> tuple[int, bytes]:
        if path == "/api/tags":
            return 200, json.dumps({"models": [{"name": "qwen3:8b", "digest": self.digest}]}).encode()
        if path == "/api/generate":
            return 200, b'{"response": ""}'
        if self.on_chat is not None:
            self.on_chat()
        if self.chat_text is not None:
            return self.chat_status, self.chat_text.encode()
        return self.chat_status, json.dumps(self.chat).encode()

    @contextmanager
    def stream(
        self, method: str, url: str, *, json: object = None, timeout: object = None, headers: object = None, follow_redirects: bool = False
    ) -> Iterator[httpx.Response]:
        path = httpx.URL(url).path
        self.sent.append((method, path, json, float(timeout.read)))
        request = httpx.Request(method, url)
        if self.redirects and path in ("/api/chat", "/result"):
            hop = self.redirects.pop(0)
            self.clock.advance(0.8)
            yield httpx.Response(307, headers={"location": hop}, request=request)
            return
        status, data = self._body("/api/chat" if path == "/result" else path)
        chunks, gap = self.slow.get(path, (None, 0.0))
        yield httpx.Response(status, stream=Chunks(_drip(data) if chunks is None else chunks, self.clock, gap), request=request)


class Timers:
    """ollama._arm, recorded: each timer's seconds and what it would do at its deadline."""

    def __init__(self) -> None:
        self.armed: list[tuple[float, Callable[[], None]]] = []

    def __call__(self, seconds: float, action: Callable[[], None]) -> Any:  # noqa: ANN401
        self.armed.append((seconds, action))
        timers = self

        class Armed:
            def start(self) -> None:
                pass

            def cancel(self) -> None:
                timers.cancelled = True

        return Armed()

    cancelled = False


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(ollama_module, "_monotonic", lambda: fake.now)
    return fake


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch, clock: Clock) -> Endpoint:
    server = Endpoint(clock)
    monkeypatch.setattr(httpx, "stream", server.stream)
    monkeypatch.setattr(config.settings, "ollama_url", URL)
    monkeypatch.setattr(config.settings, "model_digest", "")
    return server


@pytest.fixture
def timers(monkeypatch: pytest.MonkeyPatch) -> Timers:
    recorded = Timers()
    monkeypatch.setattr(ollama_module, "_arm", recorded)
    return recorded


def _provider(timeout_s: float = 1.0) -> OllamaProvider:
    return OllamaProvider(model="qwen3:8b", timeout_s=timeout_s)


def _ask(provider: Any) -> Any:  # noqa: ANN401
    return provider.generate_json("system", "user", ANALYSIS_SCHEMA)


# ---------------------------------------------------------------------------- one deadline per call


def test_a_reply_that_trickles_ends_at_the_call_s_deadline(endpoint: Endpoint, clock: Clock, timers: Timers) -> None:
    endpoint.slow["/api/chat"] = (_drip(b" " * 20 + json.dumps(endpoint.chat).encode()), 0.1)
    began = clock.now
    with pytest.raises(ProviderError, match="did not answer in time"):
        _ask(_provider(1.0))
    assert clock.now - began <= 1.1, "within the timeout and one chunk, not the 15 s the drip lasts"


@pytest.mark.parametrize("path", ["/api/generate", "/api/tags"])
def test_every_request_of_a_call_shares_its_deadline(endpoint: Endpoint, clock: Clock, timers: Timers, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    monkeypatch.setattr(config.settings, "model_digest", PINNED)  # so the build is asked before the answer
    endpoint.slow[path] = (_forever(), 0.1)
    began = clock.now
    with pytest.raises(ProviderError, match=r"did not answer in time|could not confirm its build"):
        _ask(_provider(1.0))
    assert clock.now - began <= 1.1
    assert any(sent[1] == path for sent in endpoint.sent)
    assert not any(sent[1] == "/api/chat" for sent in endpoint.sent), "no answer is asked for once the call's time is spent"


def test_redirect_hops_share_the_deadline(endpoint: Endpoint, clock: Clock, timers: Timers) -> None:
    endpoint.redirects = ["/result"] * 5  # each hop silent 0.8 s, under any one read's timeout
    with pytest.raises(ProviderError, match="did not answer in time"):
        _ask(_provider(1.0))
    assert [sent[1] for sent in endpoint.sent].count("/result") <= 1


def test_each_request_waits_at_most_what_is_left_of_the_call(endpoint: Endpoint, clock: Clock, timers: Timers) -> None:
    endpoint.slow["/api/generate"] = (None, 0.05)  # the clean start takes some of the time
    _ask(_provider(10.0))
    generate, chat = (sent for sent in endpoint.sent if sent[1] in ("/api/generate", "/api/chat"))
    assert generate[3] == pytest.approx(10.0) and chat[3] < generate[3]


def test_a_reply_without_end_is_cut_at_its_size(endpoint: Endpoint, clock: Clock, timers: Timers, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ollama_module, "MAX_REPLY_BYTES", 4096)
    endpoint.slow["/api/chat"] = ((b" " * 512 for _ in iter(int, 1)), 0.0)
    with pytest.raises(ProviderError, match="larger than any answer"):
        _ask(_provider(1.0))


def test_a_stall_late_in_a_reply_is_ended_by_the_deadline_s_timer(endpoint: Endpoint, clock: Clock, timers: Timers, monkeypatch: pytest.MonkeyPatch) -> None:
    """A read blocked on a silent connection waits for its own timeout; the call's timer, armed at what is left, cuts the
    connection so the call ends at its deadline. Here the stall is the timer firing and the read failing as it would."""

    def stall() -> None:
        seconds, cut = timers.armed[-1]
        clock.advance(seconds)
        cut()
        raise httpx.ReadError("connection shut")

    body = json.dumps(endpoint.chat).encode()
    endpoint.slow["/api/chat"] = ((body[:10],), 0.2)
    real_stream = endpoint.stream

    @contextmanager
    def stalling(*args: Any, **kwargs: Any) -> Iterator[httpx.Response]:  # noqa: ANN401
        with real_stream(*args, **kwargs) as response:
            if response.request.url.path == "/api/chat":
                response.stream = Chunks((body[:10],), clock, 0.2, then=stall)
            yield response

    monkeypatch.setattr(httpx, "stream", stalling)
    with pytest.raises(ProviderError, match="did not answer in time"):
        _ask(_provider(1.0))
    seconds, _ = timers.armed[-1]
    assert 0 < seconds <= 1.0 and timers.cancelled


def test_the_cut_wakes_a_read_blocked_on_the_reply_s_connection() -> None:
    """A read waiting with a timeout, as httpx's does, on a connection that sends nothing: the cut ends it at once, not
    at its timeout. Nothing sleeps: the read is ended whether the cut lands before it starts waiting or while it waits."""
    ours, theirs = socket.socketpair()
    ours.settimeout(30)
    ended: list[object] = []

    def read() -> None:
        try:
            ended.append(ours.recv(1))
        except OSError as error:
            ended.append(error)

    reader = threading.Thread(target=read)
    try:

        class Stream:
            def get_extra_info(self, name: str) -> object:
                return ours if name == "socket" else None

        response = httpx.Response(200, extensions={"network_stream": Stream()}, request=httpx.Request("POST", URL))
        reader.start()
        ollama_module._cut(response)
        reader.join(10)
        assert ended and not isinstance(ended[0], TimeoutError), "the blocked read returned at the cut"
    finally:
        ours.close()
        theirs.close()


def test_a_call_past_its_deadline_gives_the_admission_slot_back(endpoint: Endpoint, clock: Clock, timers: Timers) -> None:
    endpoint.slow["/api/chat"] = (_forever(), 0.1)
    controller = AdmissionController(limit=1)
    admitted = AdmittedProvider(_provider(1.0), controller, "interactive")
    with pytest.raises(ProviderError):
        _ask(admitted)
    assert controller.in_flight == 0


def test_controls_a_fast_reply_answers_and_a_silent_one_still_times_out(
    endpoint: Endpoint, clock: Clock, timers: Timers, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _ask(_provider(1.0)).text == GOOD

    def silent(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise httpx.ReadTimeout("timed out", request=httpx.Request("POST", URL))

    monkeypatch.setattr(httpx, "stream", silent)
    with pytest.raises(ProviderError, match="did not answer in time"):
        _ask(_provider(1.0))


# ---------------------------------------------------------------------------- nothing but its own clean start


def test_every_request_to_the_chat_model_that_is_not_an_answer_is_the_clean_start(endpoint: Endpoint, timers: Timers) -> None:
    provider = _provider(10.0)
    provider.wake()
    provider._start_clean()
    _ask(provider)
    bodies = [body for _method, path, body, _ in endpoint.sent if path == "/api/generate"]
    assert len(bodies) == 3 and all(body == provider._clean_start_payload() for body in bodies)
    assert all(body is not None and body["raw"] is True and body["prompt"] == "x" for body in bodies)


# ---------------------------------------------------------------------------- the server's fields, not its words


def _analysed(endpoint: Endpoint) -> tuple[Any, int]:
    outcome: Any
    try:
        outcome = analyze(_provider(10.0), load_prompt("answer-v2"), "QUESTION: anything", retry_delay_s=0)
    except ProviderError as error:
        outcome = error
    return outcome, sum(1 for sent in endpoint.sent if sent[1] == "/api/chat")


def test_an_answer_cut_at_the_context_window_is_reported_as_cut_and_not_asked_again(endpoint: Endpoint, timers: Timers) -> None:
    endpoint.chat.update(message={"content": GOOD[:30]}, done_reason="length", prompt_eval_count=16200, eval_count=184)
    outcome, calls = _analysed(endpoint)
    assert isinstance(outcome, AnswerCut) and calls == 1
    assert "16,384-token context window" in str(outcome) and "16,200" in str(outcome)


def test_an_answer_the_server_stopped_short_of_the_window_is_cut_too(endpoint: Endpoint, timers: Timers) -> None:
    endpoint.chat.update(message={"content": GOOD[:30]}, done_reason="length", prompt_eval_count=900, eval_count=128)
    outcome, calls = _analysed(endpoint)
    assert isinstance(outcome, AnswerCut) and "after 128 tokens" in str(outcome) and calls == 1


@pytest.mark.parametrize("finish", ["length", "stop"])
def test_control_a_complete_answer_is_kept_whatever_its_finish(endpoint: Endpoint, timers: Timers, finish: str) -> None:
    endpoint.chat.update(done_reason=finish)
    outcome, calls = _analysed(endpoint)
    assert not isinstance(outcome, ProviderError) and outcome.proposal is not None and calls == 1


TYPED = '{"error":"{\\"error\\":{\\"code\\":400,\\"message\\":\\"the prompt is too big\\",\\"type\\":\\"exceed_context_size_error\\",\\"n_prompt_tokens\\":20695,\\"n_ctx\\":16384}}"}'  # noqa: E501 - the server's reply, verbatim


@pytest.mark.parametrize(
    ("status", "text"),
    [
        (400, TYPED),  # llama-server's typed body, its words changed
        (400, '{"error":"the input length exceeds the context length"}'),  # the Go runner
        (500, '{"error":"the input length exceeds the context length"}'),  # the Go runner, as a 500
        (400, '{"error":"input length (20695 tokens) is longer than the context length (16384)"}'),
    ],
)
def test_a_refusal_for_size_is_a_context_overflow_whatever_its_wording(endpoint: Endpoint, timers: Timers, status: int, text: str) -> None:
    endpoint.chat_status, endpoint.chat_text = status, text
    outcome, calls = _analysed(endpoint)
    assert isinstance(outcome, ContextOverflow) and not isinstance(outcome, AnswerCut) and calls == 1
    if "20695" in text:
        assert "20,695 tokens" in str(outcome) and "16,384" in str(outcome)


def test_control_any_other_refusal_is_retried_as_an_ordinary_failure(endpoint: Endpoint, timers: Timers) -> None:
    endpoint.chat_status, endpoint.chat_text = 400, '{"error":"model not found"}'
    outcome, calls = _analysed(endpoint)
    assert isinstance(outcome, ProviderError) and not isinstance(outcome, ContextOverflow) and calls == 2


# ---------------------------------------------------------------------------- the model and the build asked for


@pytest.mark.parametrize(("named", "kept"), [("qwen3:14b", False), ("qwen3:8b", True), ("qwen3:8b:latest", True), (None, True)])
def test_an_answer_is_kept_only_from_the_model_asked(endpoint: Endpoint, timers: Timers, named: str | None, kept: bool) -> None:
    if named is None:
        endpoint.chat.pop("model")
    else:
        endpoint.chat["model"] = named
    if kept:
        assert _ask(_provider(10.0)).model in ("qwen3:8b", "qwen3:8b:latest")
    else:
        with pytest.raises(ProviderError, match="answered as qwen3:14b, not the qwen3:8b asked for"):
            _ask(_provider(10.0))


def test_a_build_swapped_while_it_answered_is_not_kept(endpoint: Endpoint, timers: Timers, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "model_digest", PINNED)

    def swap() -> None:
        endpoint.digest = "0123456789ab" + "0" * 52

    endpoint.on_chat = swap
    with pytest.raises(ProviderError, match=r"not the pinned build|build changed while it answered"):
        _ask(_provider(10.0))
    assert [sent[1] for sent in endpoint.sent] == ["/api/tags", "/api/generate", "/api/chat", "/api/tags"]


def test_control_an_unchanged_pinned_build_answers(endpoint: Endpoint, timers: Timers, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "model_digest", PINNED)
    assert _ask(_provider(10.0)).text == GOOD


def test_a_pinned_build_is_part_of_a_run_s_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "model_digest", "")
    assert "model_digest" not in run_options(), "unpinned, as on the laptop: identities stay as they were"
    monkeypatch.setattr(config.settings, "model_digest", "aaaaaaaaaaaa")
    first = run_options()
    monkeypatch.setattr(config.settings, "model_digest", "bbbbbbbbbbbb")
    assert first["model_digest"] == "aaaaaaaaaaaa" and run_options()["model_digest"] == "bbbbbbbbbbbb"


def test_after_the_pin_moves_the_same_question_is_asked_afresh(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The finder's case (a): pinned to build A, asked; re-pinned to build B, asked again: not handed A's run."""
    uploaded = client.post("/api/documents", files={"file": ("c.txt", CONTRACT.encode(), "text/plain")}).json()
    ask = {"documentId": uploaded["id"], "guidanceId": None, "question": "What notice period applies to termination for convenience?"}
    monkeypatch.setattr(config.settings, "model_digest", "aaaaaaaaaaaa")
    first = client.post("/api/runs", json=ask)
    assert first.status_code == 202
    assert client.post("/api/runs", json=ask).status_code == 200, "control: the same build is handed its run"
    monkeypatch.setattr(config.settings, "model_digest", "bbbbbbbbbbbb")
    again = client.post("/api/runs", json=ask)
    assert again.status_code == 202 and again.json()["id"] != first.json()["id"]
