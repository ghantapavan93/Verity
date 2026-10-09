from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..application.ingest_document import coverage_of, ingest_document, refuse_if_too_large
from ..application.workspace import require_document, visible_documents, visible_runs
from ..db import get_session
from ..document_names import display_created, display_name
from ..ingest.readers import SUFFIX_OF
from ..models import Document, Finding, FindingReview, Run, Section, iso
from ..schemas import CoverageReport, DocumentOut, DocumentSummary, SectionOut
from .access import current_workspace

router = APIRouter(prefix="/api/documents", tags=["documents"])


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
        sections=[SectionOut(id=s.id, number=s.number, heading=s.heading, text=s.text) for s in document.sections],
    )


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile, response: Response, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)
) -> DocumentOut:
    """201 with a document new to this workspace, or 200 with the one it already holds that has exactly these bytes."""
    refuse_if_too_large(file.size)  # the declared size, before a byte is read; the bytes are checked again once read
    data = await file.read()
    # Parsing is CPU work of up to seconds (docs/PARSER-COMPARISON.md: 44 s on a 1.25-million-character contract); it leaves the event loop.
    ingested = await run_in_threadpool(ingest_document, session, file.filename or "upload", data, workspace)
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


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> DocumentOut:
    return to_document_out(session, require_document(session, document_id, workspace), workspace)
