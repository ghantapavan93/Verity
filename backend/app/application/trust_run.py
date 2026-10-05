"""Use cases: why a run's findings are trusted, and what a later version of the document does to them.

Both read the record and write nothing. A finished run is immutable, so its manifest is derived whenever it is asked
for and is the same every time; a revised document never changes a run, it is compared with one.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from ..errors import Conflict
from ..ingest import PARSER_VERSION, TooLargeToRead, UnsupportedFile, ingest
from ..models import TERMINAL_STAGES, Document, Run
from ..runs.versions import SEMANTIC_VERSIONS, stale_versions
from ..trust.compile import FindingRecord, SpanRecord, compile_manifest
from ..trust.diff import TrustDiff, trust_diff
from ..trust.model import SectionText, TrustManifest, snapshot_hash
from .ingest_document import original_path, stored_document
from .versions import is_later_version
from .workspace import require_document


def sections_of(document: Document) -> tuple[SectionText, ...]:
    return tuple(SectionText(index, s.number, s.heading, s.text) for index, s in enumerate(document.sections))


def document_snapshot(document: Document) -> str:
    return snapshot_hash(document.parser_version or "", sections_of(document))


@lru_cache(maxsize=32)
def _read_again(path: Path, name: str, reader: str) -> tuple[SectionText, ...] | None:
    """The stored bytes as today's reader reads them, or None when they cannot be read. Nothing is written. Cached by
    path and reader: the bytes are named by their hash and never change, so one reading per reader is enough."""
    del reader  # part of the key only: a new reader is a new reading
    try:
        parsed = ingest(name, path.read_bytes())
    except (UnsupportedFile, TooLargeToRead, OSError):
        return None
    return tuple(SectionText(index, s.number, s.heading, s.text) for index, s in enumerate(parsed.sections))


def current_reading(session: Session, document: Document) -> tuple[SectionText, ...] | None:
    """The same document as today's reader reads it: the stored reading of these bytes by the current reader when
    there is one, otherwise the original bytes read again. None when neither exists. Asked only for a document an
    earlier reader read; a run's own sections are never replaced by it."""
    stored = stored_document(session, document.sha256)
    if stored is not None:
        return sections_of(stored)
    original = original_path(document)
    return _read_again(original, document.name, PARSER_VERSION) if original.is_file() else None


def manifest_of(session: Session, run: Run) -> TrustManifest:
    """The trust manifest of a finished run, from its record."""
    if run.stage not in TERMINAL_STAGES:
        raise Conflict("This run has not finished. There is nothing to account for yet.")
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
    return compile_manifest(
        run_id=run.id,
        document_id=document.id,
        document_sha256=run.document_sha256,
        reader_version=document.parser_version or "",
        current_reader=PARSER_VERSION,
        rule_versions={name: str(options.get(name) or "not recorded") for name in SEMANTIC_VERSIONS},
        stale_rules=stale_versions(options),
        sections=sections_of(document),
        findings=findings,
        current_reading=None if document.parser_version == PARSER_VERSION else current_reading(session, document),
    )


def diff_against(session: Session, workspace: str, run: Run, document_id: str) -> tuple[TrustDiff, Document]:
    """What the document, a later version of the one the run read, does to the run's findings.

    The later document must have been recorded as a later version in this workspace. Two unrelated documents can
    be compared by a machine, and the answer would be that everything is stale; calling a finding stale is a
    statement about the same contract, so it is made only where a person has said it is the same contract.
    """
    later = require_document(session, document_id, workspace)
    if later.id != run.document_id and not is_later_version(session, workspace, run.document_id, later.id):
        raise Conflict("That document has not been recorded as a later version of the one this run read. Record it as one first.")
    return trust_diff(manifest_of(session, run), sections_of(run.document), sections_of(later), later.parser_version or ""), later
