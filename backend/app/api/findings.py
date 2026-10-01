"""Findings across runs: the record a reviewer comes back to. Only findings from complete runs
whose evidence verified are listed; unresolved ones stay on their run's detail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..application.review_finding import review_finding, review_out
from ..db import get_session
from ..models import Document, EvidenceSpan, Finding, Run, iso
from ..schemas import FindingRecord, FindingReviewOut, ReviewIn

router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.post("/{finding_id}/review", response_model=FindingReviewOut, status_code=status.HTTP_201_CREATED)
def review(finding_id: str, body: ReviewIn, response: Response, session: Session = Depends(get_session)) -> FindingReviewOut:
    """Record a person's decision. 201 when it changed the state, 200 when it repeated it; `cleared` undoes."""
    reviewed = review_finding(session, finding_id, body.verdict, body.reviewer, body.note)
    if not reviewed.created:
        response.status_code = status.HTTP_200_OK
    return FindingReviewOut(finding_id=reviewed.finding.id, review=review_out(reviewed.review))


@router.get("", response_model=list[FindingRecord])
def list_findings(document_id: str | None = Query(default=None, alias="documentId"), session: Session = Depends(get_session)) -> list[FindingRecord]:
    statement = (
        select(Finding, Run, Document)
        .join(Run, Finding.run_id == Run.id)
        .join(Document, Run.document_id == Document.id)
        .where(Run.stage == "complete", Finding.status != "unresolved")
        .order_by(Run.created_at.desc(), Finding.ordinal)
        .limit(500)
    )
    if document_id:
        statement = statement.where(Run.document_id == document_id)
    records: list[FindingRecord] = []
    for finding, run, document in session.execute(statement).all():
        verified = session.scalar(select(EvidenceSpan.id).where(EvidenceSpan.finding_id == finding.id, EvidenceSpan.verified.is_(True)).limit(1))
        count = sum(1 for s in finding.spans if s.verified) if verified else 0
        citations: list[str] = []
        for span in finding.spans:
            if not span.verified or span.section is None:
                continue
            label = f"§{span.section.number}" if span.section.number else span.section.heading
            if label not in citations:
                citations.append(label)
        records.append(
            FindingRecord(
                id=finding.id,
                run_id=run.id,
                document_id=document.id,
                document_name=document.name,
                question=run.question,
                topic=finding.topic,
                status=finding.status,
                evidence_kind="coverage" if finding.status == "missing" else "passage",
                review=review_out(finding.review),
                conclusion=finding.conclusion,
                verified_spans=count,
                citations=citations,
                has_guidance=run.guidance_id is not None,
                status_source=finding.status_source,
                created_at=iso(run.created_at) or "",
            )
        )
    return records
