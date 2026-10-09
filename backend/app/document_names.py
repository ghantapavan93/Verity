"""The name a workspace knows a document by.

One stored reading per set of bytes (application/ingest_document.py), but the name and the upload date are the
uploader's, not the bytes'. A workspace is shown the name it gave the file and the date it added it; a curated
document, everyone's, keeps its own. Grants made before 2026-10-09 carry no name: the first workspace on the document
gave the stored name and still sees it, a later one sees UNNAMED, never the name another workspace chose.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session, object_session

from .models import Document, DocumentAccess, Run

UNNAMED = "uploaded file (name not recorded)"


def _grant(session: Session, document: Document, workspace: str | None) -> DocumentAccess | None:
    return session.get(DocumentAccess, (workspace, document.id)) if workspace else None


def display_name(session: Session, document: Document, workspace: str | None) -> str:
    grant = _grant(session, document, workspace)
    if grant is None:
        return document.name
    if grant.name:
        return grant.name
    first = session.query(DocumentAccess.workspace_id).filter(DocumentAccess.document_id == document.id).order_by(DocumentAccess.created_at).first()
    return document.name if first is not None and first[0] == workspace else UNNAMED


def display_created(session: Session, document: Document, workspace: str | None) -> datetime:
    grant = _grant(session, document, workspace)
    return grant.created_at if grant is not None else document.created_at


def prompt_name(session: Session, document: Document, workspace: str | None) -> str:
    """The name the model is given for the document in a run of this workspace. A grant made before names were kept
    gives the stored name, which is what every run before then was given, so their inputs rebuild unchanged."""
    grant = _grant(session, document, workspace)
    return grant.name if grant is not None and grant.name else document.name


def run_document_name(run: Run) -> str:
    """The document's name as the run's own workspace knows it; a curated run's is the stored name."""
    session = object_session(run)
    return display_name(session, run.document, run.workspace_id) if session is not None else run.document.name


def run_prompt_name(run: Run) -> str:
    """The name the model was, or is, given for a run's document (prompt_name, for the run's workspace)."""
    session = object_session(run)
    return prompt_name(session, run.document, run.workspace_id) if session is not None else run.document.name
