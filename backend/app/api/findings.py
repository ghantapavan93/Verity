"""Findings across runs: the record a reviewer comes back to. Only findings from complete runs
whose evidence verified are listed; unresolved ones stay on their run's detail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..application.clause_location import clause_numbers_by_document
from ..application.review_finding import latest_review_id, review_finding, review_out
from ..application.workspace import require_finding, require_own_run, visible_runs
from ..db import get_session
from ..document_names import run_document_name
from ..models import Document, EvidenceSpan, Finding, Run, Section, iso
from ..runs.account import account_of
from ..schemas import FindingRecord, FindingReviewOut, ReviewIn
from .access import current_workspace
from .contract import CONFLICT, FOUND, GATED, INVALID, WRITES, held_or_created, merged

router = APIRouter(prefix="/api/findings", tags=["findings"], responses=GATED)


@router.post(
    "/{finding_id}/review",
    response_model=FindingReviewOut,
    status_code=status.HTTP_201_CREATED,
    responses=merged(WRITES, INVALID, FOUND, CONFLICT, held_or_created(FindingReviewOut)),
)
def review(
    finding_id: str,
    body: ReviewIn,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    workspace: str = Depends(current_workspace),
) -> FindingReviewOut:
    """Record a person's decision. 201 when it changed the state, 200 when it repeated it; `cleared` undoes. With the gate
    on, the invite's subject is recorded beside the typed name; the name is what the browser sent and is not an identity."""
    require_own_run(require_finding(session, finding_id, workspace).run, workspace)
    reviewed = review_finding(session, finding_id, body.verdict, body.reviewer, body.note, getattr(request.state, "subject", None), body.based_on)
    if not reviewed.created:
        response.status_code = status.HTTP_200_OK
    return FindingReviewOut(finding_id=reviewed.finding.id, review=review_out(reviewed.review), latest_review_id=latest_review_id(reviewed.finding))


@router.get("", response_model=list[FindingRecord])
def list_findings(
    document_id: str | None = Query(default=None, alias="documentId"),
    session: Session = Depends(get_session),
    workspace: str = Depends(current_workspace),
) -> list[FindingRecord]:
    """Findings of the runs this workspace may read: its own and the curated ones."""
    # A fixed number of queries whatever the number listed: each finding asked again for its spans, their sections, its
    # reviews, its run's guidance and its document's name, five queries a row and 2,252 for a full list (backend audit,
    # 2026-10-19).
    statement = (
        select(Finding, Run, Document)
        .join(Run, Finding.run_id == Run.id)
        .join(Document, Run.document_id == Document.id)
        .where(Run.stage == "complete", Finding.status != "unresolved", visible_runs(workspace))
        .order_by(Run.created_at.desc(), Finding.ordinal)
        .limit(500)
        .options(
            # A cited section's number and heading name the citation; its text, up to a whole contract, is not read.
            selectinload(Finding.spans).selectinload(EvidenceSpan.section).load_only(Section.number, Section.heading),
            selectinload(Finding.reviews),
            # Held by the run, so the value check's session.get finds it rather than reading it again (runs.account).
            selectinload(Run.guidance),
        )
    )
    if document_id:
        statement = statement.where(Run.document_id == document_id)
    rows = session.execute(statement).all()
    clause_numbers = clause_numbers_by_document(session, (document.id for _, _, document in rows))
    names: dict[tuple[str | None, str], str] = {}  # one lookup per workspace and document, however many rows share them
    records: list[FindingRecord] = []
    for finding, run, document in rows:
        account = account_of(finding, clause_numbers[document.id] if finding.status != "missing" else frozenset())
        count = sum(1 for s in finding.spans if s.verified)
        name_key = (run.workspace_id, document.id)
        if name_key not in names:
            names[name_key] = run_document_name(run)
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
                shared=run.workspace_id is None,
                document_id=document.id,
                document_name=names[name_key],
                question=run.question,
                topic=finding.topic,
                status=finding.status,
                evidence_kind="coverage" if finding.status == "missing" else "passage",
                review=review_out(finding.review),
                latest_review_id=latest_review_id(finding),
                conclusion=finding.shown_conclusion,
                verified_spans=count,
                citations=citations,
                has_guidance=run.guidance_id is not None,
                status_source=finding.status_source,
                decided_by=account.decided_by,
                concerns=list(account.concerns),
                flagged=account.flagged,
                created_at=iso(run.created_at) or "",
            )
        )
    return records
