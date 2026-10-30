"""The name a workspace knows a document by.

One stored reading per set of bytes (application/ingest_document.py), but the name and the upload date are the
uploader's, not the bytes'. A workspace is shown the name it gave the file and the date it added it; a curated
document, everyone's, keeps its own. Grants made before 2026-10-09 carry no name: the first workspace on the document
gave the stored name and still sees it, a later one sees UNNAMED, never the name another workspace chose.

Since 2026-10-30 a shared row is named by its type in every store; before, an invited store's row took its first
uploader's name. Such a stored name is a workspace's own, and is shown and given to the model only for that workspace:
a curated run (a batch, the goldens) over bytes a workspace uploaded first showed that name to every other workspace
and was prompted with it, and a later workspace's new runs on an unnamed grant were given it (stress test, authz 2,
journeys 2). The name a run was given is the one its record rebuilds with (application/reconstruct_input.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session, object_session

from .models import Document, DocumentAccess, Run

UNNAMED = "uploaded file (name not recorded)"


def _grant(session: Session, document: Document, workspace: str | None) -> DocumentAccess | None:
    return session.get(DocumentAccess, (workspace, document.id)) if workspace else None


def _first_holder(session: Session, document: Document) -> str | None:
    first = session.query(DocumentAccess.workspace_id).filter(DocumentAccess.document_id == document.id).order_by(DocumentAccess.created_at).first()
    return first[0] if first is not None else None


def stored_name_is_a_workspaces(session: Session, document: Document) -> bool:
    """Whether the stored name is a workspace's choice rather than the project's: the row was named by an upload, so
    its first grant carries the same name, or (before 2026-10-09) none at all."""
    names = [name for (name,) in session.query(DocumentAccess.name).filter(DocumentAccess.document_id == document.id).order_by(DocumentAccess.created_at)]
    return bool(names) and (names[0] is None or document.name in names)


def _unheld_name(session: Session, document: Document) -> str:
    """The name for a workspace that holds no grant on the document, or for a curated run: the stored name only when it
    is the project's."""
    return UNNAMED if stored_name_is_a_workspaces(session, document) else document.name


def display_name(session: Session, document: Document, workspace: str | None) -> str:
    grant = _grant(session, document, workspace)
    if grant is None:
        return _unheld_name(session, document)
    if grant.name:
        return grant.name
    return document.name if _first_holder(session, document) == workspace else UNNAMED


def display_created(session: Session, document: Document, workspace: str | None) -> datetime:
    grant = _grant(session, document, workspace)
    return grant.created_at if grant is not None else document.created_at


def prompt_name(session: Session, document: Document, workspace: str | None) -> str:
    """The name the model is given for the document in a new run of this workspace: the name its workspace is shown
    (display_name). A run recorded before 2026-10-30 may have been given another (legacy_prompt_name), and is rebuilt
    with the one its record says."""
    return display_name(session, document, workspace)


def legacy_prompt_name(session: Session, document: Document, workspace: str | None) -> str:
    """The name the model was given before 2026-10-30: a named grant's name, otherwise the stored name, whoever chose it."""
    grant = _grant(session, document, workspace)
    return grant.name if grant is not None and grant.name else document.name


def run_document_name(run: Run) -> str:
    """The document's name as the run's own workspace knows it; a curated run's is the stored name when it is the
    project's."""
    session = object_session(run)
    return display_name(session, run.document, run.workspace_id) if session is not None else run.document.name


def run_prompt_name(run: Run) -> str:
    """The name the model is given for a run's document (prompt_name, for the run's workspace)."""
    session = object_session(run)
    return prompt_name(session, run.document, run.workspace_id) if session is not None else run.document.name


def run_legacy_prompt_name(run: Run) -> str:
    session = object_session(run)
    return legacy_prompt_name(session, run.document, run.workspace_id) if session is not None else run.document.name
