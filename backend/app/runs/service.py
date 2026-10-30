"""The run: reading → finding evidence → checking → verifying → complete | unresolved | failed.

A plain, typed orchestration service. It has state (stage rows) and branches (verified or
not), but no resumable graph yet; LangGraph is added when the flow needs what it offers
(ADR 0003).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import partial

from sqlalchemy.orm import Session

from ..analysis.service import SectionForPrompt, analyze, build_user_message, load_prompt, window_of
from ..config import settings
from ..document_names import run_prompt_name
from ..hashing import sha256_text
from ..ingest.sections import PARAGRAPH_SEPARATOR, PART_HEADING, stated_clause_numbers
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
from ..policy.durations import business_week, day_convention
from ..providers.base import ModelProvider, ProviderError
from ..retrieval.aliases import ALIAS_GROUPS, ALIASES_SHA256, WORDING, _phrase_in, expand_query
from ..retrieval.hybrid import HybridIndex, ollama_embed
from ..retrieval.lexical import LexicalIndex, tokenize
from ..verify.spans import Located, locate, verification_pass
from .events import StageEvent, bus
from .links import MAX_LINKS, Readable, _amending, _amendments, _changes_of, _definitions, _stated, because, linked
from .owner import this_process
from .prose import label_handles, unresolved_handles
from .relations import Note, Recorded, assess, dump, load, locate_relations, parts_of, relevant, unhanded_amendment
from .status import (
    Decision,
    Grounds,
    LeftOut,
    check_conditions,
    check_old_value,
    check_references,
    check_replaced,
    check_unhanded,
    check_values,
    decide,
    enclosing_sentences,
    left_out,
    settle_together,
    unseen_references,
    unshown_conditions,
)
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
        # A run's last line says why it ended (`reason=`): "unresolved" for an unverified quote and for no evidence, and
        # "failed" for a provider error and for output that is not the schema, read the same without it (ops audit).
        log.info(
            "run_id=%s document_id=%s stage=%s after=%s duration_ms=%.0f status=%s%s",
            run.id,
            run.document_id,
            stage,
            previous.stage,
            previous.duration_ms or 0,
            previous.status,
            f" reason={run.reason}" if stage in TERMINAL_STAGES and run.reason else "",
        )
    else:
        log.info("run_id=%s document_id=%s stage=%s", run.id, run.document_id, stage)
    bus.publish(StageEvent(run.id, stage, detail))


def _note_stage(
    session: Session, run: Run, stage: RunStageName, detail: str, *, output_hash: str | None = None, attempt: int | None = None, rounds: int | None = None
) -> None:
    """Record what a stage produced once it has run: counts, timing, the hash of its output, attempts and rounds."""
    row = session.query(RunStage).filter_by(run_id=run.id, stage=stage).order_by(RunStage.id.desc()).first()
    if row is not None:
        row.detail = detail
        if output_hash is not None:
            row.output_hash = output_hash
        if attempt is not None:
            row.attempt = attempt
        if rounds is not None:
            row.rounds = rounds
        session.commit()
    session.expire(run, ["stages"])
    bus.publish(StageEvent(run.id, stage, detail))


def _label(section: Section) -> str:
    """The section as the model saw it named, so a quote that copies the label in front can be forgiven."""
    return f"{section.number} {section.heading}".strip()


def verify_evidence(
    quote: str, cited_label: str, by_label: Mapping[str, Section], chosen: Sequence[Section], *, window: int
) -> tuple[Section | None, Located | None, str]:
    """Where a proposed quote is, if anywhere: first in the section the model cited, then in the other
    candidates (a real quote attributed to the wrong section is kept and marked relocated). The search is
    bounded to the first ``window`` characters of each section, which is what the prompt carried: a quote from
    a tail the model never saw is not evidence the model had (verifier v5; over the record before it, no verified
    span lay beyond the window). The one implementation; replay verification (application.reverify_run) uses it too."""
    section = by_label.get(cited_label)
    # The model was shown the first `window` characters; their end is not the text's end (verifier v11).
    located = locate(quote, section.text, _label(section), window) if section is not None else None
    if located is not None:
        return section, located, located.method
    for candidate in chosen:
        found = locate(quote, candidate.text, _label(candidate), window)
        if found is not None:
            return candidate, found, f"relocated:{found.method}"
    return section, None, "none"


def located_text(section: Section, located: Located) -> str:
    """The contract's characters a verified quote covers: what code reads a period or a value from, never the model's
    string. A quote verifies through what a tier forgives (a zero-width space, a direction mark, a typeset dash, case,
    punctuation), so the model's spelling of it can differ from the contract in exactly the characters a reader of
    numbers trips on: "9\u200b0 days" verified over the contract's "90 days" and was code's shortfall of 0 days, and
    "15 d\u200eays" over "15 days" hid code's own (stress test, 2026-10-30: hostile model, verifier). A quote found once
    the section's label is set aside (verifier "unprefixed") and starting where the text does may carry the heading's
    words of a sentence the reader split across heading and text ("… Customer one hundred" / "eighty (180) days'"), so
    the stored heading, the contract's own characters, comes first."""
    covered = section.text[located.start : located.end]
    if "unprefixed:" in located.method and located.start == 0 and section.heading:
        return f"{section.heading} {covered}"
    return covered


# A part's text that ends a passage: a stop, any closing quote or bracket after it (ingest.sections.PASSAGE_END at a
# text's end, where no space follows).
_ENDS_A_PASSAGE = re.compile(r"(?:[.!?;][\"'”’)\]]*|[。！？；][」』”’）)\]]*)\s*$")


def reading_of(sections: Sequence[Section], section: Section) -> tuple[str, int]:
    """The text a quote's sentence is read in, and where ``section``'s own text starts in it: the section's text, with
    the parts of the same clause it runs on into. The reader stores a clause longer than its cap as parts ("… (part
    2)"), cut where a passage ends, or, where none is within reach, at a space (reader v16): there a sentence runs from one
    part into the next, and the edge of a part was read as the end of its sentence, so a condition at the head of the
    sentence in the part before was never seen beside a quote in the part after (stress test, 2026-10-30). Only an edge
    inside one paragraph is joined: both parts pieces of it (no paragraph break in either), the earlier not ending a
    passage. An edge between paragraphs ends a sentence, as a paragraph break inside a part does (`_PASSAGE_END`): a cover
    page's table rows, grouped into parts at their breaks, are not one sentence across them (Recording 6c, g25)."""
    ordered = list(sections)
    here = next((i for i, s in enumerate(ordered) if s.id == section.id), None)
    if here is None:
        return section.text, 0
    before = ordered[here - 1].text if here > 0 and _runs_on(ordered[here - 1], section) else ""
    after = ordered[here + 1].text if here + 1 < len(ordered) and _runs_on(section, ordered[here + 1]) else ""
    lead = f"{before} " if before else ""
    return f"{lead}{section.text}{' ' + after if after else ''}", len(lead)


def _runs_on(earlier: Section, later: Section) -> bool:
    """Whether a sentence runs on from ``earlier`` into ``later``: two pieces of one paragraph the reader cut for size,
    the earlier not ending a passage."""
    return (
        _part_of(earlier, later)
        and PARAGRAPH_SEPARATOR not in earlier.text
        and PARAGRAPH_SEPARATOR not in later.text
        and not _ENDS_A_PASSAGE.search(earlier.text)
    )


def _part_of(other: Section, section: Section) -> bool:
    """Whether two sections are parts of one clause the reader split for size: the same number, and headings that are
    one heading with its part marks ("Fees (part 1)", "Fees (part 2)"), or the heading the last part keeps."""

    def base(heading: str) -> str:
        found = PART_HEADING.match(heading or "")
        return found.group("base") if found else heading or ""

    marked = PART_HEADING.match(other.heading or "") or PART_HEADING.match(section.heading or "")
    return bool(marked) and other.number == section.number and base(other.heading) == base(section.heading)


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


def _retrieve(sections: list[Section], question: str, guidance: str | None, frozen: FrozenOptions) -> tuple[list[Section], RetrievalModeName, dict[str, str]]:
    """The sections handed to the model, how they were chosen, and, by section id, why each section the contract points
    to was added (retrieval-v2, runs.links). `opening_fallback` means the retriever ranked no section for the question
    (since retrieval-v3: no section shares a word with it), and the opening sections were handed over instead: they were
    not chosen for it, and no link is followed from them."""
    pairs = [(s.heading, s.text) for s in sections]
    hybrid = frozen.retriever == "hybrid"
    index: LexicalIndex | HybridIndex = HybridIndex(pairs, embed=partial(ollama_embed, model=frozen.embed_model)) if hybrid else LexicalIndex(pairs)
    query = question if not guidance else f"{question} {guidance}"
    if frozen.aliases:
        query = expand_query(query)
    candidates = index.search(query, frozen.retrieval_k)
    if not candidates and sections:
        # A question the retriever ranks nothing for still gets the opening sections rather than nothing.
        return sections[: min(frozen.retrieval_k, len(sections))], "opening_fallback", {}
    ranked = [c.index for c in candidates]
    # retrieval-v2: what the top ranked sections depend on, where the contract says which (a definition, an amendment,
    # a clause or schedule they cite), added after them within the same worst-case text (runs.links).
    added = linked(sections, ranked, frozen.window)
    why = {sections[link.index].id: because(link, sections) for link in added}
    return [sections[i] for i in ranked] + [sections[link.index] for link in added], "hybrid_match" if hybrid else "lexical_match", why


# ---------------------------------------------------------------------------- what retrieval leaves on the record
# Links hand a handed section's amendments with it, at most links.MAX_LINKS of them: past that, an amendment of a section
# the model read was not handed, and nothing on the run said so; and the alias table widened a run's query while the
# record named only the table's hash (stress test, 2026-10-30, the retrieval team's report). Both are read here from what
# retrieval used, without changing what it hands, and written on the finding-evidence stage.


def fired_alias_groups(query: str) -> list[str]:
    """The alias groups that widen ``query``, each by its first phrase, in table order: expand_query's own rule (a phrase
    of the group named in the query that is not WORDING)."""
    tokens = tokenize(query)
    return [group[0] for group in ALIAS_GROUPS if any(_phrase_in(tokens, tokenize(name)) for name in group if name not in WORDING)]


def amendments_left_out(sections: Sequence[Readable], handed: set[int], links_added: int) -> list[str]:
    """The amendments of a handed section that were not handed, named with what each amends: possible only once the
    links' places were all taken, so read only then (it reads every section's amending sentences again)."""
    if links_added < MAX_LINKS:
        return []
    found = _amendments(sections, _amending(sections), _definitions(sections), _stated(sections))
    left: dict[int, str] = {}
    for index in sorted(handed):
        for link in _changes_of(found, index):
            if link.index not in handed and link.index not in left:
                section = sections[link.index]
                name = f"§{section.number} {section.heading}".strip() if section.number else section.heading
                left[link.index] = f"{name} (it amends {link.by})"
    return list(left.values())


def _retrieval_record(sections: list[Section], chosen: list[Section], linked_because: Mapping[str, str], query: str, aliases: bool) -> str:
    position = {section.id: index for index, section in enumerate(sections)}
    left = amendments_left_out(sections, {position[s.id] for s in chosen}, len(linked_because))
    noted = ""
    if left:
        one = len(left) == 1
        noted += f" · {len(left)} amendment{'' if one else 's'} of a section read {'was' if one else 'were'} not handed for want of room: " + "; ".join(left)
    fired = fired_alias_groups(query) if aliases else []
    if fired:
        noted += " · the query was widened by the alias groups: " + ", ".join(fired)
    return noted


def bound_to(provider: ModelProvider, frozen: FrozenOptions) -> ModelProvider:
    """The provider bound to the run's recorded model and decoding settings, when it is a provider that has any
    (a replayed or a test provider answers from its record and has none)."""
    bind = getattr(provider, "with_options", None)
    return bind(frozen.decoding) if bind is not None else provider


def _counted(count: int, noun: str) -> str:
    """A count and its noun in the number it takes: "1 page", "16 sections" (blind contract stress test: "1 pages")."""
    return f"{count} {noun}{'' if count == 1 else 's'}"


@verification_pass()  # what is worked out about each text is kept for this pass only (verify/spans.py)
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
        pages = f"{_counted(document.pages, 'page')} · " if document.pages else ""
        _note_stage(session, run, "reading", f"{pages}{_counted(len(sections), 'section')}", output_hash=sha256_text("\x1f".join(s.text for s in sections)))

        _set_stage(session, run, "finding_evidence", input_hash=sha256_text(f"{run.question}\x1f{run.guidance_sha256 or ''}"))
        chosen, retrieval_mode, linked_because = _retrieve(sections, run.question, guidance_text, frozen)
        by_label = {SECTION_LABEL.format(ordinal=s.ordinal): s for s in chosen}
        # What a handle reads as once the model's prose reaches a person.
        labels = {label: (f"§{s.number}" if s.number else s.heading) for label, s in by_label.items()}
        run.candidates_json = json.dumps(
            [
                {"label": label, "section_id": s.id, "number": s.number, "heading": s.heading}
                # A section the contract points to from a ranked one says why it was handed (retrieval-v2).
                | ({"linked": linked_because[s.id]} if s.id in linked_because else {})
                for label, s in by_label.items()
            ]
        )
        # A field, not only a sentence on the stage: every projection of the run can say which it was.
        run.retrieval_mode = retrieval_mode
        # The contract's own statements of replacement and precedence, located once and recorded with the run (policy-v11):
        # those touching the sections read first. What each means for a finding is added when the findings are made.
        relations = relevant(locate_relations(sections, as_utc(run.created_at).date()), {s.id for s in chosen})
        run.relations_json = dump(Recorded(tuple(relations)))
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
            _counted(len(chosen) - len(linked_because), "candidate section")
            + (f" and {len(linked_because)} the contract points to from them" if linked_because else "")
            + _retrieval_record(sections, chosen, linked_because, run.question if not guidance_text else f"{run.question} {guidance_text}", frozen.aliases)
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
        if result.rounds > 1:
            answered += " · after a rejected first answer"
        admitted = getattr(provider, "last", None)
        if admitted is not None and admitted.queue_wait_ms >= 1000:
            answered += f" · queued {admitted.queue_wait_ms / 1000:.0f} s behind {admitted.queue_depth_at_arrival + 1}"
        # The checking stage's time is the queue and the model together; this line splits them, so a day's p50 and p95 of
        # each is one grep away.
        log.info(
            "run_id=%s model_ms=%.0f queue_ms=%.0f queue_depth=%d attempts=%d rounds=%d",
            run.id,
            result.generation.latency_ms or 0,
            admitted.queue_wait_ms if admitted is not None else 0,
            admitted.queue_depth_at_arrival if admitted is not None else 0,
            result.attempts,
            result.rounds,
        )
        _note_stage(session, run, "checking", answered, output_hash=sha256_text(result.generation.text), attempt=result.attempts, rounds=result.rounds)

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
        clause_numbers = {s.number for s in sections if s.number} | printed  # a value written as one of these points (runs.values)
        handed = [(s.number, s.heading) for s in chosen]
        # The contract's own definition of a Business Day, from the whole document: what a period in business days takes
        # on the calendar rests on it (policy-v10), never on an assumption.
        cited_as = [(f"§{s.number}" if s.number else s.heading, s.text) for s in sections]
        week = business_week(cited_as)
        days = day_convention(cited_as)  # what the contract says its bare "days" are (policy-v10)
        parts = parts_of(sections) if relations else {}
        notes: dict[int, tuple[Note, ...]] = {}
        proposed: list[tuple[Finding, Decision, Grounds]] = []
        for ordinal, item in enumerate(proposal.findings):
            spans: list[EvidenceSpan] = []
            passages: list[str] = []
            dependencies: list[str] = []
            conditions: list[LeftOut] = []  # what each verified quote's own sentence carries outside it (policy-v14)
            read: list[str] = []  # what each verified quote covers in the contract: what code reads values from (policy-v17)
            all_verified = bool(item.evidence)
            for span_ordinal, evidence in enumerate(item.evidence):
                section, located, method = verify_evidence(evidence.quote, evidence.section_id, by_label, chosen, window=window)
                verified = located is not None
                all_verified = all_verified and verified
                if located is not None and section is not None:
                    read.append(located_text(section, located))
                    # What the sentences around the quote point at that the model was not handed (runs.status), read in the
                    # clause's parts the sentence runs on into (`reading_of`).
                    whole, at = reading_of(sections, section)
                    passage = enclosing_sentences(whole, at + located.start, at + located.end)
                    passages.append(passage)
                    dependencies += [d for d in unseen_references(passage, every_section, handed) if d not in dependencies]
                    if (condition := left_out(whole, at + located.start, at + located.end)) is not None:
                        conditions.append(condition)
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
                quotes=read,
                guidance=guidance_text,
                topic=item.topic,
                dependencies=dependencies,
                passages=passages,
                week=week,
                days=days,
            )
            decision = check_references(
                decision,
                label_handles(item.conclusion, labels),
                (s.number for s in sections),
                by_label,
                printed,
                [
                    handle
                    for text in (item.topic, item.conclusion, item.guidance_reference, item.observed, item.required, item.suggested_position)
                    for handle in unresolved_handles(text, labels)
                ],
            )
            decision = check_values(
                decision,
                label_handles(item.conclusion, labels),
                read,
                run.question,
                guidance_text,
                clause_numbers,
            )
            decision = check_conditions(decision, unshown_conditions(conditions, read))
            if relations:
                # What the located statements mean for this finding: only its verified quotes ground anything (runs.relations).
                answer = " ".join(label_handles(text, labels) for text in (item.conclusion, item.observed) if text)
                quoted = [(span.section_id, span.start, span.end) for span in spans if span.verified and span.section_id]
                notes[ordinal] = tuple(
                    assess(relations, quoted, answer, run.question, parts, label_handles(item.observed, labels), label_handles(item.conclusion, labels))
                )
                decision = check_replaced(decision, next((n.sentence for n in notes[ordinal] if n.effect == "replaced"), None))
                decision = check_old_value(decision, next((n.sentence for n in notes[ordinal] if n.effect == "old_value"), None))
                decision = check_unhanded(decision, unhanded_amendment(relations, quoted, {s.id for s in chosen}, run.question))
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
            proposed.append((finding, decision, Grounds(tuple(read), tuple(passages), found_in)))
        # A pass code confirmed does not stand beside a shortfall code found in a finding that bears on it (runs.status).
        settled = settle_together([d for _, d, _ in proposed], [g for _, _, g in proposed], guidance_text)
        for (finding, _, _), decision in zip(proposed, settled, strict=True):
            finding.status, finding.status_source, finding.status_reason = decision.status, decision.source, decision.reason or None
            session.add(finding)
        if notes:
            run.relations_json = dump(Recorded(tuple(relations), notes))
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
    except Exception:
        log.exception("run %s failed", run_id)
        # The exception, its class included, is in the log above; the reader is told what happened, not what was raised.
        _fail(session, run, "The server failed while answering this question. Ask the question again.", "internal_error")


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


def finished_record(run: Run, stage: RunStageName) -> str:
    """The hash of the record a run finished on, written as the input of its last stage: what no earlier stage's hash
    covers. Each finding's status and what set it, the relations and what they mean for it, the options (the verifier
    version and the window among them) and the run's identity. The evidence pack's verify.py recomputes it from
    run.json, findings.json and relations.json, so an edited status or relation fails there (stress test, 2026-10-30:
    a status turned to pass in findings.json was bound to nothing). Reviews come after the run, as rows of their own,
    and are not in it. Runs finished before 2026-10-30 have none."""
    recorded = load(run.relations_json)
    record = {
        "run": run.id,
        "fingerprint": run.fingerprint,
        "document": run.document_id,
        "task": run.task,
        "provider": run.provider,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "prompt_hash": run.prompt_hash,
        "retrieval_mode": run.retrieval_mode,
        "candidates": json.loads(run.candidates_json or "[]"),
        "options": json.loads(run.options_json or "{}"),
        "stage": stage,
        "reason": run.reason,
        "relations": [asdict(r) for r in recorded.relations] if run.relations_json else None,
        "findings": [
            {
                "id": f.id,
                "ordinal": f.ordinal,
                "status": f.status,
                "status_source": f.status_source,
                "status_reason": f.status_reason,
                "relations": [{"relation": n.relation, "effect": n.effect, "sentence": n.sentence} for n in recorded.notes.get(f.ordinal, ())],
                "match_counts": [s.match_count for s in f.spans],
            }
            for f in run.findings
        ],
    }
    return sha256_text(json.dumps(record, sort_keys=True))


def _finish(session: Session, run: Run, stage: RunStageName, note: str | None = None, error: str | None = None, reason: RunReasonName | None = None) -> None:
    run.note = note
    run.error = error
    run.reason = reason
    run.finished_at = utcnow()
    # A failed run ends wherever it failed, with whatever it had written; only a run that finished its stages has a
    # record to vouch for.
    record = finished_record(run, stage) if stage != "failed" else None
    _set_stage(session, run, stage, note or error, input_hash=record, error_code=reason if stage == "failed" else None)
