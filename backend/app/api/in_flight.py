"""What one network, or one workspace, may have in flight at once in the public store (stress test, 2026-10-30).

Every route declared `def` runs on one pool of forty request threads. The hourly windows (api/access.py) bound a rate,
not how many requests are held at once, and most reads have none: one visitor, one network, sent 120 GETs of its own
run at once, all answered, the slowest after 47 s, and the pool was theirs for a minute. Health no longer waits for
that pool (api/health.py), but every other visitor's request still did. The class had been fixed a route at a time:
uploads (two per network, api/body_limit.py), then packs, then contract reads. This is the bound at the door, for every
request in the public store:

- a network (access.client_network: an IPv4 address, an IPv6 /64) has at most settings.public_requests_per_network
  requests in flight. One past it waits up to IN_FLIGHT_WAIT_S for one of them to end, as a page's burst of reads at
  load does, then is answered 503 with Retry-After, before any route, gate or thread is spent on it;
- the event stream of a run (GET /api/runs/{id}/events) lives as long as its run, so it is counted apart, by the
  workspace its session opens (settings.public_streams_per_workspace) and by network
  (settings.public_streams_per_network). One past either is answered 429 at once; the interface then follows the run
  by polling its record (src/lib/api.ts followRun), which the bound above covers;
- health is never counted: liveness must not be throttled.

Counted on the event loop only, so the dictionaries need no lock; an entry is removed when its last request ends. The
owner's store is not bounded here, as it is not by the hourly windows.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from anyio import Semaphore, fail_after
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from ..config import settings
from . import access

log = logging.getLogger(__name__)

# The longest a request waits at the door for its network's turn: a page asks for a handful of things at once when it
# loads, and they should queue briefly, not fail. Past it the request is refused unread.
IN_FLIGHT_WAIT_S = 2.0
NETWORK_BUSY = "Your network has many requests in progress right now; nothing was done. Try again in a moment."
STREAMS_BUSY = "This workspace is already following its questions live; this one is followed by asking again."
_STREAM = re.compile(r"/api/runs/[^/]+/events")
_UNCOUNTED = frozenset({"/api/health"})


@dataclass
class _Slots:
    semaphore: Semaphore
    users: int = 0  # holding or waiting


_requests_from: dict[str, _Slots] = {}
_streams_of: dict[str, int] = {}  # keyed "workspace:<id>" and "network:<id>"


def in_flight() -> dict[str, int]:
    """Requests held now per network; for tests and status lines."""
    return {network: slots.users for network, slots in _requests_from.items()}


def streams_open() -> dict[str, int]:
    return dict(_streams_of)


def _workspace_of(request: Request) -> str | None:
    """The workspace the request's session opens, from the cookie's MAC alone: no store read at the door. An ended
    workspace's session is refused by the gate inside, as it is everywhere."""
    session = access.current_session(request)
    return access.workspace_for(session.subject) if session is not None else None


class InFlightMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not settings.anonymous_sessions or not path.startswith("/api/") or path in _UNCOUNTED:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        network = access.client_network(request)
        if _STREAM.fullmatch(path):
            await self._stream(scope, receive, send, request, network, path)
            return
        slots = _requests_from.setdefault(network, _Slots(Semaphore(max(1, settings.public_requests_per_network))))
        slots.users += 1
        try:
            try:
                with fail_after(IN_FLIGHT_WAIT_S):
                    await slots.semaphore.acquire()
            except TimeoutError:
                await _answer(send, 503, NETWORK_BUSY, retry_after=2, kind="RequestsPerNetwork", path=path)
                return
            try:
                await self.app(scope, receive, send)
            finally:
                slots.semaphore.release()
        finally:
            slots.users -= 1
            if slots.users == 0 and _requests_from.get(network) is slots:
                del _requests_from[network]

    async def _stream(self, scope: Scope, receive: Receive, send: Send, request: Request, network: str, path: str) -> None:
        workspace = _workspace_of(request)
        keys = [(f"network:{network}", settings.public_streams_per_network)]
        if workspace is not None:
            keys.append((f"workspace:{workspace}", settings.public_streams_per_workspace))
        if any(_streams_of.get(key, 0) >= limit for key, limit in keys):
            await _answer(send, 429, STREAMS_BUSY, retry_after=30, kind="StreamsOpen", path=path)
            return
        for key, _limit in keys:
            _streams_of[key] = _streams_of.get(key, 0) + 1
        try:
            await self.app(scope, receive, send)
        finally:
            for key, _limit in keys:
                if _streams_of[key] <= 1:
                    del _streams_of[key]
                else:
                    _streams_of[key] -= 1


async def _answer(send: Send, status: int, detail: str, retry_after: int, *, kind: str, path: str) -> None:
    # The same line as every other refusal (main.workbench_error, body_limit._answer), so one grep counts it by name.
    log.warning("refused path=%s status=%d kind=%s detail=%s", path, status, kind, detail, extra={"shape": f"refused {status} {kind}"})
    body = json.dumps({"detail": detail}, separators=(",", ":")).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"retry-after", str(retry_after).encode()),
        (b"cache-control", b"no-store"),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
