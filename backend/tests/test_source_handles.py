"""A section handle the model was not given is shown as such and lowers a pass (runs.prose, status.check_references).

Real run, 2026-10-15 (local qwen3:8b): the model wrote "This is found in sec_12.3." The handle names no section it was
handed, and the product dropped it, so the card read "This is found in.3." and the pass stood: an invented pointer
silently erased, and never seen by the check that lowers a pass citing a section the document does not have.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.runs.prose import UNRESOLVED
from tests.test_relations_oracle import OracleModel

QUOTE = "Customer may terminate any Cabinet Service for convenience by giving Provider ninety (90) days' written notice."
AGREEMENT = "\n\n".join(["COLOCATION AGREEMENT", "12. TERMINATION", f"12.1 {QUOTE}"])


def _ask(client: TestClient, monkeypatch: pytest.MonkeyPatch, conclusion: str) -> dict[str, Any]:
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = OracleModel({"topic": "Notice", "conclusion": conclusion, "observed": "90 days", "quotes": [QUOTE]})  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("colo.txt", AGREEMENT.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": f"Notice? {conclusion[-12:]}"})
    assert started.status_code == 202, started.text
    return client.get(f"/api/runs/{started.json()['id']}/detail").json()


def test_an_invented_handle_is_marked_and_lowers_the_pass(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    detail = _ask(client, monkeypatch, "The notice is ninety (90) days' written notice. This is found in sec_12.3.")
    finding = detail["findings"][0]
    assert finding["conclusion"].endswith(f"This is found in {UNRESOLVED}.")
    assert (finding["status"], finding["statusSource"]) == ("needs_review", "reference_check")
    # The reason names the failure as the reader sees it, not the internal handle (the raw output keeps that).
    assert "sec_" not in finding["statusReason"] and "names no section the model was given" in finding["statusReason"]
    assert UNRESOLVED in finding["statusReason"]
    assert "sec_12.3" in detail["rawOutput"]  # the model's own words are kept as it wrote them


def test_control_an_answer_with_no_handle_keeps_its_pass(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    detail = _ask(client, monkeypatch, "The notice is ninety (90) days' written notice.")
    assert detail["findings"][0]["status"] == "pass" and UNRESOLVED not in detail["findings"][0]["conclusion"]


@pytest.mark.parametrize("field", ["observed", "topic"])
def test_a_handle_the_model_was_not_given_lowers_the_pass_in_any_field(client: TestClient, monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    item = {"topic": "Notice", "conclusion": "The notice is ninety (90) days' written notice.", "observed": "90 days", "quotes": [QUOTE]}
    item[field] = f"{item[field]} (sec_12.3)"
    client.app.state.provider = OracleModel(item)  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("colo.txt", AGREEMENT.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": f"Notice in {field}?"})
    finding = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    assert (finding["status"], finding["statusSource"]) == ("needs_review", "reference_check")
