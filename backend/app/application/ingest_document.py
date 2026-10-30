"""Use case: an uploaded file becomes a Document with canonical, addressable sections.

Documents are content-addressed. The same bytes read by the same reader are one document, so a
second upload hands back the stored one, with its runs and findings, instead of a duplicate. The
original bytes are kept under data/documents by hash so an evidence pack can carry them.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import Busy, InvalidInput, TooLarge
from ..hashing import sha256_bytes, sha256_file
from ..ingest import PARSER_VERSION, TooLargeToRead, UnsupportedFile, base_name
from ..ingest.bounded import ReadingBusy, read_file
from ..ingest.coverage import coverage_report
from ..ingest.readers import SUFFIX_OF, file_type, read
from ..models import Document, DocumentAccess, Section
from .quotas import admit, document_quotas, refuse_if_spent
from .workspace import document_is_curated, grant_document, is_public

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
READINGS_BUSY = "Other contracts are being read right now, so this one was not added. Try again in a minute."
STORE_BUSY = "The store is busy with another change, so nothing was written. Try again in a moment."
log = logging.getLogger(__name__)


class _Vanished(Exception):
    """The stored reading an upload was about to reuse was deleted (a purge) before its grant could be written."""


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
        data = original.read_bytes()
        if sha256_bytes(data) != document.sha256:
            log.warning("document_id=%s stored original damaged: its bytes are not the document's; not read", document.id)
            return None
        return coverage_report(read(reading_name(document), data).coverage, PARSER_VERSION, "reconstructed")
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


def ingest_document(session: Session, filename: str, data: bytes, workspace: str | None = None, *, reading_wait: float | None = None) -> IngestedDocument:
    """``workspace`` is the uploader's; it is granted the document. Deduplication stays by bytes and reader version: a
    second workspace uploading the same bytes gets a grant on the one stored reading. The bytes tell it nothing it did
    not hold; the stored name and date are the first uploader's, so each grant keeps the name its workspace gave
    (application/workspace.py display_name). "created" is from that workspace's side: new to it, or already its.
    ``reading_wait`` is the longest to wait for a reading slot (None: until one is free); past it, Busy."""
    refuse_if_too_large(len(data))
    refuse_unsupported_type(filename, data)
    given = base_name(filename or "upload")  # the name this workspace gave the file, kept on its grant
    existing = stored_document(session, sha256_bytes(data))
    if existing is not None:
        try:
            return _reuse(session, existing, data, workspace, given)
        except _Vanished:
            # A purge deleted the reading between the lookup and the grant: these bytes are read as new. Granted on the
            # deleted row, the upload was a 500 (a foreign key), or a 200 for a document that then answered 404.
            session.rollback()
            session.expunge_all()

    # New bytes are counted against the day's before they are read, so a file that would be refused is not read (advice:
    # the count that decides is made again with the row, in store below).
    refuse_if_spent(session, document_quotas(workspace, adding_bytes=len(data)))
    started = time.perf_counter()
    try:
        parsed = read_file(filename or "upload", data, wait=reading_wait)  # read where it can be stopped (ingest/bounded.py)
    except ReadingBusy as error:
        raise Busy(READINGS_BUSY, retry_after=30) from error
    except TooLargeToRead as error:
        raise TooLarge(str(error)) from error
    except UnsupportedFile as error:
        raise InvalidInput(str(error)) from error
    parse_ms = round((time.perf_counter() - started) * 1000, 1)

    document = Document(
        # The shared row of a workspace's upload is named by its type only, in every store: identical bytes from another
        # workspace share it, and the uploader's name lives on the uploader's grant (deleted with it in a public store,
        # application/retention.py). An invited store's row took the uploader's name until 2026-10-30, and showed it to
        # other workspaces through curated runs (document_names). The project's own uploads (no workspace) keep theirs.
        name=f"document{SUFFIX_OF.get(parsed.media_type, '')}" if workspace is not None else parsed.name,
        media_type=parsed.media_type,
        sha256=parsed.sha256,
        pages=parsed.pages,
        parse_ms=parse_ms,
        parser_version=PARSER_VERSION,
        tracked_changes=parsed.tracked_changes,
        hidden_runs=parsed.hidden_runs,
        coverage_json=json.dumps(coverage_report(parsed.coverage, PARSER_VERSION, "persisted")),
        size_bytes=len(data),
    )
    document.sections = [Section(ordinal=i, number=s.number, heading=s.heading, text=s.text, part=s.part) for i, s in enumerate(parsed.sections)]

    def store() -> Document:
        # The bytes are on disk before the row exists. The row used to be committed first: a write that failed after it
        # left a document with no original, and every later upload of the same bytes was handed that row without the
        # write being tried again (fault injection, 2026-10-02). Written once the quotas have admitted the upload, so a
        # refused upload leaves no file behind.
        keep_original(document, data)
        session.add(document)
        # The uploader's grant is written in the same transaction as the document. Committed apart, a request that read
        # the row between the two commits saw a document with no grant, which the read rules call curated, and was
        # granted nothing: told the upload worked, then refused it (5 of 50 races, audit 2026-10-09). A crash in the gap
        # left an ungranted row, and the public API refused to start on it.
        if workspace is not None:
            session.flush()
            grant_document(session, document, workspace, given)
        return document

    try:
        # The workspace's quotas are counted again here, under the write lock, with the grant they limit: the count made
        # before the reading (api/access.admit_upload) was passed by every upload of a burst (war room F-13, 2026-10-13).
        admit(session, document_quotas(workspace, adding_bytes=len(data)), store)
    except IntegrityError:
        # Another request stored the same bytes between the lookup and the insert; the database kept its row (admit has
        # rolled this one back).
        winner = stored_document(session, parsed.sha256)
        if winner is None:
            raise
        try:
            # "Created" from this workspace's side: the race's loser was told a document new to it was "already in the
            # workbench" (stress test, 2026-10-30, authz 3).
            return _reuse(session, winner, data, workspace, given)
        except _Vanished:
            raise Busy(STORE_BUSY, retry_after=5) from None
    session.refresh(document)
    return IngestedDocument(document, created=True)


def _reuse(session: Session, document: Document, data: bytes, workspace: str | None, name: str) -> IngestedDocument:
    """These bytes are already stored as ``document``: its original is made whole if it is not, and the workspace is
    granted it. _Vanished when the row is deleted before the grant is written."""
    keep_original(document, data)  # the same bytes by hash: a file that is missing or damaged is written again here
    return IngestedDocument(document, created=_grant(session, document, workspace, new=False, name=name, data=data))


def _grant(session: Session, document: Document, workspace: str | None, new: bool, name: str, data: bytes | None = None) -> bool:
    """Grant the workspace the document. A document this upload created is always granted to its uploader; one already
    stored is granted unless it is curated (no grants at all, readable by every workspace) or already the workspace's.
    True when the grant is new: a document the workspace now holds, admitted against its quotas.

    Whether the stored row still exists, and its original with it, is decided under the write lock with the grant: the
    purge deletes a row and its file under the same lock (application/retention.py). Decided before it, an upload kept
    the file it saw, the purge then deleted it, and the row lived on with no original (stress test, 2026-10-30)."""
    if workspace is None:
        return False
    # A public store holds nothing curated (main.refuse_a_store_with_owner_records): a row with no grant there was left
    # behind, and reading it as curated answered an upload 200 with a document its uploader could neither read nor ask
    # about (stress test, 2026-10-30). It is granted like any other.
    if not new and not is_public(workspace) and document_is_curated(session, document.id):
        return False

    def create() -> DocumentAccess:
        if session.execute(select(Document.id).where(Document.id == document.id)).first() is None:  # read afresh, under the lock
            raise _Vanished
        if data is not None:
            original = original_path(document)
            if not original.exists():
                write_durable(original, data, document.sha256)
        return grant_document(session, document, workspace, name)

    _, created = admit(session, document_quotas(workspace), create, find=lambda: session.get(DocumentAccess, (workspace, document.id)))
    return created


def _holds(path: Path, sha256: str) -> bool:
    try:
        return sha256_file(path) == sha256
    except OSError:
        return False


def write_durable(path: Path, data: bytes, sha256: str) -> None:
    """``data`` under ``path``, whole or not at all, across a crash: written aside, flushed to the disk, then renamed into
    place (and the folder flushed, where the platform allows). With no flush, a crash soon after an upload could leave
    the name with its size and zeros for its bytes, and every pack of the document then failed its hash for good (stress
    test, 2026-10-30, ops 4). Windows refuses to replace a file another request is reading at that moment: tried again a
    few times, then a file standing there that holds these bytes is accepted, and anything else is Busy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.part")
    try:
        partial.write_bytes(data)
        with open(partial, "r+b") as handle:  # a handle that may write: Windows flushes only through one
            os.fsync(handle.fileno())
        for attempt in range(5):
            try:
                os.replace(partial, path)
                break
            except PermissionError:
                if _holds(path, sha256):
                    return
                time.sleep(0.05 * (attempt + 1))
        else:
            raise Busy(STORE_BUSY, retry_after=5)
        if os.name == "posix":
            folder = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(folder)
            finally:
                os.close(folder)
    finally:
        partial.unlink(missing_ok=True)


def keep_original(document: Document, data: bytes) -> None:
    """Store the uploaded bytes under their hash; the same bytes from any request are the same file. A file there is
    kept only when it holds them: a damaged one (cut short, zeroed by a crash) was kept as it was by every later upload
    of the same bytes, since only its name was checked (stress test, 2026-10-30, ops 4), and is now written again."""
    path = original_path(document)
    if path.is_file() and _holds(path, document.sha256):
        return
    if path.exists():
        log.warning("document_id=%s stored original damaged: written again from an upload of its bytes", document.id)
    write_durable(path, data, document.sha256)
