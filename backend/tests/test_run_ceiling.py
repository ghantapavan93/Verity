"""No run stays open forever, whoever holds it, and nobody need read it for it to end (stress test, 2026-10-30, time 1).

After the liveness fix (test_run_liveness.py) a run its worker could not end was failed at the next read of runs. Two
ways remained for a run to stay open:

- in the public store nobody may read it again: a visitor who leaves reads nothing, and retention skipped a workspace
  with a run in progress every hour, so the run kept the visitor's data, and a slot of the public queue, until a restart;
- a run its process still holds is live however long it waits (the 2026-10-01 rule): a worker thread that never comes
  back (a hang the model call's deadline does not cover) held it for the life of the API.

The retention pass now recovers runs before it decides what is in progress, and a public workspace's run held past the
longest a run can wait in the public queue (every slot of it ahead, each at its longest, plus its own) is ended
whoever holds it. That age is measured on the monotonic clock from when the run was held, so no clock step can make a
live run look old. The owner's store has no bound on its queue, so it has no such ceiling: its runs end at a read.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import config
from app import db as db_module
from app.application import recover_runs
from app.application.recover_runs import queue_ceiling_seconds, recover_interrupted_runs, stale_after_seconds
from app.application.retention import purge_expired_workspaces
from app.application.start_run import start_run
from app.db import SessionLocal
from app.models import Run, utcnow
from tests.test_quota_admission import _ask, _with_document
from tests.test_retention import end
from tests.test_run_liveness import QUESTION, _stage, _upload, store_unwritable_from


class Monotonic:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.now = 1_000.0
        monkeypatch.setattr(recover_runs, "_monotonic", lambda: self.now)


@pytest.fixture
def held_public_run(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, Monotonic]]:
    """A public visitor's run, held for its worker, which never starts: a worker that does not come back."""
    clock = Monotonic(monkeypatch)
    visitor, document_id = _with_document(public)
    from app.api.access import workspace_for

    with SessionLocal() as session:
        run = start_run(session, document_id, None, QUESTION, public.provider, workspace=workspace_for(visitor.subject)).run
        run_id = run.id
    yield run_id, clock
    recover_runs.run_ended(run_id)


def test_a_stuck_run_of_a_visitor_who_never_returns_is_ended_by_the_retention_pass(public: TestClient) -> None:
    visitor, document_id = _with_document(public)
    public.provider.fail_always = True  # type: ignore[attr-defined]
    with store_unwritable_from(1):
        assert _ask(visitor, document_id, "What notice applies?") == 202
    public.provider.fail_always = False  # type: ignore[attr-defined]
    with SessionLocal() as session:
        assert session.query(Run).filter(Run.stage.notin_(("complete", "failed", "unresolved"))).count() == 1, "stuck, and nobody reads it"
    workspace = end(visitor)
    report = purge_expired_workspaces(db_module.engine, gap_s=0.0)
    assert report.workspaces == [workspace] and not report.skipped_in_progress


def test_a_held_public_run_past_the_queue_s_longest_wait_is_ended_whoever_holds_it(held_public_run: tuple[str, Monotonic]) -> None:
    run_id, clock = held_public_run
    clock.now += queue_ceiling_seconds() - 1
    with SessionLocal() as session:
        assert recover_interrupted_runs(session) == 0, "control: inside the longest wait the queue allows, it is live"
    clock.now += 2
    with SessionLocal() as session:
        assert recover_interrupted_runs(session) == 1
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        assert run is not None and run.stage == "failed" and run.reason == "internal_error"
        assert run.error is not None and "Ask the question again" in run.error


def test_the_ceiling_is_the_whole_public_queue_ahead_at_its_longest_plus_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "public_max_runs_in_flight", 8)
    assert queue_ceiling_seconds() == 9 * stale_after_seconds()


def test_control_a_clock_step_does_not_age_a_held_run(held_public_run: tuple[str, Monotonic]) -> None:
    """The wall clock jumping 30 days makes the run's stamps old; the run has been held a second."""
    run_id, _clock = held_public_run
    with SessionLocal() as session:
        session.execute(text("UPDATE runs SET created_at = :then WHERE id = :id"), {"then": utcnow() - timedelta(days=30), "id": run_id})
        session.commit()
        assert recover_interrupted_runs(session) == 0
    assert _stage(run_id) == "reading"


def test_control_an_owner_store_run_has_no_such_ceiling(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The owner's workspace has no bound on its queue, so no wait is too long to be real: it ends at a read once no
    worker holds it (test_run_liveness.py)."""
    clock = Monotonic(monkeypatch)
    document_id = _upload(client)
    with SessionLocal() as session:
        run_id = start_run(session, document_id, None, QUESTION, client.provider, workspace="open").run.id
    try:
        clock.now += 100 * queue_ceiling_seconds()
        with SessionLocal() as session:
            assert recover_interrupted_runs(session) == 0
        assert _stage(run_id) == "reading"
    finally:
        recover_runs.run_ended(run_id)
