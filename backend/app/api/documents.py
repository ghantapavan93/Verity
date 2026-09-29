from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..application.ingest_document import ingest_document
from ..db import get_session
from ..errors import NotFound
from ..models import Document, Finding, FindingReview, Run, Section, iso
from ..schemas import DocumentOut, DocumentSummary, SectionOut

router = APIRouter(prefix="/api/documents", tags=["documents"])


def to_document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        name=document.name,
        pages=document.pages,
        sha256=document.sha256,
        parse_ms=document.parse_ms,
        parser_version=document.parser_version,
        tracked_changes=document.tracked_changes,
        hidden_runs=document.hidden_runs,
        created_at=iso(document.created_at) or "",
        sections=[SectionOut(id=s.id, number=s.number, heading=s.heading, text=s.text) for s in document.sections],
    )


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile, response: Response, session: Session = Depends(get_session)) -> DocumentOut:
    """201 with a new document, or 200 with the stored document that has exactly these bytes."""
    data = await file.read()
    ingested = ingest_document(session, file.filename or "upload", data)
    if not ingested.created:
        response.status_code = status.HTTP_200_OK
    out = to_document_out(ingested.document)
    out.reused = not ingested.created
    return out


@router.get("", response_model=list[DocumentSummary])
def list_documents(session: Session = Depends(get_session)) -> list[DocumentSummary]:
    rows = session.execute(select(Document, func.count(Section.id)).outerjoin(Section).group_by(Document.id).order_by(Document.created_at.desc())).all()
    # Verified findings and the latest complete run, per document.
    complete = select(Run).where(Run.stage == "complete").subquery()
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
            name=d.name,
            pages=d.pages,
            sections=count,
            findings=int(finding_counts.get(d.id, 0)),
            reviewed_findings=int(reviewed_counts.get(d.id, 0)),
            last_run_at=_iso_any(last_runs.get(d.id)),
            created_at=iso(d.created_at) or "",
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
def get_document(document_id: str, session: Session = Depends(get_session)) -> DocumentOut:
    document = session.get(Document, document_id)
    if document is None:
        raise NotFound("document", document_id)
    return to_document_out(document)
