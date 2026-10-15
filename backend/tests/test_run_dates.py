"""A run is reused only while the same amendment starts are reached (application.start_run, runs.relations).

Whether a replacement's stated start has been reached decides what a run says: before it, the replaced clause is
quoted under a limit (a concern); after it, the same quote answers from text the contract replaced (needs review, set by
code). The fingerprint did not carry the date, so a question asked again after the start was handed the run made before
it. Now the latest start already reached enters the identity, only when there is one; the earlier run stays as
recorded.
"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import models
from tests.test_relations_oracle import OracleModel

OLD = "Supplier shall give thirty (30) days' notice of a price increase."
DATED = "\n\n".join(
    [
        "SUPPLY AGREEMENT",
        "9. PRICES",
        f"9.1 {OLD}",
        "AMENDMENT NO. 1",
        "1. With effect from 1 January 2027, clause 9.1 of the Agreement is deleted in its entirety and replaced with the "
        'following: "9.1 Supplier shall give sixty (60) days\' notice of a price increase."',
    ]
)
UNDATED = DATED.replace("With effect from 1 January 2027, clause", "Clause")
QUESTION = "How much notice must Supplier give before raising prices?"


def _on(monkeypatch: pytest.MonkeyPatch, day: str) -> None:
    fixed = datetime.fromisoformat(f"{day}T12:00:00").replace(tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:  # type: ignore[override]
            return fixed

    monkeypatch.setattr(models, "datetime", Clock)  # models.utcnow reads `datetime` when called


def _ask(client: TestClient, monkeypatch: pytest.MonkeyPatch, agreement: str, day: str, question: str = QUESTION) -> dict[str, Any]:
    from app.runs import service

    _on(monkeypatch, day)
    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = OracleModel(  # type: ignore[attr-defined]
        {"topic": "Notice", "conclusion": "Supplier must give 30 days' notice.", "observed": "30 days", "quotes": [OLD]}
    )
    document = client.post("/api/documents", files={"file": ("supply.txt", agreement.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": question})
    assert started.status_code in (200, 202), started.text
    return started.json() | {"detail": client.get(f"/api/runs/{started.json()['id']}/detail").json()}


def _effects(run: dict[str, Any]) -> list[str]:
    return [note["effect"] for finding in run["detail"]["findings"] for note in finding["relations"]]


def test_a_run_asked_before_an_amendment_takes_effect_is_not_handed_back_after_it(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    before = _ask(client, monkeypatch, DATED, "2026-10-15")
    after = _ask(client, monkeypatch, DATED, "2027-02-01")
    assert _effects(before) == ["scoped"]  # the start is ahead: a limit code cannot apply
    assert after["id"] != before["id"] and after["reused"] is False
    assert _effects(after) == ["replaced"] and after["detail"]["findings"][0]["statusSource"] == "position_check"
    assert after["detail"]["options"]["latest_start_reached"] == "2027-01-01"
    # The earlier run is a record of what was decided then, and stays so.
    again = client.get(f"/api/runs/{before['id']}/detail").json()
    assert [n["effect"] for f in again["findings"] for n in f["relations"]] == ["scoped"]


def test_control_the_same_question_the_same_day_is_still_one_run(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    first = _ask(client, monkeypatch, DATED, "2026-10-15")
    second = _ask(client, monkeypatch, DATED, "2026-10-15")
    assert second["id"] == first["id"] and second["reused"] is True


def test_control_a_start_reached_both_times_is_still_one_run(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    first = _ask(client, monkeypatch, DATED, "2027-02-01")
    second = _ask(client, monkeypatch, DATED, "2027-03-01")
    assert second["id"] == first["id"] and second["reused"] is True


def test_control_a_document_with_no_dated_start_keeps_its_identity_across_dates(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    first = _ask(client, monkeypatch, UNDATED, "2026-10-15")
    second = _ask(client, monkeypatch, UNDATED, "2027-06-01")
    assert second["id"] == first["id"] and second["reused"] is True
    assert "latest_start_reached" not in first["detail"]["options"]


def test_the_run_is_dated_by_the_instant_its_identity_was_read(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # The relation step reads the run's created_at as the day it was asked; the identity must have read the same day, or
    # a run made just after midnight could carry one day's starts and be assessed against the next day's.
    run = _ask(client, monkeypatch, DATED, "2027-01-01")
    assert run["detail"]["createdAt"].startswith("2027-01-01T12:00:00")
    assert run["detail"]["options"]["latest_start_reached"] == "2027-01-01" and _effects(run) == ["replaced"]


def test_a_documents_starts_do_not_depend_on_the_day_they_are_read() -> None:
    from datetime import date

    from app.runs.relations import latest_start_reached, replacement_starts
    from tests.test_relations import section

    sections = [section(text, id=f"s{i}") for i, text in enumerate(DATED.split("\n\n"))]
    assert replacement_starts(sections) == ("2027-01-01",)
    assert [latest_start_reached(sections, date.fromisoformat(d)) for d in ("2026-12-31", "2027-01-01", "2030-01-01")] == [None, "2027-01-01", "2027-01-01"]
