from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
from functools import partial

from anyio import CapacityLimiter, Lock, current_time, fail_after, to_thread
from fastapi import APIRouter, Depends, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..application.ingest_document import READINGS_BUSY, IngestedDocument, coverage_of, ingest_document, refuse_if_too_large
from ..application.workspace import require_document, visible_documents, visible_runs
from ..db import get_session
from ..document_names import display_created, display_name
from ..errors import Busy, TooManyRequests
from ..ingest.bounded import READINGS_AT_ONCE
from ..ingest.readers import SUFFIX_OF
from ..models import Document, Finding, FindingReview, Run, Section, iso
from ..schemas import CoverageReport, DocumentOut, DocumentSummary, ErrorOut, SectionOut
from .access import admit_upload, client_network, current_workspace, limit_document_reads
from .contract import FOUND, GATED, INVALID, WRITES, Responses, error_responses, held_or_created, merged

router = APIRouter(prefix="/api/documents", tags=["documents"], responses=GATED)
# An upload whose body stopped arriving, or arrived too slowly (api/body_limit.py BodyStalled).
STALLED: Responses = {408: {"model": ErrorOut, "description": "The upload stopped arriving, or arrived slower than 256 kbit/s."}}

# An upload waits for its reading here, on the event loop: no thread, and no second copy of its bytes, which are taken
# from the spool only once a reading may start. Waiting on threads, sixteen uploads held sixteen copies (counter-review
# round 3), and before that 45 slow uploads held all 40 threads of the pool every sync route shares, so /api/health
# waited 10.4 s, past the liveness probe's 5 s (2026-10-13). The READINGS_AT_ONCE that may read run on threads of their
# own; a document read again for a revision check takes one of the same slots, inside ingest/bounded.py.
readings = CapacityLimiter(READINGS_AT_ONCE)
reading_threads = CapacityLimiter(READINGS_AT_ONCE)
# One reading at a time from each network (access.client_network): its other upload waits behind it, so no one network
# can hold every slot (two 5.6 KB PDFs held both for a minute and a third reader waited past Cloudflare's 100 s,
# counter-review). Event loop only, so the dict needs no lock of its own.
_reading_from: dict[str, Lock] = {}
# The longest an upload waits for its network's turn and a reading slot (ingest/bounded.py) together; with a reading's
# 30 s, an answer comes within 75 s of the body, inside Cloudflare's 100 s. Past it the upload is refused, 503 with
# Retry-After, and nothing is kept: the waits were untimed, so readings held by others left a received upload waiting
# past Cloudflare's timeout and holding its place at the door (war room W5, 2026-10-13).
READING_WAIT_SECONDS = 45.0


@asynccontextmanager
async def reading_turn(network: str) -> AsyncIterator[float]:
    """The network's turn, then a reading slot, both within READING_WAIT_SECONDS; yields what is left of that wait for
    read_file, whose slot a reading again may hold. Busy, with nothing kept, when the wait runs out."""
    due = current_time() + READING_WAIT_SECONDS
    turn = _reading_from.setdefault(network, Lock())
    try:
        async with AsyncExitStack() as held:
            try:
                with fail_after(READING_WAIT_SECONDS):
                    await turn.acquire()
                    held.callback(turn.release)
                    await readings.acquire()
                    held.callback(readings.release)
            except TimeoutError:
                raise Busy(READINGS_BUSY, retry_after=30) from None
            yield max(0.0, due - current_time())
    finally:
        # Only this network's own lock, and only once no one holds or waits for it: a lock that finished late popped the
        # one a later upload had made, and the next upload from that network read beside it (war room W5 p8).
        if _reading_from.get(network) is turn and not turn.locked() and turn.statistics().tasks_waiting == 0:
            del _reading_from[network]


def to_document_out(session: Session, document: Document, workspace: str) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        name=display_name(session, document, workspace),
        pages=document.pages,
        sha256=document.sha256,
        parse_ms=document.parse_ms,
        parser_version=document.parser_version,
        tracked_changes=document.tracked_changes,
        hidden_runs=document.hidden_runs,
        coverage=CoverageReport.model_validate(report) if (report := coverage_of(document)) else None,
        created_at=iso(display_created(session, document, workspace)) or "",
        sections=[SectionOut(id=s.id, number=s.number, heading=s.heading, text=s.text, part=s.part) for s in document.sections],
    )


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED, responses=merged(WRITES, INVALID, STALLED, held_or_created(DocumentOut)))
async def upload_document(
    file: UploadFile, request: Request, response: Response, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)
) -> DocumentOut:
    """201 with a document new to this workspace, or 200 with the one it already holds that has exactly these bytes."""
    admit_upload(request, session, workspace)  # the owner's pause; a public workspace's bounds
    refuse_if_too_large(file.size)  # the declared size, before a byte is read; the bytes are checked again once read

    def read_and_ingest(wait: float) -> IngestedDocument:
        # The bytes are taken from the spooled upload only once a reading may start (reading_turn).
        return ingest_document(session, file.filename or "upload", file.file.read(), workspace, reading_wait=wait)

    # Parsing is CPU work of up to seconds (docs/archive/PARSER-COMPARISON.md: 44 s on a 1.25-million-character contract); it leaves the event loop.
    async with reading_turn(client_network(request)) as wait:
        ingested = await to_thread.run_sync(partial(read_and_ingest, wait), limiter=reading_threads)
    if not ingested.created:
        response.status_code = status.HTTP_200_OK
    out = to_document_out(session, ingested.document, workspace)
    out.reused = not ingested.created
    return out


@router.get("", response_model=list[DocumentSummary])
def list_documents(session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> list[DocumentSummary]:
    """This workspace's documents and the curated ones; the counts beside each are of runs it may read."""
    rows = session.execute(
        select(Document, func.count(Section.id))
        .outerjoin(Section)
        .where(visible_documents(workspace))
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    ).all()
    # Verified findings and the latest complete run, per document, among the runs this workspace may read.
    complete = select(Run).where(Run.stage == "complete", visible_runs(workspace)).subquery()
    finding_counts: dict[str, int] = dict(
        session.execute(
            select(complete.c.document_id, func.count(Finding.id))
            .join(Finding, Finding.run_id == complete.c.id)
            .where(Finding.status != "unresolved")
            .group_by(complete.c.document_id)
        ).all()
    )
    # Findings whose latest review stands (confirmed or dismissed), per document.
    latest_review = select(FindingReview.finding_id, func.max(FindingReview.id).label("review_id")).group_by(FindingReview.finding_id).subquery()
    reviewed_counts: dict[str, int] = dict(
        session.execute(
            select(complete.c.document_id, func.count(FindingReview.id))
            .join(Finding, Finding.run_id == complete.c.id)
            .join(latest_review, latest_review.c.finding_id == Finding.id)
            .join(FindingReview, FindingReview.id == latest_review.c.review_id)
            .where(FindingReview.verdict != "cleared")
            .group_by(complete.c.document_id)
        ).all()
    )
    last_runs: dict[str, datetime | str | None] = dict(
        session.execute(select(complete.c.document_id, func.max(complete.c.created_at)).group_by(complete.c.document_id)).all()
    )
    return [
        DocumentSummary(
            id=d.id,
            name=display_name(session, d, workspace),
            file_type=SUFFIX_OF.get(d.media_type, "").lstrip(".") or None,
            pages=d.pages,
            sections=count,
            findings=int(finding_counts.get(d.id, 0)),
            reviewed_findings=int(reviewed_counts.get(d.id, 0)),
            last_run_at=_iso_any(last_runs.get(d.id)),
            created_at=iso(display_created(session, d, workspace)) or "",
        )
        for d, count in rows
    ]


def _iso_any(value: datetime | str | None) -> str | None:
    # SQLite hands back a string for MAX(), Postgres a datetime.
    if value is None:
        return None
    if isinstance(value, datetime):
        return iso(value)
    return iso(datetime.fromisoformat(str(value)))


@router.get(
    "/{document_id}", response_model=DocumentOut, dependencies=[Depends(limit_document_reads)], responses=merged(FOUND, error_responses(TooManyRequests))
)
def get_document(document_id: str, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> DocumentOut:
    return to_document_out(session, require_document(session, document_id, workspace), workspace)
