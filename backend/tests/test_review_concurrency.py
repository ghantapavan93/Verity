"""A review states the review it was decided against, and a decision made against a state that has changed since is
refused. Found by the adversarial review of 2026-10-08: two tabs with one finding open decided over each other; the later
click won and the earlier tab still showed its own decision as the finding's state.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any, cast

import httpx
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app import db as db_module
from app.application.review_finding import review_finding
from app.errors import Conflict
from app.models import FindingReview, ReviewVerdictName
from tests.support import upload_and_ask


def answered(client: TestClient) -> str:
    return str(upload_and_ask(client, "What notice period applies to termination for convenience?")["run"]["findings"][0]["id"])


def review(client: TestClient, finding_id: str, verdict: str, reviewer: str, based_on: int | None, note: str | None = None) -> httpx.Response:
    body: dict[str, Any] = {"verdict": verdict, "reviewer": reviewer, "note": note}
    if based_on is not None:
        body["basedOn"] = based_on
    return cast(httpx.Response, client.post(f"/api/findings/{finding_id}/review", json=body))


def rows(finding_id: str) -> int:
    with db_module.SessionLocal() as session:
        return session.query(FindingReview).filter(FindingReview.finding_id == finding_id).count()


def latest(client: TestClient, finding_id: str) -> int:
    record = next(f for f in client.get("/api/findings").json() if f["id"] == finding_id)
    return int(record["latestReviewId"])


def test_a_stale_decision_is_refused_and_nothing_is_written(client: TestClient) -> None:
    finding = answered(client)
    assert latest(client, finding) == 0
    first = review(client, finding, "confirmed", "A. Reviewer", based_on=0)
    assert first.status_code == 201
    seen = first.json()["latestReviewId"]
    assert seen > 0 and latest(client, finding) == seen
    # The second tab opened the finding before the first decision and still holds 0.
    stale = review(client, finding, "dismissed", "B. Reviewer", based_on=0)
    assert stale.status_code == 409
    assert "confirmed by A. Reviewer" in stale.json()["detail"]
    assert rows(finding) == 1 and latest(client, finding) == seen
    # The run detail and the findings list say the same current state and id.
    detail = client.get(f"/api/runs/{client.get('/api/findings').json()[0]['runId']}").json()["findings"][0]
    assert detail["review"]["verdict"] == "confirmed" and detail["latestReviewId"] == seen


def test_a_stale_tab_repeating_the_current_decision_is_not_a_conflict(client: TestClient) -> None:
    finding = answered(client)
    review(client, finding, "confirmed", "A. Reviewer", based_on=0)
    again = review(client, finding, "confirmed", "A. Reviewer", based_on=0)
    assert again.status_code == 200 and rows(finding) == 1


def test_a_cleared_review_is_a_base_like_any_other(client: TestClient) -> None:
    finding = answered(client)
    confirmed = review(client, finding, "confirmed", "A. Reviewer", based_on=0).json()["latestReviewId"]
    cleared = review(client, finding, "cleared", "A. Reviewer", based_on=confirmed)
    assert cleared.status_code == 201 and cleared.json()["review"] is None
    base = cleared.json()["latestReviewId"]
    assert base > confirmed
    # A tab that saw the confirmation, not the clearing, is stale; the message says the finding is unreviewed again.
    stale = review(client, finding, "dismissed", "B. Reviewer", based_on=confirmed)
    assert stale.status_code == 409 and "returned to unreviewed" in stale.json()["detail"]
    assert review(client, finding, "dismissed", "B. Reviewer", based_on=base).status_code == 201


def test_controls_a_current_base_and_an_omitted_one_are_recorded(client: TestClient) -> None:
    finding = answered(client)
    first = review(client, finding, "confirmed", "A. Reviewer", based_on=0).json()["latestReviewId"]
    assert review(client, finding, "dismissed", "A. Reviewer", based_on=first).status_code == 201
    # An API caller from before based_on existed is recorded whatever came before, as it always was.
    assert review(client, finding, "confirmed", "C. Caller", based_on=None).status_code == 201
    assert rows(finding) == 3
    assert review(client, finding, "confirmed", "C. Caller", based_on=-1).status_code == 422


def decide_at_once(finding: str, base: int, note: str, barrier: threading.Barrier, outcomes: list[str], verdict: ReviewVerdictName, reviewer: str) -> None:
    """One request of a racing pair: its own session, released together with the other by the barrier."""
    with db_module.SessionLocal() as session:
        barrier.wait()
        try:
            review_finding(session, finding, verdict, reviewer, note, based_on=base)
            outcomes.append("recorded")
        except Conflict:
            outcomes.append("refused")


def test_of_two_decisions_against_the_same_state_exactly_one_is_recorded(client: TestClient) -> None:
    """The check and the write share one write transaction: two requests racing from one base cannot both pass."""
    finding = answered(client)
    for round_ in range(12):
        outcomes: list[str] = []
        shared = (finding, latest(client, finding), f"round {round_}", threading.Barrier(2), outcomes)
        threads = [
            threading.Thread(target=decide_at_once, args=(*shared, verdict, reviewer))
            for verdict, reviewer in (("confirmed", "A. Reviewer"), ("dismissed", "B. Reviewer"))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert sorted(outcomes) == ["recorded", "refused"], (round_, outcomes)
        assert rows(finding) == round_ + 1


DECISIONS = st.sampled_from([("confirmed", None), ("dismissed", None), ("dismissed", "out of scope"), ("cleared", None)])


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(steps=st.lists(st.tuples(st.sampled_from(["A", "B"]), st.booleans(), DECISIONS), min_size=1, max_size=10))
def test_every_recorded_decision_was_made_against_the_state_it_replaced(client: TestClient, steps: list[tuple[str, bool, tuple[str, str | None]]]) -> None:
    """Two tabs act in any order, each refreshing or not first. A tab's decision is recorded only when the tab had seen
    the latest review or repeats it; a refusal writes nothing and hands the tab the current state. The fixture is shared
    by every example, so each continues from the review state the last one left: the finding is asked for once."""
    findings = client.get("/api/findings").json()
    finding = findings[0]["id"] if findings else answered(client)
    seen = {"A": latest(client, finding), "B": latest(client, finding)}
    for tab, refresh, (verdict, note) in steps:
        if refresh:
            seen[tab] = latest(client, finding)
        before_rows, before_id = rows(finding), latest(client, finding)
        current = next(f for f in client.get("/api/findings").json() if f["id"] == finding)["review"]
        reviewer = f"{tab}. Reviewer"
        repeats = (current is not None and (current["verdict"], current["reviewer"], current["note"]) == (verdict, reviewer, note)) or (
            current is None and verdict == "cleared"
        )
        response = review(client, finding, verdict, reviewer, based_on=seen[tab], note=note)
        if repeats:
            assert response.status_code == 200 and rows(finding) == before_rows
        elif seen[tab] != before_id:
            assert response.status_code == 409 and rows(finding) == before_rows and latest(client, finding) == before_id
        else:
            assert response.status_code == 201 and rows(finding) == before_rows + 1
        seen[tab] = latest(client, finding)


def test_a_review_that_cannot_take_the_write_lock_is_refused_as_busy_and_writes_nothing(client: TestClient) -> None:
    """Another writer holding the store past SQLite's five-second wait used to surface as a 500."""
    finding = answered(client)
    holder = sqlite3.connect(str(db_module.engine.url.database), isolation_level=None)
    try:
        holder.execute("BEGIN IMMEDIATE")
        busy = review(client, finding, "confirmed", "A. Reviewer", based_on=0)
        assert busy.status_code == 503 and "nothing was written" in busy.json()["detail"]
    finally:
        holder.rollback()
        holder.close()
    assert rows(finding) == 0
    assert review(client, finding, "confirmed", "A. Reviewer", based_on=0).status_code == 201
