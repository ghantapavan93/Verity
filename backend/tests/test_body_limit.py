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
from starlette.types import Message, Receive, Scope, Send

from app.api import documents as documents_api
from app.api.access import SESSION_COOKIE
from app.api.body_limit import BODY_TOO_LARGE, JSON_REQUEST_LIMIT, UPLOAD_REQUEST_LIMIT, UPLOAD_TOO_LARGE, BodyLimitMiddleware, body_limit
from app.application.ingest_document import MAX_UPLOAD_BYTES
from app.errors import InvalidInput
from app.ingest import UnsupportedFile, bounded
from tests.support import CONTRACT
from tests.test_anonymous import arrive


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
        if path == "/api/documents":
            continue  # asked at the door before its body (below); with a session it is bounded like these
        limit, detail = body_limit(method, path)
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
        while (await receive())["more_body"]:  # type: ignore[operator]
            pass

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/runs", "headers": []}
    asyncio.run(BodyLimitMiddleware(parser)(scope, receive, send))
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
        raise UnsupportedFile("not a contract (test)")

    # The reader itself, so each upload goes the whole way: the route, its thread, and read_file's slots.
    monkeypatch.setattr(bounded, "ingest", slow_reading)

    async def shared_pool_in_use() -> int:
        return int(to_thread.current_default_thread_limiter().borrowed_tokens)

    statuses: list[int] = []
    senders = [
        threading.Thread(
            # From six networks: each network reads one file at a time, and this test is about the slots between them.
            target=lambda i=i: statuses.append(
                client.post(
                    "/api/documents", files={"file": (f"c{i}.txt", b"AGREEMENT %d" % i, "text/plain")}, headers={"CF-Connecting-IP": f"198.51.100.{20 + i}"}
                ).status_code
            )
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
    assert peak == bounded.READINGS_AT_ONCE
    assert in_use == 0, "a reading held a thread of the shared pool"


# ---------------------------------------------------------------------------- an upload, at the door

UPLOAD_HEADERS = [(b"content-type", b"multipart/form-data; boundary=x"), (b"host", b"testserver")]


def _call_app(client: TestClient, scope: Scope, receive: Receive, send: Send) -> None:
    """The application called straight, as a server calls it, on the test client's own event loop."""
    app, portal = client.app, client.portal
    assert portal is not None

    async def call() -> None:
        await app(scope, receive, send)

    portal.call(call)


def _pulled_before_answer(client: TestClient, headers: list[tuple[bytes, bytes]]) -> tuple[int, int]:
    """Sends POST /api/documents straight to the application with an endless body and counts the chunks it pulls."""
    pulled = 0
    sent: list[Message] = []

    async def receive() -> dict[str, object]:
        nonlocal pulled
        pulled += 1
        return {"type": "http.request", "body": b"-" * 65536, "more_body": pulled < 400}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/documents",
        "raw_path": b"/api/documents",
        "query_string": b"",
        "root_path": "",
        "headers": UPLOAD_HEADERS + headers,
        "client": ("198.51.100.9", 4000),
        "server": ("testserver", 443),
    }
    _call_app(client, scope, receive, send)
    return pulled, int(sent[0]["status"])


def test_an_upload_with_no_session_is_refused_at_the_door_before_a_byte_is_read(gated: TestClient) -> None:
    """F-15: a form is spooled whole before any dependency runs; 3 MiB from a client with no session was parsed and only
    then refused. The gate now runs on the headers first."""
    assert _pulled_before_answer(gated, [(b"origin", b"https://testserver")]) == (0, 401)


def test_an_upload_from_another_origin_is_refused_at_the_door_before_a_byte_is_read(public: TestClient) -> None:
    visitor, _ = arrive(public)
    cookie = f"{SESSION_COOKIE}={visitor.cookie}".encode()
    assert _pulled_before_answer(public, [(b"cookie", cookie), (b"origin", b"https://elsewhere.example")]) == (0, 403)


def test_control_an_upload_with_a_session_is_read_and_bounded_like_any_body(public: TestClient) -> None:
    visitor, _ = arrive(public)
    assert visitor.post("/api/documents", files={"file": ("msa.txt", CONTRACT.encode(), "text/plain")}).status_code == 201
    form = httpx.Request("POST", "https://testserver/api/documents", files={"file": ("big.txt", b"a" * (UPLOAD_REQUEST_LIMIT + 1), "text/plain")})
    public.cookies.clear()
    refused = public.post("/api/documents", content=_chunked(form.read()), headers={**visitor.headers, "content-type": form.headers["content-type"]})
    assert refused.status_code == 413 and refused.json() == {"detail": UPLOAD_TOO_LARGE}


def test_the_bodies_in_flight_hold_no_more_than_the_spool(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Uploads in flight together hold at most SPOOL_BUDGET bytes of received body; past it the next is turned away with a
    time to try again, and what they held is let go when they end."""
    from app.api import body_limit as body_limit_module

    monkeypatch.setattr(body_limit_module, "SPOOL_BUDGET", 3000)

    def slow_reading(*_args: object, **_kwargs: object) -> None:
        time.sleep(0.6)
        raise InvalidInput("not a contract (test)")

    monkeypatch.setattr(documents_api, "ingest_document", slow_reading)
    answers: list[int] = []
    senders = [
        # Four networks, so the bound met here is the spool's, not each network's; each form is about 1,400 bytes.
        threading.Thread(target=lambda i=i: answers.append(_upload_from(client, f"198.51.100.{40 + i}", f"c{i}.txt", 1200)))
        for i in range(4)
    ]
    for sender in senders:
        sender.start()
        time.sleep(0.05)
    for sender in senders:
        sender.join()
    assert sorted(answers) == [422, 422, 503, 503]
    assert body_limit_module._spool_held == 0 and body_limit_module._uploads_from == {}
    assert _upload_from(client, "198.51.100.40", "again.txt", 1200) == 422, "what they held is let go once they end"


def _upload_from(client: TestClient, address: str, name: str, size: int = 0) -> int:
    content = b"AGREEMENT" + b" x" * (size // 2)
    return int(client.post("/api/documents", files={"file": (name, content, "text/plain")}, headers={"CF-Connecting-IP": address}).status_code)


def test_uploads_that_send_no_body_hold_nothing_another_network_needs(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Counter-review round 3: with sixteen places overall, eight /64s of one host sent headers alone, reconnecting as
    each place was ended, and a visitor on a ninth network got in 0 of 18 times. Places are not counted overall any
    more, only the bytes received: twenty uploads that send nothing leave room for everyone else."""
    import anyio

    from app.api import body_limit as body_limit_module

    monkeypatch.setattr(body_limit_module, "BODY_GRACE_SECONDS", 3.0)
    ended: list[int] = []

    def send_nothing(address: str) -> None:
        sent: list[Message] = []

        async def receive() -> dict[str, object]:
            await anyio.sleep(3600)  # headers only: the body never starts
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            sent.append(message)

        _call_app(client, _upload_scope(address), receive, send)
        ended.append(int(sent[0]["status"]))

    holders = [threading.Thread(target=send_nothing, args=(f"2001:db8:{n}::1",)) for n in range(20)]
    for holder in holders:
        holder.start()
    time.sleep(0.5)
    visitor = client.post("/api/documents", files={"file": ("visitor.txt", CONTRACT.encode(), "text/plain")}, headers={"CF-Connecting-IP": "198.51.100.99"})
    assert visitor.status_code == 201, "a visitor on another network still gets in"
    for holder in holders:
        holder.join()
    assert ended == [408] * 20
    assert body_limit_module._spool_held == 0 and body_limit_module._uploads_from == {}


def test_a_busy_server_does_not_make_a_prompt_client_slow(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rate was measured from when the upload began, so time the server spent elsewhere between two reads of the
    body counted against the client (counter-review round 3). Only time spent waiting for the client counts now."""
    import anyio

    from app.api import body_limit as body_limit_module

    monkeypatch.setattr(body_limit_module, "BODY_GRACE_SECONDS", 0.5)
    monkeypatch.setattr(body_limit_module, "BODY_MIN_RATE", 1000)

    async def busy_app(_scope: object, receive: Receive, send: Send) -> None:
        while (await receive()).get("more_body"):
            await anyio.sleep(0.4)  # the server busy elsewhere between two reads
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    pieces = iter([*([b"x" * 10] * 5), b""])

    async def prompt_client() -> dict[str, object]:
        piece = next(pieces)
        return {"type": "http.request", "body": piece, "more_body": bool(piece)}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    anyio.run(BodyLimitMiddleware(busy_app), _upload_scope("198.51.100.98"), prompt_client, send)
    assert sent[0]["status"] == 200, sent[0]


def test_an_upload_waiting_for_a_reading_has_not_started_one(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Uploads waited for a reading slot on threads that had already copied their bytes out of the spool: sixteen
    waiting held sixteen copies (counter-review round 3). They now wait on the event loop, and nothing is read or copied
    until a slot is theirs."""
    started: list[str] = []

    def reading(_session: object, name: str, *_args: object, **_kwargs: object) -> None:
        started.append(name)
        raise InvalidInput("not a contract (test)")

    monkeypatch.setattr(documents_api, "ingest_document", reading)
    holders = [object() for _ in range(bounded.READINGS_AT_ONCE)]
    for holder in holders:
        client.portal.call(documents_api.readings.acquire_on_behalf_of, holder)  # type: ignore[union-attr]
    answers: list[int] = []
    senders = [threading.Thread(target=lambda i=i: answers.append(_upload_from(client, f"198.51.100.{110 + i}", f"w{i}.txt"))) for i in range(3)]
    try:
        for sender in senders:
            sender.start()
        time.sleep(0.5)
        assert started == [], "nothing is read, or copied out of the spool, while no slot is free"
    finally:
        for holder in holders:
            client.portal.call(documents_api.readings.release_on_behalf_of, holder)  # type: ignore[union-attr]
        for sender in senders:
            sender.join()
    assert sorted(answers) == [422, 422, 422] and len(started) == 3


def test_one_network_cannot_take_the_door(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A single overall cap let six unfinished uploads turn every other visitor away (Codex review, 2026-10-13). Each
    network now has UPLOADS_PER_NETWORK in flight, and another network's upload still comes in."""
    from app.api import body_limit as body_limit_module

    def slow_reading(*_args: object, **_kwargs: object) -> None:
        time.sleep(0.6)
        raise InvalidInput("not a contract (test)")

    monkeypatch.setattr(documents_api, "ingest_document", slow_reading)
    answers: dict[str, list[int]] = {"one": [], "other": []}
    senders = [threading.Thread(target=lambda i=i: answers["one"].append(_upload_from(client, "198.51.100.60", f"a{i}.txt"))) for i in range(3)]
    senders.append(threading.Thread(target=lambda: answers["other"].append(_upload_from(client, "198.51.100.61", "b.txt"))))
    for sender in senders:
        sender.start()
        time.sleep(0.05)
    for sender in senders:
        sender.join()
    assert sorted(answers["one"]) == [422, 422, 503] and answers["other"] == [422]
    assert body_limit_module._spool_held == 0 and body_limit_module._uploads_from == {}


def test_an_upload_whose_body_stops_arriving_is_ended_and_frees_its_place(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stalled body held its place for as long as the client kept the connection; it is now ended after a pause."""
    import anyio

    from app.api import body_limit as body_limit_module

    monkeypatch.setattr(body_limit_module, "BODY_IDLE_SECONDS", 0.5)
    sent: list[Message] = []
    first = True

    async def receive() -> dict[str, object]:
        nonlocal first
        if first:
            first = False
            return {"type": "http.request", "body": b"--x\r\n", "more_body": True}
        await anyio.sleep(3600)  # the rest of the body never comes
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/documents",
        "raw_path": b"/api/documents",
        "query_string": b"",
        "root_path": "",
        "headers": UPLOAD_HEADERS,
        "client": ("198.51.100.70", 4000),
        "server": ("testserver", 443),
    }
    started = time.perf_counter()
    _call_app(client, scope, receive, send)
    assert time.perf_counter() - started < 5
    assert sent[0]["status"] == 408
    assert body_limit_module._spool_held == 0 and body_limit_module._uploads_from == {}


def test_each_network_reads_one_file_at_a_time_and_another_network_is_not_held_up(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two hostile files from one network held both reading slots for a minute (counter-review, 2026-10-13); its other
    uploads now wait behind its own, and another network's reading runs alongside."""
    spans: dict[str, tuple[float, float]] = {}

    def slow_reading(_session: object, name: str, *_args: object, **_kwargs: object) -> None:
        began = time.perf_counter()
        time.sleep(0.5)
        spans[name] = (began, time.perf_counter())
        raise InvalidInput("not a contract (test)")

    monkeypatch.setattr(documents_api, "ingest_document", slow_reading)

    def send(name: str, address: str) -> None:
        client.post("/api/documents", files={"file": (name, b"AGREEMENT", "text/plain")}, headers={"CF-Connecting-IP": address})

    senders = [threading.Thread(target=send, args=args) for args in (("a1.txt", "198.51.100.1"), ("a2.txt", "198.51.100.1"), ("b1.txt", "198.51.100.2"))]
    for sender in senders:
        sender.start()
        time.sleep(0.05)
    for sender in senders:
        sender.join()
    first, second = sorted((spans["a1.txt"], spans["a2.txt"]))
    assert second[0] >= first[1] - 0.01, "the same network's second reading waited for its first"
    other = spans["b1.txt"]
    assert other[0] < first[1] and first[0] < other[1], "another network's reading ran alongside"
    assert documents_api._reading_from == {}, "nothing is kept once the readings end"


def _upload_scope(address: str, headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, object]:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/documents",
        "raw_path": b"/api/documents",
        "query_string": b"",
        "root_path": "",
        "headers": UPLOAD_HEADERS + (headers or []),
        "client": (address, 4000),
        "server": ("testserver", 443),
    }


def _trickle(client: TestClient, rate: float, seconds: float) -> tuple[int, float]:
    """Sends an upload straight to the application: a form's opening, then its file at `rate` bytes a second in pieces
    five times a second, never pausing, for `seconds`, then the form's close; returns the answer's status and when."""
    import anyio

    sent: list[Message] = []
    began = time.perf_counter()
    piece = max(1, int(rate / 5))
    opening = b'--x\r\nContent-Disposition: form-data; name="file"; filename="t.txt"\r\nContent-Type: text/plain\r\n\r\n'
    opened = False

    async def receive() -> dict[str, object]:
        nonlocal opened
        if not opened:
            opened = True
            return {"type": "http.request", "body": opening, "more_body": True}
        await anyio.sleep(0.2)
        if time.perf_counter() - began > seconds:
            return {"type": "http.request", "body": b"\r\n--x--\r\n", "more_body": False}
        return {"type": "http.request", "body": b"a" * piece, "more_body": True}

    async def send(message: Message) -> None:
        sent.append(message)

    _call_app(client, _upload_scope("198.51.100.80"), receive, send)
    return int(sent[0]["status"]), time.perf_counter() - began


def test_a_body_trickled_below_the_floor_is_ended_though_it_never_pauses(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """One byte every two seconds is never idle for thirty, so it held its place indefinitely (war room W5 p2). After its
    grace a body must keep an average rate; here the floor is 1,000 bytes a second and the body sends 50."""
    from app.api import body_limit as body_limit_module

    monkeypatch.setattr(body_limit_module, "BODY_IDLE_SECONDS", 1.0)
    monkeypatch.setattr(body_limit_module, "BODY_GRACE_SECONDS", 0.5)
    monkeypatch.setattr(body_limit_module, "BODY_MIN_RATE", 1000)
    status, took = _trickle(client, rate=50, seconds=6)
    assert (status, took < 3) == (408, True), (status, took)
    assert body_limit_module._spool_held == 0 and body_limit_module._uploads_from == {}


def test_control_a_body_above_the_floor_is_not_ended(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import body_limit as body_limit_module

    monkeypatch.setattr(body_limit_module, "BODY_IDLE_SECONDS", 1.0)
    monkeypatch.setattr(body_limit_module, "BODY_GRACE_SECONDS", 0.5)
    monkeypatch.setattr(body_limit_module, "BODY_MIN_RATE", 1000)
    status, took = _trickle(client, rate=5000, seconds=2)
    assert status != 408 and took >= 2, (status, took)  # received whole, then refused as the malformed form it is


def test_one_ipv6_network_shares_its_places_whatever_its_addresses(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Counted by full address, a host with an IPv6 /64 had as many places as addresses it used; its /64 is one network."""
    from app.api import body_limit as body_limit_module

    def slow_reading(*_args: object, **_kwargs: object) -> None:
        time.sleep(0.6)
        raise InvalidInput("not a contract (test)")

    monkeypatch.setattr(documents_api, "ingest_document", slow_reading)
    answers: dict[str, list[int]] = {"same /64": [], "another /64": []}
    senders = [threading.Thread(target=lambda i=i: answers["same /64"].append(_upload_from(client, f"2001:db8:1:2::{i + 1}", f"a{i}.txt"))) for i in range(3)]
    senders.append(threading.Thread(target=lambda: answers["another /64"].append(_upload_from(client, "2001:db8:1:3::1", "b.txt"))))
    for sender in senders:
        sender.start()
        time.sleep(0.05)
    for sender in senders:
        sender.join()
    assert sorted(answers["same /64"]) == [422, 422, 503] and answers["another /64"] == [422], answers
    assert body_limit_module._spool_held == 0 and body_limit_module._uploads_from == {}


def test_a_paused_demo_refuses_an_upload_before_its_body(client: TestClient) -> None:
    """A paused demo still took a 20 MB body before saying so (war room W5 p4); the pause is now asked at the door."""
    from app import config

    pause = config.settings.data_dir / "public.paused"
    pause.write_text("")
    try:
        assert _pulled_before_answer(client, [(b"origin", b"https://testserver")]) == (0, 503)
    finally:
        pause.unlink()


def test_a_received_upload_waits_a_bounded_time_for_a_reading_slot(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """With every reading slot held, an upload waited as long as the others' readings took, past Cloudflare's 100 s, and
    held its place at the door meanwhile (war room W5). It now waits READING_WAIT_SECONDS and is told to come back."""
    monkeypatch.setattr(documents_api, "READING_WAIT_SECONDS", 0.5)
    for _ in range(bounded.READINGS_AT_ONCE):
        assert bounded._slots.acquire(timeout=5)

    def free_the_slots() -> None:
        for _ in range(bounded.READINGS_AT_ONCE):
            bounded._slots.release()

    freed = threading.Timer(4, free_the_slots)
    freed.start()
    body = f"{CONTRACT}\nWaits for a slot.".encode()  # bytes not stored yet, so they must be read
    try:
        started = time.perf_counter()
        answer = client.post("/api/documents", files={"file": ("waits.txt", body, "text/plain")})
        took = time.perf_counter() - started
    finally:
        freed.join()
    assert (answer.status_code, took < 3) == (503, True), (answer.status_code, took)
    assert answer.headers.get("retry-after") == "30" and "try again in a minute" in answer.json()["detail"].lower()
    assert client.post("/api/documents", files={"file": ("waits.txt", body, "text/plain")}).status_code == 201, "asked again, it is read"


def test_an_upload_waits_a_bounded_time_for_its_networks_turn(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The second upload from a network waits behind its first, for no longer than the same bound."""
    monkeypatch.setattr(documents_api, "READING_WAIT_SECONDS", 0.5)

    def slow_reading(*_args: object, **_kwargs: object) -> None:
        time.sleep(2)
        raise InvalidInput("not a contract (test)")

    monkeypatch.setattr(documents_api, "ingest_document", slow_reading)
    answers: dict[str, int] = {}
    first = threading.Thread(target=lambda: answers.update(first=_upload_from(client, "198.51.100.90", "a.txt")))
    first.start()
    time.sleep(0.2)
    started = time.perf_counter()
    answers["second"] = _upload_from(client, "198.51.100.90", "b.txt")
    took = time.perf_counter() - started
    first.join()
    assert (answers, took < 1.5) == ({"first": 422, "second": 503}, True), (answers, took)
    assert documents_api._reading_from == {}


def test_an_upload_that_finishes_late_never_drops_a_lock_it_does_not_hold(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The map was cleaned by key: a lock that finished late popped the one a later upload had made, and the network's
    next upload read beside it (war room W5 p8). Only the map's own entry for this lock is removed."""
    import anyio

    later = anyio.Lock()

    def reading_while_the_map_moves_on(*_args: object, **_kwargs: object) -> None:
        documents_api._reading_from["198.51.100.91"] = later  # as if a later upload had made the network's lock anew
        raise InvalidInput("not a contract (test)")

    monkeypatch.setattr(documents_api, "ingest_document", reading_while_the_map_moves_on)
    try:
        assert _upload_from(client, "198.51.100.91", "a.txt") == 422
        assert documents_api._reading_from.get("198.51.100.91") is later
    finally:
        documents_api._reading_from.pop("198.51.100.91", None)
