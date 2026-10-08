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

from ..errors import Conflict, InvalidInput
from ..models import DocumentVersion, new_id
from .workspace import require_document


@dataclass(frozen=True)
class Declared:
    version: DocumentVersion
    created: bool


def _placed(session: Session, workspace: str, document_id: str) -> DocumentVersion | None:
    return session.query(DocumentVersion).filter_by(workspace_id=workspace, document_id=document_id).one_or_none()


def declare_supersedes(session: Session, workspace: str, document_id: str, previous_document_id: str) -> Declared:
    """Record that ``document_id`` is the version after ``previous_document_id``, in this workspace."""
    require_document(session, document_id, workspace)
    require_document(session, previous_document_id, workspace)
    if document_id == previous_document_id:
        raise InvalidInput("a document cannot supersede itself")
    # Two attempts: a statement that loses a race to another statement about a different document (both opening the
    # earlier document's line) is the statement after it, as if made a moment later. Before 2026-10-08 it was refused
    # with "placed by another request" although its own document was in no line (QA campaign, two versions of one base).
    for _ in range(2):
        placed = _placed(session, workspace, document_id)
        if placed is not None:
            if placed.supersedes_document_id == previous_document_id:
                return Declared(placed, created=False)
            raise Conflict("This document already has a place in a line of versions. A version supersedes one document, and that cannot be changed.")
        try:
            previous = _placed(session, workspace, previous_document_id)
            if previous is None:  # the earlier document opens a line
                previous = DocumentVersion(workspace_id=workspace, lineage_id=new_id(), document_id=previous_document_id, supersedes_document_id=None)
                session.add(previous)
                session.flush()
            version = DocumentVersion(
                workspace_id=workspace, lineage_id=previous.lineage_id, document_id=document_id, supersedes_document_id=previous_document_id
            )
            session.add(version)
            session.commit()
            return Declared(version, created=True)
        except IntegrityError:
            # Another request placed one of the two between the lookup and the insert; the next pass reads what it recorded.
            session.rollback()
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
