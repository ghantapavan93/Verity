"""Cross-projection census with the working-tree code over a snapshot of the production store (read-only source).

For every complete run: the run view, the explanation's shown findings and the findings record must agree on counts,
statuses, status sources and verified quotes; the review shown by the run must be the review shown by the record; and
the explanation must say "reconstructable" exactly when the run recorded an input hash that the rebuilt input meets."""

from __future__ import annotations

import collections
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
LIVE = BACKEND / "data"
sys.path.insert(0, str(BACKEND))

snap = Path(tempfile.mkdtemp(prefix="verity-proj-"))
source = sqlite3.connect(f"file:{(LIVE / 'workbench.db').as_posix()}?mode=ro", uri=True)
target = sqlite3.connect(snap / "workbench.db")
source.backup(target)
target.close()
source.close()
for folder in ("documents", "memos"):
    if (LIVE / folder).exists():
        shutil.copytree(LIVE / folder, snap / folder)

from fastapi.testclient import TestClient

from app import config
from app import db as db_module
from app.main import create_app

config.settings.data_dir = snap
engine = db_module.make_engine(f"sqlite:///{(snap / 'workbench.db').as_posix()}")
db_module.engine = engine
db_module.SessionLocal.configure(bind=engine)


class NoModel:
    name, model = "ollama", "qwen3:8b"

    def healthy(self) -> tuple[bool, str]:
        return True, "census: no model is called"

    def generate_json(self, *_: object) -> None:
        raise AssertionError("the census must not call a model")


client = TestClient(create_app(provider=NoModel()), raise_server_exceptions=False).__enter__()  # type: ignore[arg-type]
db = sqlite3.connect(snap / "workbench.db")
runs = db.execute("select id, stage, document_id from runs").fetchall()
documents = [d[0] for d in db.execute("select id from documents")]

record: dict[str, dict] = {}
capped_documents = 0
for document_id in documents:
    rows = client.get(f"/api/findings?documentId={document_id}").json()
    capped_documents += 1 if len(rows) >= 500 else 0
    for row in rows:
        record[row["id"]] = row
overall = client.get("/api/findings").json()
for row in overall:
    record.setdefault(row["id"], row)

t0 = time.time()
problems: list[tuple[str, str]] = []
checked = reconstructable = hashed = 0
record_covered = record_missing = 0
by_stage = collections.Counter(stage for _, stage, _ in runs)
for run_id, stage, _document in runs:
    if stage != "complete":
        continue
    run = client.get(f"/api/runs/{run_id}").json()
    response = client.get(f"/api/runs/{run_id}/explanation")
    if response.status_code != 200:
        problems.append((run_id, f"explanation HTTP {response.status_code}"))
        continue
    explanation = response.json()
    shown = [f for f in explanation["findings"] if f.get("shown", True)]
    if len(run["findings"]) != len(shown):
        problems.append((run_id, f"count run={len(run['findings'])} explanation(shown)={len(shown)}"))
    by_id = {f["id"]: f for f in shown}
    for finding in run["findings"]:
        explained = by_id.get(finding["id"])
        if explained is None:
            problems.append((run_id, f"finding {finding['id']} missing from the explanation"))
            continue
        recorded = explained.get("recordedPolicyEvaluation") or {}
        if recorded.get("status", finding["status"]) != finding["status"] or recorded.get("source", finding["statusSource"]) != finding["statusSource"]:
            problems.append((run_id, f"status {finding['status']}/{finding['statusSource']} vs explanation {recorded.get('status')}/{recorded.get('source')}"))
        for span in finding["spans"]:
            if span.get("verified") and not any(span["quote"] == match.get("quote") and match.get("verified") for match in explained["sourceMatches"]):
                problems.append((run_id, f"verified quote of {finding['id']} missing from the explanation"))
        row = record.get(finding["id"])
        if row is None:
            record_missing += 1
            continue
        record_covered += 1
        if row["status"] != finding["status"] or row.get("statusSource") != finding["statusSource"] or row.get("review") != finding.get("review"):
            problems.append((run_id, f"record disagrees on {finding['id']}: {row['status']}/{row.get('statusSource')}/{row.get('review')}"))
    has_hash = bool(explanation["reconstruction"].get("recordedInputSha256"))
    hashed += 1 if has_hash else 0
    if explanation["reconstruction"]["reconstructable"]:
        reconstructable += 1
    if has_hash and not explanation["reconstruction"]["reconstructable"]:
        problems.append((run_id, f"hash recorded but not reconstructable: {explanation['reconstruction'].get('problem')}"))
    checked += 1

print(
    json.dumps(
        {
            "runs": len(runs),
            "by_stage": dict(by_stage),
            "complete_checked": checked,
            "explanations_reconstructable": reconstructable,
            "complete_with_recorded_hash": hashed,
            "findings_compared_with_the_record": record_covered,
            "findings_beyond_the_record_caps": record_missing,
            "documents_at_the_500_cap": capped_documents,
            "disagreements": len(problems),
            "seconds": round(time.time() - t0, 1),
        }
    )
)
for run_id, problem in problems[:10]:
    print("  ", run_id, problem)
