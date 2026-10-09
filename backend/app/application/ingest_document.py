"""Use case: an uploaded file becomes a Document with canonical, addressable sections.

Documents are content-addressed. The same bytes read by the same reader are one document, so a
second upload hands back the stored one, with its runs and findings, instead of a duplicate. The
original bytes are kept under data/documents by hash so an evidence pack can carry them.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import InvalidInput, TooLarge
from ..hashing import sha256_bytes
from ..ingest import PARSER_VERSION, TooLargeToRead, UnsupportedFile, base_name, ingest
from ..ingest.coverage import coverage_report
from ..ingest.readers import SUFFIX_OF, file_type, read
from ..models import Document, Section
from .workspace import document_is_curated, grant_document, is_public

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class IngestedDocument:
    document: Document
    created: bool  # False when the same bytes were already stored under the current reader


def document_suffix(document: Document) -> str:
    """The extension of the type the document's bytes were checked as (Document.media_type); the name's only when the
    media type is not one this reader knows."""
    return SUFFIX_OF.get(document.media_type) or Path(document.name).suffix.lower()


def reading_name(document: Document) -> str:
    """The document's name ending in its type's extension: what the stored bytes are read again under, and the name of
    the original file in an evidence pack. A name cut before 2026-10-08 may have lost its extension; the type has not."""
    suffix = document_suffix(document)
    return document.name if document.name.lower().endswith(suffix) else f"{document.name}{suffix}"


def original_path(document: Document) -> Path:
    """Where the uploaded bytes live: by content hash, with the extension of the document's type. Bytes kept before
    2026-10-08 under a name cut through its extension sit where that name put them (no extension, or a fragment of the
    name), and are found there."""
    folder = settings.data_dir / "documents"
    path = folder / f"{document.sha256}{document_suffix(document)}"
    legacy = folder / f"{document.sha256}{Path(document.name).suffix.lower()}"
    return legacy if not path.exists() and legacy.exists() else path


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
        return coverage_report(read(reading_name(document), original.read_bytes()).coverage, PARSER_VERSION, "reconstructed")
    except (UnsupportedFile, TooLargeToRead, OSError):
        return None


def stored_document(session: Session, sha256: str) -> Document | None:
    """The document with these bytes as read by the current reader, if it exists."""
    return session.query(Document).filter(Document.sha256 == sha256, Document.parser_version == PARSER_VERSION).order_by(Document.created_at.desc()).first()


def refuse_if_too_large(size: int | None) -> None:
    """The 25 MB rule, applied to a declared size before a body is read as well as to the bytes once they are."""
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise TooLarge("file larger than 25 MB")


def refuse_unsupported_type(filename: str, data: bytes) -> None:
    """The type is checked, name against bytes, before the bytes are looked up: a known document under a .docm name, or
    no name, was "reused" without its type ever being checked (sweep, 2026-10-01), and a known PDF under a .txt name was
    handed back as the PDF while unknown PDF bytes under that name were read as text (QA campaign, 2026-10-08)."""
    try:
        file_type(filename, data)
    except UnsupportedFile as error:
        raise InvalidInput(str(error)) from error


def ingest_document(session: Session, filename: str, data: bytes, workspace: str | None = None) -> IngestedDocument:
    """``workspace`` is the uploader's; it is granted the document. Deduplication stays by bytes and reader version: a
    second workspace uploading the same bytes gets a grant on the one stored reading. The bytes tell it nothing it did
    not hold; the stored name and date are the first uploader's, so each grant keeps the name its workspace gave
    (application/workspace.py display_name). "created" is from that workspace's side: new to it, or already its."""
    refuse_if_too_large(len(data))
    refuse_unsupported_type(filename, data)
    given = base_name(filename or "upload")  # the name this workspace gave the file, kept on its grant
    existing = stored_document(session, sha256_bytes(data))
    if existing is not None:
        keep_original(existing, data)  # the same bytes by hash: a row whose file is not there is completed here
        new_to_workspace = _grant(session, existing, workspace, new=False, name=given)
        return IngestedDocument(existing, created=new_to_workspace)

    started = time.perf_counter()
    try:
        parsed = ingest(filename or "upload", data)
    except TooLargeToRead as error:
        raise TooLarge(str(error)) from error
    except UnsupportedFile as error:
        raise InvalidInput(str(error)) from error
    parse_ms = round((time.perf_counter() - started) * 1000, 1)

    document = Document(
        # In a public workspace the shared row is named by its type only: identical bytes from another visitor share
        # it, and the uploader's name lives on the uploader's grant, deleted with it (application/retention.py).
        name=f"document{SUFFIX_OF.get(parsed.media_type, '')}" if is_public(workspace) else parsed.name,
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
    # The bytes are on disk before the row exists. The row used to be committed first: a write that failed after it
    # left a document with no original, and every later upload of the same bytes was handed that row without the
    # write being tried again (fault injection, 2026-10-02). A file with no row is harmless: it is named by its hash.
    keep_original(document, data)
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
        _grant(session, winner, workspace, new=False, name=given)
        return IngestedDocument(winner, created=False)
    session.refresh(document)
    _grant(session, document, workspace, new=True, name=given)
    return IngestedDocument(document, created=True)


def _grant(session: Session, document: Document, workspace: str | None, new: bool, name: str) -> bool:
    """Grant the workspace the document. A document this upload created is always granted to its uploader; one already
    stored is granted unless it is curated (no grants at all, readable by every workspace) or already the workspace's.
    True when the grant is new."""
    if workspace is None:
        return False
    if not new and document_is_curated(session, document.id):
        return False
    if not grant_document(session, document, workspace, name):
        return False
    session.commit()
    return True


def keep_original(document: Document, data: bytes) -> None:
    """Store the uploaded bytes under their hash once; the same bytes from any request are the same file."""
    path = original_path(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Written aside and renamed, so a write cut short never leaves half a file under the hash's name.
        partial = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.part")
        try:
            partial.write_bytes(data)
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)
