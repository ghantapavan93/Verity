"""The one interface the analysis service talks to. Providers return text; parsing and
validation happen in the caller, so a provider can never smuggle structure past the checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """The provider could not be reached or returned no usable output."""


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
