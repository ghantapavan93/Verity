"""Ingest a corpus (content-addressed, no model call), compute structural fingerprints, cluster
documents into families at a threshold, and evaluate against the hand labels.

    cd backend && .venv/Scripts/python scripts/cluster_corpus.py --corpus <b1 corpus dir> --corpus <pilot corpus dir>
    cd backend && .venv/Scripts/python scripts/cluster_corpus.py --threshold 0.25    # documents already in the store
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.batch.service import corpus_files, ingest_corpus  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.families.service import DEFAULT_THRESHOLD, report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", action="append", type=Path, default=[], help="directory of contracts to ingest first (repeatable)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="combined similarity at or above which two documents share a family")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as session:
        for corpus in args.corpus:
            documents = ingest_corpus(session, corpus_files(corpus))
            print(f"{corpus}: {len(documents)} documents in the store")
        out = report(session, args.threshold)
    if not out.available:
        print(out.detail)
        return 1
    print(f"\n{out.documents} labeled documents · threshold {out.threshold} · weights {out.weights}")
    if out.missing:
        print(f"not in the store: {', '.join(out.missing)}")
    print("\nfamilies:")
    for family in out.families:
        span = f" (similarity {family.min_similarity}–{family.max_similarity})" if family.min_similarity is not None else ""
        print(f"  {', '.join(family.members)}{span}")
    print("\nclosest pairs:")
    for pair in out.pairs:
        mark = "labeled" if pair.labeled else ""
        parts = f"shingles {pair.shingles:.3f}  headings {pair.headings:.3f}  terms {pair.terms:.3f}"
        print(f"  {pair.a:<10} {pair.b:<10} combined {pair.combined:.3f}  {parts}  {mark}")
    print("\nevaluation (pairwise):")
    for ev in out.evaluations:
        print(f"  {ev.label_set:<9} at {out.threshold}: precision {ev.precision} recall {ev.recall} F1 {ev.f1}")
        print(f"            best F1 {ev.best_f1} at {ev.best_threshold} · {ev.labeled_pairs} labeled pairs")
        print("            sweep " + "  ".join(f"{p.threshold:.2f}:{p.f1:.2f}" for p in ev.sweep if p.threshold <= 0.5))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
