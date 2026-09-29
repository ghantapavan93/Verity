"""Use case: the review memo, projected from a complete run's stored, verified findings.
No model call happens here; the memo cannot say anything the run did not already establish.
Asking twice returns the memo already written: the run is immutable, so the projection is too."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..config import settings
from ..errors import Conflict, NotFound
from ..memo.service import memo_docx, memo_html
from ..models import Memo, Run


@dataclass(frozen=True)
class CreatedMemo:
    memo: Memo
    created: bool  # False when the run already had its memo


def create_memo(session: Session, run_id: str) -> CreatedMemo:
    run = session.get(Run, run_id)
    if run is None:
        raise NotFound("run", run_id)
    if run.stage != "complete":
        raise Conflict(f"run is {run.stage}; a memo needs a complete run with verified findings")
    existing = session.query(Memo).filter(Memo.run_id == run.id).order_by(Memo.created_at.desc()).first()
    if existing is not None:
        return CreatedMemo(existing, created=False)
    findings = [f for f in run.findings if f.status != "unresolved"]
    titles = {s.id: (f"§{s.number} {s.heading}".strip() if s.number else s.heading) for s in run.document.sections}
    html = memo_html(run, findings, titles)
    path, digest = memo_docx(run, findings, titles, settings.data_dir / "memos")
    memo = Memo(run_id=run.id, docx_path=str(path), docx_sha256=digest, html=html)
    session.add(memo)
    session.commit()
    return CreatedMemo(memo, created=True)
