"""Rebuild every recorded model input from the record and compare it with the hash the checking stage wrote.
No model call, no change to any run. This is the measurement behind "show me exactly what the model saw".

    cd backend && .venv/Scripts/python scripts/reconstruct_inputs.py --all
    cd backend && .venv/Scripts/python scripts/reconstruct_inputs.py <run_id> [--show]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.application.reconstruct_input import reconstruct_input  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_ids", nargs="*")
    parser.add_argument("--all", action="store_true", help="every run that reached the model")
    parser.add_argument("--show", action="store_true", help="print the reconstructed user message of each run (never in a log)")
    args = parser.parse_args()

    init_db()
    verdicts: Counter[str] = Counter()
    by_prompt: Counter[tuple[str, str]] = Counter()
    truncated = 0
    slices = 0
    with SessionLocal() as session:
        run_ids = list(session.scalars(select(Run.id).where(Run.raw_output.is_not(None)).order_by(Run.created_at))) if args.all else args.run_ids
        if not run_ids:
            print("nothing to reconstruct")
            return 0
        for run_id in run_ids:
            result = reconstruct_input(session, run_id)
            verdict = "match" if result.matches else (result.problem or "mismatch")
            verdicts[verdict] += 1
            by_prompt[(result.prompt_version, "match" if result.matches else "mismatch")] += 1
            slices += len(result.slices)
            truncated += sum(1 for s in result.slices if s.truncated)
            if not result.matches or args.show:
                print(f"{run_id} {result.prompt_version}: {verdict}")
                if args.show and result.user:
                    print(result.user)
    print()
    for verdict, count in verdicts.most_common():
        print(f"{count:5d}  {verdict}")
    print()
    for (prompt_version, verdict), count in sorted(by_prompt.items()):
        print(f"{count:5d}  {prompt_version} {verdict}")
    print(f"\n{slices} context slices, {truncated} truncated to the prompt window")
    return 0 if verdicts and set(verdicts) == {"match"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
