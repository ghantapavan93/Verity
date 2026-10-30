"""Use case: the review memo, projected from a complete run's stored, verified findings.
No model call happens here; the memo cannot say anything the run did not already establish.
Asking twice returns the memo already written, while it says what a memo written now would say: the run is immutable,
its reviews are in the review head, and the rules that project it into words are in the content key."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import Conflict, NotFound
from ..hashing import sha256_text
from ..memo.service import DOCX_LAYOUT, memo_docx, memo_html
from ..models import Memo, Run
from ..runs.account import account_of, notes_of
from ..runs.status import basis
from .clause_location import ClauseLocator


@dataclass(frozen=True)
class CreatedMemo:
    memo: Memo
    created: bool  # False when the run already had its memo


def review_head(run: Run) -> str:
    """The identity of the run's review state: the latest review row of every finding, in finding order, including
    undos. A memo carries the head it was written under; a review after it changes the head, not the memo."""
    return sha256_text("\x1f".join(f"{f.id}:{f.reviews[-1].id if f.reviews else ''}" for f in run.findings))


# The date a memo is rendered with to know what it says: a memo asked for again tomorrow says the same.
KEY_DATE = "the day it is written"


def content_key(html_without_date: str) -> str:
    """What a memo says, as a key: its HTML rendered with a fixed date (every label, flag, concern and clause it shows,
    which the Word memo shares), and the Word layout's own version. Until 2026-10-30 a memo was keyed by its run and
    review head alone, so no change to its wording or to what code raises reached a memo whose reviews had not moved:
    a store written under release-2026-10-12 was handed "None. Every finding was within guidance" for a finding the
    current account flags (stress test, store evolution). A key is what the memo says, not a version to remember to
    bump: most of what a memo says is decided outside memo/ (runs.account, runs.values, clause_location)."""
    return sha256_text(f"{DOCX_LAYOUT}\x1f{html_without_date}")


def stored_memo(session: Session, run_id: str, head: str, content: str) -> Memo | None:
    return session.query(Memo).filter(Memo.run_id == run_id, Memo.review_head == head, Memo.content_sha256 == content).first()


def memo_file(memo: Memo) -> Path:
    """Where a memo's DOCX is now: in this store's memos directory, under the name it was written with. The row keeps
    the path it was written to; a store that has been copied or restored is read where it is, not where it was."""
    return settings.data_dir / "memos" / PureWindowsPath(memo.docx_path).name


def create_memo(session: Session, run_id: str) -> CreatedMemo:
    run = session.get(Run, run_id)
    if run is None:
        raise NotFound("run", run_id)
    if run.stage != "complete":
        raise Conflict(f"run is {run.stage}; a memo needs a complete run with verified findings")
    head = review_head(run)
    findings = [f for f in run.findings if f.status != "unresolved"]
    # Proposals withheld because no quote of them was found: listed and flagged, never printed as findings (memo.service).
    withheld = [f for f in run.findings if f.status == "unresolved"]
    titles = {s.id: (f"§{s.number} {s.heading}".strip() if s.number else s.heading) for s in run.document.sections}
    locator = ClauseLocator(run.document.sections)
    clauses = {span.id: label for f in findings for span in f.spans if (label := locator.label(span))}
    unseen = {f.id: named for f in findings if (named := basis(f.status_source, f.status_reason).unseen)}
    # What each finding's status rests on and what code raised about it, as the card reads it (runs.account).
    accounts = {f.id: account_of(f, locator.clause_numbers if f.status != "missing" else frozenset()) for f in [*findings, *withheld]}
    flagged = {finding_id: "; ".join(account.concerns) for finding_id, account in accounts.items() if account.flagged}
    # What the contract's own statements mean for each finding without raising a concern (runs.relations): said once each.
    related = {f.id: [n.sentence for n in notes_of(f) if n.effect == "context"] for f in findings}

    def render(date: str | None = None) -> str:
        return memo_html(
            run, findings, titles, review_head=head, clauses=clauses, unseen=unseen, flagged=flagged, withheld=withheld, related=related, date=date
        )

    content = content_key(render(KEY_DATE))
    # The memo already written for this run, review state and wording, if any; one written under other rules is kept,
    # and served by its own id, but is not the answer to this request.
    existing = stored_memo(session, run.id, head, content)
    if existing is not None:
        return CreatedMemo(existing, created=False)
    html = render()
    # The file is in place before the row exists, under a name no other request can have. The row used to be
    # committed first and the file moved after it: a process that died between the two left a memo whose DOCX was
    # never there, and every retry was handed that memo (fault injection, 2026-10-02). In this order the worst a
    # crash leaves is a file with no row, which nothing points at. The name carries the request's token, so a
    # concurrent first request that loses the insert removes its own file and never touches the winner's
    # (found while tracing, 2026-09-29).
    memos_dir = settings.data_dir / "memos"
    token = uuid.uuid4().hex
    pending_dir = memos_dir / "pending" / token
    pending_dir.mkdir(parents=True, exist_ok=True)
    try:
        pending, digest = memo_docx(
            run, findings, titles, pending_dir, review_head=head, clauses=clauses, unseen=unseen, flagged=flagged, withheld=withheld, related=related
        )
        path = memos_dir / f"memo-{run.id}-{head[:8]}-{token[:8]}.docx"
        pending.replace(path)
    finally:
        shutil.rmtree(pending_dir, ignore_errors=True)
    memo = Memo(run_id=run.id, review_head=head, content_sha256=content, docx_path=str(path), docx_sha256=digest, html=html)
    session.add(memo)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        path.unlink(missing_ok=True)
        winner = stored_memo(session, run.id, head, content)
        if winner is None:
            raise
        return CreatedMemo(winner, created=False)
    except BaseException:
        # The row did not go in (the database refused, or the request was cut off): the file must not outlive it.
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    return CreatedMemo(memo, created=True)
