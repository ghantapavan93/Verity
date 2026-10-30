"""A run is live while a worker of its process is answering it, not while its process merely exists (stress test,
2026-10-30: ops 1, concurrency 2 and 3).

Recovery left alone every run whose stage row named a live process on this host, however old. A run whose own failure
could not be written (a write lock held past the busy wait, a full disk) therefore stayed in progress for the life of
the API: it kept its question's fingerprint, one of its workspace's two slots and one of the eight public ones, and its
workspace's deletion. A run born but not yet given a stage row had no owner at all, so a crash left it open 41 minutes,
and a live queued one was declared dead with a false reason. And two readers recovering one stale run raced: the loser
hit the immutability trigger and answered 500, readers of unrelated runs included.

Now a run names its process from birth (runs.owner), a process keeps the ids of the runs its workers hold
(recover_runs.run_started / run_ended), and one conditional write ends a run: recovery fails a run of this process that
no worker holds, at once; leaves a held one alone however long it waits; and leaves quietly when another writer ended
the run first.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.application import recover_runs
from app.application.recover_runs import recover_interrupted_runs
from app.db import SessionLocal
from app.errors import Busy
from app.models import Run, RunStage, utcnow
from tests.support import CONTRACT, upload_and_ask

QUESTION = "What notice period applies to termination for convenience?"


def _upload(client: TestClient) -> str:
    response = client.post("/api/documents", files={"file": ("contract.txt", CONTRACT.encode("utf-8"), "text/plain")})
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


def _ask(client: TestClient, document_id: str, question: str = QUESTION) -> Any:  # noqa: ANN401
    return client.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": question})


@contextmanager
def store_unwritable_from(commit: int) -> Iterator[None]:
    """Every commit a run's worker makes from its ``commit``-th on fails, as when another writer holds the store's lock
    past the busy wait or the disk is full: the run's failure cannot be written either."""
    made = [0]
    real = Session.commit

    def commit_or_fail(self: Session) -> None:
        if threading.current_thread().name.startswith("run"):
            made[0] += 1
            if made[0] >= commit:
                self.rollback()
                raise OperationalError("COMMIT", {}, Exception("database is locked"))
        real(self)

    Session.commit = commit_or_fail  # type: ignore[method-assign]
    try:
        yield
    finally:
        Session.commit = real  # type: ignore[method-assign]


def _stage(run_id: str) -> str:
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        assert run is not None
        return run.stage


# ---------------------------------------------------------------------------- a run whose own ending was not written


@pytest.mark.parametrize("commit", range(1, 9))
def test_a_run_whose_worker_could_not_write_its_end_is_failed_at_the_next_read(client: TestClient, monkeypatch: pytest.MonkeyPatch, commit: int) -> None:
    # Every point of the worker's writes, from its first stage row to its last: once the store takes writes again, the
    # next read ends the run, and the same question can be asked again.
    document_id = _upload(client)
    client.provider.fail_always = True  # type: ignore[attr-defined]
    with store_unwritable_from(commit):
        started = _ask(client, document_id)
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    read = client.get(f"/api/runs/{run_id}").json()
    assert read["stage"] == "failed", f"still {read['stage']} with no worker answering it"
    client.provider.fail_always = False  # type: ignore[attr-defined]
    again = _ask(client, document_id)
    assert again.status_code == 202 and again.json()["id"] != run_id, "the question is free to be asked again"


def test_a_stuck_public_run_gives_back_its_workspace_s_slot(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config
    from tests.test_quota_admission import _ask as ask
    from tests.test_quota_admission import _with_document

    monkeypatch.setattr(config.settings, "anonymous_max_runs_in_flight", 1)
    visitor, document_id = _with_document(public)
    public.provider.fail_always = True  # type: ignore[attr-defined]
    with store_unwritable_from(1):
        assert ask(visitor, document_id, "What notice applies?") == 202
    public.provider.fail_always = False  # type: ignore[attr-defined]
    assert ask(visitor, document_id, "Which law governs?") == 202, "the stuck run held the workspace's one slot"


def test_a_worker_that_raises_never_reaches_the_server_as_an_unhandled_error(client: TestClient) -> None:
    # The request answers, and the run ends at the next read; "Exception in ASGI application" told nobody which run.
    document_id = _upload(client)
    client.provider.fail_always = True  # type: ignore[attr-defined]
    with store_unwritable_from(1):
        assert _ask(client, document_id).status_code == 202


# ---------------------------------------------------------------------------- a live run is never declared dead


def test_control_a_run_on_the_model_longer_than_any_window_is_left_alone(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = _upload(client)
    entered, release = threading.Event(), threading.Event()
    real = client.provider.generate_json

    def slow(system: str, user: str, schema: dict[str, Any]) -> Any:  # noqa: ANN401
        entered.set()
        release.wait(20)
        return real(system, user, schema)

    client.provider.generate_json = slow  # type: ignore[method-assign]
    answers: list[Any] = []
    asking = threading.Thread(target=lambda: answers.append(_ask(client, document_id)))
    asking.start()
    try:
        assert entered.wait(10)
        with SessionLocal() as session:
            run_id = session.query(Run.id).filter(Run.stage.notin_(("complete", "failed", "unresolved"))).scalar()
            assert recover_interrupted_runs(session, stale_after_s=0) == 0, "a run its worker holds is live, whatever its age"
        assert _stage(str(run_id)) not in ("failed",)
    finally:
        release.set()
        asking.join(20)
    assert answers and answers[0].status_code == 202 and _stage(str(run_id)) == "complete"


def test_control_a_run_born_and_waiting_for_its_worker_past_any_window_stays_open(client: TestClient) -> None:
    # A queued run has no stage row yet; it is this process's from its birth, and live while it is held for a worker.
    from app.application.start_run import start_run

    document_id = _upload(client)
    with SessionLocal() as session:
        run = start_run(session, document_id, None, QUESTION, client.provider, workspace="open").run
        run_id = run.id
        session.execute(text("UPDATE runs SET created_at = :then WHERE id = :id"), {"then": utcnow() - timedelta(minutes=42), "id": run_id})
        session.commit()
        assert recover_interrupted_runs(session) == 0
    assert _stage(run_id) == "reading"
    recover_runs.run_ended(run_id)  # its worker is gone without ending it: now it is not live
    with SessionLocal() as session:
        assert recover_interrupted_runs(session) == 1
    read = client.get(f"/api/runs/{run_id}").json()
    assert read["stage"] == "failed" and "stopped" in read["error"] and "42 min" not in read["error"]


def _dead_identity() -> str:
    """The identity of a process on this host that has ended: a child started for the purpose and left to exit."""
    made = subprocess.run(
        [sys.executable, "-c", "from app.runs.owner import this_process; print(this_process().render())"], capture_output=True, text=True, check=True
    )
    return made.stdout.strip()


def test_a_run_born_in_a_process_that_died_before_its_first_stage_fails_at_once(client: TestClient) -> None:
    from app.application.start_run import start_run

    document_id = _upload(client)
    with SessionLocal() as session:
        run_id = start_run(session, document_id, None, QUESTION, client.provider, workspace="open").run.id
        session.execute(text("UPDATE runs SET owner = :dead WHERE id = :id"), {"dead": _dead_identity(), "id": run_id})
        session.commit()
    recover_runs.run_ended(run_id)
    with SessionLocal() as session:
        assert recover_interrupted_runs(session) == 1, "not 41 minutes later: its process is provably gone"
    assert _ask(client, document_id).status_code == 202


def test_every_run_names_its_process_from_its_birth(client: TestClient) -> None:
    from app.runs.owner import this_process

    result = upload_and_ask(client, QUESTION, with_guidance=False)
    with SessionLocal() as session:
        run = session.get(Run, result["run_id"])
        assert run is not None and run.owner == this_process().render()
    assert not recover_runs.is_working(result["run_id"]), "a run its worker finished is no longer held"


def test_control_a_run_from_before_owners_waits_for_staleness(client: TestClient) -> None:
    from tests.test_run_endings import _run_in_flight

    run_id = _run_in_flight(client, "Is there an arbitration clause?")  # no owner, no stage row: written by older code
    with SessionLocal() as session:
        assert recover_interrupted_runs(session) == 0
        assert recover_interrupted_runs(session, stale_after_s=0) == 1
    assert _stage(run_id) == "failed"


# ---------------------------------------------------------------------------- one writer ends a run


def _stale_runs(client: TestClient, count: int) -> list[str]:
    """Runs left open by a process that has ended, each with a closed and an open stage row, as a killed batch leaves."""
    from tests.test_run_endings import _run_in_flight

    dead = _dead_identity()
    first = _run_in_flight(client, "Is there clause number 0?")
    ids = [first]
    with SessionLocal() as session:
        model = session.get(Run, first)
        assert model is not None
        for n in range(1, count):
            more = Run(
                document_id=model.document_id,
                question=f"Is there clause number {n}?",
                stage="checking",
                provider=model.provider,
                model=model.model,
                prompt_version=model.prompt_version,
                prompt_hash=model.prompt_hash,
                document_sha256=model.document_sha256,
                fingerprint=f"stale-{n}",
            )
            session.add(more)
            session.flush()
            ids.append(more.id)
        for run_id in ids:
            session.add(RunStage(run_id=run_id, stage="reading", status="ok", owner=dead, at=utcnow(), completed_at=utcnow()))
            session.add(RunStage(run_id=run_id, stage="checking", status="running", owner=dead, at=utcnow()))
        session.commit()
    return ids


def _released_together(calls: list[Callable[[], int]]) -> list[int]:
    go = threading.Barrier(len(calls))
    codes: list[int] = []

    def one(call: Callable[[], int]) -> None:
        go.wait()
        try:
            codes.append(call())
        except Exception:  # noqa: BLE001 - a server error raised through the test client is a 500
            codes.append(500)

    threads = [threading.Thread(target=one, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    return codes


@pytest.mark.parametrize("stale", [1, 5])
def test_readers_recovering_the_same_runs_together_all_answer_and_each_run_ends_once(client: TestClient, stale: int) -> None:
    ids = _stale_runs(client, stale)
    other = upload_and_ask(client, QUESTION, with_guidance=False)["run_id"]  # a finished run nobody is recovering
    paths = [f"/api/runs/{ids[0]}", f"/api/runs/{other}", f"/api/runs/{other}/detail", "/api/runs", f"/api/runs/{ids[-1]}", f"/api/runs/{ids[0]}"]
    codes = _released_together([lambda p=path: client.get(p).status_code for path in paths])
    assert codes == [200] * len(paths), codes
    with SessionLocal() as session:
        for run_id in ids:
            stages = session.query(RunStage).filter_by(run_id=run_id).order_by(RunStage.id).all()
            assert [s.stage for s in stages].count("failed") == 1, [s.stage for s in stages]
            closed, failed = stages[-2], stages[-1]
            assert closed.completed_at is not None and closed.completed_at <= failed.at, "the stage was closed once, before the run ended"


def test_a_run_another_writer_ended_since_the_scan_is_left_as_it_was_ended(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    (run_id,) = _stale_runs(client, 1)
    real = recover_runs._end_as_failed

    def worker_ended_it_first(session: Session, run: Run, latest: RunStage | None, message: str) -> bool:
        with SessionLocal() as other:
            other.execute(text("UPDATE runs SET stage = 'failed', reason = 'provider_error', error = 'the worker ended it' WHERE id = :id"), {"id": run_id})
            other.commit()
        return real(session, run, latest, message)

    monkeypatch.setattr(recover_runs, "_end_as_failed", worker_ended_it_first)
    with SessionLocal() as session:
        assert recover_interrupted_runs(session, stale_after_s=0) == 0
    assert client.get(f"/api/runs/{run_id}").json()["error"] == "the worker ended it"


def test_a_store_that_cannot_take_the_write_yet_leaves_the_run_for_the_next_read(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    (run_id,) = _stale_runs(client, 1)

    @contextmanager
    def busy(session: Session) -> Iterator[None]:
        raise Busy("The store is busy with another change, so nothing was written. Try again in a moment.", retry_after=5)
        yield

    with monkeypatch.context() as patched:
        patched.setattr(recover_runs, "write_locked", busy)
        read = client.get(f"/api/runs/{run_id}")
        assert read.status_code == 200 and read.json()["stage"] == "checking", "the read is answered; the run waits"
    assert client.get(f"/api/runs/{run_id}").json()["stage"] == "failed"
