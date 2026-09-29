"""Load the set, find each golden's run per prompt version, judge it, compare prompt versions.

Nothing here calls a model. Running the set is `scripts/run_goldens.py`, which uses the same
start_run use case as the interface, so a golden run is an ordinary run: same fingerprint,
same record, same idempotency. This module only reads those records back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from ..analysis.service import PROMPTS_DIR, PromptPackage, load_prompt
from ..application.ingest_document import ingest_document
from ..application.save_guidance import stored_guidance
from ..application.start_run import compute_fingerprint, run_options
from ..config import BACKEND_DIR
from ..hashing import sha256_bytes, sha256_text
from ..ingest import PARSER_VERSION
from ..models import TERMINAL_STAGES, Document, FindingStatusName, Run
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


@dataclass(frozen=True)
class Golden:
    id: str
    question: str
    kind: GoldenKind
    sections: tuple[str, ...]
    why: str
    category: str = ""
    guidance: str | None = None  # supplied to the run when set; the status is then judged too
    status: ExpectedStatus | None = None  # required on the finding that carries the citation


@dataclass(frozen=True)
class GoldenSet:
    sha256: str  # of the set file, so a result is tied to the questions it was judged against
    document_name: str
    document_path: Path
    document_sha256_prefix: str
    rules: str
    categories: dict[str, str]
    goldens: tuple[Golden, ...]


@dataclass(frozen=True)
class Verdict:
    outcome: VerdictName
    because: str
    statuses: tuple[FindingStatusName, ...] = ()
    cited: tuple[str, ...] = ()  # "5.3.1 exact", "sec_9 not found"


def _expected_status(value: object, golden_id: str) -> ExpectedStatus | None:
    if value is None:
        return None
    if value == "pass":
        return "pass"
    if value == "needs_review":
        return "needs_review"
    raise ValueError(f"{golden_id}: an expected status must be pass or needs_review, not {value!r}")


def load_set(path: Path = SET_PATH) -> GoldenSet:
    raw = path.read_bytes()
    data = json.loads(raw)
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
    document = data["document"]
    return GoldenSet(
        sha256=sha256_bytes(raw),
        document_name=str(document["name"]),
        document_path=BACKEND_DIR.parent / str(document["path"]),
        document_sha256_prefix=str(document["sha256"]),
        rules=str(data.get("rules", "")),
        categories=categories,
        goldens=goldens,
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


def run_for(session: Session, document: Document, golden: Golden, prompt: PromptPackage, model: str | None = None) -> Run | None:
    """The run that answers this golden under this prompt and model: the live or finished one, else the latest failed one."""
    guidance_id = guidance_id_for(session, golden)
    if golden.guidance is not None and guidance_id is None:
        return None
    key = compute_fingerprint(document.id, guidance_id, golden.question, prompt.sha256, run_options(model))
    runs = session.query(Run).filter(Run.fingerprint == key).order_by(Run.created_at.desc()).all()
    return next((r for r in runs if r.stage != "failed"), runs[0] if runs else None)


def _citations(run: Run) -> tuple[str, ...]:
    cited: list[str] = []
    for finding in run.findings:
        for span in finding.spans:
            if span.section is not None:
                cited.append(f"{span.section.number or span.section.heading} {span.method}")
            else:
                cited.append(f"{span.cited_section_label or '?'} not found")
    return tuple(cited)


def judge(golden: Golden, run: Run | None) -> Verdict:
    """Code decides. A present golden needs a verified citation in one of its sections on a finding
    that does not call the point missing (and carries the expected status when one is named); an
    absent golden needs the run not to assert the point."""
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
    wrong_status: FindingStatusName | None = None
    for finding in run.findings:
        if finding.status not in ASSERTING:
            continue
        for span in finding.spans:
            if span.verified and span.section is not None and span.section.number in golden.sections:
                if golden.status is not None and finding.status != golden.status:
                    wrong_status = finding.status
                    break
                return Verdict("pass", f"verified citation in §{span.section.number} ({span.method})", statuses, cited)
    if wrong_status is not None:
        return Verdict("fail", f"cited the right clause but decided {wrong_status} where {golden.status} was expected", statuses, cited)
    verified = sorted({span.section.number or span.section.heading for f in run.findings for span in f.spans if span.verified and span.section is not None})
    if statuses and all(s == "missing" for s in statuses):
        return Verdict("fail", "answered not found although the contract contains the point", statuses, cited)
    expected = "/".join(golden.sections)
    return Verdict(
        "fail", f"no verified citation in §{expected}; verified citations were in §{', §'.join(verified) if verified else 'nothing'}", statuses, cited
    )


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


def task_of(golden: Golden) -> str:
    return "guidance_comparison" if golden.guidance else "clause_lookup"


def compare_models(session: Session, prompt_version: str, base_model: str, candidate_model: str, golden_set: GoldenSet | None = None) -> ModelComparison:
    golden_set = golden_set or load_set()
    document = golden_document(session, golden_set)
    if document is None:
        raise ValueError("the sample has not been read by the current reader; run the golden set first")
    prompt = load_prompt(prompt_version)
    verdicts: dict[str, dict[str, Verdict]] = {}
    latencies: dict[str, list[float]] = {}
    for model in (base_model, candidate_model):
        verdicts[model] = {}
        latencies[model] = []
        for golden in golden_set.goldens:
            run = run_for(session, document, golden, prompt, model)
            verdicts[model][golden.id] = judge(golden, run)
            if run is not None and run.latency_ms is not None:
                latencies[model].append(run.latency_ms)

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
    )


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
    document = golden_document(session, golden_set)
    if document is None:
        return GoldensOut(
            available=False,
            detail="The sample has not been read by the current reader yet; run `scripts/run_goldens.py` to record the set.",
            set_sha256=golden_set.sha256,
            document_name=golden_set.document_name,
            rules=golden_set.rules,
            categories=golden_set.categories,
            goldens=goldens_out,
        )
    prompts: list[GoldenPromptOut] = []
    verdicts_by_version: dict[str, dict[str, Verdict]] = {}
    latency_by_version: dict[str, float | None] = {}
    category_names = list(golden_set.categories) or sorted({g.category for g in golden_set.goldens})
    for prompt in prompt_versions():
        verdicts: dict[str, Verdict] = {}
        rows: list[GoldenRunOut] = []
        latencies: list[float] = []
        for golden in golden_set.goldens:
            run = run_for(session, document, golden, prompt)
            verdict = judge(golden, run)
            verdicts[golden.id] = verdict
            if run is not None and run.latency_ms is not None:
                latencies.append(run.latency_ms)
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
        recorded = sum(1 for v in verdicts.values() if v.outcome != "missing")
        if recorded == 0:
            continue
        verdicts_by_version[prompt.version] = verdicts
        latency_by_version[prompt.version] = _mean(latencies)
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
                recorded=recorded,
                mean_latency_ms=latency_by_version[prompt.version],
                by_category=[c for c in by_category if c.recorded],
            )
        )
    comparison = None
    if len(prompts) >= 2:
        base, head = prompts[-2], prompts[-1]
        comparison = compare(
            verdicts_by_version[base.version],
            verdicts_by_version[head.version],
            base.version,
            head.version,
            golden_set.goldens,
            latency_by_version[base.version],
            latency_by_version[head.version],
        )
    return GoldensOut(
        available=True,
        detail=None if prompts else "The sample is read; no golden run is recorded yet. Run `scripts/run_goldens.py`.",
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
