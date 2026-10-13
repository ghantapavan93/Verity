"""No request body is read past what its route can legitimately need (api/body_limit.py).

FastAPI parses a body before any dependency runs, the access gate included: a 40 MB JSON body to /api/runs with no
session took the API to a 2 GB peak and held the event loop for 19 s (gstack /review trial, 2026-10-13), where the first
fix of the class refused only uploads, and only by their declared length. The rule is walked over every route the
application describes, for a declared length and for a body sent with none; the primitive is shown to stop pulling a
stream at its limit; and the largest legitimate bodies are shown to pass.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
from anyio import to_thread
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.api.body_limit import BODY_TOO_LARGE, JSON_REQUEST_LIMIT, UPLOAD_REQUEST_LIMIT, UPLOAD_TOO_LARGE, BodyLimitMiddleware, body_limit
from app.application.ingest_document import MAX_UPLOAD_BYTES
from app.errors import InvalidInput


@pytest.fixture
def gated(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app import config

    monkeypatch.setattr(config.settings, "access_secret", "x" * 40)
    monkeypatch.setattr(config.settings, "access_required", True)
    return client


def _operations(client: TestClient) -> list[tuple[str, str, bool]]:
    """Every (method, path, takes a body) the application describes, path parameters filled in."""
    paths: dict[str, dict[str, dict[str, object]]] = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    return [
        (method.upper(), re.sub(r"\{[^}]+\}", "x", path), "requestBody" in operation)
        for path, methods in paths.items()
        for method, operation in methods.items()
    ]


def _chunked(body: bytes) -> Iterator[bytes]:
    """A body sent with no Content-Length, as a client may (Transfer-Encoding: chunked)."""
    for start in range(0, len(body), 1 << 20):
        yield body[start : start + (1 << 20)]


def test_every_route_refuses_a_declared_length_past_its_limit_before_its_gate(gated: TestClient) -> None:
    operations = _operations(gated)
    assert len(operations) >= 25 and ("POST", "/api/runs", True) in operations and ("POST", "/api/documents", True) in operations
    for method, path, _ in operations:
        limit, detail = body_limit(method, path)
        refused = gated.request(method, path, content=b"{}", headers={"content-length": str(limit + 1), "content-type": "application/json"})
        assert refused.status_code == 413, (method, path, refused.status_code, refused.text[:120])
        assert refused.json() == {"detail": detail}


def test_every_route_that_takes_a_body_refuses_one_sent_without_a_length_past_its_limit_before_its_gate(gated: TestClient) -> None:
    bodied = [(method, path) for method, path, takes_body in _operations(gated) if takes_body]
    assert ("POST", "/api/runs") in bodied and ("POST", "/api/access/session") in bodied and ("POST", "/api/guidance") in bodied
    for method, path in bodied:
        limit, detail = body_limit(method, path)
        if path == "/api/documents":
            request = httpx.Request("POST", "http://testserver/api/documents", files={"file": ("big.txt", b"a" * (limit + 1), "text/plain")})
            content, content_type = request.read(), request.headers["content-type"]
        else:
            content, content_type = b"[" + b"{}," * (limit // 3) + b"{}]", "application/json"
        refused = gated.request(method, path, content=_chunked(content), headers={"content-type": content_type})
        assert "content-length" not in refused.request.headers
        assert refused.status_code == 413, (method, path, refused.status_code, refused.text[:120])
        assert refused.json() == {"detail": detail}
    # Control: the same routes with a small body reach the gate, which is what refuses them there.
    assert gated.post("/api/runs", json={"documentId": "x", "question": "Which law governs?"}).status_code == 401


def test_the_limit_stops_pulling_a_stream_where_it_is_passed() -> None:
    """The primitive, below FastAPI: a body four times the limit is pulled only as far as the limit, then refused unread."""
    chunk = b"{" * 65536
    chunks = 4 * JSON_REQUEST_LIMIT // len(chunk)
    pulled = 0

    async def receive() -> dict[str, object]:
        nonlocal pulled
        pulled += 1
        return {"type": "http.request", "body": chunk, "more_body": pulled < chunks}

    async def parser(_scope: object, receive: object, _send: object) -> None:
        while (await receive())["more_body"]:  # type: ignore[operator, index]
            pass

    sent: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/runs", "headers": []}
    asyncio.run(BodyLimitMiddleware(parser)(scope, receive, send))  # type: ignore[arg-type]
    assert sent[0]["status"] == 413 and sent[1]["body"] == b'{"detail":"%s"}' % BODY_TOO_LARGE.encode()
    assert pulled == JSON_REQUEST_LIMIT // len(chunk) + 1


def test_the_largest_legitimate_bodies_pass(client: TestClient) -> None:
    """False positives: guidance of 20,000 characters, each escaped to six bytes as some clients send them, is accepted;
    a 25 MB file with its form fits under the upload limit (measured on the encoded request, not sent)."""
    text = "€" * 20_000
    body = ('{"text": "%s"}' % ("\\u20ac" * 20_000)).encode()
    assert len(body) > 100_000
    accepted = client.post("/api/guidance", content=body, headers={"content-type": "application/json"})
    assert accepted.status_code == 201, accepted.text[:200]
    assert client.get(f"/api/guidance/{accepted.json()['id']}").json()["text"] == text
    upload = httpx.Request(
        "POST", "http://testserver/api/documents", files={"file": ("contract-with-a-long-name.docx", b"a" * MAX_UPLOAD_BYTES, "application/octet-stream")}
    )
    assert len(upload.read()) <= UPLOAD_REQUEST_LIMIT
    assert body_limit("POST", "/api/documents") == (UPLOAD_REQUEST_LIMIT, UPLOAD_TOO_LARGE)
    assert body_limit("PUT", "/api/documents") == (JSON_REQUEST_LIMIT, BODY_TOO_LARGE)


def test_a_refusal_carries_the_usual_headers(client: TestClient) -> None:
    refused = client.post("/api/runs", content=b"{}", headers={"content-length": str(JSON_REQUEST_LIMIT + 1), "content-type": "application/json"})
    assert refused.status_code == 413
    assert refused.headers["cache-control"] == "no-store" and refused.headers["x-content-type-options"] == "nosniff"
    assert refused.headers.get("x-request-id")


def test_uploads_are_read_two_at_a_time_on_threads_of_their_own(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """However many arrive together, at most READINGS_AT_ONCE are read at once, and none holds a thread of the pool every
    sync route shares: 45 slow uploads at once held all 40 of them and /api/health waited 10.4 s (2026-10-13)."""
    inside, peak, lock = 0, 0, threading.Lock()

    def slow_reading(*_args: object, **_kwargs: object) -> None:
        nonlocal inside, peak
        with lock:
            inside += 1
            peak = max(peak, inside)
        time.sleep(0.3)
        with lock:
            inside -= 1
        raise InvalidInput("not a contract (test)")

    monkeypatch.setattr(documents_api, "ingest_document", slow_reading)

    async def shared_pool_in_use() -> int:
        return int(to_thread.current_default_thread_limiter().borrowed_tokens)

    statuses: list[int] = []
    senders = [
        threading.Thread(
            target=lambda i=i: statuses.append(client.post("/api/documents", files={"file": (f"c{i}.txt", b"AGREEMENT %d" % i, "text/plain")}).status_code)
        )
        for i in range(6)
    ]
    for sender in senders:
        sender.start()
    time.sleep(0.15)
    in_use = client.portal.call(shared_pool_in_use)  # type: ignore[union-attr]
    for sender in senders:
        sender.join()
    assert sorted(statuses) == [422] * 6
    assert peak == documents_api.READINGS_AT_ONCE
    assert in_use == 0, "a reading held a thread of the shared pool"
