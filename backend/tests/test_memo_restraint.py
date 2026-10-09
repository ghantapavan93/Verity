"""A memo suggests a change only where review is needed (negotiation restraint).

A real-model evaluation (2026-10-09) found the model proposing a "suggested position" on clauses that already met the
guidance (net 30 days suggested against the buyer's own 45). The memo is what a reviewer forwards; it printed every
suggestion as "Suggested position." whatever the status. A suggestion is the model's, and it belongs only beside a
finding that needs review; elsewhere it stays on the record (the evidence drawer shows it, as the model's), not in the
memo.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.providers.base import Generation
from tests.support import FakeProvider, upload_and_ask

QUESTION = "What notice period applies to termination for convenience?"


class CompliantProvider(FakeProvider):
    """The same answer, but the clause meets the point: no numbers in conflict, a pass, and still a suggestion."""

    def generate_json(self, system: str, user: str, schema: dict[str, object]) -> Generation:
        payload = json.loads(super().generate_json(system, user, schema).text)
        finding = payload["findings"][0]
        finding.update(observed=None, required=None, guidance_reference=None, status_hint="pass")
        finding["suggested_position"] = "Change fifteen (15) days to thirty (30) days."
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def memo_html(client: TestClient, run_id: str) -> str:
    memo = client.post("/api/memos", json={"runId": run_id}).json()
    html: str = client.get(f"/api/memos/{memo['id']}/html").text
    return html


def test_a_finding_that_needs_review_carries_the_models_suggestion(client: TestClient) -> None:
    run_id = upload_and_ask(client, QUESTION)["run_id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert finding["status"] == "needs_review"
    html = memo_html(client, run_id)
    assert "Suggested position (the model&#x27;s)." in html or "Suggested position (the model's)." in html
    assert "thirty (30) days" in html


def test_a_finding_that_needs_no_review_suggests_nothing(client: TestClient) -> None:
    client.app.state.provider = CompliantProvider()  # type: ignore[attr-defined]
    run_id = upload_and_ask(client, QUESTION, with_guidance=False)["run_id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert finding["status"] == "pass" and finding["suggestedPosition"], "the model's suggestion is still on the record"
    html = memo_html(client, run_id)
    assert "Suggested position" not in html and "thirty (30) days" not in html
    docx = client.get(f"/api/memos/{client.post('/api/memos', json={'runId': run_id}).json()['id']}/docx")
    assert docx.status_code == 200 and b"Suggested position" not in docx.content
