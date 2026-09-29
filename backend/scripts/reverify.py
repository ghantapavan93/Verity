"""Replay verification over recorded runs with the current verifier and report what would change.
No model call, no change to any run.

    cd backend && .venv/Scripts/python scripts/reverify.py <run_id> [<run_id> ...]
    cd backend && .venv/Scripts/python scripts/reverify.py --withheld      # every run with an unverified span
    cd backend && .venv/Scripts/python scripts/reverify.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.application.reverify_run import reverify_run  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import EvidenceSpan, Finding, Run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_ids", nargs="*")
    parser.add_argument("--withheld", action="store_true", help="every run that has at least one unverified span")
    parser.add_argument("--all", action="store_true", help="every run with raw output")
    args = parser.parse_args()

    init_db()
    gained = lost = spans = 0
    with SessionLocal() as session:
        if args.all:
            run_ids = list(session.scalars(select(Run.id).where(Run.raw_output.is_not(None)).order_by(Run.created_at)))
        elif args.withheld:
            statement = select(Run.id).join(Finding, Finding.run_id == Run.id).join(EvidenceSpan, EvidenceSpan.finding_id == Finding.id)
            run_ids = sorted(set(session.scalars(statement.where(EvidenceSpan.verified.is_(False)))))
        else:
            run_ids = args.run_ids
        if not run_ids:
            print("nothing to replay")
            return 0
        for run_id in run_ids:
            replay = reverify_run(session, run_id)
            print(f"\n{replay.run_id} {replay.prompt_version} · {replay.question[:70]}")
            if replay.problem:
                print(f"   {replay.problem}")
                continue
            for span in replay.spans:
                spans += 1
                mark = {"gained": "+", "lost": "-", "moved": "~", "same": " "}[span.change]
                print(f" {mark} f{span.finding}s{span.span} {span.stored_method:<18} -> {span.method:<20} {span.section:<10} {span.quote[:60]!r}")
            gained += replay.gained
            lost += replay.lost
    print(f"\n{spans} spans replayed: {gained} newly verified, {lost} newly unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
