"""FastAPI application. Run with: uvicorn app.main:app --port 8000"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import db as db_module
from .api import access, batches, documents, engineering, findings, guidance, health, memos, model, runs, trust
from .application.ingest_document import MAX_UPLOAD_BYTES
from .application.recover_runs import recover_interrupted_runs
from .application.retention import purge_expired_workspaces, sweep_orphaned_files
from .config import settings
from .db import SessionLocal, init_db
from .errors import WorkbenchError
from .providers import make_provider
from .providers.base import ModelProvider
from .runs.events import bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def refuse_a_store_with_owner_records() -> None:
    """Anonymous visitors are served from a store of their own. A store holding anything that is not a visitor's (a
    curated document or run, an invited reader's) is the owner's: refusing to start keeps a misplaced
    WORKBENCH_DATA_DIR from putting the owner's record in front of the public."""
    with db_module.engine.connect() as connection:
        owned = connection.execute(
            text(
                "SELECT (SELECT COUNT(*) FROM runs WHERE workspace_id IS NULL OR workspace_id NOT LIKE 'pw-%') "
                "+ (SELECT COUNT(*) FROM documents d WHERE NOT EXISTS (SELECT 1 FROM document_access a WHERE a.document_id = d.id)) "
                "+ (SELECT COUNT(*) FROM document_access WHERE workspace_id NOT LIKE 'pw-%')"
            )
        ).scalar()
    if owned:
        raise RuntimeError(
            f"WORKBENCH_ANONYMOUS_SESSIONS is on but this store holds {owned} owner or curated records; "
            "point WORKBENCH_DATA_DIR at the public store. Refusing to start."
        )


async def _retain_hourly() -> None:
    while True:
        try:
            await asyncio.to_thread(purge_expired_workspaces, db_module.engine)
            await asyncio.to_thread(sweep_orphaned_files, db_module.engine)
        except Exception:  # a failed pass is logged and tried again next hour; it never takes the API down
            log.exception("retention pass failed")
        await asyncio.sleep(3600)


# The 25 MB file and room for its form, as Caddy's request_body max_size (deploy/cloud/Caddyfile, 26 MiB).
UPLOAD_REQUEST_LIMIT = MAX_UPLOAD_BYTES + 1024 * 1024

# The same set as deploy/cloud/Caddyfile and next.config.ts, so the policy does not depend on the edge.
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "frame-ancestors 'none'",
}


def create_app(provider: ModelProvider | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db()
        if settings.anonymous_sessions:
            refuse_a_store_with_owner_records()
        with SessionLocal() as session:
            recovered = recover_interrupted_runs(session)
        if recovered:
            log.warning("recovered_runs=%d marked failed after restart", recovered)
        bus.bind_loop(asyncio.get_running_loop())
        app.state.provider = provider or make_provider()
        # The public demo store deletes ended visitor workspaces: once now, then hourly (application/retention.py).
        retention = asyncio.create_task(_retain_hourly()) if settings.anonymous_sessions else None
        yield
        if retention is not None:
            retention.cancel()

    access.check_configuration()
    app = FastAPI(title="Contract Workbench", version="0.1.0", lifespan=lifespan)
    # Responses over 1 KB go out compressed; Starlette leaves text/event-stream alone, so the live
    # run stream is unaffected. Lighthouse found the document JSON going out raw.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        # The session cookie travels with requests from the interface's own origins, which are listed, never "*".
        # Through the tunnel the interface and the API are one origin and this is not used; on a laptop they are two ports.
        allow_credentials=True,
    )

    @app.exception_handler(WorkbenchError)
    async def workbench_error(_request: Request, error: WorkbenchError) -> JSONResponse:
        retry_after = getattr(error, "retry_after", None)
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
        return JSONResponse({"detail": str(error)}, status_code=error.status_code, headers=headers)

    @app.middleware("http")
    async def request_log(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        # FastAPI reads a whole form, to disk, before any dependency runs: a 40 MB body with no session was stored and
        # only then refused (security review, 2026-10-13). Behind a tunnel nothing caps the body short of Cloudflare's
        # 100 MB, so an upload that declares more than the 25 MB file and its form is refused here, unread. The size of a
        # body sent without a declared length is still checked once read (ingest_document.refuse_if_too_large).
        declared = request.headers.get("content-length", "")
        if request.method == "POST" and request.url.path == "/api/documents" and declared.isdigit() and int(declared) > UPLOAD_REQUEST_LIMIT:
            return JSONResponse({"detail": "file larger than 25 MB"}, status_code=413, headers={"Cache-Control": "no-store", **SECURITY_HEADERS})
        started = time.perf_counter()
        response = await call_next(request)
        # For a streamed response this is the time to first byte, not the life of the stream.
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        # Every answer the API gives is one reader's (a contract, its findings, a memo) or about the live system: no
        # cache on the way may keep it. A route that sets its own policy keeps it.
        if request.url.path.startswith("/api") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        # The browser's protections, on every response whatever edge is in front: Caddy set them (deploy/cloud/Caddyfile),
        # but a Cloudflare Tunnel, the workstation's edge, sets none (observed on the live site, 2026-10-13). A route with
        # a policy of its own keeps it (the memo's).
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path != "/api/health":
            log.info(
                "request_id=%s method=%s path=%s status=%d duration_ms=%.0f", request_id, request.method, request.url.path, response.status_code, duration_ms
            )
        return response

    # Health, the gate itself and the published research record are open; everything else is mounted behind the gate here, in one place, so a route
    # added to any of these routers is behind it without anyone remembering (a test walks every route to be sure).
    app.include_router(health.router)
    app.include_router(access.router)
    app.include_router(engineering.public_router)
    gate = [Depends(access.require_access)]
    writes = [*gate, Depends(access.limit_public_writes)]
    # model: waking the model spends, so it needs a session and the workbench's own origin, but it changes nothing a
    # reader owns and does not count against their writes (api/model.py).
    for router in (documents.router, engineering.router, model.router):
        app.include_router(router, dependencies=gate)
    for router in (guidance.router, findings.router, memos.router, trust.router):
        app.include_router(router, dependencies=writes)
    # Corpus jobs read the store by content across workspaces: the owner's tool, not a visitor's (api/access.owner_only).
    app.include_router(batches.router, dependencies=[*gate, Depends(access.owner_only)])
    app.include_router(runs.router, dependencies=[*gate, Depends(access.limit_run_starts)])
    return app


app = create_app()
