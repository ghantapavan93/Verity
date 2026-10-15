"""No request body is read past what its route can legitimately need, nor by a request its route would refuse.

FastAPI reads and parses a whole body before any dependency runs, the access gate included, so a body is paid for by
the server before anyone is asked who sent it: a 40 MB JSON body to /api/runs, with no session, took the API to a
2 GB peak and held the event loop for 19 s, and Cloudflare passes up to 100 MB (gstack /review trial, 2026-10-13). The
first fix of this class (security review of the same day) refused only uploads, and only by their declared length.

Here every request is bounded, on the bytes actually received as well as on the length declared, so a chunked body
with no Content-Length is cut off at the same point: an upload at the 25 MB file and room for its form, everything else
at JSON_REQUEST_LIMIT. A refused body gets 413 before its route, its gate or its parser sees more of it.

An upload is also asked at the door what its route would ask first on its headers alone: the access gate (session,
origin), the owner's pause and a public store's disk, before a byte of its form is read, since a form is spooled whole
before any dependency runs (3 MiB from a client with no session was parsed and only then refused, war room F-15).

What uploads in flight are bounded by is what they cost, not a count of places anyone can take. Each network
(access.client_network: an IPv4 address, an IPv6 /64) has at most UPLOADS_PER_NETWORK in flight; all of them together
hold at most SPOOL_BUDGET bytes of received body, what the /tmp spool can hold, so an upload that has sent nothing holds
nothing. A body must keep arriving: no wait for it longer than BODY_IDLE_SECONDS, and after its first
BODY_GRACE_SECONDS of waiting an average of at least BODY_MIN_RATE, or it is ended with 408. Only time spent waiting
for the client counts, so a server busy elsewhere cannot make a client slow. A received upload then waits a bounded
time for its reading (api/documents.py) and is read within a bounded time (ingest/bounded.py).

Each earlier door was held shut for nothing: a global cap of six by six unfinished uploads (Codex review); then, with
two per network and sixteen overall, by a byte every two seconds (war room W5), and by eight IPv6 /64s of one host
sending headers alone and reconnecting as each place was ended (counter-review round 3, 2026-10-13: a visitor on a
ninth network got in 0 of 18 times). Taking the spool now takes sending it: hundreds of megabytes, kept arriving.
"""

from __future__ import annotations

import json

from anyio import current_time, fail_after, to_thread
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..application.ingest_document import MAX_UPLOAD_BYTES
from ..errors import WorkbenchError
from . import access

UPLOAD_PATH = "/api/documents"
# The 25 MB file and room for its form, as Caddy's request_body max_size (deploy/cloud/Caddyfile, 26 MiB).
UPLOAD_REQUEST_LIMIT = MAX_UPLOAD_BYTES + 1024 * 1024
# The largest body any other route takes is a guidance text of 20,000 characters (schemas.GuidanceIn), at most about
# 120 KB as JSON with every character escaped; 1 MiB parses in milliseconds and costs tens of MB at worst.
JSON_REQUEST_LIMIT = 1024 * 1024
# Two uploads in flight per network, so one network cannot take the spool. The spool is /tmp, a 512 MiB tmpfs charged
# to the container's memory (deploy/cloud/compose.yml): 384 MiB of received bodies, about fifteen of the largest. At
# its worst the container then holds the full spool, two readings at their 768 MB bound, their two 26 MiB copies in the
# API and their handed-over files in /tmp, and the API itself: about 2.2 to 2.3 GiB of its 2.5 GiB. Counted on the event loop
# only, so no lock is needed. A body waited for thirty seconds at most at a time, and after its first ten at 32 KiB a
# second (256 kbit/s) on average or better: the largest form holds its bytes for at most about fourteen minutes, and
# only while it is sent.
UPLOADS_PER_NETWORK = 2
SPOOL_BUDGET = 384 * 1024 * 1024
BODY_IDLE_SECONDS = 30.0
BODY_GRACE_SECONDS = 10.0
BODY_MIN_RATE = 32 * 1024

UPLOAD_TOO_LARGE = "file larger than 25 MB"
BODY_TOO_LARGE = "request body larger than 1 MB"
UPLOADS_BUSY = "Too many contracts are being added right now; try again in a moment."
NETWORK_BUSY = "Your network is already adding two contracts; try again when one is done."
BODY_STALLED = "the upload stopped arriving, or arrived slower than 256 kbit/s"

_uploads_from: dict[str, int] = {}
_spool_held = 0


def body_limit(method: str, path: str) -> tuple[int, str]:
    """The most a request to this route may send, and what a refusal says."""
    if method == "POST" and path == UPLOAD_PATH:
        return UPLOAD_REQUEST_LIMIT, UPLOAD_TOO_LARGE
    return JSON_REQUEST_LIMIT, BODY_TOO_LARGE


class BodyRefused(HTTPException):
    """Raised from the counting receive: FastAPI passes an HTTPException met while reading a body through unchanged
    (fastapi/routing.py), where any other error would become a 400."""

    def __init__(self, status_code: int, detail: str, retry_after: int | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail, headers={"Retry-After": str(retry_after)} if retry_after else None)
        self.retry_after = retry_after


class BodyTooLarge(BodyRefused):
    def __init__(self, detail: str) -> None:
        super().__init__(413, detail)


class BodyStalled(BodyRefused):
    """An upload's body stopped arriving, or arrived too slowly."""

    def __init__(self) -> None:
        super().__init__(408, BODY_STALLED)


class SpoolFull(BodyRefused):
    """The uploads in flight already hold the spool's budget; this one is ended and what it sent is let go."""

    def __init__(self) -> None:
        super().__init__(503, UPLOADS_BUSY, retry_after=5)


def _gate_refusal(scope: Scope) -> WorkbenchError | None:
    """What the upload route would refuse on the headers alone: the same functions, so the two never differ. The request
    object shares the scope's state, which the route's own gate sets again."""
    try:
        access.refuse_upload_on_headers(Request(scope))
    except WorkbenchError as refusal:
        return refusal
    return None


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        global _spool_held
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit, detail = body_limit(scope["method"], scope["path"])
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await _answer(send, 413, detail)  # refused unread
            return
        upload = limit == UPLOAD_REQUEST_LIMIT
        if upload:
            # The gate may look the session's workspace up in the store: off the event loop, like the route's own.
            refusal = await to_thread.run_sync(_gate_refusal, scope)
            if refusal is not None:
                await _answer(send, refusal.status_code, str(refusal))  # refused unread
                return
            network = access.client_network(Request(scope))
            if _uploads_from.get(network, 0) >= UPLOADS_PER_NETWORK:
                await _answer(send, 503, NETWORK_BUSY, retry_after=5)
                return
            if declared.isdigit() and _spool_held + int(declared) > SPOOL_BUDGET:
                await _answer(send, 503, UPLOADS_BUSY, retry_after=5)  # what it says it will send does not fit: refused unread
                return
            _uploads_from[network] = _uploads_from.get(network, 0) + 1
        received = 0
        held = 0  # of the spool's budget, released when the request ends
        waited = 0.0  # time spent waiting for the client's next bytes
        body_done = False
        started = False

        async def counted_receive() -> Message:
            nonlocal received, held, waited, body_done
            global _spool_held
            if upload and not body_done:
                # Only while the body is arriving: afterwards receive() waits for a disconnect, as long as the answer takes.
                allowed = min(BODY_IDLE_SECONDS, BODY_GRACE_SECONDS + received / BODY_MIN_RATE - waited)
                if allowed <= 0:
                    raise BodyStalled()
                began = current_time()
                try:
                    with fail_after(allowed):
                        message = await receive()
                except TimeoutError:
                    raise BodyStalled() from None
                finally:
                    waited += current_time() - began
            else:
                message = await receive()
            if message["type"] == "http.request":
                size = len(message.get("body", b""))
                received += size
                body_done = not message.get("more_body", False)
                if received > limit:
                    raise BodyTooLarge(detail)
                if upload:
                    if _spool_held + size > SPOOL_BUDGET:
                        raise SpoolFull()
                    _spool_held += size
                    held += size
            return message

        async def watched_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counted_receive, watched_send)
        except BodyRefused as refused:
            # A route that reads its body itself, outside FastAPI's parsing, lets the refusal reach here.
            if not started:
                await _answer(send, refused.status_code, str(refused.detail), refused.retry_after)
        finally:
            if upload:
                _spool_held -= held
                if _uploads_from[network] <= 1:
                    del _uploads_from[network]
                else:
                    _uploads_from[network] -= 1


async def _answer(send: Send, status: int, detail: str, retry_after: int | None = None) -> None:
    body = json.dumps({"detail": detail}, separators=(",", ":")).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"connection", b"close")]
    if retry_after is not None:
        headers.append((b"retry-after", str(retry_after).encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
