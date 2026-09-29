"""Does BM25 hand the model the section the answer lives in? Measured against labels, no model call.

    .venv/Scripts/python scripts/eval_retrieval.py

Three labelled sets: CUAD-30 (experts' spans), the SkillOpt CUAD split (experts' spans), and the
goldens on the sample (section numbers). A candidate section counts as a hit when it carries an
expert span (app.batch.cuad_match.retrieved_carries) or its number is one the golden names.
Thresholds are pre-registered in docs/RETRIEVAL.md.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402

from app.batch.cuad_match import retrieved_carries  # noqa: E402
from app.config import settings  # noqa: E402
from app.ingest import ingest  # noqa: E402
from app.retrieval.lexical import LexicalIndex  # noqa: E402

KS = (1, 3, 5, 6, 8)
EMBED_MODEL = "nomic-embed-text"
RRF_K = 60
_embed_cache: dict[str, list[list[float]]] = {}
TASK = json.loads((BACKEND / "app" / "batch" / "tasks" / "cuad-clauses.json").read_text(encoding="utf-8"))
QUESTION_BY_CATEGORY = {str(f["cuad_category"]): str(f["question"]) for f in TASK["fields"]}


@dataclass(frozen=True)
class Case:
    set_name: str
    category: str
    question: str
    sections: list[tuple[str, str, str]]  # (number, heading, text) in document order
    matches: Any  # callable(number, text) -> bool


@dataclass(frozen=True)
class Outcome:
    set_name: str
    category: str
    reachable: bool
    rank: int | None  # 1-based rank of the first hit within the top max(KS), None if none
    noise_at_6: float | None  # share of the top-6 candidates that are not hits, when the case is reachable


_sections_cache: dict[str, list[tuple[str, str, str]]] = {}


def sections_of(path: Path) -> list[tuple[str, str, str]]:
    key = str(path)
    if key not in _sections_cache:
        parsed = ingest(path.name, path.read_bytes())
        _sections_cache[key] = [(s.number, s.heading, s.text) for s in parsed.sections]
    return _sections_cache[key]


def span_cases(set_name: str, texts_dir: Path, labels: dict[str, dict[str, list[str]]], files_by_title: dict[str, str]) -> list[Case]:
    cases: list[Case] = []
    for title, by_category in labels.items():
        file = files_by_title.get(title)
        if file is None:
            continue
        sections = sections_of(texts_dir / file)
        for category, spans in by_category.items():
            if not spans or category not in QUESTION_BY_CATEGORY:
                continue
            cases.append(
                Case(set_name, category, QUESTION_BY_CATEGORY[category], sections, lambda _n, text, spans=spans: any(retrieved_carries(text, e) for e in spans))
            )
    return cases


def golden_cases() -> list[Case]:
    data = json.loads((BACKEND / "app" / "goldens" / "set.json").read_text(encoding="utf-8"))
    sample = BACKEND.parent / str(data["document"]["path"])
    sections = sections_of(sample)
    cases: list[Case] = []
    for golden in data["goldens"]:
        if golden["kind"] != "present" or not golden["sections"]:
            continue
        wanted = set(golden["sections"])
        question = str(golden["question"]) + (f" {golden['guidance']}" if golden.get("guidance") else "")
        cases.append(Case("goldens", str(golden["category"]), question, sections, lambda number, _t, wanted=wanted: number in wanted))
    return cases


def embed(texts: list[str]) -> list[list[float]]:
    response = httpx.post(f"{settings.ollama_url}/api/embed", json={"model": EMBED_MODEL, "input": texts}, timeout=600.0)
    response.raise_for_status()
    vectors: list[list[float]] = response.json()["embeddings"]
    return vectors


def section_vectors(case: Case) -> list[list[float]]:
    key = str(hash(tuple(text for _n, _h, text in case.sections)))
    if key not in _embed_cache:
        out: list[list[float]] = []
        texts = [f"{heading} {text[:2000]}" for _n, heading, text in case.sections]
        for start in range(0, len(texts), 64):
            out += embed(texts[start : start + 64])
        _embed_cache[key] = out
    return _embed_cache[key]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1.0)


def ranked_indices(case: Case, mode: str, k: int) -> list[int]:
    """Section indices in rank order for BM25, dense embeddings, or their reciprocal-rank fusion."""
    index = LexicalIndex([(heading, text) for _n, heading, text in case.sections])
    lexical = [c.index for c in index.search(case.question, len(case.sections))] or list(range(len(case.sections)))
    if mode == "bm25":
        return lexical[:k]
    query = embed([f"search_query: {case.question}"])[0]
    vectors = section_vectors(case)
    dense = sorted(range(len(vectors)), key=lambda i: -cosine(query, vectors[i]))
    if mode == "dense":
        return dense[:k]
    fused: dict[int, float] = {}
    for ranking in (lexical, dense):
        for rank, i in enumerate(ranking, start=1):
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(fused, key=lambda i: -fused[i])[:k]


def evaluate(case: Case, mode: str = "bm25", k: int = max(KS)) -> Outcome:
    hits = [case.matches(number, text) for number, _heading, text in case.sections]
    reachable = any(hits)
    ranked = [hits[i] for i in ranked_indices(case, mode, k)]
    rank = next((i + 1 for i, hit in enumerate(ranked) if hit), None)
    noise = (sum(1 for h in ranked[:6] if not h) / max(1, len(ranked[:6]))) if reachable else None
    return Outcome(case.set_name, case.category, reachable, rank, noise)


def summarise(outcomes: list[Outcome]) -> dict[str, Any]:
    n = len(outcomes)
    reachable = [o for o in outcomes if o.reachable]
    row: dict[str, Any] = {"cases": n, "reachable": len(reachable)}
    for k in KS:
        row[f"R@{k}"] = sum(1 for o in reachable if o.rank is not None and o.rank <= k) / max(1, len(reachable))
    row["MRR"] = sum(1 / o.rank for o in reachable if o.rank is not None) / max(1, len(reachable))
    noises = [o.noise_at_6 for o in reachable if o.noise_at_6 is not None]
    row["noise@6"] = sum(noises) / max(1, len(noises))
    return row


def table(title: str, rows: dict[str, dict[str, Any]]) -> str:
    lines = [f"**{title}**", "", "| Set | cases | reachable | R@1 | R@3 | R@5 | R@6 | R@8 | MRR | noise@6 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in rows.items():
        lines.append(
            f"| {name} | {r['cases']} | {r['reachable']} | " + " | ".join(f"{r[f'R@{k}']:.2f}" for k in KS) + f" | {r['MRR']:.2f} | {r['noise@6']:.2f} |"
        )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["bm25", "dense", "hybrid"], action="append", help="ranking to evaluate (repeatable); default bm25")
    args = parser.parse_args(argv)
    modes = args.mode or ["bm25"]
    corpora = BACKEND / "app" / "batch" / "corpora"
    cuad30 = json.loads((corpora / "cuad-30.json").read_text(encoding="utf-8"))
    labels30 = json.loads((corpora / "cuad-30-labels.json").read_text(encoding="utf-8"))
    cases = span_cases("CUAD-30", BACKEND / "data" / "cuad" / "corpus-30", labels30, {c["title"]: c["file"] for c in cuad30["contracts"]})

    skill_dir = BACKEND / "data" / "skillopt" / "data"
    labels_skill: dict[str, dict[str, list[str]]] = {}
    files_skill: dict[str, str] = {}
    for split in ("train", "val", "test"):
        items_path = skill_dir / split / "items.json"
        if items_path.exists():
            for item in json.loads(items_path.read_text(encoding="utf-8")):
                labels_skill.setdefault(item["title"], {})[item["category"]] = list(item["expert_spans"])
                files_skill[item["title"]] = item["contract_name"]
    cases += span_cases("CUAD-SkillOpt-30", skill_dir / "contracts", labels_skill, files_skill)
    cases += golden_cases()

    for mode in modes:
        outcomes = [evaluate(c, mode) for c in cases]
        by_set = {name: summarise([o for o in outcomes if o.set_name == name]) for name in ("CUAD-30", "CUAD-SkillOpt-30", "goldens")}
        cuad_all = summarise([o for o in outcomes if o.set_name.startswith("CUAD")])
        labels = {"bm25": "BM25, heading x3", "dense": f"dense ({EMBED_MODEL}, cosine)", "hybrid": f"hybrid (BM25 + {EMBED_MODEL}, RRF)"}
        label = labels[mode]
        print(table(f"{label}; k = {settings.retrieval_k} in production", {**by_set, "CUAD both": cuad_all}))
        print()
        categories = sorted({o.category for o in outcomes if o.set_name.startswith("CUAD")})
        cuad = [o for o in outcomes if o.set_name.startswith("CUAD")]
        print(table(f"{mode}: CUAD by category, both sets", {c: summarise([o for o in cuad if o.category == c]) for c in categories}))
        print()
    unreachable = [o for o in outcomes if not o.reachable]
    print(
        f"unreachable (no section carries the span at all): {len(unreachable)} of {len(outcomes)}; by set: "
        + ", ".join(f"{s}={sum(1 for o in unreachable if o.set_name == s)}" for s in by_set)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
