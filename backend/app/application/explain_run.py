"""Use case: the read-only explanation of a run, "Why this answer?", assembled from the record alone.

One projection, owned here so the interface renders what happened and never assembles domain truth itself.
Six things, each from persisted rows: what was read (the document, its reader and its coverage); what
retrieval chose (the candidates in rank order, and the ContextSlice of each that the prompt carried); the
exact model input, rebuilt and checked against the checking stage's hash; what the model proposed (its
own words, parsed from the stored raw output and correlated to the findings by ordinal); what the verifier
established for each quote (the SourceMatch: cited label, located section, method, occurrences, offsets,
and whether the located span lies inside the reconstructed slice the model saw); and the status as it was
recorded, with its source and its sentence.

Three rules keep it honest. The model's proposal is never guessed from a finding's text: it is
`raw_output` parsed under the shape the model was asked for, indexed by `Finding.ordinal`, or it is
reported as not reconstructable. A span is inside the model-visible context only when its offsets fall
within the ContextSlice for its section; nothing here assumes the window starts at zero. And no typed fact
or rule is recomputed by today's parser and presented as what the run established: the finding carries the
status, the source and the sentence that were recorded, and those are what is shown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..analysis.schema import AnalysisOut
from ..analysis.service import MAX_SECTION_CHARS_IN_PROMPT
from ..errors import NotFound
from ..models import Finding, Run, RunStage, Section
from ..schemas import (
    CoverageReport,
    ExplanationCandidate,
    ExplanationFinding,
    ExplanationReading,
    ExplanationReconstruction,
    ExplanationReproducibility,
    ModelProposal,
    ProposalEvidence,
    RecordedPolicyEvaluation,
    RunExplanation,
    SourceMatch,
)
from .ingest_document import coverage_of
from .reconstruct_input import ContextSlice, reconstruct_input
from .review_finding import review_out

PROPOSAL_NOT_RECONSTRUCTABLE = "Model proposal not reconstructable for this run."

# What each recorded status source means, in one sentence, so the interface repeats it rather than deciding it.
SOURCE_SUMMARIES: dict[str, str] = {
    "computed_days": "the status was computed by code from the duration in the verified quote and the rule in the guidance",
    "position_check": "lowered to needs review by code: the day count the model stated is not in the verified quote or the guidance",
    "ambiguous_fact": "lowered to needs review by code: the verified quote states a duration two ways that disagree",
    "reference_check": "lowered to needs review by code: the conclusion names a section this document does not have",
    "model_hint": "no deterministic policy evaluation: the status is the model's hint; no comparable durations were found in the quote and the guidance",
    "no_evidence": "no deterministic policy evaluation: no status was given, because a quoted passage could not be verified",
}
DETERMINISTIC_SOURCES = frozenset({"computed_days", "position_check", "ambiguous_fact", "reference_check"})


@dataclass(frozen=True)
class _Located:
    label: str | None
    heading: str


def _labels_by_section(run: Run) -> dict[str, tuple[str, str, str]]:
    """section id → (label, number, heading) for every candidate the run handed to the model."""
    try:
        candidates = json.loads(run.candidates_json or "[]")
    except ValueError:
        return {}
    return {c["section_id"]: (c["label"], c.get("number", ""), c.get("heading", "")) for c in candidates}


def _heading(number: str, heading: str) -> str:
    return f"§{number} · {heading}" if number else heading


def _reading(run: Run) -> ExplanationReading:
    document = run.document
    sections = list(document.sections)
    reading = next((s for s in run.stages if s.stage == "reading"), None)
    report = coverage_of(document)
    coverage = CoverageReport.model_validate(report) if report else None
    not_read = [f"{p.part.replace('_', ' ')} ({p.count})" for p in (coverage.parts if coverage else []) if p.status == "omitted" and p.count > 0]
    return ExplanationReading(
        document_id=document.id,
        document_name=document.name,
        document_sha256=document.sha256,
        reader_version=document.parser_version,
        pages=document.pages,
        sections=len(sections),
        numbered_sections=sum(1 for s in sections if s.number),
        tracked_changes=document.tracked_changes or 0,
        hidden_runs=document.hidden_runs or 0,
        coverage=coverage,
        not_read=not_read,
        recorded_sections_hash=reading.output_hash if reading else None,
    )


def _proposals(run: Run, findings: list[Finding]) -> tuple[list[ModelProposal], str | None]:
    """The model's own words, from the stored raw output under the shape it was asked for, one per finding by ordinal.
    Anything that does not fit that shape, or does not line up with the findings, is reported, never guessed."""
    if not run.raw_output:
        return [], PROPOSAL_NOT_RECONSTRUCTABLE
    try:
        parsed = AnalysisOut.model_validate_json(run.raw_output)
    except ValidationError:
        return [], PROPOSAL_NOT_RECONSTRUCTABLE
    if findings and (len(parsed.findings) != len(findings) or any(f.ordinal >= len(parsed.findings) for f in findings)):
        return [], PROPOSAL_NOT_RECONSTRUCTABLE
    return [
        ModelProposal(
            ordinal=ordinal,
            topic=item.topic,
            conclusion=item.conclusion,
            status_hint=item.status_hint,
            observed=item.observed,
            required=item.required,
            guidance_reference=item.guidance_reference,
            suggested_position=item.suggested_position,
            evidence=[ProposalEvidence(cited_label=e.section_id, quote=e.quote) for e in item.evidence],
        )
        for ordinal, item in enumerate(parsed.findings)
    ], None


def _inside(span_section_id: str | None, start: int, end: int, verified: bool, slices: dict[str, ContextSlice]) -> bool | None:
    """Whether the located span lies within the ContextSlice the model was shown for that section. None when there
    is nothing to compare: an unverified span, or a run whose slices could not be reconstructed."""
    if not verified or span_section_id is None:
        return None
    piece = slices.get(span_section_id)
    if piece is None:
        return None
    return piece.start <= start and end <= piece.end


def _findings(run: Run, findings: list[Finding], slices: dict[str, ContextSlice]) -> list[ExplanationFinding]:
    by_section = _labels_by_section(run)
    sections_by_id: dict[str, Section] = {s.id: s for s in run.document.sections}
    out: list[ExplanationFinding] = []
    for finding in findings:
        matches: list[SourceMatch] = []
        for span in finding.spans:
            located = by_section.get(span.section_id or "")
            section = sections_by_id.get(span.section_id or "")
            heading = _heading(located[1], located[2]) if located else (_heading(section.number, section.heading) if section else "")
            matches.append(
                SourceMatch(
                    quote=span.quote,
                    cited_label=span.cited_section_label,
                    located_section_id=span.section_id if span.verified else None,
                    located_label=located[0] if (located and span.verified) else None,
                    located_heading=heading if span.verified else "",
                    verified=span.verified,
                    method=span.method,
                    match_count=span.match_count,
                    start=span.start,
                    end=span.end,
                    relocated=span.method.startswith("relocated:"),
                    inside_model_visible_context=_inside(span.section_id, span.start, span.end, span.verified, slices),
                )
            )
        source = finding.status_source or ""
        out.append(
            ExplanationFinding(
                id=finding.id,
                ordinal=finding.ordinal,
                topic=finding.topic,
                conclusion=finding.conclusion,
                status=finding.status,
                shown=run.stage == "complete" and finding.status != "unresolved",
                source_matches=matches,
                recorded_policy_evaluation=RecordedPolicyEvaluation(
                    status=finding.status,
                    status_source=source,
                    status_reason=finding.status_reason,
                    deterministic=source in DETERMINISTIC_SOURCES,
                    summary=SOURCE_SUMMARIES.get(source, "no deterministic policy evaluation was recorded for this finding"),
                ),
                review=review_out(finding.review),
            )
        )
    return out


def explain_run(session: Session, run_id: str) -> RunExplanation:
    run = session.get(Run, run_id)
    if run is None:
        raise NotFound("run", run_id)
    findings = sorted(run.findings, key=lambda f: f.ordinal)
    rebuilt = reconstruct_input(session, run.id)
    slices = {piece.section_id: piece for piece in rebuilt.slices}
    lengths = {s.id: len(s.text) for s in run.document.sections}

    retrieval: list[ExplanationCandidate] = []
    for rank, (section_id, (label, number, heading)) in enumerate(_labels_by_section(run).items(), start=1):
        piece = slices.get(section_id)
        retrieval.append(
            ExplanationCandidate(
                rank=rank,
                label=label,
                section_id=section_id,
                number=number,
                heading=heading,
                characters=lengths.get(section_id, 0),
                slice_start=piece.start if piece else None,
                slice_end=piece.end if piece else None,
                truncated=piece.truncated if piece else None,
            )
        )
    outside = sum(lengths.get(piece.section_id, 0) - (piece.end - piece.start) for piece in rebuilt.slices)
    checking = next((s for s in run.stages if s.stage == "checking"), None)
    proposals, proposals_problem = _proposals(run, findings)

    reconstruction = ExplanationReconstruction(
        reconstructable=rebuilt.matches,
        problem=rebuilt.problem,
        recorded_input_sha256=rebuilt.recorded_input_sha256,
        rebuilt_input_sha256=rebuilt.input_sha256,
        window_chars=MAX_SECTION_CHARS_IN_PROMPT,
        characters_outside_context=outside if rebuilt.slices else None,
        question=run.question,
        has_guidance=run.guidance_id is not None,
        guidance_text=run.guidance.text if run.guidance else None,
        prompt_version=run.prompt_version,
        prompt_hash=run.prompt_hash,
        model=run.model,
        options=json.loads(run.options_json or "{}"),
        queue_note=_queue_note(checking),
    )
    return RunExplanation(
        run_id=run.id,
        question=run.question,
        stage=run.stage,
        reason=run.reason,
        reading=_reading(run),
        retrieval=retrieval,
        reconstruction=reconstruction,
        proposals=proposals,
        proposals_problem=proposals_problem,
        findings=_findings(run, findings, slices),
        reproducibility=ExplanationReproducibility(
            run_id=run.id,
            document_id=run.document_id,
            document_sha256=run.document_sha256,
            reader_version=run.document.parser_version,
            guidance_sha256=run.guidance_sha256,
            prompt_version=run.prompt_version,
            prompt_hash=run.prompt_hash,
            recorded_input_sha256=rebuilt.recorded_input_sha256,
            input_matches=rebuilt.matches,
            evidence_pack_path=f"/api/runs/{run.id}/evidence-pack",
        ),
    )


def _queue_note(checking: RunStage | None) -> str | None:
    """The admission wait the checking stage recorded in its detail ("queued 12 s behind 3"), if any."""
    if checking is None or not checking.detail or "queued" not in checking.detail:
        return None
    return checking.detail.split("·", 1)[-1].strip() if "·" in checking.detail else checking.detail
