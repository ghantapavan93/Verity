"""The gate: with a secret configured, nothing but health and the gate itself answers without a session.

Written before the host was published without Cloudflare Access in front of it. The claim to hold is not that the
page asks for an invite; it is that the API does: someone who opens the developer tools and calls a route directly
gets a 401 from every one of them, the event stream, the uploads and the downloads included."""

from __future__ import annotations

import logging
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import access
from app.api.access import SESSION_COOKIE, SlidingWindow, mint, verify
from app.main import create_app
from tests.support import CONTRACT, upload_and_ask

SECRET = "test-secret-" + "x" * 40
ORIGIN = "https://testserver"
OPEN = {"/api/health", "/api/access", "/api/access/session"}


@pytest.fixture
def gated(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The application with the gate on, as the deployment runs it: https, one origin."""
    monkeypatch.setattr(config.settings, "access_secret", SECRET)
    monkeypatch.setattr(config.settings, "app_url", ORIGIN)
    monkeypatch.setattr(config.settings, "access_revoked", [])
    monkeypatch.setattr(access, "exchanges", SlidingWindow(access.EXCHANGE_LIMIT, access.EXCHANGE_WINDOW_S))
    monkeypatch.setattr(access, "run_starts", SlidingWindow(access.RUN_LIMIT, access.RUN_WINDOW_S))
    client.base_url = ORIGIN  # a Secure cookie is only sent back over https
    return client


def invite(subject: str = "min-kyu", days: int = 14) -> str:
    return mint(subject, "verity-invite", days * 86400, SECRET)


def enter(client: TestClient, token: str | None = None) -> None:
    response = client.post("/api/access/session", json={"invite": token or invite()})
    assert response.status_code == 200, response.text


def test_with_no_secret_the_gate_is_off_and_says_so(client: TestClient) -> None:
    assert client.get("/api/access").json() == {"required": False, "entered": True, "subject": None}
    assert client.get("/api/health").json()["access"] == "off"
    assert client.get("/api/runs").status_code == 200
    assert client.post("/api/access/session", json={"invite": "anything"}).json()["entered"] is True, "nothing to exchange, nothing refused"


def test_every_route_but_health_and_the_gate_refuses_a_request_with_no_session(gated: TestClient) -> None:
    """Walked from the application's own description of its routes, so a route added later is covered without anyone
    adding it here."""
    paths: dict[str, dict[str, object]] = gated.app.openapi()["paths"]  # type: ignore[attr-defined]
    assert all(path.startswith("/api") for path in paths), "every route the application serves is under /api, which is what the tunnel sends it"
    guarded = [(method.upper(), re.sub(r"\{[^}]+\}", "x", path)) for path, methods in paths.items() if path not in OPEN for method in sorted(methods)]
    assert len(guarded) >= 24, guarded
    for needed in (
        ("POST", "/api/documents"),
        ("POST", "/api/runs"),
        ("GET", "/api/runs/x/events"),
        ("GET", "/api/runs/x/evidence-pack"),
        ("GET", "/api/memos/x/docx"),
        ("GET", "/api/memos/x/html"),
        ("GET", "/api/batches/x/values.csv"),
        ("POST", "/api/findings/x/review"),
    ):
        assert needed in guarded, needed
    for method, path in guarded:
        response = gated.request(method, path, json={} if method == "POST" else None)
        assert response.status_code == 401, (method, path, response.status_code, response.text[:120])
        assert response.json() == {"detail": "This is a private preview. Open your invite link to enter."}
    assert set(paths) >= OPEN, "the open routes are exactly these, and they exist"
    # And a cookie that is not one this server signed is no cookie.
    for forged in ("", "v1.e30.00", "garbage", mint("min-kyu", "verity-session", 3600, "another-secret-" + "y" * 40), invite()):
        gated.cookies.set(SESSION_COOKIE, forged, domain="testserver")
        assert gated.get("/api/runs").status_code == 401, forged[:20]
        gated.cookies.clear()


def test_an_invite_is_exchanged_for_a_session_cookie_and_the_workbench_works(gated: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    assert gated.get("/api/access").json() == {"required": True, "entered": False, "subject": None}
    before = gated.get("/api/health").json()
    assert (before["access"], before["provider"], before["model"]) == ("required", "", ""), "before the gate, health names nothing"

    token = invite("min-kyu")
    with caplog.at_level(logging.INFO):
        # The whole link works as well as the bare token: it is what a reader has to paste.
        entered = gated.post("/api/access/session", json={"invite": f"{ORIGIN}/?document=d1&run=r1#invite={token}"})
    assert entered.status_code == 200 and entered.json() == {"required": True, "entered": True, "subject": "min-kyu"}
    assert token not in caplog.text and SECRET not in caplog.text, "neither the invite nor the secret reaches a log"

    cookie = entered.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    for attribute in ("HttpOnly", "Secure", "SameSite=strict", "Path=/", "Max-Age=604800"):
        assert attribute in cookie, (attribute, cookie)
    assert "Domain" not in cookie, "a __Host- cookie belongs to this host alone"
    assert entered.headers["cache-control"] == "no-store"

    assert gated.get("/api/access").json() == {"required": True, "entered": True, "subject": "min-kyu"}
    after = gated.get("/api/health").json()
    assert after["access"] == "entered" and after["model"] == "fake-1"

    # The real path, behind the gate: upload, run, the event stream, the explanation, the memo, the pack.
    result = upload_and_ask(gated, "How much notice does the customer need to give to terminate for convenience?")
    run_id = result["run_id"]
    assert result["run"]["stage"] == "complete"
    for path in (f"/api/runs/{run_id}/events", f"/api/runs/{run_id}/explanation", f"/api/runs/{run_id}/evidence-pack", "/api/findings", "/api/documents"):
        assert gated.get(path).status_code == 200, path
    memo = gated.post("/api/memos", json={"runId": run_id}).json()
    assert gated.get(memo["htmlUrl"]).status_code == 200 and gated.get(memo["docxUrl"]).status_code == 200

    # Without the cookie the same routes are closed again.
    gated.cookies.clear()
    assert gated.get(f"/api/runs/{run_id}/events").status_code == 401
    assert gated.get(memo["docxUrl"]).status_code == 401
    assert gated.post("/api/documents", files={"file": ("a.txt", CONTRACT.encode(), "text/plain")}).status_code == 401


def test_a_token_is_good_only_as_what_it_was_signed_as_and_only_for_its_time() -> None:
    now = time.time()
    good = mint("didier", "verity-invite", 3600, SECRET, now=now)
    session = verify(good, "verity-invite", SECRET, now=now + 10)
    assert session is not None and session.subject == "didier" and session.expires_at == int(now) + 3600
    body, mac = good.rsplit(".", 1)
    refused = {
        "another audience": verify(good, "verity-session", SECRET, now=now),
        "expired": verify(good, "verity-invite", SECRET, now=now + 3600),
        "not yet issued": verify(mint("didier", "verity-invite", 3600, SECRET, now=now + 600), "verity-invite", SECRET, now=now),
        "another secret": verify(good, "verity-invite", "another-secret-" + "y" * 40, now=now),
        "no secret": verify(good, "verity-invite", "", now=now),
        "a changed claim": verify(f"{body[:-2]}AA.{mac}", "verity-invite", SECRET, now=now),
        "a changed mac": verify(f"{body}.{'0' * len(mac)}", "verity-invite", SECRET, now=now),
        "no mac": verify(body, "verity-invite", SECRET, now=now),
        "another version": verify(good.replace("v1.", "v2.", 1), "verity-invite", SECRET, now=now),
        "not a token": verify("not a token", "verity-invite", SECRET, now=now),
        "empty": verify("", "verity-invite", SECRET, now=now),
        "missing": verify(None, "verity-invite", SECRET, now=now),
        "oversized": verify(good + "A" * 2000, "verity-invite", SECRET, now=now),
        "non-ascii": verify(good + "é", "verity-invite", SECRET, now=now),
    }
    assert all(value is None for value in refused.values()), [name for name, value in refused.items() if value is not None]


def test_a_bad_invite_is_refused_without_saying_why_and_sets_no_cookie(gated: TestClient) -> None:
    expired = mint("min-kyu", "verity-invite", -10, SECRET)
    a_session = mint("min-kyu", "verity-session", 3600, SECRET)
    for bad in ("nonsense", expired, a_session, mint("min-kyu", "verity-invite", 3600, "another-secret-" + "y" * 40)):
        response = gated.post("/api/access/session", json={"invite": bad})
        assert response.status_code == 422 and response.json() == {"detail": "That invite is not valid, or it has expired. Ask for a new link."}
        assert "set-cookie" not in response.headers
    assert gated.get("/api/runs").status_code == 401


def test_a_revoked_reader_is_out_at_once_invite_and_session_alike(gated: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    enter(gated, invite("min-kyu"))
    assert gated.get("/api/runs").status_code == 200
    monkeypatch.setattr(config.settings, "access_revoked", ["min-kyu"])
    assert gated.get("/api/runs").status_code == 401, "the session already in the browser stops working"
    assert gated.post("/api/access/session", json={"invite": invite("min-kyu")}).status_code == 422
    gated.cookies.clear()
    enter(gated, invite("didier"))
    assert gated.get("/api/runs").status_code == 200, "another reader is untouched"


def test_a_change_must_come_from_the_workbench_itself(gated: TestClient) -> None:
    enter(gated)
    assert gated.get("/api/runs", headers={"Origin": "https://elsewhere.example"}).status_code == 200, "reading is the cookie's business alone"
    refused = gated.post("/api/guidance", json={"text": "x"}, headers={"Origin": "https://elsewhere.example"})
    assert refused.status_code == 403 and refused.json() == {"detail": "This request did not come from the workbench."}
    assert gated.post("/api/guidance", json={"text": "x"}, headers={"Origin": ORIGIN}).status_code == 201
    assert gated.post("/api/access/session", json={"invite": invite()}, headers={"Origin": "https://elsewhere.example"}).status_code == 403


def test_guessing_at_the_exchange_and_starting_runs_are_both_limited(gated: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for _ in range(access.EXCHANGE_LIMIT):
        assert gated.post("/api/access/session", json={"invite": "guess"}).status_code == 422
    limited = gated.post("/api/access/session", json={"invite": invite()})
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0, "even a good invite waits once the address has been guessing"
    assert "Too many attempts" in limited.json()["detail"]
    # Another address is not held up by it (the tunnel passes the reader's address on).
    assert gated.post("/api/access/session", json={"invite": invite()}, headers={"CF-Connecting-IP": "203.0.113.9"}).status_code == 200

    monkeypatch.setattr(access, "run_starts", SlidingWindow(2, 600))
    document = gated.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    body = {"documentId": document["id"], "guidanceId": None}
    statuses = [gated.post("/api/runs", json=body | {"question": f"How is the agreement terminated for convenience, part {n}?"}).status_code for n in range(3)]
    assert statuses == [202, 202, 429]
    assert gated.get("/api/runs").status_code == 200, "reading is not limited"


def test_the_window_forgets_what_is_older_than_itself() -> None:
    window = SlidingWindow(2, 60)
    assert window.take("a", now=0) is None and window.take("a", now=10) is None
    assert window.take("a", now=20) == pytest.approx(40), "the wait is until the oldest event leaves the window"
    assert window.take("b", now=20) is None, "keys are separate"
    assert window.take("a", now=61) is None


def test_a_short_secret_is_refused_when_the_application_is_created(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "access_secret", "short")
    with pytest.raises(RuntimeError, match="shorter than 32 characters"):
        create_app()
