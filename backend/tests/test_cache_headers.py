"""A reader's contract, findings and memos are never stored by a cache on the way: every API response says no-store
unless it sets its own policy. Observed through Caddy in the cloud rehearsal (2026-10-09): no /api response carried
Cache-Control at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.support import upload_and_ask


def test_every_private_response_says_no_store(client: TestClient) -> None:
    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    run_id, document_id = result["run_id"], result["document"]["id"]
    memo = client.post("/api/memos", json={"runId": run_id}).json()
    paths = [
        "/api/health",
        "/api/documents",
        f"/api/documents/{document_id}",
        "/api/runs",
        f"/api/runs/{run_id}",
        f"/api/runs/{run_id}/detail",
        f"/api/runs/{run_id}/events",
        f"/api/runs/{run_id}/evidence-pack",
        "/api/findings",
        f"/api/memos/{memo['id']}/html",
        "/api/runs/0000000000000000",
    ]
    for path in paths:
        response = client.get(path)
        assert response.headers.get("cache-control") == "no-store", (path, response.status_code, response.headers.get("cache-control"))


def test_a_memo_page_runs_nothing_and_loads_nothing(client: TestClient) -> None:
    """The memo page is served from the workbench's own origin and carries text from an uploaded contract. It is escaped
    when written; the policy is the second line: no script, no fetch, no frame, only its own inline style."""
    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    memo = client.post("/api/memos", json={"runId": result["run_id"]}).json()
    page = client.get(f"/api/memos/{memo['id']}/html")
    policy = page.headers.get("content-security-policy", "")
    assert page.status_code == 200 and "<style>" in page.text
    assert "default-src 'none'" in policy and "style-src 'unsafe-inline'" in policy and "frame-ancestors 'none'" in policy
    assert "script-src" not in policy, "nothing may run: default-src 'none' already says so"


def test_every_response_carries_the_browsers_protections_whatever_edge_is_in_front(client: TestClient) -> None:
    """A Cloudflare Tunnel adds none of these (the live site, 2026-10-13), so the API sends them itself; a route with a
    policy of its own (the memo) keeps it, and nothing names the server's software."""
    from app.api.memos import MEMO_POLICY
    from app.main import SECURITY_HEADERS

    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    run_id = result["run_id"]
    memo = client.post("/api/memos", json={"runId": run_id}).json()
    for path in ("/api/health", "/api/documents", f"/api/runs/{run_id}", "/api/runs/0000000000000000", f"/api/memos/{memo['id']}/html"):
        response = client.get(path)
        for name, value in SECURITY_HEADERS.items():
            expected = MEMO_POLICY if (name == "Content-Security-Policy" and path.endswith("/html")) else value
            assert response.headers.get(name) == expected, (path, name, response.headers.get(name))
        assert "x-powered-by" not in response.headers
    assert "frame-ancestors 'none'" in MEMO_POLICY  # the memo's own policy forbids framing too


def test_an_upload_declaring_more_than_the_limit_is_refused_unread_even_without_a_session(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """FastAPI stores a whole form before any check runs: a 40 MB body with no session was written to disk and only then
    refused (security review, 2026-10-13). A declared size over the limit is refused before the body is read."""
    from app import config
    from app.api.body_limit import UPLOAD_REQUEST_LIMIT

    monkeypatch.setattr(config.settings, "access_secret", "x" * 40)
    monkeypatch.setattr(config.settings, "access_required", True)
    body = b"a" * (UPLOAD_REQUEST_LIMIT + 1)
    refused = client.post("/api/documents", files={"file": ("big.txt", body, "text/plain")})
    assert refused.status_code == 413 and refused.json() == {"detail": "file larger than 25 MB"}
    assert refused.headers.get("x-content-type-options") == "nosniff"
    stored = [p for p in config.settings.data_dir.rglob("*") if p.is_file() and p.stat().st_size >= UPLOAD_REQUEST_LIMIT]
    assert stored == []
    # Control: a small upload without a session reaches the gate and is refused there, not as too large.
    assert client.post("/api/documents", files={"file": ("small.txt", b"AGREEMENT", "text/plain")}).status_code in (401, 403)
