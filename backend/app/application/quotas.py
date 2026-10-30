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
    bytes of new documents in a UTC day, public    their recorded sizes, with this one's   ingest_document
    questions a public workspace asks in a day     its runs made today                     start_run
    new runs in a UTC day, every reader            runs with a workspace made today        start_run

The same definitions give the early answers that spare work: api/access.admit_upload refuses before a file is read,
api/model.wake wakes no model for a question that would be refused. Those decide nothing; the count in `admit` does.

A daily quota counts the day of the row it limits, not the day the count happens to be made on (`daily`). A run is
stamped with the `now` start_run read for its identity, before the write lock; the count, inside the lock, read the
clock again. A request that read `now` on day D and was counted after 00:00 UTC was counted against D+1, which does not
hold its D stamp: a burst queued behind a long write across midnight was admitted whole, 8 runs on a day capped at 3
(stress test, 2026-10-30, time 2). The run quotas are therefore made for the run's own instant (`run_quotas(at=...)`),
and a day is counted exactly, from its midnight to the next. A grant and a document are stamped when their row is
flushed, inside the lock and after the count, so counting on the clock read there can only undercount the day before.
The per-address and per-reader windows (api/access.SlidingWindow) and the wake-up budget (wake_model) are not here: they
live in this process's memory and record an event in the same step, under one lock, that checks it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from ..config import settings
from ..db import write_locked
from ..errors import AccessRequired, Busy, TooManyRequests, WorkbenchError
from ..models import TERMINAL_STAGES, Document, DocumentAccess, Run, VisitorWorkspace, as_utc, utcnow
from .workspace import PUBLIC_PREFIX, is_public


@dataclass(frozen=True)
class Quota:
    """At most `limit` of the rows `count` counts; `refusal` is what a request past it is told."""

    limit: int
    count: Callable[[Session], int]
    refusal: Callable[[], WorkbenchError]


DAY = timedelta(days=1)


def day_start(at: datetime | None = None) -> datetime:
    """The start of the UTC day of ``at`` (the current one when None): every daily quota resets here."""
    moment = (at or utcnow()).astimezone(UTC)
    return datetime(moment.year, moment.month, moment.day, tzinfo=UTC)


def seconds_to_tomorrow(at: datetime | None = None) -> int:
    """How long until the day of ``at`` is over, from now: at least a second. A request stamped on a day that ended while
    it waited for the lock is refused against that day, and may ask again at once, as it would be stamped on the next."""
    return max(1, int((day_start(at) + DAY - utcnow()).total_seconds()) + 1)


def _of_day(column: InstrumentedAttribute[datetime], at: datetime | None) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """The rows of the UTC day of ``at``, exactly: from its midnight to the next. Read when the count is made, so a
    quota made for no instant counts the day the lock was had on."""
    start = day_start(at)
    return column >= start, column < start + DAY


def daily(
    limit: int, count: Callable[[Session, tuple[ColumnElement[bool], ...]], int], column: InstrumentedAttribute[datetime], refusal: str, at: datetime | None
) -> Quota:
    """At most ``limit`` rows a UTC day: ``count`` counts the rows matching its day's conditions, which are those of the
    day of ``at``, the instant the row being admitted carries. Refused with ``refusal`` and a Retry-After to the end of
    that day."""
    return Quota(
        limit,
        lambda session: count(session, _of_day(column, at)),
        lambda: TooManyRequests(refusal, retry_after=seconds_to_tomorrow(at)),
    )


def _grants(session: Session, *where: ColumnElement[bool]) -> int:
    return session.scalar(select(func.count()).select_from(DocumentAccess).where(*where)) or 0


def _public_bytes(session: Session, day: tuple[ColumnElement[bool], ...]) -> int:
    """The sizes of the documents stored on the day that a public workspace holds."""
    held = select(DocumentAccess.document_id).where(DocumentAccess.document_id == Document.id, DocumentAccess.workspace_id.like(f"{PUBLIC_PREFIX}%"))
    total = session.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0)).where(*day, held.exists()))
    return int(total or 0)


def _runs(session: Session, *where: ColumnElement[bool]) -> int:
    return session.scalar(select(func.count(Run.id)).where(*where)) or 0


def _ended(session: Session, workspace: str) -> int:
    """1 when the public workspace is no longer registered or has ended, 0 while it is open: read inside the write lock,
    a fresh read of the store, never an object this session loaded earlier."""
    expires = session.scalar(select(VisitorWorkspace.expires_at).where(VisitorWorkspace.workspace_id == workspace))
    return 1 if expires is None or as_utc(expires) <= utcnow() else 0


VISIT_ENDED = "This visit has ended and what it added has been deleted, so nothing was added. Reload the page to start again."


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
            lambda: AccessRequired(VISIT_ENDED),
        ),
    )


def document_quotas(workspace: str | None, adding_bytes: int = 0) -> tuple[Quota, ...]:
    """What a new grant (a document the workspace holds) is counted against: a public workspace's being open, its own
    bound, then every public workspace's uploads today, by count and, for a document stored new (``adding_bytes``, its
    size; a grant of one already held stores nothing), by bytes. Other workspaces hold what they upload without a bound."""
    if not is_public(workspace):
        return ()
    held = settings.anonymous_max_documents
    budget = settings.anonymous_max_upload_bytes_per_day
    in_bytes = (
        # Refused once today's bytes and this document's together pass the budget: the count reaching budget + 1.
        daily(
            budget + 1,
            lambda session, day: _public_bytes(session, day) + adding_bytes,
            Document.created_at,
            "The demo has taken all the contract text it takes in a day. Try again tomorrow (UTC).",
            at=None,
        ),
    )
    return (
        *workspace_open(workspace),
        Quota(
            held,
            lambda session: _grants(session, DocumentAccess.workspace_id == workspace),
            lambda: TooManyRequests(f"This demo workspace already holds {held} contracts, its limit. Ask about one of them.", retry_after=3600),
        ),
        # A grant is stamped when its row is flushed, inside the lock after this count: counted on the day the lock was had.
        daily(
            settings.anonymous_max_uploads_per_day,
            lambda session, day: _grants(session, DocumentAccess.workspace_id.like(f"{PUBLIC_PREFIX}%"), *day),
            DocumentAccess.created_at,
            "The demo has taken all the uploads it takes in a day. Try again tomorrow (UTC).",
            at=None,
        ),
        *(in_bytes if budget > 0 else ()),
    )


def run_quotas(workspace: str | None, at: datetime | None = None) -> tuple[Quota, ...]:
    """What a new run is counted against: a public workspace's being open and its questions that day, then every reader's
    new runs that day (settings.max_runs_per_day; 0 is no ceiling). The day is that of ``at``, the instant the run is
    stamped with (start_run), so a run is counted against the day it carries; None, the day the count is made on (the
    early answers: api/model.wake). The project's own runs (no workspace: goldens, batches) are neither bounded nor
    counted."""
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
            daily(
                asked,
                lambda session, day: _runs(session, Run.workspace_id == workspace, *day),
                Run.created_at,
                f"This demo workspace has asked {asked} questions today, its limit. Try again tomorrow (UTC).",
                at,
            )
        )
    ceiling = settings.max_runs_per_day
    if ceiling > 0:
        quotas.append(
            daily(
                ceiling,
                lambda session, day: _runs(session, Run.workspace_id.isnot(None), *day),
                Run.created_at,
                f"Today's run budget for this workbench is spent ({ceiling} new questions). Answers already given still open; "
                "new questions can be asked again after midnight UTC.",
                at,
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
