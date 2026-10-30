"""Score a CUAD-30 batch against the experts' spans, by the rule pre-registered in docs/CUAD.md.

    .venv/Scripts/python scripts/score_cuad.py <batch_id>              # markdown to stdout
    .venv/Scripts/python scripts/score_cuad.py <batch_id> --json FILE  # also every scored pair as JSON

What is scored is the pre-registered population, not what the batch happens to hold: every contract of the manifest
asked every question of the task (210 pairs for CUAD-30), joined to the batch by the bytes it read. Each pair gets one
outcome. A pair whose run failed, is still in progress, or that the batch never asked of those bytes is a miss for
recall, and a recording with any such pair gets no verdict.

The value scored is the one the batch reports: the first finding whose citation verified (cuad_match.answer_index),
with the texts the verifier located for it. A located text hits an expert span when, after casefolding and collapsing
whitespace, one contains the other, or the two share at least half of their word tokens. For a miss, the retrieval
check asks whether any expert span sat in a section the retriever handed to the model: contained in it, or with at
least 80% of the span's word tokens present in it.

Until 2026-10-30 the scorer took the located texts of every asserting finding, and built its denominators from the
batch's own items, so a failed run left them (stress test EVL-4, EVL-5).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.batch.cuad_match import ANSWERING, OUTCOMES, UNFINISHED, Outcome, answered_texts, outcome, retrieved_carries  # noqa: E402
from app.batch.service import located_texts, value_for  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Batch, Document, Run, Section  # noqa: E402

MANIFEST = BACKEND / "app" / "batch" / "corpora" / "cuad-30.json"
LABELS = BACKEND / "app" / "batch" / "corpora" / "cuad-30-labels.json"
TASK = BACKEND / "app" / "batch" / "tasks" / "cuad-clauses.json"
TASK_NAME = "cuad-clauses"
PRECISION_FLOOR = 0.80
RECALL_FLOOR = 0.50
RETRIEVAL_TRIGGER = 1 / 3


@dataclass(frozen=True)
class Expected:
    """One pair of the pre-registered population: a contract of the manifest, by its bytes, and a question of the task."""

    file: str
    title: str
    sha256: str
    field: str
    category: str
    experts: tuple[str, ...]


@dataclass(frozen=True)
class Scored:
    contract: str
    file: str
    field: str
    category: str
    outcome: Outcome
    run_id: str | None  # None: the batch holds no run for this pair
    expert_spans: int
    located: str | None
    citation: str | None
    method: str | None
    latency_ms: float | None
    reused: bool
    expert_in_retrieved: bool | None  # for a miss or a wrong citation: did a retrieved section carry an expert span?


@dataclass(frozen=True)
class Rates:
    """One row's rates. Precision is over the answered pairs the experts labelled; recall over every pair they labelled,
    finished or not; absence agreement over the finished pairs they did not label. None where the denominator is 0."""

    counts: dict[Outcome, int]
    labelled: int
    precision: float | None
    recall: float | None
    absence: float | None


def population(manifest_path: Path = MANIFEST, labels_path: Path = LABELS, task_path: Path = TASK) -> list[Expected]:
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    labels: dict[str, dict[str, list[str]]] = json.loads(labels_path.read_text(encoding="utf-8"))
    task: dict[str, Any] = json.loads(task_path.read_text(encoding="utf-8"))
    return [
        Expected(
            file=str(contract["file"]),
            title=str(contract["title"]),
            sha256=str(contract["sha256"]),
            field=str(field["key"]),
            category=str(field["cuad_category"]),
            experts=tuple(labels.get(str(contract["title"]), {}).get(str(field["cuad_category"]), [])),
        )
        for contract in manifest["contracts"]
        for field in task["fields"]
    ]


@dataclass(frozen=True)
class Recorded:
    """What the score of one pair needs from its run: as the store holds it, or as a committed recording keeps it."""

    run_id: str
    value: str  # the batch's value for the run (batch.service.value_for): answered, not_found, withheld, failed, in_progress
    findings: list[tuple[str, list[str]]]  # each finding's status and the texts the verifier located for it, in order
    citation: str | None
    method: str | None
    latency_ms: float | None
    reused: bool
    expert_in_retrieved: bool | None  # did a section handed to the model carry an expert span; None without spans


def recorded(session: Session | None, run: Run, experts: Sequence[str], reused: bool = False) -> Recorded:
    value = value_for(run)
    carried: bool | None = None
    if experts and session is not None:
        retrieved = retrieved_texts(session, run)
        carried = any(retrieved_carries(section, expert) for section in retrieved for expert in experts)
    return Recorded(
        run_id=run.id,
        value=value.outcome,
        findings=[(finding.status, located_texts(finding)) for finding in run.findings],
        citation=value.citation,
        method=value.method,
        latency_ms=run.latency_ms,
        reused=reused,
        expert_in_retrieved=carried,
    )


def judge(expected: Expected, run: Recorded | None) -> Scored:
    """One pair's outcome: only the texts of the finding the batch reports are compared (cuad_match.answered_texts), and a
    pair with no run is not run."""
    texts = (answered_texts(run.findings) or []) if run is not None and run.value == "answered" else []
    result: Outcome = "not run" if run is None else outcome(run.value, texts, expected.experts)
    return Scored(
        contract=expected.title,
        file=expected.file,
        field=expected.field,
        category=expected.category,
        outcome=result,
        run_id=run.run_id if run is not None else None,
        expert_spans=len(expected.experts),
        located=texts[0] if texts else None,
        citation=run.citation if run is not None else None,
        method=run.method if run is not None else None,
        latency_ms=run.latency_ms if run is not None else None,
        reused=run.reused if run is not None else False,
        expert_in_retrieved=run.expert_in_retrieved if run is not None and result in ("missed", "cited elsewhere") else None,
    )


def judge_run(run: Run, experts: Sequence[str]) -> tuple[Outcome, Recorded, list[str]]:
    """What one run counts as against these experts' spans, with what was read from it and the texts scored."""
    record = recorded(None, run, experts)
    scored = judge(Expected(file="", title="", sha256="", field="", category="", experts=tuple(experts)), record)
    return scored.outcome, record, (answered_texts(record.findings) or []) if record.value == "answered" else []


def retrieved_texts(session: Session, run: Run) -> list[str]:
    candidates: list[dict[str, Any]] = json.loads(run.candidates_json or "[]")
    ids = [str(c["section_id"]) for c in candidates if c.get("section_id")]
    if not ids:
        return []
    return list(session.execute(select(Section.text).where(Section.id.in_(ids))).scalars().all())


def batch_runs(session: Session, batch: Batch, expected: Sequence[Expected]) -> dict[tuple[str, str], Recorded]:
    """The batch's runs by the bytes they read and the question they asked. A pair is joined to the manifest by sha256,
    so a file of the manifest's name holding other bytes is not scored against the experts' spans of the original."""
    experts = {(pair.sha256, pair.field): pair.experts for pair in expected}
    runs: dict[tuple[str, str], Recorded] = {}
    for item in batch.items:
        document = session.get(Document, item.document_id)
        if document is None or (document.sha256, item.field) in runs:
            continue
        key = (document.sha256, item.field)
        runs[key] = recorded(session, item.run, experts.get(key, ()), item.reused)
    return runs


def score(session: Session, batch_id: str, manifest_path: Path = MANIFEST, labels_path: Path = LABELS, task_path: Path = TASK) -> tuple[Batch, list[Scored]]:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise SystemExit(f"no batch {batch_id}")
    expected = population(manifest_path, labels_path, task_path)
    runs = batch_runs(session, batch, expected)
    scored = sorted((judge(pair, runs.get((pair.sha256, pair.field))) for pair in expected), key=lambda s: (s.file, s.field))
    return batch, scored


# ----------------------------------------------------------------------------- a committed recording


def write_recording(path: Path, batch: Batch, runs: dict[tuple[str, str], Recorded]) -> None:
    """What scoring the batch reads from the store, so a figure published from it is re-derived by code from git alone
    (tests/test_docs_claims.py). The located texts are the verifier's, cut from CUAD contracts (CC BY 4.0)."""
    head = {
        "batch": batch.id,
        "task": batch.task,
        "corpus": batch.corpus,
        "model": batch.model,
        "finished_at": batch.finished_at.isoformat() if batch.finished_at else None,
    }
    pairs = []
    for (sha256, field), run in sorted(runs.items()):
        # A finding that does not assert the point is never the answer, so its located texts are not kept.
        findings = [(status, texts if status in ANSWERING else []) for status, texts in run.findings]
        pairs.append(json.dumps({"sha256": sha256, "field": field, **asdict(run), "findings": findings}, ensure_ascii=False))
    body = json.dumps(head, indent=1, ensure_ascii=False)[:-2] + ',\n "pairs": [\n' + ",\n".join(pairs) + "\n ]\n}\n"
    path.write_text(body, encoding="utf-8", newline="\n")


@dataclass(frozen=True)
class Recording:
    id: str  # the batch's
    task: str
    finished_at: str | None
    runs: dict[tuple[str, str], Recorded]


def load_recording(path: Path) -> Recording:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    runs: dict[tuple[str, str], Recorded] = {}
    for pair in data["pairs"]:
        fields = {key: value for key, value in pair.items() if key not in ("sha256", "field")}
        fields["findings"] = [(str(status), [str(text) for text in texts]) for status, texts in fields["findings"]]
        runs[(str(pair["sha256"]), str(pair["field"]))] = Recorded(**fields)
    return Recording(id=str(data["batch"]), task=str(data["task"]), finished_at=data.get("finished_at"), runs=runs)


def score_recording(recording: Recording, manifest_path: Path = MANIFEST, labels_path: Path = LABELS, task_path: Path = TASK) -> list[Scored]:
    expected = population(manifest_path, labels_path, task_path)
    return sorted((judge(pair, recording.runs.get((pair.sha256, pair.field))) for pair in expected), key=lambda s: (s.file, s.field))


def refusals(batch: Batch | Recording) -> list[str]:
    """What about the batch itself keeps it from carrying the pre-registered verdict."""
    reasons: list[str] = []
    if batch.task != TASK_NAME:
        reasons.append(f"the batch ran task {batch.task}, not {TASK_NAME}")
    if batch.finished_at is None:
        reasons.append("the batch never finished")
    return reasons


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def rates(scored: Sequence[Scored]) -> dict[str, Rates]:
    """Each category's row and "all", in the order the categories first appear: one definition for the table and the
    verdict. Recall counts a failed, in-progress or not-run pair the experts labelled as a miss."""
    groups: dict[str, list[Scored]] = {}
    for s in scored:
        groups.setdefault(s.category, []).append(s)
    groups["all"] = list(scored)
    out: dict[str, Rates] = {}
    for category, rows in groups.items():
        counts: dict[Outcome, int] = dict.fromkeys(OUTCOMES, 0)
        counts.update(Counter(s.outcome for s in rows))
        labelled = sum(1 for s in rows if s.expert_spans)
        correct, elsewhere = counts["correct"], counts["cited elsewhere"]
        absent_ok, asserted = counts["correct absence"], counts["asserted where experts found none"]
        out[category] = Rates(counts, labelled, _ratio(correct, correct + elsewhere), _ratio(correct, labelled), _ratio(absent_ok, absent_ok + asserted))
    return out


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 1)


def shown(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def table(scored: Sequence[Scored]) -> str:
    lines = [
        "| Category | expert spans | correct | cited elsewhere | missed | correct absence | asserted, experts found none | failed | in progress | not run "
        "| precision | recall | absence agreement |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for category, row in rates(scored).items():
        c = row.counts
        label = f"**{category}**" if category == "all" else category
        lines.append(
            f"| {label} | {row.labelled} | {c['correct']} | {c['cited elsewhere']} | {c['missed']} | {c['correct absence']} | "
            f"{c['asserted where experts found none']} | {c['failed']} | {c['in progress']} | {c['not run']} | "
            f"{shown(row.precision)} | {shown(row.recall)} | {shown(row.absence)} |"
        )
    return "\n".join(lines)


def verdict(scored: Sequence[Scored], refusals: Sequence[str] = ()) -> str:
    """The pre-registered verdict, or the reasons the recording cannot carry it. A recording with an unfinished pair is
    not scored as fit or unfit: with failures dropped, six failed questions of seven once read "recall 1.00, fit"."""
    overall = rates(scored)["all"]
    precision, recall = overall.precision or 0.0, overall.recall or 0.0
    failed, in_progress, not_run = (overall.counts[name] for name in ("failed", "in progress", "not run"))
    unfinished = failed + in_progress + not_run
    counted = f", with the {unfinished} unfinished pairs counted as misses" if unfinished else ""
    lines = [f"citation precision {precision:.2f} (floor {PRECISION_FLOOR:.2f}), recall {recall:.2f} (floor {RECALL_FLOOR:.2f}){counted}"]
    reasons = list(refusals)
    if unfinished:
        reasons.append(f"{failed} failed, {in_progress} in progress and {not_run} not run of {len(scored)} values")
    if reasons:
        lines.append(f"verdict: not scorable under the pre-registered rule: {'; '.join(reasons)}")
    elif precision >= PRECISION_FLOOR and recall >= RECALL_FLOOR:
        lines.append("verdict: fit to draft a repository review of these categories")
    else:
        lines.append("verdict: NOT fit to draft a repository review of these categories; see the categories below the floors")
    misses = [s for s in scored if s.outcome in ("missed", "cited elsewhere")]
    not_retrieved = [s for s in misses if s.expert_in_retrieved is False]
    if misses:
        share = len(not_retrieved) / len(misses)
        lines.append(
            f"retrieval: {len(not_retrieved)} of {len(misses)} misses had no expert span among the retrieved sections ({share:.0%}); "
            + (
                "retrieval failed the measurement and earns its replacement"
                if share > RETRIEVAL_TRIGGER
                else "retrieval is not the main cause; the model answered from sections that carried the span"
            )
        )
    return "\n".join(lines)


def misses_to_read(scored: Sequence[Scored], labels: dict[str, dict[str, list[str]]]) -> str:
    lines: list[str] = []
    for s in scored:
        if s.outcome not in ("missed", "cited elsewhere", "asserted where experts found none") and s.outcome not in UNFINISHED:
            continue
        expert = labels.get(s.contract, {}).get(s.category, [])
        expert_head = (expert[0][:90] + ("..." if len(expert[0]) > 90 else "")) if expert else "(none)"
        ours = f'{s.citation or "-"} "{(s.located or "")[:90]}"' if s.located else "-"
        retrieved = "" if s.expert_in_retrieved is None else (" | expert span retrieved: yes" if s.expert_in_retrieved else " | expert span retrieved: no")
        lines.append(f'- {s.file[:40]} / {s.field}: {s.outcome}; experts: "{expert_head}"; workbench: {ours}{retrieved}')
    return "\n".join(lines) if lines else "(none)"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("batch_id", nargs="?", help="the batch in the store")
    parser.add_argument("--json", type=Path, help="also write every scored pair to this file")
    parser.add_argument("--record", type=Path, help="also write what the score read from the store to this file, to commit")
    parser.add_argument("--recording", type=Path, help="score a committed recording instead of the store")
    args = parser.parse_args(argv)
    if (args.batch_id is None) == (args.recording is None):
        parser.error("name a batch in the store or a committed --recording, one of them")
    source: Batch | Recording
    if args.recording is not None:
        source = load_recording(args.recording)
        scored = score_recording(source)
    else:
        init_db()
        with SessionLocal() as session:
            source, scored = score(session, args.batch_id)
            if args.record:
                write_recording(args.record, source, batch_runs(session, source, population()))
    labels: dict[str, dict[str, list[str]]] = json.loads(LABELS.read_text(encoding="utf-8"))
    with_run = [s for s in scored if s.run_id is not None]
    created = [s for s in with_run if not s.reused]
    latencies = [s.latency_ms for s in created if s.latency_ms is not None]
    print(f"batch {source.id}: task {source.task}, {len(scored)} pairs pre-registered, {len(with_run)} with a run, {len(created)} runs created")
    print(f"model latency p50 {percentile(latencies, 0.5)} ms, p95 {percentile(latencies, 0.95)} ms")
    print()
    print(table(scored))
    print()
    print(verdict(scored, refusals(source)))
    print()
    print("Misses, disagreements and unfinished pairs, to read one by one:")
    print(misses_to_read(scored, labels))
    if args.json:
        args.json.write_text(json.dumps([asdict(s) for s in scored], indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwritten {args.json}")
    if args.record:
        print(f"recorded {args.record}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
