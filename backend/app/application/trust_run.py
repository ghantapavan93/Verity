"""Use cases: why a run's findings are trusted, and what a later version of the document does to them.

Both read the record and write nothing. A finished run is immutable, so its manifest is derived whenever it is asked
for and is the same every time; a revised document never changes a run, it is compared with one.
"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session

from ..errors import Conflict
from ..hashing import sha256_bytes
from ..ingest import PARSER_VERSION, TooLargeToRead, UnsupportedFile
from ..ingest.bounded import read_file
from ..models import TERMINAL_STAGES, Document, Run
from ..runs.versions import SEMANTIC_VERSIONS, earlier_versions, unknown_versions
from ..trust.compile import FindingRecord, SpanRecord, compile_manifest
from ..trust.diff import TrustDiff, trust_diff
from ..trust.model import TRUST_VERSION, SectionText, TrustManifest, snapshot_hash
from .ingest_document import original_path, reading_name, stored_document
from .versions import is_later_version
from .workspace import require_document


def sections_of(document: Document) -> tuple[SectionText, ...]:
    return tuple(SectionText(index, s.number, s.heading, s.text) for index, s in enumerate(document.sections))


def document_snapshot(document: Document) -> str:
    return snapshot_hash(document.parser_version or "", sections_of(document))


class _NotNow(Exception):
    """A reading refused at a bound, which load can cause: answered as unreadable now, never kept as unreadable."""


Reading = tuple[SectionText, ...] | None
# Documents are read again off the request's thread, one at a time, each once. A request waits REREAD_WAIT_SECONDS for
# its reading and is otherwise answered without it ("could not be read again"), while the reading finishes for the next
# request. Each request had read on a thread of the pool every sync route shares, waiting as long as a slot took: sixty
# at once held that pool and /api/health answered after 21.5 s (war room W5 p5, 2026-10-13). One at a time, so readings
# again never hold more than one of the READINGS_AT_ONCE slots uploads need (ingest/bounded.py).
REREAD_WAIT_SECONDS = 2.0
_KEPT = 32
# A reading holds the document's text, so it is kept for minutes, not for the life of the process, and every
# retention pass drops all of them (application/retention.py): kept by path, the reading of a deleted visitor's
# contract stayed in memory after its workspace was deleted (release integration, 2026-10-13).
READING_KEPT_SECONDS = 600.0
_rereads = ThreadPoolExecutor(max_workers=1, thread_name_prefix="verity-reread")
_readings: OrderedDict[tuple[Path, str, str], tuple[Future[Reading], float]] = OrderedDict()
_readings_lock = threading.Lock()


def _read_again(path: Path, name: str, reader: str, sha256: str = "") -> Reading:
    """The stored bytes as today's reader reads them, or None when they cannot be read now. Nothing is written. Kept by
    path and reader, the latest _KEPT: the bytes are named by their hash and never change, so one reading per reader is
    enough. A refusal at a bound, or a failure, is not kept: a reading timed out under load once stayed "unreadable"
    for the life of the process (counter-review, 2026-10-13)."""
    key = (path, name, reader)
    now = time.monotonic()
    with _readings_lock:
        for old_key, (old, asked) in list(_readings.items()):
            if old.done() and now - asked > READING_KEPT_SECONDS:
                del _readings[old_key]
        kept = _readings.get(key)
        if kept is None:
            reading = _rereads.submit(_read_once, path, name, sha256)
            _readings[key] = (reading, now)
            while len(_readings) > _KEPT:
                _, (dropped, _) = _readings.popitem(last=False)
                dropped.cancel()  # one not yet started is not read; one reading finishes unkept
        else:
            reading = kept[0]
            _readings.move_to_end(key)
    try:
        return reading.result(timeout=REREAD_WAIT_SECONDS)
    except TimeoutError:
        return None  # still waiting or being read: not read now, and asked again it may be
    except BaseException as failed:
        with _readings_lock:
            if key in _readings and _readings[key][0] is reading:
                del _readings[key]
        if isinstance(failed, (_NotNow, CancelledError)):  # refused at a bound, or dropped before it was read
            return None
        raise


def _read_once(path: Path, name: str, sha256: str = "") -> Reading:
    try:
        data = path.read_bytes()
        if sha256 and sha256_bytes(data) != sha256:
            # A damaged original is never read as the document (stress test, 2026-10-30, ops 4): not read now, and not
            # kept as unreadable, so the upload that writes it whole again is read the next time.
            raise _NotNow
        parsed = read_file(name, data)
    except TooLargeToRead as refused:  # before UnsupportedFile, which it is a kind of
        raise _NotNow from refused
    except (UnsupportedFile, OSError):
        return None
    return tuple(SectionText(index, s.number, s.heading, s.text) for index, s in enumerate(parsed.sections))


def forget_readings() -> None:
    """Drop every reading and manifest kept: after each retention pass, and in tests, which change the reader under the
    same path. Both hold a contract's text."""
    with _readings_lock:
        _readings.clear()
    with _manifests_lock:
        _manifests.clear()


# A finished run's manifest depends only on its record, its document's sections and today's rules, yet every GET of
# /trust and /trust/diff located every span in every section again: 10 s per GET on a real 2.8 MB filing with three
# spans, 62 to 73 s with fifteen (stress test, 2026-10-30, performance 6). It is worked out once per run and the rules it
# was worked out under, one request at a time, and kept like a reading: the latest MANIFESTS_KEPT, for minutes, dropped
# by every retention pass. One that could not read its document again is not kept (current_reading: a reading timed out
# under load must not stay "could not be read again").
MANIFESTS_KEPT = 64
ManifestKey = tuple[str, str, str, str, tuple[tuple[str, str], ...]]
_manifests: OrderedDict[ManifestKey, tuple[TrustManifest, float]] = OrderedDict()
_manifests_lock = threading.Lock()
_working_out: dict[ManifestKey, threading.Lock] = {}


def _kept_manifest(key: ManifestKey, now: float) -> TrustManifest | None:
    kept = _manifests.get(key)
    if kept is None or now - kept[1] > READING_KEPT_SECONDS:
        return None
    _manifests.move_to_end(key)
    return kept[0]


def current_reading(session: Session, document: Document) -> tuple[SectionText, ...] | None:
    """The same document as today's reader reads it: the stored reading of these bytes by the current reader when
    there is one, otherwise the original bytes read again. None when neither exists. Asked only for a document an
    earlier reader read; a run's own sections are never replaced by it."""
    stored = stored_document(session, document.sha256)
    if stored is not None:
        return sections_of(stored)
    original = original_path(document)
    return _read_again(original, reading_name(document), PARSER_VERSION, document.sha256) if original.is_file() else None


def manifest_of(session: Session, run: Run) -> TrustManifest:
    """The trust manifest of a finished run, from its record."""
    if run.stage not in TERMINAL_STAGES:
        raise Conflict("This run has not finished. There is nothing to account for yet.")
    key: ManifestKey = (run.id, run.document_sha256, PARSER_VERSION, TRUST_VERSION, tuple(sorted((k, str(v)) for k, v in SEMANTIC_VERSIONS.items())))
    with _manifests_lock:
        kept = _kept_manifest(key, time.monotonic())
        if kept is not None:
            return kept
        working = _working_out.setdefault(key, threading.Lock())
    with working:
        try:
            with _manifests_lock:
                kept = _kept_manifest(key, time.monotonic())  # worked out by the request this one waited for
            if kept is not None:
                return kept
            manifest, whole = _work_out(session, run)
            if whole:
                with _manifests_lock:
                    _manifests[key] = (manifest, time.monotonic())
                    while len(_manifests) > MANIFESTS_KEPT:
                        _manifests.popitem(last=False)
            return manifest
        finally:
            with _manifests_lock:
                _working_out.pop(key, None)


def _work_out(session: Session, run: Run) -> tuple[TrustManifest, bool]:
    """The manifest, and whether it may be kept: not when its document, read by an earlier reader, could not be read
    again now."""
    document = run.document
    index_of = {section.id: index for index, section in enumerate(document.sections)}
    findings = [
        FindingRecord(
            finding_id=finding.id,
            ordinal=finding.ordinal,
            topic=finding.topic,
            status=finding.status,
            spans=tuple(
                SpanRecord(
                    ordinal=span.ordinal,
                    quote=span.quote,
                    cited_label=span.cited_section_label,
                    verified=span.verified,
                    method=span.method,
                    section=index_of.get(span.section_id) if span.section_id else None,
                    start=span.start,
                    end=span.end,
                )
                for span in finding.spans
            ),
        )
        for finding in run.findings
    ]
    options = json.loads(run.options_json or "{}")
    again = None if document.parser_version == PARSER_VERSION else current_reading(session, document)
    manifest = compile_manifest(
        run_id=run.id,
        document_id=document.id,
        document_sha256=run.document_sha256,
        reader_version=document.parser_version or "",
        current_reader=PARSER_VERSION,
        rule_versions={name: str(options.get(name) or "not recorded") for name in SEMANTIC_VERSIONS},
        stale_rules=earlier_versions(options),
        unknown_rules=unknown_versions(options),
        sections=sections_of(document),
        findings=findings,
        current_reading=again,
    )
    return manifest, document.parser_version == PARSER_VERSION or again is not None


def later_version(session: Session, workspace: str, run: Run, document_id: str) -> Document:
    """The document a run may be compared with: the run's own, or one recorded as a later version of it in this
    workspace. Two unrelated documents can be compared by a machine, and the answer would be that everything is stale;
    calling a finding stale is a statement about the same contract, so it is made only where a person has said it is
    the same contract. Asked before the comparison is built, so a refused one costs nothing (api/trust.py)."""
    later = require_document(session, document_id, workspace)
    if later.id != run.document_id and not is_later_version(session, workspace, run.document_id, later.id):
        raise Conflict("That document has not been recorded as a later version of the one this run read. Record it as one first.")
    return later


def diff_with(session: Session, run: Run, later: Document) -> TrustDiff:
    """What the document, a later version of the one the run read (later_version), does to the run's findings."""
    return trust_diff(manifest_of(session, run), sections_of(run.document), sections_of(later), later.parser_version or "")
