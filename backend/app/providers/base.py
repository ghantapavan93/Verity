"""The one interface the analysis service talks to. Providers return text; parsing and
validation happen in the caller, so a provider can never smuggle structure past the checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """The provider could not be reached or returned no usable output. Its message is shown to the reader, so it is
    said in plain words: never an exception's own text (journey audit, 2026-10-09: "[WinError 10061] …"), which can
    carry the endpoint's address, paths and OS detail. That goes to the log."""


def failed_call(what: str, error: httpx.HTTPError) -> str:
    """A failed call to the model endpoint in words a reader can act on. ``what`` names the call ("the model",
    "embedding with nomic-embed-text"). The error's class is written to the log beside the sentence, never into it: the
    sentence reaches visitors (blind contract stress test, 2026-10-16: "… not reachable (ConnectError)")."""
    if isinstance(error, httpx.ConnectError):
        sentence = f"{what}: the model endpoint is not reachable"
    elif isinstance(error, httpx.TimeoutException):
        sentence = f"{what}: the model endpoint did not answer in time"
    elif isinstance(error, httpx.HTTPStatusError):
        sentence = f"{what}: the model endpoint answered HTTP {error.response.status_code}"
    else:
        sentence = f"{what}: the request to the model endpoint failed"
    log.warning("%s (%s)", sentence, type(error).__name__)
    return sentence


class ContextOverflow(ProviderError):
    """The request is larger than the model's context window. Trying again cannot help, and answering from a prompt
    the server has cut would be an answer about text the model did not read."""


class AnswerCut(ContextOverflow):
    """The server stopped the answer before it was complete (Ollama's done_reason "length"): the prompt and the answer
    filled the context window, or the server capped the answer. Not the model's invalid output, and not asked again: the
    same prompt is cut the same way, and a corrected round's longer prompt sooner (stress test, 2026-10-30)."""


@dataclass
class Generation:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    model: str


class ModelProvider(Protocol):
    name: str
    model: str

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation: ...

    def healthy(self) -> tuple[bool, str]: ...
