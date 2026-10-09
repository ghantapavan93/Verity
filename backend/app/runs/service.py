"""The run: reading → finding evidence → checking → verifying → complete | unresolved | failed.

A plain, typed orchestration service. It has state (stage rows) and branches (verified or
not), but no resumable graph yet; LangGraph is added when the flow needs what it offers
(ADR 0003).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial

from sqlalchemy.orm import Session

from ..analysis.service import MAX_SECTION_CHARS_IN_PROMPT, SectionForPrompt, analyze, build_user_message, load_prompt, window_of
from ..config import settings
from ..document_names import run_prompt_name
from ..hashing import sha256_text
from ..ingest.sections import stated_clause_numbers
from ..models import (
    RUN_STAGES,
    TERMINAL_STAGES,
    EvidenceSpan,
    Finding,
    RetrievalModeName,
    Run,
    RunReasonName,
    RunStage,
    RunStageName,
    Section,
    as_utc,
    utcnow,
)
from ..providers.base import ModelProvider, ProviderError
from ..retrieval.aliases import ALIASES_SHA256, expand_query
from ..retrieval.hybrid import HybridIndex, ollama_embed
from ..retrieval.lexical import LexicalIndex
from ..verify.spans import Located, locate
from .events import StageEvent, bus
from .owner import this_process
from .prose import label_handles
from .status import Decision, Grounds, check_references, decide, enclosing_sentences, settle_together, unseen_references
from .transitions import assert_transition
from .versions import stale_versions

log = logging.getLogger(__name__)

# Labels the model cites; stable per run because sections are handed over in document order.
SECTION_LABEL = "sec_{ordinal}"


@dataclass
class RunInputs:
    run: Run
    sections: list[Section]
    guidance_text: str | None


def _set_stage(
    session: Session, run: Run, stage: RunStageName, detail: str | None = None, *, input_hash: str | None = None, error_code: str | None = None
) -> None:
    """Enter a stage: the previous stage row is closed as ok with its duration, the new row opened.
    A terminal stage is opened and closed in the same write, so a finished run never carries a
    running row and needs no later update (the database forbids one)."""
    if stage not in RUN_STAGES:
        raise ValueError(f"unknown run stage {stage!r}")
    now = utcnow()
    previous = session.query(RunStage).filter_by(run_id=run.id).order_by(RunStage.id.desc()).first()
    assert_transition(previous.stage if previous is not None else None, stage)
    if previous is not None and previous.completed_at is None:
        # Closed and committed before the run can turn terminal: once it has, the database refuses
        # every update to the run's rows, including this one.
        previous.completed_at = now
        previous.duration_ms = round((now - as_utc(previous.at)).total_seconds() * 1000, 1)
        previous.status = "failed" if stage == "failed" else "ok"
        if previous.status == "failed":
            previous.error_code = error_code
        session.commit()
    run.stage = stage
    row = RunStage(run_id=run.id, stage=stage, at=now, detail=detail, status="running", input_hash=input_hash, owner=this_process().render())
    if stage in TERMINAL_STAGES:
        row.completed_at = now
        row.duration_ms = 0.0
        row.status = "ok" if stage == "complete" else "failed"
        row.error_code = error_code
    session.add(row)
    session.commit()
    if previous is not None:
        log.info(
            "run_id=%s document_id=%s stage=%s after=%s duration_ms=%.0f status=%s",
            run.id,
            run.document_id,
            stage,
            previous.stage,
            previous.duration_ms or 0,
            previous.status,
        )
    else:
        log.info("run_id=%s document_id=%s stage=%s", run.id, run.document_id, stage)
    bus.publish(StageEvent(run.id, stage, detail))


def _note_stage(session: Session, run: Run, stage: RunStageName, detail: str, *, output_hash: str | None = None, attempt: int | None = None) -> None:
    """Record what a stage produced once it has run: counts, timing, the hash of its output, attempts."""
    row = session.query(RunStage).filter_by(run_id=run.id, stage=stage).order_by(RunStage.id.desc()).first()
    if row is not None:
        row.detail = detail
        if output_hash is not None:
            row.output_hash = output_hash
        if attempt is not None:
            row.attempt = attempt
        session.commit()
    session.expire(run, ["stages"])
    bus.publish(StageEvent(run.id, stage, detail))


def _label(section: Section) -> str:
    """The section as the model saw it named, so a quote that copies the label in front can be forgiven."""
    return f"{section.number} {section.heading}".strip()


def verify_evidence(
    quote: str, cited_label: str, by_label: Mapping[str, Section], chosen: Sequence[Section], window: int = MAX_SECTION_CHARS_IN_PROMPT
) -> tuple[Section | None, Located | None, str]:
    """Where a proposed quote is, if anywhere: first in the section the model cited, then in the other
    candidates (a real quote attributed to the wrong section is kept and marked relocated). The search is
    bounded to the first ``window`` characters of each section, which is what the prompt carried: a quote from
    a tail the model never saw is not evidence the model had (verifier v5; over the record before it, no verified
    span lay beyond the window). The one implementation; replay verification (application.reverify_run) uses it too."""
    section = by_label.get(cited_label)
    located = locate(quote, section.text[:window], _label(section)) if section is not None else None
    if located is not None:
        return section, located, located.method
    for candidate in chosen:
        found = locate(quote, candidate.text[:window], _label(candidate))
        if found is not None:
            return candidate, found, f"relocated:{found.method}"
    return section, None, "none"


class StaleRun(RuntimeError):
    """The run was created under rules or a configuration the code executing it no longer has. It is not executed."""


@dataclass(frozen=True)
class FrozenOptions:
    """What a run recorded when it was created, read back for its execution. The environment chooses the defaults when
    a run is created; after that the run executes from its own record, whatever the process's settings have become
    (found 2026-10-02: a run created at six sections and executed after the setting became one was handed one, with
    six on its record)."""

    retrieval_k: int
    retriever: str
    aliases: bool
    embed_model: str
    window: int
    decoding: Mapping[str, object]

    @classmethod
    def of(cls, run: Run) -> FrozenOptions:
        options: dict[str, object] = json.loads(run.options_json or "{}")
        stale = stale_versions(options)
        if stale:
            raise StaleRun(f"This run was created under other rules than the code now has ({'; '.join(stale)}). It was not executed; ask again.")
        recorded_aliases = options.get("retrieval_aliases")
        if recorded_aliases and recorded_aliases != ALIASES_SHA256[:12]:
            raise StaleRun(f"This run was created with alias table {recorded_aliases}; the table is now {ALIASES_SHA256[:12]}. It was not executed; ask again.")
        if "retrieval_k" not in options:
            raise StaleRun("This run recorded no retrieval_k, so there is nothing to execute it from. It was not executed; ask again.")
        return cls(
            retrieval_k=int(str(options["retrieval_k"])),
            retriever=str(options.get("retrieval", "bm25")),  # only a non-default retriever is recorded (application.start_run)
            aliases=bool(recorded_aliases),
            embed_model=str(options.get("embed_model", settings.embed_model)),
            window=window_of(options),
            decoding={"model": options.get("model") or run.model, **{name: options[name] for name in ("temperature", "seed", "num_ctx") if name in options}},
        )


def _retrieve(sections: list[Section], question: str, guidance: str | None, frozen: FrozenOptions) -> tuple[list[Section], RetrievalModeName]:
    """The sections handed to the model, and how they were chosen. `opening_fallback` means the retriever ranked no
    section for the question, and the opening sections were handed over instead: they were not chosen for it."""
    pairs = [(s.heading, s.text) for s in sections]
    hybrid = frozen.retriever == "hybrid"
    index: LexicalIndex | HybridIndex = HybridIndex(pairs, embed=partial(ollama_embed, model=frozen.embed_model)) if hybrid else LexicalIndex(pairs)
    query = question if not guidance else f"{question} {guidance}"
    if frozen.aliases:
        query = expand_query(query)
    candidates = index.search(query, frozen.retrieval_k)
    if not candidates and sections:
        # A question the retriever ranks nothing for still gets the opening sections rather than nothing.
        return sections[: min(frozen.retrieval_k, len(sections))], "opening_fallback"
    return [sections[c.index] for c in candidates], "hybrid_match" if hybrid else "lexical_match"


def bound_to(provider: ModelProvider, frozen: FrozenOptions) -> ModelProvider:
    """The provider bound to the run's recorded model and decoding settings, when it is a provider that has any
    (a replayed or a test provider answers from its record and has none)."""
    bind = getattr(provider, "with_options", None)
    return bind(frozen.decoding) if bind is not None else provider


def execute_run(session: Session, run_id: str, provider: ModelProvider) -> None:
    run = session.get(Run, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    try:
        _set_stage(session, run, "reading", input_hash=run.document_sha256)
        frozen = FrozenOptions.of(run)
        provider = bound_to(provider, frozen)
        document = run.document
        sections = list(document.sections)
        guidance_text = run.guidance.text if run.guidance else None
        pages = f"{document.pages} pages · " if document.pages else ""
        _note_stage(session, run, "reading", f"{pages}{len(sections)} sections", output_hash=sha256_text("\x1f".join(s.text for s in sections)))

        _set_stage(session, run, "finding_evidence", input_hash=sha256_text(f"{run.question}\x1f{run.guidance_sha256 or ''}"))
        chosen, retrieval_mode = _retrieve(sections, run.question, guidance_text, frozen)
        by_label = {SECTION_LABEL.format(ordinal=s.ordinal): s for s in chosen}
        # What a handle reads as once the model's prose reaches a person.
        labels = {label: (f"§{s.number}" if s.number else s.heading) for label, s in by_label.items()}
        run.candidates_json = json.dumps([{"label": label, "section_id": s.id, "number": s.number, "heading": s.heading} for label, s in by_label.items()])
        # A field, not only a sentence on the stage: every projection of the run can say which it was.
        run.retrieval_mode = retrieval_mode
        session.commit()
        _note_stage(
            session,
            run,
            "finding_evidence",
            # Said on the record when it happens: over the store on 2026-10-02 it had happened in 32 of 850 runs, and
            # the stage read "6 candidate sections" all the same, as if they had been chosen for the question. The
            # sentence says what the retriever did, not why: on an agreement of two sections BM25 scores every section
            # at zero or below although both contain the question's words, and "no section matched the question's
            # words" was untrue there.
            f"{len(chosen)} candidate section{'s' if len(chosen) != 1 else ''}"
            if retrieval_mode != "opening_fallback"
            else f"retrieval ranked no section for this question; the opening {len(chosen)} of {len(sections)} were read instead",
            output_hash=sha256_text("\x1f".join(s.id for s in chosen)),
        )

        prompt = load_prompt(run.prompt_version)
        window = frozen.window
        user_message = build_user_message(
            run.question,
            guidance_text,
            run_prompt_name(run),
            [SectionForPrompt(label, s.number, s.heading, s.text) for label, s in by_label.items()],
            window=window,
        )
        _set_stage(
            session, run, "checking", "against guidance" if guidance_text else "against the question", input_hash=sha256_text(prompt.sha256 + user_message)
        )
        result = analyze(provider, prompt, user_message)
        run.raw_output = result.generation.text
        run.input_tokens = result.generation.input_tokens
        run.output_tokens = result.generation.output_tokens
        run.latency_ms = result.generation.latency_ms
        run.model = result.generation.model
        session.commit()
        seconds = (result.generation.latency_ms or 0) / 1000
        answered = f"model answered in {seconds:.0f} s" if seconds >= 1 else "model answered"
        if result.attempts > 1:
            answered += f" · attempt {result.attempts}"
        admitted = getattr(provider, "last", None)
        if admitted is not None and admitted.queue_wait_ms >= 1000:
            answered += f" · queued {admitted.queue_wait_ms / 1000:.0f} s behind {admitted.queue_depth_at_arrival + 1}"
        _note_stage(session, run, "checking", answered, output_hash=sha256_text(result.generation.text), attempt=result.attempts)

        if result.proposal is None:
            _finish(
                session,
                run,
                "failed",
                error=f"The analysis model did not return a valid result after {result.attempts} attempts. Last problem: {result.validation_error}",
                reason="invalid_output",
            )
            return

        _set_stage(session, run, "verifying", input_hash=sha256_text(result.generation.text))
        proposal = result.proposal
        if proposal.insufficient_evidence or not proposal.findings:
            searched = ", ".join(f"§{s.number}" if s.number else s.heading for s in chosen)
            _note_stage(session, run, "verifying", "no passages to verify")
            _finish(
                session,
                run,
                "unresolved",
                # The product's sentence, about the sections handed over. The model's own note stays in the raw output:
                # it may word the absence as a fact about the agreement, which these sections cannot show.
                note=f"The model did not find a passage that answers this in the sections it was given. Sections searched: {searched}.",
                reason="insufficient_evidence",
            )
            return

        verified_any = False
        verified_count = 0
        total_count = 0
        withheld_count = 0
        all_sections_by_id = {s.id: s for s in sections}
        every_section = [(s.number, s.heading) for s in sections]
        printed = stated_clause_numbers([s.text for s in sections])  # the clause numbers the document's own text opens
        handed = [(s.number, s.heading) for s in chosen]
        proposed: list[tuple[Finding, Decision, Grounds]] = []
        for ordinal, item in enumerate(proposal.findings):
            spans: list[EvidenceSpan] = []
            passages: list[str] = []
            dependencies: list[str] = []
            all_verified = bool(item.evidence)
            for span_ordinal, evidence in enumerate(item.evidence):
                section, located, method = verify_evidence(evidence.quote, evidence.section_id, by_label, chosen, window=window)
                verified = located is not None
                all_verified = all_verified and verified
                if located is not None and section is not None:
                    # What the sentences around the quote point at that the model was not handed (runs.status).
                    passage = enclosing_sentences(section.text, located.start, located.end)
                    passages.append(passage)
                    dependencies += [d for d in unseen_references(passage, every_section, handed) if d not in dependencies]
                total_count += 1
                verified_count += 1 if verified else 0
                spans.append(
                    EvidenceSpan(
                        ordinal=span_ordinal,
                        section_id=section.id if section is not None and section.id in all_sections_by_id else None,
                        cited_section_label=evidence.section_id,
                        start=located.start if located else -1,
                        end=located.end if located else -1,
                        quote=evidence.quote,
                        verified=verified,
                        method=method,
                        match_count=located.count if located else None,
                    )
                )
            decision = decide(
                item.status_hint,
                item.observed,
                item.required,
                guidance_text is not None,
                all_verified,
                quotes=[span.quote for span in spans if span.verified],
                guidance=guidance_text,
                topic=item.topic,
                dependencies=dependencies,
                passages=passages,
            )
            decision = check_references(decision, label_handles(item.conclusion, labels), (s.number for s in sections), by_label, printed)
            verified_any = verified_any or all_verified
            if not all_verified:
                withheld_count += 1
            finding = Finding(
                run_id=run.id,
                ordinal=ordinal,
                topic=label_handles(item.topic, labels)[:255],
                conclusion=label_handles(item.conclusion, labels),
                guidance_reference=label_handles(item.guidance_reference, labels) or None,
                observed=label_handles(item.observed, labels) or None,
                required=label_handles(item.required, labels) or None,
                suggested_position=label_handles(item.suggested_position, labels) or None,
                spans=spans,
            )
            found_in = tuple((span.section_id, all_sections_by_id[span.section_id].number) for span in spans if span.verified and span.section_id)
            proposed.append((finding, decision, Grounds(tuple(span.quote for span in spans if span.verified), tuple(passages), found_in)))
        # A pass code confirmed does not stand beside a shortfall code found in a finding that bears on it (runs.status).
        settled = settle_together([d for _, d, _ in proposed], [g for _, _, g in proposed], guidance_text)
        for (finding, _, _), decision in zip(proposed, settled, strict=True):
            finding.status, finding.status_source, finding.status_reason = decision.status, decision.source, decision.reason or None
            session.add(finding)
        session.commit()
        if total_count == 0:
            # An answer with no quoted passage is not a finding; the schema asks for at least one,
            # and this is the backstop when a provider ignores that.
            searched = ", ".join(f"§{s.number}" if s.number else s.heading for s in chosen)
            _note_stage(session, run, "verifying", "no passages to verify")
            _finish(
                session,
                run,
                "unresolved",
                note=f"The model answered without quoting any passage, so no finding is shown. Sections searched: {searched}.",
                reason="insufficient_evidence",
            )
            return
        verified_note = f"{verified_count} of {total_count} quote{'s' if total_count != 1 else ''} verified"
        if withheld_count:
            verified_note += f" · {withheld_count} finding{'s' if withheld_count != 1 else ''} withheld"
        located_spans = [(s.section_id, s.start, s.end, s.verified, s.method) for f in run.findings for s in f.spans]
        _note_stage(session, run, "verifying", verified_note, output_hash=sha256_text(json.dumps(located_spans, sort_keys=True)))

        if verified_any:
            _finish(session, run, "complete")
        else:
            _finish(
                session,
                run,
                "unresolved",
                note="The finding was withheld: the passages the model cited could not be matched verbatim to the uploaded document. "
                "The raw output is kept on the run.",
                reason="citations_unverified",
            )
    except StaleRun as error:
        log.warning("run_id=%s not executed: %s", run_id, error)
        _fail(session, run, str(error), "internal_error")
    except ProviderError as error:
        log.exception("run %s failed at the provider", run_id)
        _fail(session, run, str(error), "provider_error")
    except Exception as error:
        log.exception("run %s failed", run_id)
        _fail(session, run, f"{type(error).__name__}: {error}", "internal_error")


def _fail(session: Session, run: Run, error: str, reason: RunReasonName) -> None:
    """Record a failure. The session is rolled back first, because the failure may be the database's own: a run
    that staleness recovery in another process has already ended refuses every further write, and writing the
    failure into the same session raised again (found while tracing, 2026-09-29; seen at twenty concurrent runs
    the day before). A run another writer ended keeps that writer's record; this worker leaves quietly."""
    session.rollback()
    session.refresh(run)
    if run.stage in TERMINAL_STAGES:
        log.warning("run_id=%s already %s when its worker failed: %s", run.id, run.stage, error)
        return
    _finish(session, run, "failed", error=error, reason=reason)


def _finish(session: Session, run: Run, stage: RunStageName, note: str | None = None, error: str | None = None, reason: RunReasonName | None = None) -> None:
    run.note = note
    run.error = error
    run.reason = reason
    run.finished_at = utcnow()
    _set_stage(session, run, stage, note or error, error_code=reason if stage == "failed" else None)
