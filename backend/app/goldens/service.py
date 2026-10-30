"""Load the set, find each golden's run per prompt version, judge it, compare prompt versions.

Nothing here calls a model. Running the set is `scripts/run_goldens.py`, which uses the same
start_run use case as the interface, so a golden run is an ordinary run: same fingerprint,
same record, same idempotency. This module only reads those records back: by what each run
stored (`recordings`), so a recording made under an older reader or older rules is found and
shown as what it is, and judged by the text of the sections it cited, not their numbers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from ..analysis.service import PROMPTS_DIR, PromptPackage, load_prompt
from ..application.ingest_document import ingest_document
from ..application.save_guidance import stored_guidance
from ..application.start_run import compute_fingerprint, identity_options
from ..config import BACKEND_DIR, settings
from ..hashing import sha256_bytes, sha256_text
from ..ingest import PARSER_VERSION
from ..models import TERMINAL_STAGES, Document, EvidenceSpan, Finding, FindingStatusName, Run, Section, StatusSourceName, as_utc, utcnow
from ..policy.durations import Duration, parse_durations
from ..runs.versions import SEMANTIC_VERSIONS
from ..schemas import (
    GoldenCategoryCount,
    GoldenCompareOut,
    GoldenDelta,
    GoldenExpectation,
    GoldenOut,
    GoldenPromptOut,
    GoldenRunOut,
    GoldensOut,
)

SET_PATH = Path(__file__).with_name("set.json")
GoldenKind = Literal["present", "absent"]
VerdictName = Literal["pass", "fail", "missing"]
ExpectedStatus = Literal["pass", "needs_review"]
# Statuses that assert the contract addresses the point.
ASSERTING: frozenset[FindingStatusName] = frozenset({"pass", "needs_review"})
# The sources of a needs review that code set over the model's hint because the evidence does not establish the answer
# (runs/status.py, runs/service.py). A pass carried by such a finding stays a pass, since the lowering can be right about
# a wrong section reference in a right answer (Recording 6c's g38), but the verdict says so and the report counts it.
LOWERED_BY_CODE: frozenset[StatusSourceName] = frozenset({"position_check", "reference_check", "ambiguous_fact"})
LOWERED_NOTE = "carried by a finding code lowered to needs review"


@dataclass(frozen=True)
class Golden:
    id: str
    question: str
    kind: GoldenKind
    sections: tuple[str, ...]
    why: str
    category: str = ""
    guidance: str | None = None  # supplied to the run when set; the status is then judged too
    status: ExpectedStatus | None = None  # required on every finding that carries a citation in the golden's sections
    expected_value: str | None = None  # a period the carrying finding's answer must state ("60 days"), read by policy.durations
    # (section, anchor) for each named section that has text: a golden from the set is judged by these, a golden
    # written without them (a test's) by section number.
    anchors: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class GoldenSet:
    sha256: str  # of the set file, so a result is tied to the questions it was judged against
    document_name: str
    document_path: Path
    document_sha256_prefix: str
    rules: str
    categories: dict[str, str]
    goldens: tuple[Golden, ...]
    anchors: dict[str, str]  # section number under today's reader → section_anchor of its text
    earlier_anchors: dict[str, tuple[str, ...]]  # the same sections' anchors as an earlier reader read them, where they differ


@dataclass(frozen=True)
class Verdict:
    outcome: VerdictName
    because: str
    statuses: tuple[FindingStatusName, ...] = ()
    cited: tuple[str, ...] = ()  # "5.3.1 exact", "sec_9 not found"
    lowered: StatusSourceName | None = None  # a pass carried only by a finding code lowered, and by which check


def _expected_status(value: object, golden_id: str) -> ExpectedStatus | None:
    if value is None:
        return None
    if value == "pass":
        return "pass"
    if value == "needs_review":
        return "needs_review"
    raise ValueError(f"{golden_id}: an expected status must be pass or needs_review, not {value!r}")


def expected_period(value: str, golden_id: str = "") -> Duration:
    """The one period an expected value names, read as the status decision reads one."""
    periods = [m.duration for m in parse_durations(value) if m.duration is not None]
    if len(periods) != 1:
        raise ValueError(f"{golden_id}: an expected value names exactly one period, not {value!r}")
    return periods[0]


def section_anchor(text: str) -> str | None:
    """A section's identity by its text: the first 16 hex digits of the SHA-256 of the text casefolded, whitespace
    collapsed; None for a section with no text, where no quote can be found. A golden names its sections by these, so a
    reader that renumbers a section does not change what a recording under the old numbering cited: reader v14 made
    5.3.1 into 5.3(a), and every committed recording, judged under the relabelled set, fell from 37 of 44 to 28 (stress
    test EVL-2, 2026-10-30)."""
    folded = " ".join(text.casefold().split())
    return sha256_text(folded)[:16] if folded else None


def load_set(path: Path = SET_PATH) -> GoldenSet:
    raw = path.read_bytes()
    data = json.loads(raw)
    anchors = {str(number): str(anchor) for number, anchor in (data.get("anchors") or {}).items()}
    earlier = {str(number): tuple(str(a) for a in found) for number, found in (data.get("earlier_anchors") or {}).items()}
    goldens = tuple(
        Golden(
            id=str(g["id"]),
            question=str(g["question"]).strip(),
            kind=g["kind"],
            sections=tuple(str(s) for s in g.get("sections", [])),
            why=str(g.get("why", "")),
            category=str(g.get("category", "")),
            guidance=(str(g["guidance"]).strip() or None) if g.get("guidance") else None,
            status=_expected_status(g.get("status"), str(g["id"])),
            expected_value=str(g["expected_value"]) if g.get("expected_value") else None,
            anchors=tuple((str(n), anchor) for n in g.get("sections", []) if str(n) in anchors for anchor in (anchors[str(n)], *earlier.get(str(n), ()))),
        )
        for g in data["goldens"]
    )
    ids = [g.id for g in goldens]
    if len(set(ids)) != len(ids):
        raise ValueError("golden ids must be unique")
    categories = {str(k): str(v) for k, v in (data.get("categories") or {}).items()}
    for golden in goldens:
        if golden.kind not in ("present", "absent"):
            raise ValueError(f"{golden.id}: kind must be present or absent")
        if golden.kind == "present" and not golden.sections:
            raise ValueError(f"{golden.id}: a present golden names the sections that answer it")
        if golden.status is not None and golden.status not in ASSERTING:
            raise ValueError(f"{golden.id}: an expected status must be pass or needs_review")
        if golden.status is not None and golden.guidance is None:
            raise ValueError(f"{golden.id}: a status is only decided against guidance")
        if categories and golden.category not in categories:
            raise ValueError(f"{golden.id}: unknown category {golden.category!r}")
        if golden.expected_value is not None:
            expected_period(golden.expected_value, golden.id)
    document = data["document"]
    return GoldenSet(
        sha256=sha256_bytes(raw),
        document_name=str(document["name"]),
        document_path=BACKEND_DIR.parent / str(document["path"]),
        document_sha256_prefix=str(document["sha256"]),
        rules=str(data.get("rules", "")),
        categories=categories,
        goldens=goldens,
        anchors=anchors,
        earlier_anchors=earlier,
    )


def golden_document(session: Session, golden_set: GoldenSet) -> Document | None:
    """The sample as parsed by the current reader. Older parses of the same file are left alone."""
    return (
        session.query(Document)
        .filter(Document.sha256.startswith(golden_set.document_sha256_prefix), Document.parser_version == PARSER_VERSION)
        .order_by(Document.created_at.desc())
        .first()
    )


def ensure_golden_document(session: Session, golden_set: GoldenSet) -> Document:
    existing = golden_document(session, golden_set)
    if existing is not None:
        return existing
    document = ingest_document(session, golden_set.document_path.name, golden_set.document_path.read_bytes()).document
    if not document.sha256.startswith(golden_set.document_sha256_prefix):
        raise ValueError(f"{golden_set.document_path} is not the file the set was written for (sha256 {document.sha256[:16]})")
    return document


def prompt_versions() -> list[PromptPackage]:
    """Every prompt file in the repository, oldest version first by name."""
    return [load_prompt(path.stem) for path in sorted(PROMPTS_DIR.glob("*.md"))]


def guidance_id_for(session: Session, golden: Golden) -> str | None:
    """The stored guidance record for this golden's policy text, if the runner has saved it."""
    if golden.guidance is None:
        return None
    guidance = stored_guidance(session, sha256_text(golden.guidance))
    return guidance.id if guidance else None


@dataclass(frozen=True)
class Recording:
    """One sitting of the set, found by what its runs stored: one reading of the sample, one prompt, one model and one
    set of recorded options, with the run that answers each golden recorded in it."""

    document: Document
    prompt: PromptPackage
    model: str
    options: dict[str, object]
    runs: dict[str, Run]
    current: bool  # every run carries today's identity: the runs a request asked today would be handed

    @property
    def made(self) -> datetime:
        return max(as_utc(run.created_at) for run in self.runs.values())

    def label(self) -> str:
        """What the recording was made on, from its own record."""
        options = self.options
        rules = rules_named(options) or "rules not recorded (made before 2026-10-02)"
        days = sorted(as_utc(run.created_at).date().isoformat() for run in self.runs.values())
        parts = [self.prompt.version, self.model, f"reader {self.document.parser_version or 'unversioned'}", rules, f"k {options.get('retrieval_k', '?')}"]
        if "section_window" in options:
            parts.append(f"window {options['section_window']}")
        if "retrieval_aliases" in options:
            parts.append(f"alias table {options['retrieval_aliases']}")
        parts.append(f"recorded {days[0]}" if days[0] == days[-1] else f"recorded {days[0]} to {days[-1]}")
        return " · ".join(parts)


def rules_named(options: Mapping[str, object]) -> str:
    """The versions of the rules a run's options record, as the documents name them: "policy-v16, verifier v11, retrieval-v2"."""
    named = {"policy_version": "", "verifier_version": "verifier ", "retrieval_version": "", "input_version": ""}
    return ", ".join(f"{prefix}{options[key]}" for key, prefix in named.items() if key in options)


def sample_documents(session: Session, golden_set: GoldenSet) -> list[Document]:
    """Every reading of the sample's bytes, by any reader, oldest first."""
    return session.query(Document).filter(Document.sha256.startswith(golden_set.document_sha256_prefix)).order_by(Document.created_at).all()


def _chosen(runs: Sequence[Run]) -> Run | None:
    """Of one golden's runs, newest first: the live or finished one, else the latest failed one."""
    return next((r for r in runs if r.stage != "failed"), runs[0] if runs else None)


def recordings(session: Session, documents: Sequence[Document], goldens: Sequence[Golden], prompt: PromptPackage, model: str | None = None) -> list[Recording]:
    """Every recording of these goldens under this prompt and model on these readings, found by what each run stored
    (document, question, guidance, prompt hash, options), never by recomputing today's fingerprint, so a version moved
    since hides nothing that was recorded. The report looked runs up by today's fingerprint on today's reading only, and
    over a store holding 673 golden runs it said "no golden run is recorded yet" (stress test EVL-2, 2026-10-30)."""
    wanted = model or settings.model
    by_asked: dict[tuple[str, str | None], list[Golden]] = {}
    for golden in goldens:
        guidance_id = guidance_id_for(session, golden)
        if golden.guidance is None or guidance_id is not None:
            by_asked.setdefault((golden.question, guidance_id), []).append(golden)
    by_id = {document.id: document for document in documents}
    if not by_id or not by_asked:
        return []
    runs = (
        session.query(Run)
        .filter(
            Run.document_id.in_(list(by_id)),
            Run.prompt_hash == prompt.sha256,
            Run.question.in_(sorted({question for question, _guidance in by_asked})),
            Run.workspace_id.is_(None),
        )
        .order_by(Run.created_at.desc())
        .all()
    )
    groups: dict[tuple[str, str], dict[str, list[Run]]] = {}
    for run in runs:
        options = json.loads(run.options_json or "{}")
        # The model asked for, as the run's options name it; a run recorded before they did names it on its own row.
        if str(options.get("model", run.model)) != wanted:
            continue
        key = (run.document_id, json.dumps(options, sort_keys=True))
        for golden in by_asked.get((run.question, run.guidance_id), []):
            groups.setdefault(key, {}).setdefault(golden.id, []).append(run)
    now = utcnow()
    found: list[Recording] = []
    for (document_id, options_text), by_golden in groups.items():
        document = by_id[document_id]
        chosen = {golden_id: picked for golden_id, candidates in by_golden.items() if (picked := _chosen(candidates)) is not None}
        today = identity_options(session, document, model, now)
        current = all(run.fingerprint == compute_fingerprint(document.id, run.guidance_id, run.question, prompt.sha256, today) for run in chosen.values())
        found.append(Recording(document, prompt, wanted, json.loads(options_text), chosen, current))
    return found


def best_recording(found: Sequence[Recording]) -> Recording | None:
    """The recording that speaks for a prompt version: the most complete, then one under today's rules, then the latest."""
    return max(found, key=lambda r: (len(r.runs), r.current, r.made), default=None)


def run_for(session: Session, document: Document, golden: Golden, prompt: PromptPackage, model: str | None = None) -> Run | None:
    """The run that answers this golden under this prompt and model on this reading: the one under today's identity,
    which a request would be handed; else the run of the most complete earlier recording, found by what it stored. That
    one is shown as recorded and never handed to a request: application.start_run looks up today's key only."""
    guidance_id = guidance_id_for(session, golden)
    if golden.guidance is not None and guidance_id is None:
        return None
    options = identity_options(session, document, model, utcnow())
    key = compute_fingerprint(document.id, guidance_id, golden.question, prompt.sha256, options)
    current = _chosen(session.query(Run).filter(Run.fingerprint == key).order_by(Run.created_at.desc()).all())
    if current is not None:
        return current
    earlier = best_recording(recordings(session, [document], (golden,), prompt, model))
    return earlier.runs.get(golden.id) if earlier is not None else None


def _citations(run: Run) -> tuple[str, ...]:
    cited: list[str] = []
    for finding in run.findings:
        for span in finding.spans:
            if span.section is not None:
                cited.append(f"{span.section.number or span.section.heading} {span.method}")
            else:
                cited.append(f"{span.cited_section_label or '?'} not found")
    return tuple(cited)


def _named(golden: Golden, section: Section) -> str | None:
    """The golden's label for the section a quote verified in, or None when the golden does not name it: by its text
    for a section the set anchors, whatever number the run's reading gave it; by number for a named section that has
    no text today (reader v15 reads §5.6 as a heading alone; reader v3 kept the survival lead-in under it) and for a
    golden written without anchors."""
    anchor = section_anchor(section.text)
    by_text = next((label for label, named in golden.anchors if named == anchor), None)
    if by_text is not None:
        return by_text
    anchored = {label for label, _named in golden.anchors}
    return section.number if section.number in golden.sections and section.number not in anchored else None


def _numbered(span: EvidenceSpan, label: str) -> str:
    number = span.section.number if span.section is not None else ""
    return f"; that reading numbers it §{number}" if number and number != label else ""


def _states(finding: Finding, period: Duration) -> bool:
    """Whether the answer states the period, in its conclusion or its observed value."""
    return any(m.duration == period for text in (finding.conclusion, finding.observed) for m in parse_durations(text))


def judge(golden: Golden, run: Run | None) -> Verdict:
    """Code decides. A present golden needs a verified citation in one of its sections on a finding that does not call
    the point missing; when the golden names a status, every such finding must have it, and when it names a period, the
    carrying finding's answer must state it. An absent golden needs the run not to assert the point."""
    if run is None:
        return Verdict("missing", "no run recorded for this prompt version")
    statuses = tuple(f.status for f in run.findings)
    cited = _citations(run)
    if run.stage == "failed":
        return Verdict("fail", f"the run failed ({run.reason})", statuses, cited)
    if run.stage not in TERMINAL_STAGES:
        return Verdict("missing", "the run is still in progress", statuses, cited)

    if golden.kind == "absent":
        if run.stage == "unresolved":
            return Verdict("pass", f"nothing asserted; the run was {run.reason}", statuses, cited)
        asserting = [s for s in statuses if s in ASSERTING]
        if asserting:
            return Verdict("fail", f"asserted {', '.join(sorted(set(asserting)))} for a point the contract does not contain", statuses, cited)
        return Verdict("pass", "answered not found", statuses, cited)

    if run.stage == "unresolved":
        return Verdict("fail", f"withheld ({run.reason}) although the contract contains the point", statuses, cited)
    carriers = [
        (finding, span, label)
        for finding in run.findings
        if finding.status in ASSERTING
        for span in finding.spans
        if span.verified and span.section is not None and (label := _named(golden, span.section)) is not None
    ]
    if golden.status is not None:
        # Every finding that cites the clause decides it: a pass and a needs review on the same quote is no decision,
        # and it used to satisfy either expectation (stress test EVL-3, 2026-10-30).
        others = sorted({finding.status for finding, _span, _label in carriers} - {golden.status})
        if others and any(finding.status == golden.status for finding, _span, _label in carriers):
            return Verdict("fail", f"cited the right clause and decided both {golden.status} and {others[0]}; {golden.status} was expected", statuses, cited)
        if others:
            return Verdict("fail", f"cited the right clause but decided {others[0]} where {golden.status} was expected", statuses, cited)
    if carriers and golden.expected_value is not None:
        period = expected_period(golden.expected_value, golden.id)
        stating = [carrier for carrier in carriers if _states(carrier[0], period)]
        if not stating:
            stated = sorted({m.surface for f, _s, _l in carriers for text in (f.conclusion, f.observed) for m in parse_durations(text)})
            said = f"states {', '.join(stated)}" if stated else "states no period"
            return Verdict("fail", f"cited the right clause, but the answer {said} where {golden.expected_value} was asked for", statuses, cited)
        carriers = stating
    if carriers:
        # A finding code did not lower carries the pass when there is one; otherwise the verdict says which check lowered it.
        finding, span, label = next((c for c in carriers if c[0].status_source not in LOWERED_BY_CODE), carriers[0])
        lowered = finding.status_source if finding.status_source in LOWERED_BY_CODE else None
        because = f"verified citation in §{label} ({span.method}{_numbered(span, label)})"
        return Verdict("pass", f"{because}; {LOWERED_NOTE} ({lowered})" if lowered else because, statuses, cited, lowered)
    verified = sorted({span.section.number or span.section.heading for f in run.findings for span in f.spans if span.verified and span.section is not None})
    if statuses and all(s == "missing" for s in statuses):
        return Verdict("fail", "answered not found although the contract contains the point", statuses, cited)
    expected = "/".join(golden.sections)
    return Verdict(
        "fail", f"no verified citation in §{expected}; verified citations were in §{', §'.join(verified) if verified else 'nothing'}", statuses, cited
    )


def lowered_passes(rows: Sequence[GoldenRunOut]) -> list[str]:
    """The goldens whose pass rests on a finding code lowered to needs review: how much of a score the lowering carries."""
    return [row.golden_id for row in rows if row.verdict == "pass" and LOWERED_NOTE in row.because]


def compare(
    base: dict[str, Verdict],
    head: dict[str, Verdict],
    base_version: str,
    head_version: str,
    goldens: tuple[Golden, ...],
    base_latency_ms: float | None = None,
    head_latency_ms: float | None = None,
) -> GoldenCompareOut:
    rows: list[GoldenDelta] = []
    for golden in goldens:
        b, h = base[golden.id], head[golden.id]
        # A golden recorded under only one version is not compared; it is reported as such.
        changed = b.outcome != "missing" and h.outcome != "missing" and (b.cited != h.cited or b.statuses != h.statuses)
        if b.outcome == "missing" or h.outcome == "missing":
            change: Literal["better", "worse", "same"] = "same"
            note = f"not recorded under {base_version if b.outcome == 'missing' else head_version}"
        elif b.outcome != "pass" and h.outcome == "pass":
            change, note = "better", h.because
        elif b.outcome == "pass" and h.outcome != "pass":
            change, note = "worse", h.because
        else:
            change, note = "same", h.because
        rows.append(GoldenDelta(golden_id=golden.id, base=b.outcome, head=h.outcome, change=change, changed=changed, note=note))
    latency_delta = None if base_latency_ms is None or head_latency_ms is None else round(head_latency_ms - base_latency_ms, 1)
    return GoldenCompareOut(
        base=base_version,
        head=head_version,
        better=sum(1 for r in rows if r.change == "better"),
        worse=sum(1 for r in rows if r.change == "worse"),
        same=sum(1 for r in rows if r.change == "same"),
        changed=sum(1 for r in rows if r.changed),
        latency_delta_ms=latency_delta,
        rows=rows,
    )


@dataclass(frozen=True)
class ModelComparison:
    """The same prompt answered by two models, judged golden by golden and summed per task."""

    prompt_version: str
    base_model: str
    candidate_model: str
    compare: GoldenCompareOut
    base_by_task: dict[str, tuple[int, int]]  # task → (passes, recorded)
    candidate_by_task: dict[str, tuple[int, int]]
    base_latency_ms: float | None
    candidate_latency_ms: float | None
    base_recording: str = ""  # Recording.label of what each side was judged on
    candidate_recording: str = ""


def task_of(golden: Golden) -> str:
    return "guidance_comparison" if golden.guidance else "clause_lookup"


def compare_models(session: Session, prompt_version: str, base_model: str, candidate_model: str, golden_set: GoldenSet | None = None) -> ModelComparison:
    golden_set = golden_set or load_set()
    documents = sample_documents(session, golden_set)
    if not documents:
        raise ValueError("the sample has not been read yet; run the golden set first")
    prompt = load_prompt(prompt_version)
    candidate = best_recording(recordings(session, documents, golden_set.goldens, prompt, candidate_model))
    base_found = recordings(session, documents, golden_set.goldens, prompt, base_model)
    if candidate is not None:
        # The two models are compared on one reading under the same options, the model apart.
        like = [r for r in base_found if r.document.id == candidate.document.id and _apart_from_model(r.options) == _apart_from_model(candidate.options)]
        base_found = like
    base = best_recording(base_found)
    verdicts: dict[str, dict[str, Verdict]] = {}
    latencies: dict[str, list[float]] = {}
    for model, shown in ((base_model, base), (candidate_model, candidate)):
        runs = shown.runs if shown is not None else {}
        verdicts[model] = {golden.id: judge(golden, runs.get(golden.id)) for golden in golden_set.goldens}
        latencies[model] = [run.latency_ms for run in runs.values() if run.latency_ms is not None]

    def by_task(model: str) -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        for golden in golden_set.goldens:
            verdict = verdicts[model][golden.id]
            passes, recorded = out.get(task_of(golden), (0, 0))
            out[task_of(golden)] = (passes + (verdict.outcome == "pass"), recorded + (verdict.outcome != "missing"))
        return out

    return ModelComparison(
        prompt_version=prompt.version,
        base_model=base_model,
        candidate_model=candidate_model,
        compare=compare(
            verdicts[base_model],
            verdicts[candidate_model],
            base_model,
            candidate_model,
            golden_set.goldens,
            _mean(latencies[base_model]),
            _mean(latencies[candidate_model]),
        ),
        base_by_task=by_task(base_model),
        candidate_by_task=by_task(candidate_model),
        base_latency_ms=_mean(latencies[base_model]),
        candidate_latency_ms=_mean(latencies[candidate_model]),
        base_recording=base.label() if base is not None else "not recorded",
        candidate_recording=candidate.label() if candidate is not None else "not recorded",
    )


def _apart_from_model(options: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in options.items() if key != "model"}


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def report(session: Session, golden_set: GoldenSet | None = None) -> GoldensOut:
    golden_set = golden_set or load_set()
    goldens_out = [
        GoldenOut(
            id=g.id,
            question=g.question,
            why=g.why,
            category=g.category,
            guidance=g.guidance,
            expect=GoldenExpectation(kind=g.kind, sections=list(g.sections), status=g.status),
        )
        for g in golden_set.goldens
    ]
    documents = sample_documents(session, golden_set)
    if not documents:
        return GoldensOut(
            available=False,
            detail="The sample has not been read yet; run `scripts/run_goldens.py` to record the set.",
            set_sha256=golden_set.sha256,
            document_name=golden_set.document_name,
            rules=golden_set.rules,
            categories=golden_set.categories,
            goldens=goldens_out,
        )
    document = golden_document(session, golden_set) or documents[-1]
    prompts: list[GoldenPromptOut] = []
    shown: list[Recording] = []
    verdicts_by_version: dict[str, dict[str, Verdict]] = {}
    latency_by_version: dict[str, float | None] = {}
    category_names = list(golden_set.categories) or sorted({g.category for g in golden_set.goldens})
    for prompt in prompt_versions():
        recording = best_recording(recordings(session, documents, golden_set.goldens, prompt))
        if recording is None:
            continue
        verdicts: dict[str, Verdict] = {}
        rows: list[GoldenRunOut] = []
        for golden in golden_set.goldens:
            run = recording.runs.get(golden.id)
            verdict = judge(golden, run)
            verdicts[golden.id] = verdict
            rows.append(
                GoldenRunOut(
                    golden_id=golden.id,
                    run_id=run.id if run else None,
                    stage=run.stage if run else None,
                    reason=run.reason if run else None,
                    latency_ms=run.latency_ms if run else None,
                    statuses=list(verdict.statuses),
                    cited=list(verdict.cited),
                    verdict=verdict.outcome,
                    because=verdict.because,
                )
            )
        shown.append(recording)
        verdicts_by_version[prompt.version] = verdicts
        latency_by_version[prompt.version] = _mean([run.latency_ms for run in recording.runs.values() if run.latency_ms is not None])
        by_category = [
            GoldenCategoryCount(
                category=category,
                passes=sum(1 for g in golden_set.goldens if g.category == category and verdicts[g.id].outcome == "pass"),
                recorded=sum(1 for g in golden_set.goldens if g.category == category and verdicts[g.id].outcome != "missing"),
            )
            for category in category_names
        ]
        prompts.append(
            GoldenPromptOut(
                version=prompt.version,
                hash=prompt.sha256,
                runs=rows,
                passes=sum(1 for v in verdicts.values() if v.outcome == "pass"),
                recorded=sum(1 for v in verdicts.values() if v.outcome != "missing"),
                mean_latency_ms=latency_by_version[prompt.version],
                by_category=[c for c in by_category if c.recorded],
            )
        )
    notes: list[str] = []
    if any(not recording.current for recording in shown):
        rules = rules_named(SEMANTIC_VERSIONS)
        notes.append(
            "Shown for each prompt version, its most complete recording: "
            + "; ".join(recording.label() for recording in shown)
            + f". {'None is' if not any(r.current for r in shown) else 'Not every one is'} under today's rules ({rules}, reader {PARSER_VERSION}),"
            " so a question asked today is answered anew; each is judged as recorded, by the text of the sections it cited."
        )
    comparison = None
    if len(shown) >= 2:
        base, head = shown[-2], shown[-1]
        if base.document.id == head.document.id and base.options == head.options:
            comparison = compare(
                verdicts_by_version[base.prompt.version],
                verdicts_by_version[head.prompt.version],
                base.prompt.version,
                head.prompt.version,
                golden_set.goldens,
                latency_by_version[base.prompt.version],
                latency_by_version[head.prompt.version],
            )
        else:
            notes.append(f"{base.prompt.version} and {head.prompt.version} were not recorded on one reading under the same options, so they are not compared.")
    return GoldensOut(
        available=True,
        detail=(" ".join(notes) or None) if prompts else "The sample is read; no golden run is recorded yet. Run `scripts/run_goldens.py`.",
        set_sha256=golden_set.sha256,
        document_id=document.id,
        document_name=document.name,
        document_sha256=document.sha256,
        rules=golden_set.rules,
        categories=golden_set.categories,
        goldens=goldens_out,
        prompts=prompts,
        compare=comparison,
    )
