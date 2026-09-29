"""Use case: no run may stay "in progress" forever, and no live run may be declared dead.

A run is interrupted when its current stage has made no progress for longer than the longest
thing a stage can legitimately do (the model call, bounded by its timeout) plus a margin. Such a
run is recorded as failed with the reason, so the same question can be asked again (a failed run
does not block its fingerprint) and the record says what happened. The rule is by staleness,
not by process: the API, the golden runner and a batch runner all write runs into the same
database, and a restart of one must not fail the others' live work. It runs at startup and
whenever runs are read.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Run, RunStage, as_utc, utcnow
from ..runs.events import TERMINAL

log = logging.getLogger(__name__)

STALE_MARGIN_S = 60.0


def stale_after_seconds() -> float:
    return settings.model_timeout_s + STALE_MARGIN_S


def recover_interrupted_runs(session: Session, stale_after_s: float | None = None) -> int:
    """Mark runs whose current stage started longer ago than ``stale_after_s`` as failed. Returns how many."""
    limit = timedelta(seconds=stale_after_seconds() if stale_after_s is None else stale_after_s)
    now = utcnow()
    recovered = 0
    for run in session.query(Run).filter(Run.stage.notin_(sorted(TERMINAL))).all():
        latest = session.query(RunStage).filter_by(run_id=run.id).order_by(RunStage.id.desc()).first()
        started = as_utc(latest.at) if latest is not None else as_utc(run.created_at)
        if now - started < limit:
            continue
        minutes = int((now - started).total_seconds() // 60)
        message = (
            f"Interrupted: no progress for {minutes} min after the {run.stage} stage started; the process running it "
            "stopped or restarted. Ask the question again."
        )
        if latest is not None and latest.completed_at is None:
            latest.completed_at = now
            latest.duration_ms = round((now - started).total_seconds() * 1000, 1)
            latest.status = "failed"
            latest.error_code = "internal_error"
        session.commit()  # the stage row is closed before the run turns terminal; after that it cannot be touched
        run.stage = "failed"
        run.reason = "internal_error"
        run.error = message
        run.finished_at = now
        session.add(
            RunStage(run_id=run.id, stage="failed", at=now, detail=message, completed_at=now, duration_ms=0.0, status="failed", error_code="internal_error")
        )
        session.commit()
        log.warning("run_id=%s recovered_as=failed reason=internal_error stale_minutes=%d", run.id, minutes)
        recovered += 1
    return recovered
