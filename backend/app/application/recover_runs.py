"""Use case: no run may stay "in progress" forever, and no live run may be declared dead.

A run is interrupted when its current stage has made no progress for longer than the longest
thing a stage can legitimately do (the model call, bounded by its timeout) plus a margin. Such a
run is recorded as failed with the reason, so the same question can be asked again (a failed run
does not block its fingerprint) and the record says what happened. The rule is by staleness,
not by process: the API, the golden runner and a batch runner all write runs into the same
database, and a restart of one must not fail the others' live work. The exceptions are exact
rather than assumed. A run names the process that made it from its birth (runs.owner), and each
stage row the process that opened it (runs.owner module); and each process keeps the ids of the
runs its workers hold (run_started, run_ended). Then:

- a run whose process provably no longer exists on this host is failed at once;
- a run of this process that a worker holds is live, however long it waits for the model;
- a run of this process that no worker holds is failed at once: its worker ended without
  recording how (its own failure could not be written: a write lock past the busy wait, a full
  disk). Until 2026-10-30 such a run was left alone because its process was alive, so it held
  its question, its workspace's slots and its workspace's deletion for the life of the API
  (stress test, ops 1); and a run born but not yet given a stage row had no owner at all, so a
  crash left it open for the whole window and a live queued one was declared dead (concurrency 2);
- another live process's run on this host is left to that process; a run of another host, or one
  written before owners, waits for staleness;
- a public workspace's run is ended, whoever holds it, once it has been held longer than any run can wait in the
  public queue: every slot ahead of it at its longest, and its own (queue_ceiling_seconds). Held was live however long,
  so a worker that never came back held its run for the life of the API (stress test, 2026-10-30, time 1). The age is
  the monotonic time since it was held, never its wall-clock stamps, which a clock step can age by days. The owner's
  store has no bound on its queue, so no ceiling: its runs end at a read once no worker holds them.

A run is ended by one conditional write (_end_as_failed): under the write lock, only if it is
still as it was seen. Two readers recovering one run raced, and the loser's write hit the
immutability trigger and answered 500, readers of unrelated runs included (concurrency 3). It
runs at startup, whenever runs are read, before a question is asked, and at each retention pass in the public store
(where a visitor who left reads nothing again); a store that cannot take the write yet leaves the run for the next read
and never fails the read.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import write_locked
from ..errors import Busy
from ..models import Run, RunStage, as_utc, utcnow
from ..runs.events import TERMINAL, StageEvent, bus
from ..runs.owner import ProcessIdentity, owner_is_alive_here, owner_is_gone, this_process
from .workspace import is_public

log = logging.getLogger(__name__)

MAX_MODEL_CALLS_PER_RUN = 4  # analysis.service: two validation rounds, each with one transport retry
STALE_MARGIN_S = 60.0

# The runs this process's workers hold, with the monotonic instant each was held: entered when a run is born
# (application/start_run.py, before its row commits, so no read ever sees a run of this process that is not yet held),
# left when its worker ends however it ends (api/runs.py). A process that starts runs and then exits (a batch, the
# goldens) need not leave them: its runs are then a gone process's.
_held: dict[str, float] = {}
_held_lock = threading.Lock()
_monotonic = time.monotonic


def run_started(run_id: str) -> None:
    with _held_lock:
        _held[run_id] = _monotonic()


def run_ended(run_id: str) -> None:
    with _held_lock:
        _held.pop(run_id, None)


def is_working(run_id: str) -> bool:
    with _held_lock:
        return run_id in _held


def _held_for(run_id: str) -> float | None:
    """How long this process has held the run, on the monotonic clock; None when it does not hold it."""
    with _held_lock:
        since = _held.get(run_id)
    return None if since is None else _monotonic() - since


def stale_after_seconds() -> float:
    # A legitimate run can span four model calls without writing progress: one transport retry and one
    # corrected retry, each up to the model timeout. Each call is now two requests (a one-token clean start, then the
    # answer: providers.ollama), but the first computes one token and the second waits on the same loaded model.
    # Declaring it dead earlier freed its fingerprint while it was alive (independent review, 2026-09-29). The window is
    # the worst legitimate case plus a minute.
    return settings.model_timeout_s * MAX_MODEL_CALLS_PER_RUN + STALE_MARGIN_S


def queue_ceiling_seconds() -> float:
    """The longest a public workspace's run can legitimately be held: every slot of the public queue ahead of it
    (settings.public_max_runs_in_flight) at its longest, and its own. A run held longer is waiting on nothing that will
    come back."""
    return (settings.public_max_runs_in_flight + 1) * stale_after_seconds()


def _is_this_process(owner: str | None) -> bool:
    identity = ProcessIdentity.parse(owner or "")
    me = this_process()
    return (
        identity is not None
        and identity.host == me.host
        and identity.pid == me.pid
        and (identity.started == me.started or not identity.started or not me.started)
    )


def recover_interrupted_runs(session: Session, stale_after_s: float | None = None) -> int:
    """Mark runs whose current stage started longer ago than ``stale_after_s`` as failed, and runs that provably have no
    one answering them at once. Returns how many."""
    limit = timedelta(seconds=stale_after_seconds() if stale_after_s is None else stale_after_s)
    now = utcnow()
    recovered = 0
    open_runs = session.query(Run).filter(Run.stage.notin_(sorted(TERMINAL))).all()
    if not open_runs:
        return 0
    # Every open run's latest stage row in one query: this runs on every read of a run, and asked once per open run, so
    # a queue of thirty made every poll of every page thirty-one queries (backend audit, 2026-10-19).
    latest_ids = select(func.max(RunStage.id)).where(RunStage.run_id.in_([run.id for run in open_runs])).group_by(RunStage.run_id)
    latest_of = {row.run_id: row for row in session.query(RunStage).filter(RunStage.id.in_(latest_ids))}
    for run in open_runs:
        latest = latest_of.get(run.id)
        owner = latest.owner if latest is not None else run.owner
        started = as_utc(latest.at) if latest is not None else as_utc(run.created_at)
        gone = owner_is_gone(owner)
        unheld = not gone and owner_is_alive_here(owner) and _is_this_process(owner) and not is_working(run.id)
        held_for = _held_for(run.id)
        overdue = not gone and is_public(run.workspace_id) and held_for is not None and held_for >= queue_ceiling_seconds()
        if not gone and not unheld and not overdue:
            if now - started < limit:
                continue
            if owner_is_alive_here(owner):
                # The process is here and alive, and (if it is this one) a worker holds the run: it is queued for the
                # model or on it. Its own handlers end it; the staleness window is for processes that cannot be seen.
                continue
        minutes = int((now - started).total_seconds() // 60)
        if gone:
            # The process's identity goes to the log below, never into what a reader sees (journey audit, 2026-10-09).
            message = f"Interrupted: the server process running the {run.stage} stage stopped. Ask the question again."
        elif overdue:
            message = (
                f"Interrupted: no answer after {int((held_for or 0) // 60)} min, longer than any question waits in this demo's queue; "
                "the work on it was stopped. Ask the question again."
            )
        elif unheld:
            message = (
                f"Interrupted: the work on this question stopped during the {run.stage} stage before it could record how it ended. Ask the question again."
            )
        else:
            message = (
                f"Interrupted: no progress for {minutes} min after the {run.stage} stage started; the process running it "
                "stopped or restarted. Ask the question again."
            )
        try:
            ended = _end_as_failed(session, run, latest, message)
        except (Busy, OperationalError) as error:
            # The store cannot take the write yet: the read is still answered, and the next read tries again.
            log.warning("run_id=%s left open for the next read: %s", run.id, type(error).__name__)
            continue
        if not ended:
            continue  # another writer ended it, or it moved on, since it was read
        log.warning("run_id=%s recovered_as=failed reason=internal_error stale_minutes=%d owner=%s", run.id, minutes, owner)
        bus.publish(StageEvent(run.id, "failed", message))  # an open stream to this run ends now, not at the next heartbeat
        recovered += 1
    if recovered:
        session.expire_all()  # the runs and stage rows this session loaded were written past it
    return recovered


def _end_as_failed(session: Session, run: Run, latest: RunStage | None, message: str) -> bool:
    """End the run as failed, only if it is still as it was seen: the same stage and the same latest stage row, read
    again under the write lock. True when this call ended it; False when another writer ended it, or it moved on, in the
    meantime, and then nothing is written. The statements go in the order the immutability triggers allow: the open
    stage row is closed while the run is not yet terminal, then the run, then the failed row is added."""
    seen_stage, seen_latest = run.stage, latest.id if latest is not None else None
    with write_locked(session):
        stage = session.execute(select(Run.stage).where(Run.id == run.id)).scalar()
        latest_now = session.execute(select(func.max(RunStage.id)).where(RunStage.run_id == run.id)).scalar()
        if stage != seen_stage or stage in TERMINAL or latest_now != seen_latest:
            return False
        now = utcnow()
        if latest is not None and latest.completed_at is None:
            started: datetime = as_utc(latest.at)
            session.execute(
                update(RunStage)
                .where(RunStage.id == latest.id, RunStage.completed_at.is_(None))
                .values(completed_at=now, duration_ms=round((now - started).total_seconds() * 1000, 1), status="failed", error_code="internal_error")
            )
        session.execute(
            update(Run).where(Run.id == run.id, Run.stage == seen_stage).values(stage="failed", reason="internal_error", error=message, finished_at=now)
        )
        session.execute(
            insert(RunStage).values(
                run_id=run.id, stage="failed", at=now, detail=message, completed_at=now, duration_ms=0.0, status="failed", error_code="internal_error"
            )
        )
    return True
