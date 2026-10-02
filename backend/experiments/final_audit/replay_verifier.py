"""What verifier v6 costs, measured on the store, read-only: every verified span is looked for again, in the section and
within the window it was recorded with, by the verifier as it is now. A span that was verified by an earlier tier
and is not found today is one the new rule would have withheld. No model is called and nothing is written.

    cd backend && .venv/Scripts/python experiments/final_audit/replay_verifier.py
"""

from __future__ import annotations

import collections
import json
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.analysis.service import window_of
from app.config import settings
from app.verify.spans import VERIFIER_VERSION, locate

db = sqlite3.connect(f"file:{(settings.data_dir / 'workbench.db').as_posix()}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
rows = db.execute(
    """select s.quote, s.method, sec.text, sec.number, sec.heading, r.options_json, r.id as run_id, r.question
       from evidence_spans s join findings f on f.id = s.finding_id join runs r on r.id = f.run_id join sections sec on sec.id = s.section_id
       where s.verified = 1"""
).fetchall()
print(f"verified spans in the store: {len(rows)}; by the tier that verified them: {dict(collections.Counter(r['method'] for r in rows).most_common())}")
lost = []
for r in rows:
    window = window_of(json.loads(r["options_json"] or "{}"))
    if locate(r["quote"], r["text"][:window], f"{r['number']} {r['heading']}".strip()) is None:
        lost.append(r)
print(f"not located by verifier {VERIFIER_VERSION} today: {len(lost)} span(s) in {len({r['run_id'] for r in lost})} run(s)")
for r in lost:
    print(f"   {r['run_id']} ({r['method']}): {r['quote'][:80]!r}")
goldens = {g["question"] for g in json.loads((BACKEND / "app" / "goldens" / "set.json").read_text(encoding="utf-8"))["goldens"]}
print("of those, on a golden question:", sum(1 for r in lost if r["question"] in goldens))
