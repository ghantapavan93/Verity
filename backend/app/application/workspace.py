"""Who may read what: the one place the rule lives.

A reviewer who enters by an invite works in a workspace derived from that invite (api.access.workspace_for). What the
workspace uploads, asks and writes is its own. What the project put on the record before workspaces existed, and
everything the goldens and batches make, is curated: readable by every workspace, changed by none.

The rule, record by record:

    document     readable when the workspace holds an access grant, or when no workspace holds one (curated)
    run          readable when its workspace is this one, or none (curated)
    guidance     readable when its workspace is this one, or none (curated)
    finding      follows its run;  review follows its finding;  memo follows its run;  the event stream follows its run

A record that may not be read answers exactly as a record that does not exist: NotFound, the same 404 and the same
sentence. A curated record that a request would change answers Forbidden, because its existence is public anyway.
"""

from __future__ import annotations

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ..errors import Forbidden, NotFound
from ..models import Document, DocumentAccess, Finding, Guidance, Memo, Run


def document_is_curated(session: Session, document_id: str) -> bool:
    return session.query(DocumentAccess.document_id).filter(DocumentAccess.document_id == document_id).first() is None


def can_read_document(session: Session, document: Document, workspace: str) -> bool:
    if document_is_curated(session, document.id):
        return True
    return session.get(DocumentAccess, (workspace, document.id)) is not None


def can_read_run(run: Run, workspace: str) -> bool:
    return run.workspace_id is None or run.workspace_id == workspace


def can_read_guidance(guidance: Guidance, workspace: str) -> bool:
    return guidance.workspace_id is None or guidance.workspace_id == workspace


def grant_document(session: Session, document: Document, workspace: str) -> bool:
    """Let the workspace read the document. True when the grant is new."""
    if session.get(DocumentAccess, (workspace, document.id)) is not None:
        return False
    session.add(DocumentAccess(workspace_id=workspace, document_id=document.id))
    return True


# ---------------------------------------------------------------------------- loaders that refuse like a miss


def require_document(session: Session, document_id: str, workspace: str) -> Document:
    document = session.get(Document, document_id)
    if document is None or not can_read_document(session, document, workspace):
        raise NotFound("document", document_id)
    return document


def require_run(session: Session, run_id: str, workspace: str) -> Run:
    run = session.get(Run, run_id)
    if run is None or not can_read_run(run, workspace):
        raise NotFound("run", run_id)
    return run


def require_guidance(session: Session, guidance_id: str, workspace: str) -> Guidance:
    guidance = session.get(Guidance, guidance_id)
    if guidance is None or not can_read_guidance(guidance, workspace):
        raise NotFound("guidance", guidance_id)
    return guidance


def require_finding(session: Session, finding_id: str, workspace: str) -> Finding:
    finding = session.get(Finding, finding_id)
    if finding is None or not can_read_run(finding.run, workspace):
        raise NotFound("finding", finding_id)
    return finding


def require_memo(session: Session, memo_id: str, workspace: str) -> Memo:
    memo = session.get(Memo, memo_id)
    if memo is None or not can_read_run(memo.run, workspace):
        raise NotFound("memo", memo_id)
    return memo


def require_own_run(run: Run, workspace: str) -> None:
    """A change to a run or anything under it: only its own workspace may make one, and a curated record takes none."""
    if run.workspace_id is None:
        raise Forbidden("This is a curated record. It is read only; its review is kept as recorded.")
    if run.workspace_id != workspace:
        raise NotFound("run", run.id)


# ---------------------------------------------------------------------------- filters for lists


def visible_runs(workspace: str) -> ColumnElement[bool]:
    return or_(Run.workspace_id.is_(None), Run.workspace_id == workspace)


def visible_documents(workspace: str) -> ColumnElement[bool]:
    granted = select(DocumentAccess.document_id).where(DocumentAccess.document_id == Document.id)
    mine = select(DocumentAccess.document_id).where(DocumentAccess.document_id == Document.id, DocumentAccess.workspace_id == workspace)
    return or_(~exists(granted), exists(mine))
