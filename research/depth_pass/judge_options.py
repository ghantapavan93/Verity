"""Judge the goldens recorded under a run option against the baseline recording of the same prompt (answer-v2, k = 6,
reader v4 document). `run_goldens.py --report` compares prompt versions; this compares option values under one prompt,
reading the store only (no model call).

usage: python judge_options.py section_window      # runs whose options carry section_window
       python judge_options.py retrieval_aliases   # runs whose options carry retrieval_aliases
       python judge_options.py v5                  # runs on the reader-v5 golden document with both defaults on
       [--out results/goldens-<key>.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.analysis.service import load_prompt  # noqa: E402
from app.application.start_run import compute_fingerprint, run_options  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.goldens.service import guidance_id_for, judge, load_set  # noqa: E402
from app.models import Document, Run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("key", choices=["section_window", "retrieval_aliases", "v5"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    key = args.key
    out = args.out or str(Path(__file__).parent / "results" / f"goldens-{key.replace('_', '-')}.json")
    init_db()
    golden_set = load_set()
    prompt = load_prompt("answer-v2")
    with SessionLocal() as session:
        documents = session.query(Document).filter(Document.sha256.startswith(golden_set.document_sha256_prefix)).order_by(Document.created_at.desc()).all()
        by_version = {d.parser_version: d for d in reversed(documents)}  # the latest document per reader version
        base_doc = by_version["v4"]
        cand_doc = by_version.get("v5") if key == "v5" else base_doc
        rows: list[dict[str, object]] = []
        gains, regressions, same_pass, same_fail, pending = [], [], [], [], []
        latencies: list[float] = []
        for golden in golden_set.goldens:
            guidance_id = guidance_id_for(session, golden)
            # The baseline was recorded before the two options existed: its identity carries neither.
            baseline_options = {k: v for k, v in run_options(None).items() if k not in ("section_window", "retrieval_aliases")}
            base_key = compute_fingerprint(base_doc.id, guidance_id, golden.question, prompt.sha256, baseline_options)
            base_runs = session.query(Run).filter(Run.fingerprint == base_key).order_by(Run.created_at.desc()).all()
            base = next((r for r in base_runs if r.stage != "failed"), base_runs[0] if base_runs else None)
            cand = None
            if cand_doc is not None:
                query = session.query(Run).filter(Run.document_id == cand_doc.id, Run.question == golden.question, Run.prompt_hash == prompt.sha256)
                query = query.filter(Run.guidance_id == guidance_id) if guidance_id else query.filter(Run.guidance_id.is_(None))
                runs = [r for r in query.order_by(Run.created_at.desc()).all() if (key in json.loads(r.options_json or "{}")) == (key != "v5")]
                if key == "v5":
                    runs = [r for r in runs if "section_window" in r.options_json and "retrieval_aliases" in r.options_json]
                cand = next((r for r in runs if r.stage != "failed"), runs[0] if runs else None)
            b, h = judge(golden, base), judge(golden, cand)
            if cand is not None and cand.latency_ms:
                latencies.append(cand.latency_ms)
            if h.outcome == "missing":
                pending.append(golden.id)
            elif b.outcome != "pass" and h.outcome == "pass":
                gains.append(golden.id)
            elif b.outcome == "pass" and h.outcome != "pass":
                regressions.append(golden.id)
            elif h.outcome == "pass":
                same_pass.append(golden.id)
            else:
                same_fail.append(golden.id)
            rows.append(
                {
                    "golden": golden.id,
                    "category": golden.category,
                    "base_run": base.id if base else None,
                    "base": b.outcome,
                    "candidate_run": cand.id if cand else None,
                    "candidate": h.outcome,
                    "because": h.because,
                }
            )
            print(f"{golden.id} {golden.category[:12]:<12} base={b.outcome:<7} cand={h.outcome:<7} {golden.question[:48]:<48} {h.because[:90]}")
        latencies.sort()
        result = {
            "key": key,
            "baseline_document": base_doc.id,
            "candidate_document": cand_doc.id if cand_doc else None,
            "judged": len(golden_set.goldens) - len(pending),
            "candidate_pass": len(gains) + len(same_pass),
            "gains": gains,
            "regressions": regressions,
            "same_pass": len(same_pass),
            "same_fail": same_fail,
            "pending": pending,
            "median_model_latency_s": round(latencies[len(latencies) // 2] / 1000, 1) if latencies else None,
            "rows": rows,
        }
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"\ncandidate pass: {result['candidate_pass']} of {result['judged']} judged ({len(pending)} pending); "
        f"gains {gains}; regressions {regressions}; same fail {same_fail}"
    )
    print("wrote", out)


if __name__ == "__main__":
    main()
