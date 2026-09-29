"""Use case: guidance text becomes a record, content-addressed. The same words are one guidance
row, so a run's fingerprint (which carries the guidance id) is the same whenever the same policy
is pasted, and the golden runner and the interface share records."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..hashing import sha256_text
from ..models import Guidance


@dataclass(frozen=True)
class SavedGuidance:
    guidance: Guidance
    created: bool


def stored_guidance(session: Session, sha256: str) -> Guidance | None:
    return session.query(Guidance).filter(Guidance.sha256 == sha256).order_by(Guidance.created_at).first()


def save_guidance(session: Session, text: str, source: str = "pasted") -> SavedGuidance:
    text = text.strip()
    digest = sha256_text(text)
    existing = stored_guidance(session, digest)
    if existing is not None:
        return SavedGuidance(existing, created=False)
    guidance = Guidance(text=text, sha256=digest, source=source)
    session.add(guidance)
    session.commit()
    return SavedGuidance(guidance, created=True)
