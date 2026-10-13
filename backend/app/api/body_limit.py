"""No request body is read past what its route can legitimately need.

FastAPI reads and parses a whole body before any dependency runs, the access gate included, so a body is paid for by
the server before anyone is asked who sent it: a 40 MB JSON body to /api/runs, with no session, took the API to a
2 GB peak and held the event loop for 19 s, and Cloudflare passes up to 100 MB (gstack /review trial, 2026-10-13). The
first fix of this class (security review of the same day) refused only uploads, and only by their declared length.

Here every request is bounded, on the bytes actually received as well as on the length declared, so a chunked body
with no Content-Length is cut off at the same point: an upload at the 25 MB file and room for its form, everything else
at JSON_REQUEST_LIMIT. A refused body gets 413 before its route, its gate or its parser sees more of it.
"""

from __future__ import annotations

import json

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..application.ingest_document import MAX_UPLOAD_BYTES

UPLOAD_PATH = "/api/documents"
# The 25 MB file and room for its form, as Caddy's request_body max_size (deploy/cloud/Caddyfile, 26 MiB).
UPLOAD_REQUEST_LIMIT = MAX_UPLOAD_BYTES + 1024 * 1024
# The largest body any other route takes is a guidance text of 20,000 characters (schemas.GuidanceIn), at most about
# 120 KB as JSON with every character escaped; 1 MiB parses in milliseconds and costs tens of MB at worst.
JSON_REQUEST_LIMIT = 1024 * 1024

UPLOAD_TOO_LARGE = "file larger than 25 MB"
BODY_TOO_LARGE = "request body larger than 1 MB"


def body_limit(method: str, path: str) -> tuple[int, str]:
    """The most a request to this route may send, and what a refusal says."""
    if method == "POST" and path == UPLOAD_PATH:
        return UPLOAD_REQUEST_LIMIT, UPLOAD_TOO_LARGE
    return JSON_REQUEST_LIMIT, BODY_TOO_LARGE


class BodyTooLarge(HTTPException):
    """Raised from the counting receive: FastAPI passes an HTTPException met while reading a body through unchanged
    (fastapi/routing.py), where any other error would become a 400."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=413, detail=detail)


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit, detail = body_limit(scope["method"], scope["path"])
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await _refuse(send, detail)  # refused unread
            return
        received = 0
        started = False

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge(detail)
            return message

        async def watched_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counted_receive, watched_send)
        except BodyTooLarge:
            # A route that reads its body itself, outside FastAPI's parsing, lets the refusal reach here.
            if not started:
                await _refuse(send, detail)


async def _refuse(send: Send, detail: str) -> None:
    body = json.dumps({"detail": detail}, separators=(",", ":")).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"connection", b"close")]
    await send({"type": "http.response.start", "status": 413, "headers": headers})
    await send({"type": "http.response.body", "body": body})
