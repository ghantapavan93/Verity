"""Ollama provider: local models, structured output through the `format` JSON schema."""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..config import settings
from .base import Generation, ProviderError


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str | None = None, base_url: str | None = None, timeout_s: float | None = None) -> None:
        self.model = model or settings.model
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.timeout_s = timeout_s or settings.model_timeout_s

    def options(self) -> dict[str, Any]:
        return {"temperature": settings.temperature, "seed": settings.seed, "num_ctx": settings.num_ctx}

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
            "options": self.options(),
        }
        started = time.perf_counter()
        try:
            response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout_s)
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
