"""Use case: the review memo, projected from a complete run's stored, verified findings.
No model call happens here; the memo cannot say anything the run did not already establish.
Asking twice returns the memo already written: the run is immutable, so the projection is too."""

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
from ..memo.service import memo_docx, memo_html
from ..models import Memo, Run


@dataclass(frozen=True)
class CreatedMemo:
    memo: Memo
    created: bool  # False when the run already had its memo


def review_head(run: Run) -> str:
    """The identity of the run's review state: the latest review row of every finding, in finding order, including
    undos. A memo carries the head it was written under; a review after it changes the head, not the memo."""
    return sha256_text("\x1f".join(f"{f.id}:{f.reviews[-1].id if f.reviews else ''}" for f in run.findings))


def stored_memo(session: Session, run_id: str, head: str) -> Memo | None:
    return session.query(Memo).filter(Memo.run_id == run_id, Memo.review_head == head).first()


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
    existing = stored_memo(session, run.id, head)
    if existing is not None:
        return CreatedMemo(existing, created=False)
    findings = [f for f in run.findings if f.status != "unresolved"]
    titles = {s.id: (f"§{s.number} {s.heading}".strip() if s.number else s.heading) for s in run.document.sections}
    html = memo_html(run, findings, titles, review_head=head)
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
        pending, digest = memo_docx(run, findings, titles, pending_dir, review_head=head)
        path = memos_dir / f"memo-{run.id}-{head[:8]}-{token[:8]}.docx"
        pending.replace(path)
    finally:
        shutil.rmtree(pending_dir, ignore_errors=True)
    memo = Memo(run_id=run.id, review_head=head, docx_path=str(path), docx_sha256=digest, html=html)
    session.add(memo)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        path.unlink(missing_ok=True)
        winner = stored_memo(session, run.id, head)
        if winner is None:
            raise
        return CreatedMemo(winner, created=False)
    except BaseException:
        # The row did not go in (the database refused, or the request was cut off): the file must not outlive it.
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    return CreatedMemo(memo, created=True)
