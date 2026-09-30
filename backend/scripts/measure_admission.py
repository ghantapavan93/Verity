"""Does batch work harm interactive latency, and does weighted admission help? Measured, not assumed.

Two rounds against the live model, each with the same work: a batch runner asking N fields over the corpus with
concurrency C (workload batch) while a person asks Q questions one after another (workload interactive), all in one
process so that they share the one admission controller. Round A serves the queue first come, first served (the
a single arrival queue); round B serves it as shipped (four interactive admissions per batch admission). The
numbers that matter are the interactive queue waits under each, and whether the batch still finished.

    cd backend && .venv/Scripts/python scripts/measure_admission.py --corpus data/cuad/corpus-30 --documents 3 --questions 4

Writes data/logs/admission-<stamp>.json and prints the two tables. No run is reused: every question carries a
letters-only nonce so the measurement is of calls made, not records found.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.application.ingest_document import ingest_document  # noqa: E402
from app.application.start_run import start_run  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.providers import admission, make_provider  # noqa: E402
from app.providers.admission import Policy, Workload  # noqa: E402
from app.runs.service import execute_run  # noqa: E402

QUESTIONS = [
    "What is the limitation of liability?",
    "How can this agreement be terminated?",
    "What law governs this agreement?",
    "Is there a non-compete clause?",
]
FIELDS = ["What is the limitation of liability?", "What law governs this agreement?", "Can either party terminate for convenience?"]


def nonce() -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(8))


def ask(document_id: str, question: str, workload: Workload, waits: list[tuple[str, float, float]]) -> None:
    provider = make_provider(workload=workload)
    with SessionLocal() as session:
        started = start_run(session, document_id, None, f"{question} [[m:{nonce()}]]", provider)
        run_id = started.run.id
        begun = time.perf_counter()
        execute_run(session, run_id, provider)
    last = getattr(provider, "last", None)
    waits.append((workload, last.queue_wait_ms if last else 0.0, (time.perf_counter() - begun) * 1000))


def round_trip(label: str, policy: Policy, documents: list[str], questions: int, concurrency: int) -> dict[str, object]:
    admission.policy = policy
    waits: list[tuple[str, float, float]] = []
    batch_jobs = [(doc, field) for doc in documents for field in FIELDS]
    lock = threading.Lock()

    def batch_worker() -> None:
        while True:
            with lock:
                if not batch_jobs:
                    return
                doc, field = batch_jobs.pop(0)
            ask(doc, field, "batch", waits)

    def person() -> None:
        for i in range(questions):
            ask(documents[i % len(documents)], QUESTIONS[i % len(QUESTIONS)], "interactive", waits)

    started = time.perf_counter()
    workers = [threading.Thread(target=batch_worker) for _ in range(concurrency)]
    for w in workers:
        w.start()
    time.sleep(3)  # the batch is already queued when the person arrives
    someone = threading.Thread(target=person)
    someone.start()
    someone.join()
    interactive_done = time.perf_counter() - started
    for w in workers:
        w.join()
    total = time.perf_counter() - started
    by = {"interactive": [w for w in waits if w[0] == "interactive"], "batch": [w for w in waits if w[0] == "batch"]}
    summary: dict[str, object] = {
        "label": label,
        "policy": policy,
        "interactive_queue_wait_ms": sorted(w[1] for w in by["interactive"]),
        "interactive_wall_ms": sorted(w[2] for w in by["interactive"]),
        "batch_queue_wait_ms": sorted(w[1] for w in by["batch"]),
        "person_finished_s": round(interactive_done, 1),
        "everything_finished_s": round(total, 1),
        "calls": len(waits),
    }
    print(f"\n{label}: person finished in {interactive_done:.0f} s, everything in {total:.0f} s")
    print(f"  interactive queue waits (ms): {[round(w[1]) for w in by['interactive']]}")
    print(f"  batch queue waits (ms):       {[round(w[1]) for w in by['batch']]}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--documents", type=int, default=3)
    parser.add_argument("--questions", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()
    init_db()
    print(f"admission limit {admission.limit}; provider {make_provider().name}")
    paths = sorted(Path(args.corpus).glob("*"))[: args.documents]
    documents: list[str] = []
    with SessionLocal() as session:
        for path in paths:
            documents.append(ingest_document(session, path.name, path.read_bytes()).document.id)
    results = [
        round_trip("A · first come, first served", "fifo", documents, args.questions, args.concurrency),
        round_trip("B · four interactive per batch", "weighted", documents, args.questions, args.concurrency),
    ]
    out = BACKEND / "data" / "logs" / f"admission-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nwritten {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
