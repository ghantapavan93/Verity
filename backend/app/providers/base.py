"""The one interface the analysis service talks to. Providers return text; parsing and
validation happen in the caller, so a provider can never smuggle structure past the checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class ProviderError(RuntimeError):
    """The provider could not be reached or returned no usable output. Its message is shown to the reader, so it is
    said in plain words: never an exception's own text (journey audit, 2026-10-09: "[WinError 10061] …"), which can
    carry the endpoint's address, paths and OS detail. That goes to the log."""


def failed_call(what: str, error: httpx.HTTPError) -> str:
    """A failed call to the model endpoint in words a reader can act on, with the error's class for whoever reads the
    log beside it. ``what`` names the call ("the model", "embedding with nomic-embed-text")."""
    kind = type(error).__name__
    if isinstance(error, httpx.ConnectError):
        return f"{what}: the model endpoint is not reachable ({kind})"
    if isinstance(error, httpx.TimeoutException):
        return f"{what}: the model endpoint did not answer in time ({kind})"
    if isinstance(error, httpx.HTTPStatusError):
        return f"{what}: the model endpoint answered HTTP {error.response.status_code} ({kind})"
    return f"{what}: the request to the model endpoint failed ({kind})"


class ContextOverflow(ProviderError):
    """The request is larger than the model's context window. Trying again cannot help, and answering from a prompt
    the server has cut would be an answer about text the model did not read."""


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
