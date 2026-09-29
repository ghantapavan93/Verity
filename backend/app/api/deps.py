from __future__ import annotations

from fastapi import Request

from ..providers.base import ModelProvider


def get_provider(request: Request) -> ModelProvider:
    provider: ModelProvider = request.app.state.provider
    return provider
