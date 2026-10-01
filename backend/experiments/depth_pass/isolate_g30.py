"""g30 withheld under the combined tree (reader v5 document, window 6,000, aliases on) and passed under each option alone
on the v4 document. Which element moves it: g30 on the v5 document under each of the other three settings.

Runs are reused by fingerprint, so a second invocation makes no model call. The answer recorded on 2026-10-01: all
three withhold the same paraphrase; the six candidates and their text are identical to the v4 document's, and the two
model inputs differ in one line, the contract's filename (docs/GOLDENS.md, Recording 6c).

usage: python isolate_g30.py [--out results/g30-isolation.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app import config  # noqa: E402
from app.application.save_guidance import save_guidance  # noqa: E402
from app.application.start_run import start_run  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.goldens.service import judge, load_set  # noqa: E402
from app.models import Document, Run  # noqa: E402
from app.providers import make_provider  # noqa: E402
from app.runs.service import execute_run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(Path(__file__).parent / "results" / "g30-isolation.json"))
    args = parser.parse_args()
    init_db()
    golden_set = load_set()
    golden = next(g for g in golden_set.goldens if g.id == "g30")
    provider = make_provider(workload="batch")
    rows: list[dict[str, object]] = []
    with SessionLocal() as session:
        docs = session.query(Document).filter(Document.sha256.startswith(golden_set.document_sha256_prefix)).order_by(Document.created_at).all()
        v5 = {d.parser_version: d for d in docs}["v5"]
        document_id = v5.id
        gid = save_guidance(session, golden.guidance, source="golden").guidance.id
        for window, aliases in ((5000, False), (6000, False), (5000, True)):
            config.settings.section_window = window
            config.settings.retrieval_aliases = aliases
            started = start_run(session, v5.id, gid, golden.question, provider, prompt_version="answer-v2")
            began = time.perf_counter()
            if started.created:
                execute_run(session, started.run.id, provider)
            session.expire_all()
            run = session.get(Run, started.run.id)
            assert run is not None
            verdict = judge(golden, run)
            quotes = [{"cited": s.cited_section_label, "verified": s.verified, "quote": s.quote} for f in run.findings for s in f.spans]
            rows.append(
                {
                    "window": window,
                    "aliases": aliases,
                    "run_id": run.id,
                    "created": started.created,
                    "outcome": verdict.outcome,
                    "because": verdict.because,
                    "spans": quotes,
                }
            )
            print(
                f"window={window} aliases={aliases} created={started.created} run={run.id} {verdict.outcome} "
                f"{time.perf_counter() - began:5.1f} s  {verdict.because}"
            )
    Path(args.out).write_text(json.dumps({"golden": "g30", "document": document_id, "rows": rows}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
