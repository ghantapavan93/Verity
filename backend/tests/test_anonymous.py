"""Public use without an invite: every visitor is handed a session of their own, never a shared one.

With anonymous sessions on (WORKBENCH_ANONYMOUS_SESSIONS) the gate stays required. A browser that has no session asks
POST /api/access/visit; the server makes an unpredictable subject, signs a session for it like an invite's, and every
route then serves that subject's workspace exactly as it serves an invited reader's. Anonymous never means shared: two
visitors are two workspaces, and neither can reach the other's records by any id.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app import config
from app.api import access
from app.api.access import SESSION_COOKIE, mint, verify, workspace_for
from app.db import SessionLocal
from app.models import VisitorWorkspace
from tests.support import CONTRACT
from tests.test_access import ORIGIN, SECRET
from tests.test_workspaces import QUESTION, Reviewer, make_curated, work


class Visitor:
    """One browser: its own cookie, sent on every request, never another's."""

    def __init__(self, client: TestClient, cookie: str | None) -> None:
        self.client = client
        self.cookie = cookie
        self.headers = {"Origin": ORIGIN, **({"Cookie": f"{SESSION_COOKIE}={cookie}"} if cookie else {})}

    # The test client keeps one cookie jar for every request; each browser here sends its own cookie and nothing else.
    def get(self, path: str) -> Response:
        self.client.cookies.clear()
        response: Response = self.client.get(path, headers=self.headers)
        self.client.cookies.clear()
        return response

    def post(self, path: str, json: dict[str, object] | None = None, files: dict[str, tuple[str, bytes, str]] | None = None) -> Response:
        self.client.cookies.clear()
        response: Response = self.client.post(path, headers=self.headers, json=json, files=files)
        self.client.cookies.clear()
        return response

    @property
    def subject(self) -> str:
        session = verify(self.cookie, "verity-session", SECRET)
        assert session is not None
        return session.subject


def arrive(client: TestClient, cookie: str | None = None, address: str = "198.51.100.7") -> tuple[Visitor, Response]:
    """What the page does on a first visit: ask for a session, keep the cookie it is given."""
    headers = {"Origin": ORIGIN, "CF-Connecting-IP": address, **({"Cookie": f"{SESSION_COOKIE}={cookie}"} if cookie else {})}
    client.cookies.clear()
    response = client.post("/api/access/visit", headers=headers)
    client.cookies.clear()
    found = re.search(rf"{SESSION_COOKIE}=([^;]+)", response.headers.get("set-cookie", ""))
    return Visitor(client, found.group(1) if found else cookie), response


@pytest.fixture
def public(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The deployment's settings: the gate required, anonymous sessions on, https, one origin."""
    monkeypatch.setattr(config.settings, "access_secret", SECRET)
    monkeypatch.setattr(config.settings, "access_required", True)
    monkeypatch.setattr(config.settings, "anonymous_sessions", True)
    monkeypatch.setattr(config.settings, "app_url", ORIGIN)
    monkeypatch.setattr(config.settings, "access_revoked", [])
    access.visits.reset()
    access.address_uploads.reset()
    access.address_runs.reset()
    client.base_url = ORIGIN
    return client


# ---------------------------------------------------------------------------- the session


def test_a_first_visit_is_handed_its_own_session_with_no_step_in_between(public: TestClient) -> None:
    before = public.get("/api/access").json()
    assert before == {"required": True, "entered": False, "subject": None, "anonymous": True, "retentionDays": 7}
    a, made = arrive(public)
    assert made.status_code == 200 and made.json()["entered"] is True and made.json()["anonymous"] is True
    cookie = made.headers["set-cookie"]
    for attribute in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert attribute.lower() in cookie.lower(), attribute
    assert made.headers["cache-control"] == "no-store"
    assert a.subject.startswith("anon-") and len(a.subject) >= 5 + 32, "unpredictable: 24 random bytes"
    assert a.get("/api/runs").status_code == 200 and a.get("/api/documents").json() == []
    b, _ = arrive(public)
    assert b.subject != a.subject and workspace_for(b.subject) != workspace_for(a.subject), "anonymous never means shared"


def test_a_visit_with_a_session_keeps_it_and_mints_nothing(public: TestClient) -> None:
    a, _ = arrive(public)
    again, response = arrive(public, cookie=a.cookie)
    assert response.status_code == 200 and "set-cookie" not in response.headers, "refresh keeps the workspace"
    assert again.subject == a.subject


def test_the_client_cannot_choose_its_subject(public: TestClient) -> None:
    """No fixation: a cookie the server did not sign is no session, and the visit makes a new subject of its own."""
    forged = mint("anon-chosen-by-the-client", "verity-session", 3600, "another-secret-" + "y" * 40)
    visitor, response = arrive(public, cookie=forged)
    assert response.status_code == 200 and visitor.subject != "anon-chosen-by-the-client"
    assert Visitor(public, forged).get("/api/documents").status_code == 401


def test_an_expired_or_forged_session_fails_safely_and_a_new_visit_starts_afresh(public: TestClient) -> None:
    a, _ = arrive(public)
    expired = mint(a.subject, "verity-session", 60, SECRET, now=time.time() - 3600)
    for cookie in (expired, "garbage", "v1.e30.00"):
        stale = Visitor(public, cookie)
        assert stale.get("/api/documents").status_code == 401
        fresh, response = arrive(public, cookie=cookie)
        assert response.status_code == 200 and fresh.subject != a.subject


def test_a_visit_from_another_site_is_refused(public: TestClient) -> None:
    response = public.post("/api/access/visit", headers={"Origin": "https://elsewhere.example"})
    assert response.status_code == 403 and "set-cookie" not in response.headers


def test_without_anonymous_sessions_a_visit_mints_nothing(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_sessions", False)
    response = public.post("/api/access/visit", headers={"Origin": ORIGIN})
    assert response.status_code == 403 and "set-cookie" not in response.headers
    assert public.get("/api/access").json()["anonymous"] is False


def test_one_address_cannot_mint_sessions_without_end(public: TestClient) -> None:
    statuses = [arrive(public, address="203.0.113.50")[1].status_code for _ in range(access.VISIT_LIMIT + 1)]
    assert statuses[:-1] == [200] * access.VISIT_LIMIT and statuses[-1] == 429
    assert arrive(public, address="203.0.113.51")[1].status_code == 200, "another address is its own bucket"


def test_simultaneous_first_visits_are_separate_workspaces(public: TestClient) -> None:
    subjects: list[str] = []

    def visit(index: int) -> None:
        visitor, response = arrive(public, address=f"192.0.2.{index}")
        assert response.status_code == 200
        subjects.append(visitor.subject)

    threads = [threading.Thread(target=visit, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(subjects) == 8 and len({workspace_for(s) for s in subjects}) == 8


# ---------------------------------------------------------------------------- isolation


def test_visitor_b_reaches_nothing_of_visitor_a(public: TestClient) -> None:
    a, _ = arrive(public)
    b, _ = arrive(public, address="198.51.100.8")
    ids = work(cast(Reviewer, a))
    probes = {
        "document": b.get(f"/api/documents/{ids['document']}"),
        "run": b.get(f"/api/runs/{ids['run']}"),
        "run detail": b.get(f"/api/runs/{ids['run']}/detail"),
        "explanation": b.get(f"/api/runs/{ids['run']}/explanation"),
        "evidence pack": b.get(f"/api/runs/{ids['run']}/evidence-pack"),
        "events": b.get(f"/api/runs/{ids['run']}/events"),
        "review": b.post(f"/api/findings/{ids['finding']}/review", json={"verdict": "dismissed", "reviewer": "B", "note": None}),
        "memo page": b.get(f"/api/memos/{ids['memo']}/html"),
        "memo docx": b.get(f"/api/memos/{ids['memo']}/docx"),
        "memo of A's run": b.post("/api/memos", json={"runId": ids["run"]}),
        "guidance": b.get(f"/api/guidance/{ids['guidance']}"),
        "a run on A's document": b.post("/api/runs", json={"documentId": ids["document"], "guidanceId": None, "question": "x?"}),
    }
    for name, response in probes.items():
        assert response.status_code == 404, (name, response.status_code, response.text[:120])
    for path in ("/api/documents", "/api/runs", "/api/findings"):
        assert b.get(path).json() == [], path
    assert a.get(f"/api/runs/{ids['run']}").status_code == 200, "control: A still reads its own"


def test_identical_bytes_reveal_nothing_of_the_other_visitor(public: TestClient) -> None:
    a, _ = arrive(public)
    b, _ = arrive(public, address="198.51.100.8")
    first = a.post("/api/documents", files={"file": ("acme-confidential.txt", CONTRACT.encode(), "text/plain")}).json()
    second = b.post("/api/documents", files={"file": ("mine.txt", CONTRACT.encode(), "text/plain")})
    assert second.status_code == 201, "new to B: nothing says another visitor holds these bytes"
    assert second.json()["name"] == "mine.txt" and "acme" not in second.text and first["name"] == "acme-confidential.txt"


def test_a_visitor_sees_none_of_the_curated_record(public: TestClient) -> None:
    """The public store holds no curated rows, and if one did, an anonymous visitor still would not read it."""
    curated = make_curated(public)
    a, _ = arrive(public)
    assert a.get("/api/documents").json() == [] and a.get("/api/runs").json() == [] and a.get("/api/findings").json() == []
    for path in (f"/api/documents/{curated['document']}", f"/api/runs/{curated['run']}", f"/api/runs/{curated['run']}/evidence-pack"):
        assert a.get(path).status_code == 404, path


def test_isolation_survives_a_restart(public: TestClient) -> None:
    a, _ = arrive(public)
    b, _ = arrive(public, address="198.51.100.8")
    document = a.post("/api/documents", files={"file": ("a.txt", CONTRACT.encode(), "text/plain")}).json()
    from app.main import create_app

    with TestClient(create_app(provider=public.provider), base_url=ORIGIN) as restarted:
        assert Visitor(restarted, a.cookie).get(f"/api/documents/{document['id']}").status_code == 200
        assert Visitor(restarted, b.cookie).get(f"/api/documents/{document['id']}").status_code == 404


# ---------------------------------------------------------------------------- limits


def test_a_workspace_holds_a_bounded_number_of_documents(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_max_documents", 2)
    a, _ = arrive(public)
    codes = [a.post("/api/documents", files={"file": (f"d{i}.txt", f"{CONTRACT}\n{i}".encode(), "text/plain")}).status_code for i in range(3)]
    assert codes[:2] == [201, 201] and codes[2] == 429


def test_fresh_sessions_do_not_escape_the_global_daily_ceiling(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "max_runs_per_day", 2)
    codes = []
    for index in range(3):
        visitor, _ = arrive(public, address=f"192.0.2.{index + 20}")
        document = visitor.post("/api/documents", files={"file": ("c.txt", f"{CONTRACT}\n{index}".encode(), "text/plain")}).json()
        codes.append(visitor.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": f"{QUESTION} {index}"}).status_code)
    assert codes == [202, 202, 429]


def test_fresh_sessions_from_one_address_share_its_run_and_upload_limits(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access.address_runs, "limit", 2)
    codes = []
    for index in range(3):
        visitor, _ = arrive(public, address="203.0.113.9")
        visitor.headers["CF-Connecting-IP"] = "203.0.113.9"
        document = visitor.post("/api/documents", files={"file": ("c.txt", f"{CONTRACT}\n{index}".encode(), "text/plain")}).json()
        codes.append(visitor.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": f"{QUESTION} {index}"}).status_code)
    assert codes == [202, 202, 429]


def test_the_owner_can_pause_uploads_and_runs_without_a_restart(public: TestClient, tmp_path: Path) -> None:
    a, _ = arrive(public)
    document = a.post("/api/documents", files={"file": ("a.txt", CONTRACT.encode(), "text/plain")}).json()
    (tmp_path / "public.paused").write_text("", encoding="utf-8")
    try:
        paused_upload = a.post("/api/documents", files={"file": ("b.txt", b"other text here", "text/plain")})
        paused_run = a.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": QUESTION})
        assert paused_upload.status_code == 503 and paused_run.status_code == 503
        assert "paused" in paused_upload.json()["detail"].lower()
        assert a.get(f"/api/documents/{document['id']}").status_code == 200, "reading still works"
        assert public.get("/api/engineering/contract-state").status_code == 200, "the research still works"
    finally:
        (tmp_path / "public.paused").unlink()
    assert a.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": QUESTION}).status_code == 202


def test_a_visit_registers_its_workspace_for_retention(public: TestClient) -> None:
    a, _ = arrive(public)
    with SessionLocal() as session:
        row = session.get(VisitorWorkspace, workspace_for(a.subject))
        assert row is not None and row.expires_at > row.created_at
