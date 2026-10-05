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

from .api import access, batches, documents, engineering, findings, guidance, health, memos, runs, trust
from .application.recover_runs import recover_interrupted_runs
from .config import settings
from .db import SessionLocal, init_db
from .errors import WorkbenchError
from .providers import make_provider
from .providers.base import ModelProvider
from .runs.events import bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def create_app(provider: ModelProvider | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db()
        with SessionLocal() as session:
            recovered = recover_interrupted_runs(session)
        if recovered:
            log.warning("recovered_runs=%d marked failed after restart", recovered)
        bus.bind_loop(asyncio.get_running_loop())
        app.state.provider = provider or make_provider()
        yield

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
        started = time.perf_counter()
        response = await call_next(request)
        # For a streamed response this is the time to first byte, not the life of the stream.
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        if request.url.path != "/api/health":
            log.info(
                "request_id=%s method=%s path=%s status=%d duration_ms=%.0f", request_id, request.method, request.url.path, response.status_code, duration_ms
            )
        return response

    # Health and the gate itself are open; everything else is mounted behind the gate here, in one place, so a route
    # added to any of these routers is behind it without anyone remembering (a test walks every route to be sure).
    app.include_router(health.router)
    app.include_router(access.router)
    gate = [Depends(access.require_access)]
    for router in (documents.router, guidance.router, findings.router, memos.router, batches.router, engineering.router, trust.router):
        app.include_router(router, dependencies=gate)
    app.include_router(runs.router, dependencies=[*gate, Depends(access.limit_run_starts)])
    return app


app = create_app()
