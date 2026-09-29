"""Score a CUAD-30 batch against the experts' spans, by the rule pre-registered in docs/CUAD.md.

    .venv/Scripts/python scripts/score_cuad.py <batch_id>              # markdown to stdout
    .venv/Scripts/python scripts/score_cuad.py <batch_id> --json FILE  # also every scored item as JSON

A located text hits an expert span when, after casefolding and collapsing whitespace, one contains
the other, or the two share at least half of their word tokens. For a miss, the retrieval check asks
whether any expert span sat in a section the retriever handed to the model: contained in it, or
with at least 80% of the span's word tokens present in it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.batch.cuad_match import hits, retrieved_carries  # noqa: E402
from app.batch.service import value_for  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Batch, BatchItem, Document, Run, Section  # noqa: E402

MANIFEST = BACKEND / "app" / "batch" / "corpora" / "cuad-30.json"
LABELS = BACKEND / "app" / "batch" / "corpora" / "cuad-30-labels.json"
TASK = BACKEND / "app" / "batch" / "tasks" / "cuad-clauses.json"
PRECISION_FLOOR = 0.80
RECALL_FLOOR = 0.50
RETRIEVAL_TRIGGER = 1 / 3

OUTCOMES = ("correct", "cited elsewhere", "missed", "correct absence", "asserted where experts found none", "failed", "in progress")


@dataclass(frozen=True)
class Scored:
    contract: str
    file: str
    field: str
    category: str
    outcome: str
    run_id: str
    expert_spans: int
    located: str | None
    citation: str | None
    method: str | None
    latency_ms: float | None
    reused: bool
    expert_in_retrieved: bool | None  # for a miss or a wrong citation: did a retrieved section carry an expert span?


def located_texts(run: Run) -> list[str]:
    texts: list[str] = []
    for finding in run.findings:
        if finding.status not in ("pass", "needs_review"):
            continue
        for span in finding.spans:
            if span.verified and span.section is not None and span.start >= 0:
                texts.append(span.section.text[span.start : span.end])
    return texts


def retrieved_texts(session: Session, run: Run) -> list[str]:
    candidates: list[dict[str, Any]] = json.loads(run.candidates_json or "[]")
    ids = [str(c["section_id"]) for c in candidates if c.get("section_id")]
    if not ids:
        return []
    return list(session.execute(select(Section.text).where(Section.id.in_(ids))).scalars().all())


def score_item(session: Session, item: BatchItem, title: str, file: str, category: str, experts: list[str]) -> Scored:
    run = item.run
    value = value_for(run)
    texts = located_texts(run)
    if value.outcome == "answered" and not experts:
        outcome = "asserted where experts found none"
    elif value.outcome == "answered":
        outcome = "correct" if any(hits(text, experts) for text in texts) else "cited elsewhere"
    elif value.outcome in ("not_found", "withheld"):
        outcome = "missed" if experts else "correct absence"
    elif value.outcome == "failed":
        outcome = "failed"
    else:
        outcome = "in progress"
    expert_in_retrieved: bool | None = None
    if outcome in ("missed", "cited elsewhere"):
        retrieved = retrieved_texts(session, run)
        expert_in_retrieved = any(retrieved_carries(section, expert) for section in retrieved for expert in experts)
    return Scored(
        contract=title,
        file=file,
        field=item.field,
        category=category,
        outcome=outcome,
        run_id=run.id,
        expert_spans=len(experts),
        located=texts[0] if texts else None,
        citation=value.citation,
        method=value.method,
        latency_ms=run.latency_ms,
        reused=item.reused,
        expert_in_retrieved=expert_in_retrieved,
    )


def score(session: Session, batch_id: str) -> tuple[Batch, list[Scored]]:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise SystemExit(f"no batch {batch_id}")
    manifest: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    labels: dict[str, dict[str, list[str]]] = json.loads(LABELS.read_text(encoding="utf-8"))
    task: dict[str, Any] = json.loads(TASK.read_text(encoding="utf-8"))
    title_by_file = {str(c["file"]): str(c["title"]) for c in manifest["contracts"]}
    category_by_field = {str(f["key"]): str(f["cuad_category"]) for f in task["fields"]}
    scored: list[Scored] = []
    for item in batch.items:
        document = session.get(Document, item.document_id)
        file = document.name if document is not None else item.document_id
        title = title_by_file.get(file, file)
        category = category_by_field[item.field]
        experts = labels.get(title, {}).get(category, [])
        scored.append(score_item(session, item, title, file, category, experts))
    scored.sort(key=lambda s: (s.file, s.field))
    return batch, scored


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 1)


def rate(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:.2f}" if denominator else "n/a"


def table(scored: list[Scored]) -> str:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(OUTCOMES, 0))
    for s in scored:
        counts[s.category][s.outcome] += 1
        counts["all"][s.outcome] += 1
    lines = [
        "| Category | expert spans | correct | cited elsewhere | missed | correct absence | asserted, experts found none | precision | recall | absence agreement |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    categories = [*dict.fromkeys(s.category for s in scored), "all"]
    for category in categories:
        c = counts[category]
        with_span = sum(1 for s in scored if (s.category == category or category == "all") and s.expert_spans)
        correct, elsewhere, missed = c["correct"], c["cited elsewhere"], c["missed"]
        absent_ok, asserted = c["correct absence"], c["asserted where experts found none"]
        label = f"**{category}**" if category == "all" else category
        lines.append(
            f"| {label} | {with_span} | {correct} | {elsewhere} | {missed} | {absent_ok} | {asserted} | "
            f"{rate(correct, correct + elsewhere)} | {rate(correct, correct + elsewhere + missed)} | {rate(absent_ok, absent_ok + asserted)} |"
        )
    return "\n".join(lines)


def verdict(scored: list[Scored]) -> str:
    correct = sum(s.outcome == "correct" for s in scored)
    elsewhere = sum(s.outcome == "cited elsewhere" for s in scored)
    missed = sum(s.outcome == "missed" for s in scored)
    precision = correct / (correct + elsewhere) if correct + elsewhere else 0.0
    recall = correct / (correct + elsewhere + missed) if correct + elsewhere + missed else 0.0
    lines = [f"citation precision {precision:.2f} (floor {PRECISION_FLOOR:.2f}), recall {recall:.2f} (floor {RECALL_FLOOR:.2f})"]
    fit = precision >= PRECISION_FLOOR and recall >= RECALL_FLOOR
    lines.append(
        "verdict: fit to draft a repository review of these categories"
        if fit
        else "verdict: NOT fit to draft a repository review of these categories; see the categories below the floors"
    )
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


def misses_to_read(scored: list[Scored], labels: dict[str, dict[str, list[str]]]) -> str:
    lines: list[str] = []
    for s in scored:
        if s.outcome not in ("missed", "cited elsewhere", "asserted where experts found none", "failed"):
            continue
        expert = labels.get(s.contract, {}).get(s.category, [])
        expert_head = (expert[0][:90] + ("..." if len(expert[0]) > 90 else "")) if expert else "(none)"
        ours = f'{s.citation or "-"} "{(s.located or "")[:90]}"' if s.located else "-"
        retrieved = "" if s.expert_in_retrieved is None else (" | expert span retrieved: yes" if s.expert_in_retrieved else " | expert span retrieved: no")
        lines.append(f'- {s.file[:40]} / {s.field}: {s.outcome}; experts: "{expert_head}"; workbench: {ours}{retrieved}')
    return "\n".join(lines) if lines else "(none)"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("batch_id")
    parser.add_argument("--json", type=Path, help="also write every scored item to this file")
    args = parser.parse_args(argv)
    init_db()
    with SessionLocal() as session:
        batch, scored = score(session, args.batch_id)
        labels: dict[str, dict[str, list[str]]] = json.loads(LABELS.read_text(encoding="utf-8"))
        created = [s.latency_ms for s in scored if not s.reused and s.latency_ms is not None]
        print(f"batch {batch.id}: task {batch.task}, corpus {batch.corpus}, model {batch.model}, {len(scored)} values, {len(created)} runs created")
        print(f"model latency p50 {percentile(created, 0.5)} ms, p95 {percentile(created, 0.95)} ms")
        print()
        print(table(scored))
        print()
        print(verdict(scored))
        print()
        print("Misses and disagreements, to read one by one:")
        print(misses_to_read(scored, labels))
        if args.json:
            args.json.write_text(json.dumps([asdict(s) for s in scored], indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"\nwritten {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
