"""Ollama provider: local models, structured output through the `format` JSON schema."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from typing import Any

import httpx

from ..config import settings
from .base import ContextOverflow, Generation, ProviderError


def _overflow_message(body: str, limit: int) -> str:
    """What the server said, as a sentence a person can act on. The token count is the server's own."""
    found = re.search(r"request \((\d+) tokens\)", body)
    size = f"{int(found.group(1)):,} tokens" if found else "more tokens than the model can hold"
    return (
        f"The question, the guidance and the sections handed to the model come to {size}; its context window holds {limit:,}. "
        "The request was refused rather than answered from a cut prompt. Shorten the guidance or the question and ask again."
    )


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

    def healthy(self) -> tuple[bool, str]:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            names = [m.get("name", "") for m in response.json().get("models", [])]
        except (httpx.HTTPError, ValueError) as error:
            return False, f"Ollama not reachable at {self.base_url}: {error}"
        if self.model not in names and f"{self.model}:latest" not in names:
            return False, f"model {self.model} is not pulled (have: {', '.join(names) or 'none'})"
        return True, f"{self.model} ready"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "think": False,
            # A prompt larger than the context window is refused, never cut. Left to its default the server drops
            # text to make room and answers anyway: asked for a notice period stated at the start of a prompt of
            # 20,695 tokens, it evaluated 8,194 of them and answered "30 days" where the text said 47, with nothing
            # in the response to say so (measured against Ollama 0.35.0, 2026-10-02). `shift` is the same rule for
            # the answer: it may not push the prompt out of the window while it is being written.
            "truncate": False,
            "shift": False,
            "options": self.options(),
        }
        started = time.perf_counter()
        try:
            response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout_s)
            if response.status_code == 400 and "exceed" in response.text and "context" in response.text:
                raise ContextOverflow(_overflow_message(response.text, int(self.options()["num_ctx"])))
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as error:
            raise ProviderError(f"Ollama request failed: {error}") from error
        except ValueError as error:
            raise ProviderError("Ollama returned a non-JSON response") from error
        latency_ms = (time.perf_counter() - started) * 1000
        content = (body.get("message") or {}).get("content", "")
        if not content:
            raise ProviderError("Ollama returned an empty message")
        return Generation(
            text=content,
            input_tokens=body.get("prompt_eval_count"),
            output_tokens=body.get("eval_count"),
            latency_ms=latency_ms,
            model=body.get("model", self.model),
        )
