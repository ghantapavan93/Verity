"""The six CUAD-30 cases whose expert span lies beyond (or across) the old 5,000-character window, run under a given
window through the ordinary run path (start_run + execute_run, the live provider) and scored with the CUAD rule.

Runs are reused by fingerprint, so a second invocation under the same window makes no model call and only re-reads
the record. Writes ordinary immutable runs into the main store the first time.

usage: python tail_cases.py [--window 6000] [--out results/tail-cases-6000.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app import config  # noqa: E402
from app.application.ingest_document import ingest_document  # noqa: E402
from app.application.start_run import start_run  # noqa: E402
from app.batch.cuad_match import hits  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.hashing import sha256_bytes  # noqa: E402
from app.models import Document, Run  # noqa: E402
from app.providers import make_provider  # noqa: E402
from app.runs.service import execute_run  # noqa: E402

TASK = json.loads((BACKEND / "app" / "batch" / "tasks" / "cuad-clauses.json").read_text(encoding="utf-8"))
QUESTION = {f["key"]: f["question"] for f in TASK["fields"]}
CATEGORY = {f["key"]: f.get("category") or f.get("cuad_category") or f["label"] for f in TASK["fields"]}
LABELS = json.loads((BACKEND / "app" / "batch" / "corpora" / "cuad-30-labels.json").read_text(encoding="utf-8"))
MANIFEST = {c["file"]: c["title"] for c in json.loads((BACKEND / "app" / "batch" / "corpora" / "cuad-30.json").read_text(encoding="utf-8"))["contracts"]}
TEXTS = BACKEND / "data" / "cuad" / "corpus-30"

# From results/window-census.json at 5,000: the four spans that start beyond the window and the two it cuts.
CASES = [
    ("01-2themartcominc", "liability_cap"),
    ("01-2themartcominc", "uncapped_liability"),
    ("22-prolonginternationalcorp", "governing_law"),
    ("25-separateaccountiiofagl", "governing_law"),
    ("02-alamogordofinancialcorp", "governing_law"),
    ("14-impcotechnologiesinc", "non_compete"),
]


def outcome(run: Run, experts: list[str]) -> str:
    if run.stage != "complete":
        return f"{run.stage}:{run.reason}"
    shown = [f for f in run.findings if f.status != "unresolved"]
    if not shown or all(f.status == "missing" for f in shown):
        return "not found"
    located = [s.quote for f in shown for s in f.spans if s.verified]
    if not experts:
        return "asserted where experts found none"
    return "correct" if any(hits(q, experts) for q in located) else "cited elsewhere"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--window", type=int, default=6000)
    parser.add_argument("--out", default=None)
    parser.add_argument("--existing", action="store_true", help="read the recorded runs only: no upload, no model call (any reader version of the file)")
    args = parser.parse_args()
    config.settings.section_window = args.window
    out = args.out or str(Path(__file__).parent / "results" / f"tail-cases-{args.window}.json")
    init_db()
    provider = None if args.existing else make_provider(workload="batch")
    rows: list[dict[str, object]] = []
    with SessionLocal() as session:
        for prefix, field in CASES:
            path = next(p for p in TEXTS.glob(prefix + "*.txt"))
            experts = LABELS[MANIFEST[path.name]][CATEGORY[field]]
            created = False
            if args.existing:
                sha = sha256_bytes(path.read_bytes())
                document_ids = [d.id for d in session.query(Document).filter(Document.sha256 == sha).all()]
                run = (
                    session.query(Run)
                    .filter(Run.document_id.in_(document_ids), Run.question == QUESTION[field], Run.guidance_id.is_(None), Run.stage != "failed")
                    .order_by(Run.created_at.desc())
                    .all()
                )
                run = next((r for r in run if json.loads(r.options_json or "{}").get("section_window", 5000) == args.window), None)
                assert run is not None, f"no recorded run for {prefix} {field} at {args.window}"
            else:
                assert provider is not None
                document = ingest_document(session, path.name, path.read_bytes()).document
                started = start_run(session, document.id, None, QUESTION[field], provider)
                created = started.created
                if created:
                    execute_run(session, started.run.id, provider)
                session.expire_all()
                run = session.get(Run, started.run.id)
                assert run is not None
            verdict = outcome(run, experts)
            rows.append(
                {
                    "contract": prefix,
                    "field": field,
                    "window": args.window,
                    "run_id": run.id,
                    "document_id": run.document_id,
                    "created": created,
                    "outcome": verdict,
                }
            )
            print(f"{prefix[:22]:22} {field:20} window={args.window} run={run.id} created={created} -> {verdict}")
    result = {"window": args.window, "cases": rows, "correct": sum(1 for r in rows if r["outcome"] == "correct"), "of": len(rows)}
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
