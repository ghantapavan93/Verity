"""Quotas: how many rows of a kind a workspace, or every reader together, may add; enforced where the row is written.

A quota is counted, and the row it limits is written, in one transaction no concurrent request can interleave: `admit`,
under the store's write lock (db.write_locked). A count made anywhere else is advice. Until 2026-10-13 every quota here
was counted before its write and never again: a workspace's documents before its upload was read, the grant written
seconds later, so sixteen uploads at once were all held against a cap of ten; and the day's runs before the run's insert,
so eight of ten starts released together got past a ceiling of three (war room F-13 / R10). That ceiling is the spend
stop for a paid GPU.

    quota                                          counts                                  written by
    rows a public workspace adds once it has ended whether it has ended (none may be)      ingest_document, start_run,
                                                                                           save_guidance
    documents a public workspace holds             its grants                              ingest_document
    uploads in a UTC day, every public workspace   public grants made today                ingest_document
    questions a public workspace asks in a day     its runs made today                     start_run
    new runs in a UTC day, every reader            runs with a workspace made today        start_run

The same definitions give the early answers that spare work: api/access.admit_upload refuses before a file is read,
api/model.wake wakes no model for a question that would be refused. Those decide nothing; the count in `admit` does.
The per-address and per-reader windows (api/access.SlidingWindow) and the wake-up budget (wake_model) are not here: they
live in this process's memory and record an event in the same step, under one lock, that checks it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ..config import settings
from ..db import write_locked
from ..errors import AccessRequired, Busy, TooManyRequests, WorkbenchError
from ..models import TERMINAL_STAGES, DocumentAccess, Run, VisitorWorkspace, as_utc, utcnow
from .workspace import PUBLIC_PREFIX, is_public


@dataclass(frozen=True)
class Quota:
    """At most `limit` of the rows `count` counts; `refusal` is what a request past it is told."""

    limit: int
    count: Callable[[Session], int]
    refusal: Callable[[], WorkbenchError]


def day_start() -> datetime:
    """The start of the current UTC day: every daily quota resets here."""
    now = utcnow()
    return datetime(now.year, now.month, now.day, tzinfo=UTC)


def seconds_to_tomorrow() -> int:
    return int((day_start() + timedelta(days=1) - utcnow()).total_seconds()) + 1


def _grants(session: Session, *where: ColumnElement[bool]) -> int:
    return session.scalar(select(func.count()).select_from(DocumentAccess).where(*where)) or 0


def _runs(session: Session, *where: ColumnElement[bool]) -> int:
    return session.scalar(select(func.count(Run.id)).where(*where)) or 0


def _ended(session: Session, workspace: str) -> int:
    """1 when the public workspace is no longer registered or has ended, 0 while it is open: read inside the write lock,
    a fresh read of the store, never an object this session loaded earlier."""
    expires = session.scalar(select(VisitorWorkspace.expires_at).where(VisitorWorkspace.workspace_id == workspace))
    return 1 if expires is None or as_utc(expires) <= utcnow() else 0


def workspace_open(workspace: str | None) -> tuple[Quota, ...]:
    """A public workspace takes a row only while it is registered and has not ended: a quota of one ended workspace,
    which an open one never reaches. Counted under the write lock with the rest, the lock retention deletes under
    (application/retention.py), so a request let in before the purge cannot write after it: an upload read while its
    workspace was purged wrote its grant, document and file afterwards, into a workspace no longer listed, and nothing
    would ever delete them (war room W5 p6). Rows that hang from a run or a document (findings, reviews, memos) cannot
    outlive theirs: the store enforces the keys."""
    if not is_public(workspace):
        return ()
    assert workspace is not None
    return (
        Quota(
            1,
            lambda session: _ended(session, workspace),
            lambda: AccessRequired("This visit has ended and what it added has been deleted, so nothing was added. Reload the page to start again."),
        ),
    )


def document_quotas(workspace: str | None) -> tuple[Quota, ...]:
    """What a new grant (a document the workspace holds) is counted against: a public workspace's being open, its own
    bound, then every public workspace's uploads today. Other workspaces hold what they upload without a bound."""
    if not is_public(workspace):
        return ()
    held = settings.anonymous_max_documents
    return (
        *workspace_open(workspace),
        Quota(
            held,
            lambda session: _grants(session, DocumentAccess.workspace_id == workspace),
            lambda: TooManyRequests(f"This demo workspace already holds {held} contracts, its limit. Ask about one of them.", retry_after=3600),
        ),
        Quota(
            settings.anonymous_max_uploads_per_day,
            lambda session: _grants(session, DocumentAccess.workspace_id.like(f"{PUBLIC_PREFIX}%"), DocumentAccess.created_at >= day_start()),
            lambda: TooManyRequests("The demo has taken all the uploads it takes in a day. Try again tomorrow (UTC).", retry_after=seconds_to_tomorrow()),
        ),
    )


def run_quotas(workspace: str | None) -> tuple[Quota, ...]:
    """What a new run is counted against: a public workspace's being open and its questions today, then every reader's
    new runs today (settings.max_runs_per_day; 0 is no ceiling). The project's own runs (no workspace: goldens,
    batches) are neither bounded nor counted."""
    if workspace is None:
        return ()
    quotas: list[Quota] = [*workspace_open(workspace)]
    if is_public(workspace):
        # Questions still being answered, first: the model answers one call at a time, first come first served
        # (providers.admission), so one visitor's queue of thirty was every other visitor's ten-minute wait (security
        # review, 2026-10-14). The daily count below bounds the spend; this bounds the queue.
        in_flight = settings.anonymous_max_runs_in_flight
        quotas.append(
            Quota(
                in_flight,
                lambda session: _runs(session, Run.workspace_id == workspace, Run.stage.notin_(TERMINAL_STAGES)),
                lambda: TooManyRequests(
                    f"This demo workspace has {in_flight} questions being answered. Ask the next one when an answer arrives.", retry_after=30
                ),
            )
        )
        # Every visitor's together: the per-workspace bound above still let thirty visitors queue sixty questions, the
        # last of them half an hour from an answer, with nothing to say so (backend audit, 2026-10-19). Past the bound a
        # question is refused at once and says why; a retry passes when an answer arrives.
        waiting = settings.public_max_runs_in_flight
        quotas.append(
            Quota(
                waiting,
                lambda session: _runs(session, Run.workspace_id.like(f"{PUBLIC_PREFIX}%"), Run.stage.notin_(TERMINAL_STAGES)),
                lambda: Busy(
                    f"{waiting} visitors' questions are being answered, the most this demo queues: the model answers one at a time. "
                    "Nothing was started; ask again in a minute or two.",
                    retry_after=60,
                ),
            )
        )
        asked = settings.anonymous_max_runs_per_day
        quotas.append(
            Quota(
                asked,
                lambda session: _runs(session, Run.workspace_id == workspace, Run.created_at >= day_start()),
                lambda: TooManyRequests(
                    f"This demo workspace has asked {asked} questions today, its limit. Try again tomorrow (UTC).", retry_after=seconds_to_tomorrow()
                ),
            )
        )
    ceiling = settings.max_runs_per_day
    if ceiling > 0:
        quotas.append(
            Quota(
                ceiling,
                lambda session: _runs(session, Run.workspace_id.isnot(None), Run.created_at >= day_start()),
                lambda: TooManyRequests(
                    f"Today's run budget for this workbench is spent ({ceiling} new questions). Answers already given still open; "
                    "new questions can be asked again after midnight UTC.",
                    retry_after=seconds_to_tomorrow(),
                ),
            )
        )
    return tuple(quotas)


def refuse_if_spent(session: Session, quotas: Sequence[Quota]) -> None:
    """Refuse with the first quota that is spent. Inside `admit` this is the count that binds; anywhere else, advice."""
    for quota in quotas:
        if quota.count(session) >= quota.limit:
            raise quota.refusal()


def _nothing() -> None:
    return None


def admit[T](session: Session, quotas: Sequence[Quota], create: Callable[[], T], find: Callable[[], T | None] = _nothing) -> tuple[T, bool]:
    """The one way a row a quota limits is written: (the row, True) when `create` made it, (the row, False) when `find`
    found it already there, which spends nothing.

    `find` and the quotas are asked first without the lock, so a repeat, or a request already past a quota, never waits
    for a writer. Otherwise, under the write lock: `find` again (another request may have written the row since), every
    quota counted again, then `create`, committed before the lock is released. A spent quota raises its refusal and
    nothing is written. Reading and parsing happen before this, never inside it."""
    found = find()
    if found is not None:
        return found, False
    refuse_if_spent(session, quotas)
    with write_locked(session):
        found = find()
        if found is not None:
            return found, False
        refuse_if_spent(session, quotas)
        return create(), True
