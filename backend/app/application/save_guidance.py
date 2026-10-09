"""Use case: guidance text becomes a record, content-addressed. The same words are one guidance
row, so a run's fingerprint (which carries the guidance id) is the same whenever the same policy
is pasted, and the golden runner and the interface share records."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..errors import InvalidInput
from ..hashing import sha256_text
from ..ingest.invisible import visible_text
from ..models import Guidance
from .workspace import is_public


@dataclass(frozen=True)
class SavedGuidance:
    guidance: Guidance
    created: bool


def stored_guidance(session: Session, sha256: str, workspace: str | None = None) -> Guidance | None:
    """The guidance with these words that this workspace may use: its own, or a curated one (no workspace), the same
    rule as reading it (workspace.can_read_guidance): a public workspace uses only its own."""
    rows = session.query(Guidance).filter(Guidance.sha256 == sha256).order_by(Guidance.created_at).all()
    return next((g for g in rows if g.workspace_id == workspace or (g.workspace_id is None and not is_public(workspace))), None)


def save_guidance(session: Session, text: str, source: str = "pasted", workspace: str | None = None) -> SavedGuidance:
    text = visible_text(text).strip()  # guidance is read by the day parser too: no invisible characters in it
    if not text:
        # Found while tracing (2026-09-29): whitespace was stored as empty guidance and the status logic was told guidance existed.
        raise InvalidInput("guidance is empty once whitespace is removed; paste a rule, a note or an instruction, or ask without guidance")
    digest = sha256_text(text)
    existing = stored_guidance(session, digest, workspace)
    if existing is not None:
        return SavedGuidance(existing, created=False)
    guidance = Guidance(text=text, sha256=digest, source=source, workspace_id=workspace)
    session.add(guidance)
    session.commit()
    return SavedGuidance(guidance, created=True)
