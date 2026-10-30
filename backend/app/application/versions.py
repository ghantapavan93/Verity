"""Use case: say that one document is a later version of another, and read the line of versions back.

A document row is one reading of one set of bytes. Nothing in the bytes says that two rows are the same contract a
week apart, and a filename says it least of all. A person says it, once, and it is recorded as a workspace's own
statement: appended, never edited, never visible to another workspace.

The rules. Both documents must be readable by the workspace. A document supersedes at most one other and belongs to
one line; saying the same thing twice is the same statement, and saying something else about a document already
placed is a conflict, which is also what makes a cycle impossible: the later version must not be placed yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import refused_as_not_open
from ..errors import Conflict, InvalidInput
from ..models import DocumentVersion, new_id
from .quotas import admit, workspace_open
from .workspace import require_document


@dataclass(frozen=True)
class Declared:
    version: DocumentVersion
    created: bool


def _placed(session: Session, workspace: str, document_id: str) -> DocumentVersion | None:
    return session.query(DocumentVersion).filter_by(workspace_id=workspace, document_id=document_id).one_or_none()


def declare_supersedes(session: Session, workspace: str, document_id: str, previous_document_id: str) -> Declared:
    """Record that ``document_id`` is the version after ``previous_document_id``, in this workspace.

    Written through quotas.admit with the workspace's being open, like every other row a workspace adds: the lookup,
    the conflict check and both inserts in one transaction under the write lock retention deletes under. Written apart,
    a statement let in just before its workspace ended and committed after the purge left rows for a workspace no purge
    would list again; they kept two visitors' shared contracts for good, and the next start of the public API refused
    the store (stress test, 2026-10-30, concurrency 4 and journeys 1)."""
    require_document(session, document_id, workspace)
    require_document(session, previous_document_id, workspace)
    if document_id == previous_document_id:
        raise InvalidInput("a document cannot supersede itself")

    def already_said() -> DocumentVersion | None:
        placed = _placed(session, workspace, document_id)
        if placed is None:
            return None
        if placed.supersedes_document_id == previous_document_id:
            return placed
        raise Conflict("This document already has a place in a line of versions. A version supersedes one document, and that cannot be changed.")

    def say() -> DocumentVersion:
        # A statement about a different document that opened the earlier document's line first is the line this one
        # joins, as if made a moment later (QA campaign, 2026-10-08: two versions of one base).
        previous = _placed(session, workspace, previous_document_id)
        if previous is None:  # the earlier document opens a line
            previous = DocumentVersion(workspace_id=workspace, lineage_id=new_id(), document_id=previous_document_id, supersedes_document_id=None)
            session.add(previous)
            session.flush()
        version = DocumentVersion(workspace_id=workspace, lineage_id=previous.lineage_id, document_id=document_id, supersedes_document_id=previous_document_id)
        session.add(version)
        session.flush()
        return version

    # Two attempts: under the write lock no statement can interleave, but a lookup that missed the line another statement
    # opened is answered as the statement after it, as before the lock (2026-10-08), not refused.
    for _ in range(2):
        try:
            version, created = admit(session, workspace_open(workspace), say, find=already_said)
            return Declared(version, created=created)
        except IntegrityError as error:
            if refused_as_not_open(error):
                raise  # the store's refusal: the workspace has ended (answered as quotas.workspace_open would, app.main)
            continue  # admit has rolled it back; the next pass reads what is recorded
    raise Conflict("Another request was changing this line of versions at the same moment. Try again.")


def lineage(session: Session, workspace: str, document_id: str) -> list[DocumentVersion]:
    """Every version of the line this document belongs to in this workspace, in the order they were recorded; empty
    when the document has not been placed in one."""
    require_document(session, document_id, workspace)
    placed = _placed(session, workspace, document_id)
    if placed is None:
        return []
    return session.query(DocumentVersion).filter_by(workspace_id=workspace, lineage_id=placed.lineage_id).order_by(DocumentVersion.id).all()


def is_later_version(session: Session, workspace: str, earlier_document_id: str, later_document_id: str) -> bool:
    """Whether the workspace has said, directly or through versions in between, that the later document descends
    from the earlier one. Walks the statements upward from the later document; a line has no cycles."""
    current = _placed(session, workspace, later_document_id)
    while current is not None and current.supersedes_document_id is not None:
        if current.supersedes_document_id == earlier_document_id:
            return True
        current = _placed(session, workspace, current.supersedes_document_id)
    return False
