"""Use case: a person records a decision about a finding.

Model proposes, code verifies, a person adjudicates. Reviews are appended, never edited: the
latest row is the state, `cleared` returns the finding to unreviewed, and repeating the same
decision writes nothing. The finding and its run are never changed by a review.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..errors import Conflict, NotFound
from ..ingest.invisible import visible_text
from ..models import Finding, FindingReview, ReviewVerdictName, iso
from ..schemas import ReviewOut


def review_out(review: FindingReview | None) -> ReviewOut | None:
    """The one mapping of a review row to its API shape: the current decision, or nothing when unreviewed or cleared."""
    if review is None or review.verdict == "cleared":
        return None
    return ReviewOut(verdict=review.verdict, reviewer=review.reviewer, note=review.note, at=iso(review.created_at) or "", access_subject=review.access_subject)


@dataclass(frozen=True)
class Reviewed:
    finding: Finding
    review: FindingReview | None  # the current state after this call; None when unreviewed
    created: bool  # False when the request repeated the current state


def latest_review_id(finding: Finding) -> int:
    """The id of the finding's latest review row, a cleared one included; 0 when it has none."""
    return finding.reviews[-1].id if finding.reviews else 0


def review_finding(
    session: Session,
    finding_id: str,
    verdict: ReviewVerdictName,
    reviewer: str,
    note: str | None,
    access_subject: str | None = None,
    based_on: int | None = None,
) -> Reviewed:
    """``based_on`` is the latest review id the reviewer saw. Two people with one finding open decided over each other:
    the later click won and the earlier one's screen still showed its own decision (adversarial review, 2026-10-08).
    With ``based_on`` the check and the write share one write transaction, so a decision made against a state that has
    changed since is refused and nothing is written; repeating the current decision is not a conflict."""
    finding = session.get(Finding, finding_id)
    if finding is None:
        raise NotFound("finding", finding_id)
    if finding.status == "unresolved" or finding.run.stage != "complete":
        raise Conflict("only a finding shown as an answer can be reviewed; this one was withheld or its run did not complete")

    reviewer = visible_text(reviewer).strip()
    note = visible_text(note or "").strip() or None
    if based_on is not None and session.get_bind().dialect.name == "sqlite":
        # Take the write lock before reading the latest review: two stale tabs cannot both pass the check below.
        session.commit()
        session.execute(text("BEGIN IMMEDIATE"))
        session.expire(finding, ["reviews"])
    latest = finding.reviews[-1] if finding.reviews else None
    if latest is not None and (latest.verdict, latest.reviewer, latest.note) == (verdict, reviewer, note):
        session.commit()
        return Reviewed(finding, finding.review, created=False)
    if verdict == "cleared" and finding.review is None:
        session.commit()
        return Reviewed(finding, None, created=False)
    if based_on is not None and based_on != latest_review_id(finding):
        current = finding.review
        session.rollback()
        said = f"{current.verdict} by {current.reviewer}" if current else "returned to unreviewed"
        raise Conflict(f"This finding was {said} after you opened it. Its current decision is shown; decide again if you still disagree.")

    row = FindingReview(finding_id=finding.id, verdict=verdict, reviewer=reviewer, note=note, access_subject=access_subject)
    session.add(row)
    session.commit()
    session.refresh(finding)
    return Reviewed(finding, finding.review, created=True)
