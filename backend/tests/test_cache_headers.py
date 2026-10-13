"""A reader's contract, findings and memos are never stored by a cache on the way: every API response says no-store
unless it sets its own policy. Observed through Caddy in the cloud rehearsal (2026-10-09): no /api response carried
Cache-Control at all.
"""

from __future__ import annotations

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
