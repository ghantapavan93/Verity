from __future__ import annotations

from ..config import settings
from .admission import AdmissionController, AdmittedProvider, Workload
from .base import Generation, ModelProvider, ProviderError
from .ollama import OllamaProvider
from .replay import RecordingProvider, ReplayProvider

__all__ = ["Generation", "ModelProvider", "OllamaProvider", "ProviderError", "RecordingProvider", "ReplayProvider", "admission", "make_provider"]

# One controller per process: every provider this process hands out shares it, so the API's interactive calls and a
# batch runner in the same process queue on the same bound.
admission = AdmissionController(limit=max(1, settings.model_concurrency))


def _raw_provider(name: str | None, model: str | None) -> ModelProvider:
    chosen = (name or settings.provider).lower()
    if chosen == "ollama":
        return OllamaProvider(model=model)
    if chosen == "replay":
        return ReplayProvider(settings.replay_file, model=model)
    if chosen == "record":
        return RecordingProvider(OllamaProvider(model=model), settings.replay_file)
    raise ProviderError(f"unknown provider {chosen!r}; 'ollama' answers live, 'record' and 'replay' serve the browser tests")


def make_provider(name: str | None = None, model: str | None = None, workload: Workload = "interactive") -> ModelProvider:
    """A provider for this process, admitted through the shared controller under the given workload class."""
    return AdmittedProvider(_raw_provider(name, model), admission, workload)
