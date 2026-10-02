from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..providers.base import ModelProvider
from ..schemas import HealthOut
from . import access
from .deps import get_provider

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(request: Request, provider: ModelProvider = Depends(get_provider)) -> HealthOut:
    """Open to everyone, because the supervisor and the page ask before anyone has entered. Past the gate it names
    the model and its state; before it, only whether the workbench is up and that the gate is on."""
    ok, detail = provider.healthy()
    if access.enabled() and access.current_session(request) is None:
        return HealthOut(ok=ok, provider="", model="", detail="private preview: an invite is needed", access="required")
    return HealthOut(ok=ok, provider=provider.name, model=provider.model, detail=detail, access="entered" if access.enabled() else "off")
