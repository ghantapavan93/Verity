"""Use case: an uploaded file becomes a Document with canonical, addressable sections.

Documents are content-addressed. The same bytes read by the same reader are one document, so a
second upload hands back the stored one, with its runs and findings, instead of a duplicate. The
original bytes are kept under data/documents by hash so an evidence pack can carry them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..errors import InvalidInput, TooLarge
from ..hashing import sha256_bytes
from ..ingest import PARSER_VERSION, UnsupportedFile, ingest
from ..models import Document, Section

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class IngestedDocument:
    document: Document
    created: bool  # False when the same bytes were already stored under the current reader


def original_path(document: Document) -> Path:
    """Where the uploaded bytes live: by content hash, with the original extension."""
    return settings.data_dir / "documents" / f"{document.sha256}{Path(document.name).suffix.lower()}"


def stored_document(session: Session, sha256: str) -> Document | None:
    """The document with these bytes as read by the current reader, if it exists."""
    return session.query(Document).filter(Document.sha256 == sha256, Document.parser_version == PARSER_VERSION).order_by(Document.created_at.desc()).first()


def ingest_document(session: Session, filename: str, data: bytes) -> IngestedDocument:
    if len(data) > MAX_UPLOAD_BYTES:
        raise TooLarge("file larger than 25 MB")
    existing = stored_document(session, sha256_bytes(data))
    if existing is not None:
        return IngestedDocument(existing, created=False)

    started = time.perf_counter()
    try:
        parsed = ingest(filename or "upload", data)
    except UnsupportedFile as error:
        raise InvalidInput(str(error)) from error
    parse_ms = round((time.perf_counter() - started) * 1000, 1)

    document = Document(
        name=parsed.name,
        media_type=parsed.media_type,
        sha256=parsed.sha256,
        pages=parsed.pages,
        parse_ms=parse_ms,
        parser_version=PARSER_VERSION,
        tracked_changes=parsed.tracked_changes,
        hidden_runs=parsed.hidden_runs,
    )
    document.sections = [Section(ordinal=i, number=s.number, heading=s.heading, text=s.text) for i, s in enumerate(parsed.sections)]
    session.add(document)
    session.commit()
    session.refresh(document)

    path = original_path(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return IngestedDocument(document, created=True)
