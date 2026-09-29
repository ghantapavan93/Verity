"""Use case: a person records a decision about a finding.

Model proposes, code verifies, a person adjudicates. Reviews are appended, never edited: the
latest row is the state, `cleared` returns the finding to unreviewed, and repeating the same
decision writes nothing. The finding and its run are never changed by a review.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..errors import Conflict, NotFound
from ..models import Finding, FindingReview, ReviewVerdictName


@dataclass(frozen=True)
class Reviewed:
    finding: Finding
    review: FindingReview | None  # the current state after this call; None when unreviewed
    created: bool  # False when the request repeated the current state


def review_finding(session: Session, finding_id: str, verdict: ReviewVerdictName, reviewer: str, note: str | None) -> Reviewed:
    finding = session.get(Finding, finding_id)
    if finding is None:
        raise NotFound("finding", finding_id)
    if finding.status == "unresolved" or finding.run.stage != "complete":
        raise Conflict("only a finding shown as an answer can be reviewed; this one was withheld or its run did not complete")

    reviewer = reviewer.strip()
    note = (note or "").strip() or None
    latest = finding.reviews[-1] if finding.reviews else None
    if latest is not None and (latest.verdict, latest.reviewer, latest.note) == (verdict, reviewer, note):
        return Reviewed(finding, finding.review, created=False)
    if verdict == "cleared" and finding.review is None:
        return Reviewed(finding, None, created=False)

    row = FindingReview(finding_id=finding.id, verdict=verdict, reviewer=reviewer, note=note)
    session.add(row)
    session.commit()
    session.refresh(finding)
    return Reviewed(finding, finding.review, created=True)
