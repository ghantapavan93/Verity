from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session, object_session

from ..application.trust_run import diff_with, document_snapshot, later_version, manifest_of
from ..application.versions import declare_supersedes, lineage
from ..application.workspace import require_run
from ..db import get_session
from ..document_names import display_name
from ..errors import Busy
from ..models import DocumentVersion, iso
from ..schemas import (
    DocumentVersionOut,
    SupersedesIn,
    TrustDependencyOut,
    TrustDiffOut,
    TrustEvidenceOut,
    TrustFactOut,
    TrustFindingChangeOut,
    TrustFindingOut,
    TrustManifestOut,
    TrustObligationChangeOut,
    TrustObligationOut,
    TrustSectionChangesOut,
)
from ..trust.diff import TrustDiff
from ..trust.model import TrustManifest
from .access import current_workspace, limit_document_reads, trust_reads_building

router = APIRouter(prefix="/api", tags=["trust"])


# ----------------------------------------------------------------------------- mapping


def manifest_out(manifest: TrustManifest) -> TrustManifestOut:
    return TrustManifestOut(
        manifest_id=manifest.manifest_id,
        trust_version=manifest.trust_version,
        run_id=manifest.run_id,
        document_id=manifest.document_id,
        document_sha256=manifest.document_sha256,
        snapshot_hash=manifest.snapshot_hash,
        reader_version=manifest.reader_version,
        rule_versions=dict(manifest.rule_versions),
        counts=manifest.counts(),
        findings=[
            TrustFindingOut(
                finding_id=proof.finding_id,
                ordinal=proof.ordinal,
                topic=proof.topic,
                recorded_status=proof.recorded_status,
                state=proof.state.value,
                evidence=[
                    TrustEvidenceOut(
                        span=e.span, quote=e.quote, located=e.located, section=e.section_name, start=e.start, end=e.end, method=e.method, places=e.places
                    )
                    for e in proof.evidence
                ],
                obligations=[
                    TrustObligationOut(
                        id=o.obligation_id,
                        need=o.need.value,
                        standing=o.standing.value,
                        reason=o.reason,
                        depends_on=[TrustDependencyOut(on=d.on.value, ref=d.ref) for d in o.depends_on],
                        span=o.span,
                        fact=TrustFactOut(kind=o.fact.kind.value, value=o.fact.value, surface=o.fact.surface) if o.fact else None,
                    )
                    for o in proof.obligations
                ],
            )
            for proof in manifest.findings
        ],
    )


def diff_out(diff: TrustDiff, from_document_id: str, to_document_id: str) -> TrustDiffOut:
    return TrustDiffOut(
        manifest_id=diff.manifest_id,
        run_id=diff.run_id,
        from_document_id=from_document_id,
        to_document_id=to_document_id,
        from_snapshot=diff.from_snapshot,
        to_snapshot=diff.to_snapshot,
        sections=TrustSectionChangesOut(
            identical=diff.sections.identical, changed=list(diff.sections.changed), removed=list(diff.sections.removed), added=list(diff.sections.added)
        ),
        sections_total=diff.sections_total,
        sections_searched=diff.sections_searched,
        sections_reused=diff.sections_reused,
        counts=diff.counts(),
        findings=[
            TrustFindingChangeOut(
                finding_id=f.finding_id,
                ordinal=f.ordinal,
                topic=f.topic,
                before=f.before.value,
                after=f.after.value,
                verdict=f.verdict.value,
                why=list(f.why),
                obligations=[
                    TrustObligationChangeOut(
                        id=o.obligation_id,
                        need=o.need.value,
                        before=o.before.value,
                        after=o.after.value,
                        verdict=o.verdict.value,
                        reason=o.reason,
                        places_before=o.places_before,
                        places_after=o.places_after,
                    )
                    for o in f.obligations
                ],
            )
            for f in diff.findings
        ],
    )


def version_out(version: DocumentVersion) -> DocumentVersionOut:
    document = version.document
    session = object_session(version)
    return DocumentVersionOut(
        lineage_id=version.lineage_id,
        document_id=document.id,
        name=display_name(session, document, version.workspace_id) if session is not None else document.name,
        sha256=document.sha256,
        snapshot_hash=document_snapshot(document),
        reader_version=document.parser_version,
        supersedes_document_id=version.supersedes_document_id,
        recorded_at=iso(version.created_at) or "",
    )


# ----------------------------------------------------------------------------- routes


@contextmanager
def _trust_read(request: Request) -> Iterator[None]:
    """A few trust reads built at a time (access.TRUST_READS_AT_ONCE), each counted in the public store as a contract
    view, only once it is built: a run or document this workspace cannot see, or a "try again", spends none of the hour."""
    if not trust_reads_building.acquire(blocking=False):
        raise Busy("Other readers' trust checks are being worked out; nothing was lost. Try again in a few seconds.", retry_after=5)
    try:
        limit_document_reads(request)
        yield
    finally:
        trust_reads_building.release()


@router.get("/runs/{run_id}/trust", response_model=TrustManifestOut)
def run_trust(run_id: str, request: Request, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> TrustManifestOut:
    """What each finding of a finished run stands on: its quotes, whether each stands once, the typed values they
    state, and the reader and rules it was made under."""
    run = require_run(session, run_id, workspace)
    with _trust_read(request):
        return manifest_out(manifest_of(session, run))


@router.get("/runs/{run_id}/trust/diff", response_model=TrustDiffOut)
def run_trust_diff(
    run_id: str,
    request: Request,
    document_id: str = Query(alias="documentId"),
    session: Session = Depends(get_session),
    workspace: str = Depends(current_workspace),
) -> TrustDiffOut:
    """What a later version of the document does to this run's findings: which are stale and why, which were
    established again, which the revision did not reach. Nothing is changed by asking."""
    run = require_run(session, run_id, workspace)
    later = later_version(session, workspace, run, document_id)
    with _trust_read(request):
        return diff_out(diff_with(session, run, later), run.document_id, later.id)


@router.post("/documents/{document_id}/supersedes", response_model=DocumentVersionOut, status_code=status.HTTP_201_CREATED)
def record_supersedes(
    document_id: str, body: SupersedesIn, response: Response, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)
) -> DocumentVersionOut:
    """Say that this document is the version after another. 201 when the statement is new, 200 when it was already made."""
    declared = declare_supersedes(session, workspace, document_id, body.previous_document_id)
    if not declared.created:
        response.status_code = status.HTTP_200_OK
    return version_out(declared.version)


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionOut])
def document_versions(document_id: str, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> list[DocumentVersionOut]:
    """The line of versions this document belongs to in this workspace, oldest first; empty when it is in none."""
    return [version_out(version) for version in lineage(session, workspace, document_id)]
