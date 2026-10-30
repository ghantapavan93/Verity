from __future__ import annotations

import asyncio
import os
import shutil
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Request

from .. import db
from ..config import settings
from ..providers.base import ModelProvider
from ..schemas import HealthOut
from . import access

router = APIRouter(prefix="/api", tags=["health"])

# Below this much free space an upload (up to 25 MB), its reading and a run's record may not fit.
MIN_FREE_BYTES = 256 * 1024 * 1024


def storage_problem() -> str | None:
    """Why the store cannot take a write, or None. Read from the file system's permissions and free space, and from
    what the engine met (db.store_fault: a damaged file, an I/O or full disk, a store the engine could not write), never
    by taking a write lock: the first screen asks for health, and a check that waited on a long write would hold it up.
    No sizes or error names are given; the endpoint is public."""
    if db.store_fault() is not None:
        return "the store failed a read or a write: uploads, runs and records may not be recorded or read"
    data_dir = settings.data_dir
    if not data_dir.is_dir():
        return "the data directory is missing: uploads and runs cannot be recorded"
    for path in (data_dir, data_dir / "workbench.db", data_dir / "documents", data_dir / "memos"):
        if path.exists() and not os.access(path, os.W_OK):
            return "storage is read-only: uploads and runs cannot be recorded"
    # One threshold with the refusal: a public store pauses writes below its own floor (access.refuse_if_disk_low), and
    # health said ok between 256 MiB and that floor while every upload was refused (ops audit, 2026-10-19).
    floor = settings.public_min_free_bytes if settings.anonymous_sessions else MIN_FREE_BYTES
    if shutil.disk_usage(data_dir).free < floor:
        return "storage is nearly full: uploads and runs may not be recorded"
    return None


# The model's answer to health, kept this long: every visitor's page asks for health, and each ask was a request for the
# model server's whole list of models (security audit, 2026-10-30). A model that goes away is seen within the interval.
HEALTH_PROBE_TTL_S = 10.0
# Weakly keyed: a provider that is gone takes its answer with it, and a new one at the same address is asked afresh.
_probes: weakref.WeakKeyDictionary[ModelProvider, tuple[float, tuple[bool, str]]] = weakref.WeakKeyDictionary()
_probes_lock = threading.Lock()


def probe_model(provider: ModelProvider) -> tuple[bool, str]:
    """The provider's health, asked at most once per HEALTH_PROBE_TTL_S for each provider. One probe at a time: requests
    that arrive while it is asked wait for its answer, rather than each asking the model server again."""
    with _probes_lock:
        now = time.monotonic()
        kept = _probes.get(provider)
        if kept is not None and now - kept[0] < HEALTH_PROBE_TTL_S:
            return kept[1]
        answer = provider.healthy()
        _probes[provider] = (now, answer)
        return answer


# The model's probe is a network call, so it leaves the event loop, but on a thread of its own: on the request threads
# every sync route shares it waited behind them as health did (stress test, 2026-10-30). One thread, since probe_model
# asks one at a time anyway; a request that finds a fresh answer never reaches it.
_PROBE_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="health-probe")


async def _probe_off_the_loop(provider: ModelProvider) -> tuple[bool, str]:
    with _probes_lock:
        kept = _probes.get(provider)
        if kept is not None and time.monotonic() - kept[0] < HEALTH_PROBE_TTL_S:
            return kept[1]
    return await asyncio.get_running_loop().run_in_executor(_PROBE_THREAD, probe_model, provider)


LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def model_location() -> tuple[Literal["server", "hosted"], str]:
    """("server", "") when the model is on this machine: its URL is this machine's loopback, or the deployment says the
    endpoint is another container here (WORKBENCH_MODEL_ON_SERVER); ("hosted", label) for anywhere else."""
    host = (urlsplit(settings.ollama_url).hostname or "").lower()
    return ("server", "") if host in LOOPBACK or settings.model_on_server else ("hosted", settings.model_host)


@router.get("/health", response_model=HealthOut)
async def health(request: Request) -> HealthOut:
    """Open to everyone, because the supervisor and the page ask before anyone has entered. Past the gate it names
    the model and its state; before it, only whether the workbench is up and that the gate is on. A store that cannot
    take a write is not healthy, whatever the model's state. A visitor who has not entered never makes it ask the
    model, and a deployment whose model bills by the second can leave the model to the answer itself.

    It answers on the event loop and takes none of the request threads, not even for a dependency: declared `def`, it
    waited behind them, and one visitor's 120 concurrent reads of its own run held it for 21 s, past the supervisor's
    10 s, so the probe that restarts the API measured the queue, not the process (stress test, 2026-10-30). What it
    does here is a check of the file system and a token's MAC; the model's probe has its own thread."""
    provider: ModelProvider = request.app.state.provider
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
            fault="store" if problem is not None else "",
        )
    if settings.health_probes_model:
        ok, detail = await _probe_off_the_loop(provider)
    else:
        ok, detail = True, f"{provider.model}: checked before every answer, not by health"
    fault: Literal["", "store", "model"] = "" if ok else "model"
    if problem is not None:
        ok, detail, fault = False, problem, "store"
    return HealthOut(
        ok=ok,
        provider=provider.name,
        model=provider.model,
        detail=detail,
        access="entered" if access.enabled() else "off",
        model_location=location,
        model_host=host,
        fault=fault,
    )
