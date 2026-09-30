"""Run a field-extraction task over a corpus of contracts and print the batch report.

    cd backend && .venv/Scripts/python scripts/run_batch.py --corpus ../../ivo-experiments/experiments/b1-word-structure/corpus --task core-fields
    cd backend && .venv/Scripts/python scripts/run_batch.py --corpus <dir> --task core-fields --concurrency 2 --label b1-corpus
    cd backend && .venv/Scripts/python scripts/run_batch.py --report <batch_id>

Every (document, field) is an ordinary run: same fingerprint, same verification, same immutable
record. Runs that already exist are reused and counted as such. The numbers are in docs/BATCH.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.batch.service import report, run_batch  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.providers import make_provider  # noqa: E402


def print_report(batch_id: str) -> None:
    with SessionLocal() as session:
        out = report(session, batch_id)
    print(f"\nbatch {out.id} · task {out.task} · corpus {out.corpus} · model {out.model} · concurrency {out.concurrency}")
    print(f"  documents {out.documents} · runs requested {out.requested} · created {out.runs_created} · reused {out.runs_reused}")
    print(f"  wall {out.wall_minutes} min · documents/min {out.documents_per_minute} · values/min {out.values_per_minute}")
    print(f"  answered {out.answered} of {out.requested}")
    print(f"  model latency p50 {out.model_latency_p50_ms} ms · p95 {out.model_latency_p95_ms} ms · mean {out.model_latency_mean_ms} ms")
    print(f"  invalid output {out.invalid_output_runs} · provider errors {out.provider_error_runs} · retries {out.retries}")
    print(f"  failed by reason {out.failed_runs_by_reason}")
    print(f"  findings {out.findings} · withheld {out.withheld_findings} · spans {out.spans} · verified {out.verified_spans}")
    print()
    for row in out.rows:
        cells = []
        for field in out.fields:
            value = row.values[field.key]
            cells.append(f"{field.key}={value.outcome}{' ' + value.citation if value.citation else ''}")
        print(f"  {row.document_name:<28} {' | '.join(cells)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", action="append", type=Path, default=[], help="directory of .docx, .pdf or .txt contracts (repeatable)")
    parser.add_argument("--task", default="core-fields", help="task file under app/batch/tasks")
    parser.add_argument("--label", help="corpus label recorded on the batch; default: the directory name")
    parser.add_argument("--concurrency", type=int, default=1, help="runs in flight at once")
    parser.add_argument("--prompt", help="prompt version; default: the configured one")
    parser.add_argument("--model", help="model; default: the configured one")
    parser.add_argument("--report", metavar="BATCH_ID", help="print the report of a recorded batch and exit")
    args = parser.parse_args()
    init_db()
    if args.report:
        print_report(args.report)
        return 0
    if not args.corpus:
        parser.error("--corpus is required unless --report is given")
    provider = make_provider(model=args.model, workload="batch")
    ok, detail = provider.healthy()
    if not ok:
        print(f"provider not ready: {detail}")
        return 2
    batch_id = run_batch(
        SessionLocal, provider, args.corpus, args.task, corpus_label=args.label, concurrency=args.concurrency, prompt_version=args.prompt, model=args.model
    )
    print_report(batch_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
