"""Use case: what the verifier did across every finished run, counted from the records.

The number a reader wants before trusting the word "verified": how often the model's quotes were
found, by which method, and how often a finding was withheld because they were not.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import EvidenceSpan, Finding, Run, iso
from ..schemas import CitationRecordOut
from .workspace import visible_runs

ANSWERED = ("complete", "unresolved")  # runs where the model answered and the verifier had something to check


def citation_record(session: Session, workspace: str | None = None) -> CitationRecordOut:
    """Over every run when ``workspace`` is None (the project's own census); otherwise over the runs it may read."""
    answered = Run.stage.in_(ANSWERED) if workspace is None else (Run.stage.in_(ANSWERED) & visible_runs(workspace))
    runs_by_stage = dict(session.execute(select(Run.stage, func.count()).where(answered).group_by(Run.stage)).all())
    first_at, last_at = session.execute(select(func.min(Run.created_at), func.max(Run.created_at)).where(answered)).one()

    finding_rows = session.execute(select(Finding.status, func.count()).join(Run, Finding.run_id == Run.id).where(answered).group_by(Finding.status)).all()
    findings = sum(count for _status, count in finding_rows)
    withheld = sum(count for status, count in finding_rows if status == "unresolved")

    span_rows = session.execute(
        select(EvidenceSpan.method, EvidenceSpan.verified, func.count())
        .join(Finding, EvidenceSpan.finding_id == Finding.id)
        .join(Run, Finding.run_id == Run.id)
        .where(answered)
        .group_by(EvidenceSpan.method, EvidenceSpan.verified)
    ).all()
    by_method: dict[str, int] = {}
    for method, verified, count in span_rows:
        if verified:
            by_method[method] = by_method.get(method, 0) + count

    return CitationRecordOut(
        runs=sum(runs_by_stage.values()),
        complete_runs=int(runs_by_stage.get("complete", 0)),
        unresolved_runs=int(runs_by_stage.get("unresolved", 0)),
        findings=findings,
        withheld_findings=withheld,
        spans=sum(count for _method, _verified, count in span_rows),
        verified_spans=sum(by_method.values()),
        by_method=dict(sorted(by_method.items(), key=lambda item: -item[1])),
        first_run_at=_iso(first_at),
        last_run_at=_iso(last_at),
    )


def _iso(value: datetime | str | None) -> str | None:
    # SQLite hands back a string for MIN()/MAX(), Postgres a datetime.
    if value is None:
        return None
    return iso(value if isinstance(value, datetime) else datetime.fromisoformat(str(value)))
