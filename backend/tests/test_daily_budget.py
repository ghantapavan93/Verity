"""A day's model spend has a ceiling: past WORKBENCH_MAX_RUNS_PER_DAY new runs (all readers together), a new question is
refused with a sentence and the time it opens again, while every answer already given still opens and a question asked
before is still handed its run. Triage risk review, 2026-10-09: the per-reader limit (20 runs in 10 minutes) let one
invitee spend a month's GPU budget in a day, after which every demonstration failed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config
from tests.support import upload_and_ask


def ask(client: TestClient, document_id: str, question: str) -> tuple[int, dict[str, object], dict[str, str]]:
    response = client.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": question})
    return response.status_code, response.json(), dict(response.headers)


def test_past_the_days_budget_a_new_question_waits_and_answers_already_given_do_not(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    first = upload_and_ask(client, "What notice period applies to termination for convenience?", with_guidance=False)
    document_id = first["document"]["id"]
    monkeypatch.setattr(config.settings, "max_runs_per_day", 2)
    assert ask(client, document_id, "Who owns the data?")[0] == 202
    status, body, headers = ask(client, document_id, "Which law governs?")
    assert status == 429 and "run budget" in str(body["detail"]) and int(headers["retry-after"]) > 0
    again, reused, _ = ask(client, document_id, "What notice period applies to termination for convenience?")
    assert again == 200 and reused["reused"] is True, "a question asked before is handed its run, budget or not"
    assert client.get(f"/api/runs/{first['run_id']}").status_code == 200


def test_controls_no_budget_set_is_no_ceiling(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "max_runs_per_day", 0)
    first = upload_and_ask(client, "What notice period applies to termination for convenience?", with_guidance=False)
    for question in ("Who owns the data?", "Which law governs?", "Is there a renewal?"):
        assert ask(client, first["document"]["id"], question)[0] == 202
