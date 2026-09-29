"""The honest local envelope: 1, 5, 10 and 20 concurrent questions against a running API, with the
live model. Reports wall time, time in queue before the model was asked, model latency, verification
time, failures and the API process's peak working set. Nothing here says millions.

    .venv/Scripts/python scripts/load_envelope.py --api http://127.0.0.1:8002 --document ../public/samples/cloud-service-agreement.docx

Questions are the golden set's, each asked once across all levels, so no run is reused and every
level pays the full price. Start the API you measure with its own data directory.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

BACKEND = Path(__file__).resolve().parents[1]
LEVELS = (1, 5, 10, 20)
TERMINAL = {"complete", "unresolved", "failed"}


@dataclass
class Sample:
    question: str
    wall_ms: float
    queue_ms: float | None
    model_ms: float | None
    verify_ms: float | None
    stage: str


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))], 0)


def pid_on_port(port: int) -> int | None:
    out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False).stdout
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line:
            return int(line.split()[-1])
    return None


def working_set_mb(pid: int) -> float | None:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=False).stdout
    match = re.search(r'"([\d,]+) K"', out)
    return round(int(match.group(1).replace(",", "")) / 1024, 1) if match else None


class MemoryWatch:
    def __init__(self, pid: int | None) -> None:
        self.pid = pid
        self.peak: float | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.pid is not None:
                value = working_set_mb(self.pid)
                if value is not None and (self.peak is None or value > self.peak):
                    self.peak = value
            self._stop.wait(1.0)

    def __enter__(self) -> MemoryWatch:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


def ask_and_wait(client: httpx.Client, document_id: str, question: str) -> Sample:
    began = time.perf_counter()
    started = client.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": question})
    started.raise_for_status()
    run_id = started.json()["id"]
    while True:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["stage"] in TERMINAL:
            break
        time.sleep(1.0)
    wall_ms = (time.perf_counter() - began) * 1000
    detail = client.get(f"/api/runs/{run_id}/detail").json()
    stages = {s["stage"]: s for s in detail.get("stages", [])}
    created = detail.get("createdAt")
    checking = stages.get("checking", {}).get("at")
    queue_ms = None
    if created and checking:
        from datetime import datetime

        queue_ms = (datetime.fromisoformat(checking) - datetime.fromisoformat(created)).total_seconds() * 1000
    return Sample(
        question=question,
        wall_ms=wall_ms,
        queue_ms=queue_ms,
        model_ms=run.get("latencyMs"),
        verify_ms=stages.get("verifying", {}).get("durationMs"),
        stage=run["stage"],
    )


def level_row(level: int, samples: list[Sample], elapsed_s: float, peak_mb: float | None) -> str:
    walls = [s.wall_ms for s in samples]
    queues = [s.queue_ms for s in samples if s.queue_ms is not None]
    models = [s.model_ms for s in samples if s.model_ms is not None]
    verifies = [s.verify_ms for s in samples if s.verify_ms is not None]
    failed = sum(1 for s in samples if s.stage == "failed")

    def fmt(value: float | None) -> str:
        return "-" if value is None else f"{value / 1000:.1f}"

    return (
        f"| {level} | {elapsed_s:.0f} | {fmt(percentile(walls, 0.5))} / {fmt(percentile(walls, 0.95))} | "
        f"{fmt(percentile(queues, 0.5))} / {fmt(percentile(queues, 0.95))} | {fmt(percentile(models, 0.5))} / {fmt(percentile(models, 0.95))} | "
        f"{percentile(verifies, 0.5) or 0:.0f} / {percentile(verifies, 0.95) or 0:.0f} | {failed} | {peak_mb if peak_mb is not None else '-'} |"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8002")
    parser.add_argument("--document", type=Path, required=True, help="the contract to ask about; uploaded once")
    parser.add_argument("--levels", default=",".join(str(n) for n in LEVELS))
    parser.add_argument("--json", type=Path, help="also write every sample here")
    args = parser.parse_args(argv)
    levels = [int(n) for n in args.levels.split(",")]

    goldens: dict[str, Any] = json.loads((BACKEND / "app" / "goldens" / "set.json").read_text(encoding="utf-8"))
    questions = [str(g["question"]) for g in goldens["goldens"] if not g.get("guidance")]
    if sum(levels) > len(questions):
        print(f"need {sum(levels)} distinct questions, have {len(questions)}")
        return 2

    client = httpx.Client(base_url=args.api, timeout=1200.0)
    with args.document.open("rb") as handle:
        uploaded = client.post("/api/documents", files={"file": (args.document.name, handle.read(), "application/octet-stream")})
    uploaded.raise_for_status()
    document_id = uploaded.json()["id"]
    port = int(args.api.rsplit(":", 1)[-1].rstrip("/"))
    pid = pid_on_port(port)
    print(f"API pid {pid}, document {document_id}, {len(questions)} questions available")
    print()
    print("| concurrent | level wall s | run wall s p50 / p95 | queue s p50 / p95 | model s p50 / p95 | verify ms p50 / p95 | failed | API peak MB |")
    print("|---|---|---|---|---|---|---|---|")
    every: list[dict[str, Any]] = []
    cursor = 0
    for level in levels:
        batch = questions[cursor : cursor + level]
        cursor += level
        began = time.perf_counter()
        with MemoryWatch(pid) as memory, ThreadPoolExecutor(max_workers=level) as pool:
            samples = list(pool.map(lambda q: ask_and_wait(client, document_id, q), batch))
        elapsed = time.perf_counter() - began
        print(level_row(level, samples, elapsed, memory.peak), flush=True)
        every += [{"level": level, **vars(s)} for s in samples]
    if args.json:
        args.json.write_text(json.dumps(every, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
