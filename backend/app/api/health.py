from __future__ import annotations

import os
import shutil
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request

from ..config import settings
from ..providers.base import ModelProvider
from ..schemas import HealthOut
from . import access
from .deps import get_provider

router = APIRouter(prefix="/api", tags=["health"])

# Below this much free space an upload (up to 25 MB), its reading and a run's record may not fit.
MIN_FREE_BYTES = 256 * 1024 * 1024


def storage_problem() -> str | None:
    """Why the store cannot take a write, or None. Read from the file system's permissions and free space, never by
    taking a write lock: the first screen asks for health, and a check that waited on a long write would hold it up.
    No sizes are named; the endpoint is public."""
    data_dir = settings.data_dir
    if not data_dir.is_dir():
        return "the data directory is missing: uploads and runs cannot be recorded"
    for path in (data_dir, data_dir / "workbench.db", data_dir / "documents", data_dir / "memos"):
        if path.exists() and not os.access(path, os.W_OK):
            return "storage is read-only: uploads and runs cannot be recorded"
    if shutil.disk_usage(data_dir).free < MIN_FREE_BYTES:
        return "storage is nearly full: uploads and runs may not be recorded"
    return None


LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def model_location() -> tuple[Literal["server", "hosted"], str]:
    """("server", "") when the model URL is this machine's loopback; ("hosted", label) for anywhere else."""
    host = (urlsplit(settings.ollama_url).hostname or "").lower()
    return ("server", "") if host in LOOPBACK else ("hosted", settings.model_host)


@router.get("/health", response_model=HealthOut)
def health(request: Request, provider: ModelProvider = Depends(get_provider)) -> HealthOut:
    """Open to everyone, because the supervisor and the page ask before anyone has entered. Past the gate it names
    the model and its state; before it, only whether the workbench is up and that the gate is on. A store that cannot
    take a write is not healthy, whatever the model's state. A visitor who has not entered never makes it ask the
    model, and a deployment whose model bills by the second can leave the model to the answer itself."""
    location, host = model_location()
    problem = storage_problem()
    if access.enabled() and access.current_session(request) is None:
        return HealthOut(
            ok=problem is None,
            provider="",
            model="",
            detail=problem or "private preview: an invite is needed",
            access="required",
            model_location=location,
            model_host=host,
        )
    if settings.health_probes_model:
        ok, detail = provider.healthy()
    else:
        ok, detail = True, f"{provider.model}: checked before every answer, not by health"
    if problem is not None:
        ok, detail = False, problem
    return HealthOut(
        ok=ok,
        provider=provider.name,
        model=provider.model,
        detail=detail,
        access="entered" if access.enabled() else "off",
        model_location=location,
        model_host=host,
    )
