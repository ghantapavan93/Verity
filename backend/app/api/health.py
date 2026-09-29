from __future__ import annotations

from fastapi import APIRouter, Depends

from ..providers.base import ModelProvider
from ..schemas import HealthOut
from .deps import get_provider

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(provider: ModelProvider = Depends(get_provider)) -> HealthOut:
    ok, detail = provider.healthy()
    return HealthOut(ok=ok, provider=provider.name, model=provider.model, detail=detail)
