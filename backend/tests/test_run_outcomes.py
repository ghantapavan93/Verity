"""A list of runs says what each run concluded, not only that it finished (2026-10-09 review: two runs of one question
both read "Complete · 1 finding", one having found the period and the other nothing)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.support import upload_and_ask


def test_each_run_in_the_list_carries_its_findings_by_status(client: TestClient) -> None:
    review = upload_and_ask(client, "What notice period applies to termination for convenience?")["run_id"]
    client.app.state.provider.no_evidence = True  # type: ignore[attr-defined]
    missing = upload_and_ask(client, "Is there a most favoured nation clause?")["run_id"]
    rows = {r["id"]: r for r in client.get("/api/runs").json()}
    assert rows[review]["outcomes"] == {"needs_review": 1} and rows[review]["findings"] == 1
    assert rows[missing]["stage"] != "complete" and rows[missing]["outcomes"] == {} and rows[missing]["findings"] == 0, (
        "a run that concluded nothing claims no outcome"
    )
    assert sum(rows[review]["outcomes"].values()) == rows[review]["findings"]
