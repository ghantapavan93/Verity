"""How often does an answer-bearing span sit in the part of a section the model never sees?

The reader splits sections at 6,000 characters; before 2026-10-01 the prompt carried the first 5,000 of each
candidate. Over the CUAD-30 labels (experts' spans) this counts, per labelled span, the section that carries it,
that section's length, and where the span starts and ends inside it. No model call, nothing written to any store.

usage: python tail_measure.py [--window 5000] [--out results/window-census.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.batch.cuad_match import retrieved_carries  # noqa: E402
from app.ingest import ingest  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.casefold())


def position(section: str, span: str) -> tuple[int, int] | None:
    """Start and end of the span inside the section, on whitespace-collapsed casefolded text, by its first and
    last forty characters (CUAD spans are copied from the same source text, so this nearly always lands)."""
    s = norm(section)
    head = norm(span)[:40]
    tail = norm(span)[-40:]
    i = s.find(head)
    if i < 0:
        return None
    j = s.find(tail, i)
    end = j + len(tail) if j >= 0 else min(len(s), i + len(norm(span)))
    return i, end


def census(window: int) -> dict[str, object]:
    results: list[dict[str, object]] = []
    contracts = json.loads((BACKEND / "app" / "batch" / "corpora" / "cuad-30.json").read_text(encoding="utf-8"))["contracts"]
    labels = json.loads((BACKEND / "app" / "batch" / "corpora" / "cuad-30-labels.json").read_text(encoding="utf-8"))
    texts = BACKEND / "data" / "cuad" / "corpus-30"
    for contract in contracts:
        path = texts / contract["file"]
        if not path.exists():
            continue
        parsed = ingest(path.name, path.read_bytes())
        sections = [s.text for s in parsed.sections]
        for category, spans in labels.get(contract["title"], {}).items():
            for span in spans:
                carriers = [t for t in sections if retrieved_carries(t, span)]
                if not carriers:
                    results.append({"file": path.name[:40], "category": category, "carried": False})
                    continue
                section = max(carriers, key=len)  # the longest carrier is the worst case for the window
                pos = position(section, span)
                results.append(
                    {
                        "file": path.name[:40],
                        "category": category,
                        "carried": True,
                        "section_len": len(section),
                        "start": pos[0] if pos else None,
                        "end": pos[1] if pos else None,
                    }
                )
    carried = [r for r in results if r["carried"]]
    located = [r for r in carried if r["start"] is not None]
    beyond = [r for r in located if r["start"] >= window]  # type: ignore[operator]
    cut = [r for r in located if r["start"] < window < r["end"]]  # type: ignore[operator]
    return {
        "window": window,
        "labelled_spans": len(results),
        "carried_by_a_section": len(carried),
        "carrier_longer_than_window": sum(1 for r in carried if r["section_len"] > window),  # type: ignore[operator]
        "position_located": len(located),
        "starts_beyond_window": beyond,
        "cut_by_window": cut,
        "longest_carriers": sorted(r["section_len"] for r in carried)[-10:],  # type: ignore[type-var]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--window", type=int, default=5000)
    parser.add_argument("--out", default=str(Path(__file__).parent / "results" / "window-census.json"))
    args = parser.parse_args()
    result = census(args.window)
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"labelled spans {result['labelled_spans']}; carried {result['carried_by_a_section']}; carrier longer than {args.window}: "
        f"{result['carrier_longer_than_window']}; start beyond: {len(result['starts_beyond_window'])}; cut: {len(result['cut_by_window'])}"  # type: ignore[arg-type]
    )
    print("wrote", args.out)


if __name__ == "__main__":
    main()
