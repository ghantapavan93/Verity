from __future__ import annotations

from ..config import settings
from .base import Generation, ModelProvider, ProviderError
from .ollama import OllamaProvider
from .replay import RecordingProvider, ReplayProvider

__all__ = ["Generation", "ModelProvider", "OllamaProvider", "ProviderError", "RecordingProvider", "ReplayProvider", "make_provider"]


def make_provider(name: str | None = None, model: str | None = None) -> ModelProvider:
    chosen = (name or settings.provider).lower()
    if chosen == "ollama":
        return OllamaProvider(model=model)
    if chosen == "replay":
        return ReplayProvider(settings.replay_file, model=model)
    if chosen == "record":
        return RecordingProvider(OllamaProvider(model=model), settings.replay_file)
    raise ProviderError(f"unknown provider {chosen!r}; 'ollama' answers live, 'record' and 'replay' serve the browser tests")
