"""A daily quota counts the row it limits on the row's own instant (stress test, 2026-10-30, time 2).

A run is stamped with `now`, read once in start_run for its identity and its created_at, before the write lock. The
daily counts in quotas.py read the clock again, inside the lock. A request that read `now` on day D and reached the
count after 00:00 UTC was counted against D+1, which does not hold its D stamp: it was counted against no day. A burst
queued behind a long write across midnight was admitted whole (6 of 6, 8 runs on a day capped at 3), and a single
request in the last milliseconds of a full day passed (8 of 100 trials). The refusal names midnight UTC, so anyone can
aim for it.

Each case here sets the two clocks apart, as a lock wait across midnight does: start_run's (the stamp) and quotas' (the
count). Nothing sleeps: the clocks are set, not waited for. The property: for any stamp and any later count, the runs
stamped on a UTC day never exceed the cap. Controls: both clocks on one day, and both after midnight.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config
from app.application import quotas, start_run
from app.db import SessionLocal
from app.models import Run, utcnow
from tests.support import upload_and_ask
from tests.test_quota_admission import _ask, _with_document, windows_lifted

pytestmark = pytest.mark.usefixtures(windows_lifted.__name__)


def _midnight() -> datetime:
    """The next 00:00 UTC: day D is today, D+1 tomorrow."""
    now = utcnow()
    return datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(days=1)


def _clocks(monkeypatch: pytest.MonkeyPatch, stamp: datetime, count: datetime) -> None:
    """The run is stamped at `stamp` (start_run's clock); the quotas count at `count` (quotas' clock)."""
    monkeypatch.setattr(start_run, "utcnow", lambda: stamp)
    monkeypatch.setattr(quotas, "utcnow", lambda: count)


def _stamped_on(day: datetime) -> int:
    of_day = (Run.workspace_id.isnot(None), Run.created_at >= day, Run.created_at < day + timedelta(days=1))
    with SessionLocal() as session:
        return session.scalar(select(func.count(Run.id)).where(*of_day)) or 0


def _ask_owner(client: TestClient, document_id: str, question: str) -> int:
    return client.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": question}).status_code


def test_a_run_stamped_before_midnight_and_counted_after_it_counts_against_its_own_day(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    first = upload_and_ask(client, "What notice period applies to termination for convenience?", with_guidance=False)
    monkeypatch.setattr(config.settings, "max_runs_per_day", 1)
    midnight = _midnight()
    _clocks(monkeypatch, stamp=midnight - timedelta(microseconds=1), count=midnight + timedelta(microseconds=100))
    refused = client.post("/api/runs", json={"documentId": first["document"]["id"], "guidanceId": None, "question": "Which law governs?"})
    assert refused.status_code == 429, "day D is full: a run stamped D is refused, wherever the count's clock has got to"
    # Midnight has passed while it waited: a retry is stamped D+1 and passes at once, so it is not told to wait a day.
    assert int(refused.headers["retry-after"]) <= 2
    assert _stamped_on(midnight - timedelta(days=1)) == 1


def test_a_burst_queued_across_midnight_takes_only_what_its_day_has_left(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The finder's case: cap 3, day D holds 2, six questions stamped just before midnight and counted just after."""
    first = upload_and_ask(client, "What notice period applies to termination for convenience?", with_guidance=False)
    document_id = first["document"]["id"]
    monkeypatch.setattr(config.settings, "max_runs_per_day", 3)
    midnight = _midnight()
    assert _ask_owner(client, document_id, "Which law governs?") == 202  # day D now holds 2
    _clocks(monkeypatch, stamp=midnight - timedelta(milliseconds=100), count=midnight + timedelta(milliseconds=100))
    codes = [_ask_owner(client, document_id, f"What notice does termination for convenience need, case {i}?") for i in range(6)]
    assert sorted(codes) == [202] + [429] * 5
    assert _stamped_on(midnight - timedelta(days=1)) == 3, "the cap of day D, not past it"
    assert _stamped_on(midnight) == 0


def test_a_public_workspace_s_daily_questions_count_on_the_run_s_own_day(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_max_runs_per_day", 1)
    visitor, document_id = _with_document(public)
    assert _ask(visitor, document_id, "What notice applies?") == 202
    midnight = _midnight()
    _clocks(monkeypatch, stamp=midnight - timedelta(microseconds=1), count=midnight + timedelta(microseconds=100))
    assert _ask(visitor, document_id, "Which law governs?") == 429


@pytest.mark.parametrize(
    ("stamp_s", "count_s"),
    [(-0.1, 0.1), (-0.000001, 0.0), (-0.000001, 30.0), (-5.0, 600.0), (0.0, 0.1), (-0.2, -0.1)],
)
def test_property_runs_stamped_on_a_day_never_pass_its_cap_whenever_the_count_is_made(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, stamp_s: float, count_s: float
) -> None:
    first = upload_and_ask(client, "What notice period applies to termination for convenience?", with_guidance=False)
    document_id = first["document"]["id"]
    cap = 2
    monkeypatch.setattr(config.settings, "max_runs_per_day", cap)
    midnight = _midnight()
    _clocks(monkeypatch, stamp=midnight + timedelta(seconds=stamp_s), count=midnight + timedelta(seconds=count_s))
    for i in range(4):
        _ask_owner(client, document_id, f"What notice does termination for convenience need, case {i}?")
    assert _stamped_on(midnight - timedelta(days=1)) <= cap
    assert _stamped_on(midnight) <= cap


def test_control_a_day_s_runs_do_not_count_against_the_day_before(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both clocks past midnight: D+1 has its whole budget, whatever D used."""
    first = upload_and_ask(client, "What notice period applies to termination for convenience?", with_guidance=False)
    monkeypatch.setattr(config.settings, "max_runs_per_day", 1)
    midnight = _midnight()
    _clocks(monkeypatch, stamp=midnight + timedelta(microseconds=50), count=midnight + timedelta(microseconds=100))
    assert _ask_owner(client, first["document"]["id"], "Which law governs?") == 202
    assert _ask_owner(client, first["document"]["id"], "Who may assign?") == 429


def test_control_a_run_stamped_after_midnight_is_not_counted_against_the_day_before(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A count is of its day exactly: a run stamped D+1 that reached the lock first does not use D's budget."""
    first = upload_and_ask(client, "What notice period applies to termination for convenience?", with_guidance=False)
    document_id = first["document"]["id"]
    monkeypatch.setattr(config.settings, "max_runs_per_day", 2)
    midnight = _midnight()
    _clocks(monkeypatch, stamp=midnight + timedelta(microseconds=10), count=midnight + timedelta(microseconds=20))
    assert _ask_owner(client, document_id, "Which law governs?") == 202  # D+1's first
    _clocks(monkeypatch, stamp=midnight - timedelta(microseconds=10), count=midnight + timedelta(microseconds=30))
    assert _ask_owner(client, document_id, "Who may assign?") == 202, "day D holds one run of its two"
    assert _ask_owner(client, document_id, "What is the term?") == 429
    assert _stamped_on(midnight - timedelta(days=1)) == 2 and _stamped_on(midnight) == 1


def test_a_refusal_whose_day_has_not_turned_waits_for_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    moment = datetime(2026, 10, 30, 23, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(quotas, "utcnow", lambda: moment)
    assert quotas.seconds_to_tomorrow(moment) == 3601
    assert quotas.seconds_to_tomorrow(moment - timedelta(days=1)) == 1, "a day already over: try again at once"
