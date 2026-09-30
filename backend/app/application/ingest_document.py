"""Use case: an uploaded file becomes a Document with canonical, addressable sections.

Documents are content-addressed. The same bytes read by the same reader are one document, so a
second upload hands back the stored one, with its runs and findings, instead of a duplicate. The
original bytes are kept under data/documents by hash so an evidence pack can carry them.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import InvalidInput, TooLarge
from ..hashing import sha256_bytes
from ..ingest import PARSER_VERSION, TooLargeToRead, UnsupportedFile, ingest
from ..ingest.coverage import coverage_report
from ..ingest.readers import read
from ..models import Document, Section

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class IngestedDocument:
    document: Document
    created: bool  # False when the same bytes were already stored under the current reader


def original_path(document: Document) -> Path:
    """Where the uploaded bytes live: by content hash, with the original extension."""
    return settings.data_dir / "documents" / f"{document.sha256}{Path(document.name).suffix.lower()}"


def coverage_of(document: Document) -> dict[str, object] | None:
    """What the reading did with each part of the file, with its schema version, reader version and source. Persisted at
    upload since 2026-09-29; for a reading made before that, reconstructed from the stored bytes under the same reader,
    labelled "reconstructed", never written back (a document a finished run read is immutable). None when the bytes
    are gone or the reader has moved on."""
    if document.coverage_json:
        loaded: dict[str, object] = json.loads(document.coverage_json)
        return loaded
    original = original_path(document)
    if document.parser_version != PARSER_VERSION or not original.exists():
        return None
    try:
        return coverage_report(read(document.name, original.read_bytes()).coverage, PARSER_VERSION, "reconstructed")
    except (UnsupportedFile, TooLargeToRead, OSError):
        return None


def stored_document(session: Session, sha256: str) -> Document | None:
    """The document with these bytes as read by the current reader, if it exists."""
    return session.query(Document).filter(Document.sha256 == sha256, Document.parser_version == PARSER_VERSION).order_by(Document.created_at.desc()).first()


def refuse_if_too_large(size: int | None) -> None:
    """The 25 MB rule, applied to a declared size before a body is read as well as to the bytes once they are."""
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise TooLarge("file larger than 25 MB")


def ingest_document(session: Session, filename: str, data: bytes) -> IngestedDocument:
    refuse_if_too_large(len(data))
    existing = stored_document(session, sha256_bytes(data))
    if existing is not None:
        return IngestedDocument(existing, created=False)

    started = time.perf_counter()
    try:
        parsed = ingest(filename or "upload", data)
    except TooLargeToRead as error:
        raise TooLarge(str(error)) from error
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
        coverage_json=json.dumps(coverage_report(parsed.coverage, PARSER_VERSION, "persisted")),
    )
    document.sections = [Section(ordinal=i, number=s.number, heading=s.heading, text=s.text) for i, s in enumerate(parsed.sections)]
    session.add(document)
    try:
        session.commit()
    except IntegrityError:
        # Another request stored the same bytes between the lookup and the insert; the database kept its row.
        session.rollback()
        winner = stored_document(session, parsed.sha256)
        if winner is None:
            raise
        keep_original(winner, data)
        return IngestedDocument(winner, created=False)
    session.refresh(document)
    keep_original(document, data)
    return IngestedDocument(document, created=True)


def keep_original(document: Document, data: bytes) -> None:
    """Store the uploaded bytes under their hash once; the same bytes from any request are the same file."""
    path = original_path(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
