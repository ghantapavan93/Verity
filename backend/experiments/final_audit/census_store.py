"""Phases 9 and 24: a consistency census of the production store, taken on a snapshot, and the restore of that
snapshot into a working application.

The snapshot is made with SQLite's online backup API from a read-only connection (the live database is never written)
plus a copy of the documents and memos directories. Everything after that reads the snapshot only.
"""

from __future__ import annotations

import collections
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PureWindowsPath

BACKEND = Path(__file__).resolve().parents[2]
LIVE = BACKEND / "data"
sys.path.insert(0, str(BACKEND))

snap = Path(tempfile.mkdtemp(prefix="verity-snapshot-"))
t0 = time.perf_counter()
source = sqlite3.connect(f"file:{(LIVE / 'workbench.db').as_posix()}?mode=ro", uri=True)
target = sqlite3.connect(snap / "workbench.db")
source.backup(target)
target.close()
live_counts = {
    t: source.execute(f"select count(*) from {t}").fetchone()[0] for t in ("documents", "runs", "findings", "evidence_spans", "memos", "finding_reviews")
}
source.close()
for folder in ("documents", "memos"):
    if (LIVE / folder).exists():
        shutil.copytree(LIVE / folder, snap / folder)
print(f"snapshot at {snap} in {time.perf_counter() - t0:.1f} s; db {(snap / 'workbench.db').stat().st_size / 1e6:.1f} MB")
wal = LIVE / "workbench.db-wal"
print(f"live WAL file: {wal.stat().st_size if wal.exists() else 0} bytes (a plain copy of workbench.db alone would miss whatever is only in it)")

db = sqlite3.connect(snap / "workbench.db")
db.row_factory = sqlite3.Row
print(
    "integrity_check:", db.execute("pragma integrity_check").fetchone()[0], "| foreign_key_check rows:", len(db.execute("pragma foreign_key_check").fetchall())
)
counts = {t: db.execute(f"select count(*) from {t}").fetchone()[0] for t in live_counts}
print("row counts snapshot == live:", counts == live_counts, counts)

problems: dict[str, list[str]] = collections.defaultdict(list)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---- documents and their bytes
docs = db.execute("select id, name, sha256, parser_version from documents").fetchall()
have_bytes = 0
expected_files = set()
for d in docs:
    path = snap / "documents" / f"{d['sha256']}{Path(d['name']).suffix.lower()}"
    expected_files.add(path.name)
    if not path.exists():
        problems["document row without bytes"].append(f"{d['id']} {d['name'][:40]} (reader {d['parser_version']})")
        continue
    have_bytes += 1
    if sha(path) != d["sha256"]:
        problems["document bytes do not hash to the row"].append(d["id"])
on_disk = {p.name for p in (snap / "documents").iterdir()} if (snap / "documents").exists() else set()
orphan_docs = sorted(on_disk - expected_files)
print(f"documents: {len(docs)} rows, {have_bytes} with bytes whose hash matches; files with no row: {len(orphan_docs)}")

# ---- sections, runs, guidance
print(
    "sections whose document is missing:",
    db.execute("select count(*) from sections s left join documents d on d.id = s.document_id where d.id is null").fetchone()[0],
)
print(
    "runs whose document hash disagrees with the document:",
    db.execute("select count(*) from runs r join documents d on d.id = r.document_id where r.document_sha256 != d.sha256").fetchone()[0],
)
print(
    "runs whose guidance hash disagrees with the guidance:",
    db.execute("select count(*) from runs r join guidance g on g.id = r.guidance_id where r.guidance_sha256 != g.sha256").fetchone()[0],
)
bad_guidance = [g["id"] for g in db.execute("select id, text, sha256 from guidance") if hashlib.sha256(g["text"].encode("utf-8")).hexdigest() != g["sha256"]]
print("guidance rows whose text does not hash to the row:", len(bad_guidance))
print("runs with no document row:", db.execute("select count(*) from runs r left join documents d on d.id = r.document_id where d.id is null").fetchone()[0])
print("findings with no run:", db.execute("select count(*) from findings f left join runs r on r.id = f.run_id where r.id is null").fetchone()[0])
print(
    "spans with no finding:", db.execute("select count(*) from evidence_spans s left join findings f on f.id = s.finding_id where f.id is null").fetchone()[0]
)
print(
    "reviews with no finding:",
    db.execute("select count(*) from finding_reviews v left join findings f on f.id = v.finding_id where f.id is null").fetchone()[0],
)
print("non-terminal runs:", dict(db.execute("select stage, count(*) from runs where stage not in ('complete','failed','unresolved') group by 1").fetchall()))

# ---- verified spans: the section belongs to the run's document, and the offsets recover the quote under the recorded tier
template = (BACKEND / "app" / "application" / "verify_template.txt").read_text(encoding="utf-8")
from app.verify import spans as verifier

namespace: dict[str, object] = {"__file__": str(snap / "verify.py"), "__name__": "pack_verify"}
exec(template.replace("__QUOTE_MAP__", json.dumps(json.dumps({chr(k): v for k, v in verifier._QUOTE_MAP.items()}))).split("def main():")[0], namespace)
same = namespace["same"]
spans = db.execute(
    """select s.id, s.quote, s.method, s.start, s.end, s.section_id, sec.text, sec.document_id as section_doc, r.document_id as run_doc, r.id as run_id
       from evidence_spans s join findings f on f.id = s.finding_id join runs r on r.id = f.run_id left join sections sec on sec.id = s.section_id
       where s.verified = 1"""
).fetchall()
wrong_doc = no_section = not_recovered = 0
for s in spans:
    if s["text"] is None:
        no_section += 1
        continue
    if s["section_doc"] != s["run_doc"]:
        wrong_doc += 1
    if not same(s["text"][s["start"] : s["end"]], s["quote"], s["method"]):  # type: ignore[operator]
        not_recovered += 1
        problems["verified span not recovered at its offsets"].append(f"{s['run_id']} span {s['id']} ({s['method']})")
print(
    f"verified spans: {len(spans)}; section missing: {no_section}; section of another document: {wrong_doc}; offsets do not recover the quote: {not_recovered}"
)
unverified_with_offsets = db.execute("select count(*) from evidence_spans where verified = 0 and start >= 0").fetchone()[0]
print("unverified spans that carry offsets anyway:", unverified_with_offsets)

# ---- memos
memos = db.execute("select id, run_id, docx_path, docx_sha256 from memos").fetchall()
ok = 0
memo_files = set()
for m in memos:
    path = snap / "memos" / PureWindowsPath(m["docx_path"]).name
    memo_files.add(path.name)
    if not path.is_file():
        problems["memo row without its DOCX"].append(f"{m['id']} run {m['run_id']} ({PureWindowsPath(m['docx_path']).name})")
    elif sha(path) != m["docx_sha256"]:
        problems["memo DOCX does not hash to the row"].append(m["id"])
    else:
        ok += 1
stray = (
    sorted(p.relative_to(snap / "memos").as_posix() for p in (snap / "memos").rglob("*") if p.is_file() and p.name not in memo_files)
    if (snap / "memos").exists()
    else []
)
print(f"memos: {len(memos)} rows, {ok} with a DOCX whose hash matches; files with no row: {len(stray)} {stray[:6]}")
print("absolute paths stored in memos.docx_path:", sum(1 for m in memos if ":" in m["docx_path"] or m["docx_path"].startswith("/")), "of", len(memos))

for kind, items in problems.items():
    print(f"PROBLEM {kind}: {len(items)}")
    for item in items[:8]:
        print("     ", item)
if orphan_docs:
    print("files under documents/ with no row:", orphan_docs[:6])

# ---- restore: start the application on the snapshot, moved to another directory, and use it
restored = Path(tempfile.mkdtemp(prefix="verity-restored-")) / "data"
shutil.copytree(snap, restored)
os.environ["WORKBENCH_DATA_DIR"] = str(restored)
from fastapi.testclient import TestClient

from app import config
from app import db as db_module
from app.main import create_app

config.settings.data_dir = restored
engine = db_module.make_engine(f"sqlite:///{(restored / 'workbench.db').as_posix()}")
db_module.engine = engine
db_module.SessionLocal.configure(bind=engine)


class NoModel:
    name, model = "ollama", "qwen3:8b"

    def healthy(self) -> tuple[bool, str]:
        return True, "restore check: no model is called"

    def generate_json(self, *_: object) -> None:
        raise AssertionError("the restore check must not call a model")


client = TestClient(create_app(provider=NoModel()), raise_server_exceptions=False).__enter__()  # type: ignore[arg-type]
HERO = "e5a20e2283e8416e"
run = client.get(f"/api/runs/{HERO}")
print(
    f"\nrestored app: hero run HTTP {run.status_code}, stage {run.json().get('stage')}, findings {len(run.json().get('findings', []))}, review {run.json()['findings'][0].get('review') if run.status_code == 200 else None}"
)
explanation = client.get(f"/api/runs/{HERO}/explanation").json()
print(
    "restored app: explanation reconstructable:",
    explanation["reconstruction"]["reconstructable"],
    "| window:",
    explanation["reconstruction"].get("windowChars"),
    "| recorded hash:",
    str(explanation["reconstruction"].get("recordedInputSha256"))[:16],
)
for m in memos:
    resp = client.get(f"/api/memos/{m['id']}/docx")
    print(
        f"restored app: memo {m['id']} DOCX HTTP {resp.status_code}, hash matches the row: {resp.status_code == 200 and hashlib.sha256(resp.content).hexdigest() == m['docx_sha256']}"
    )

# ---- evidence packs for old and new runs, verified with the pack's own verify.py
complete = [r["id"] for r in db.execute("select id from runs where stage = 'complete' order by created_at")]
sample = sorted(set(complete[:12] + complete[len(complete) // 2 - 3 : len(complete) // 2 + 3] + complete[-12:] + [HERO]), key=complete.index)
passed = failed = 0
notes: collections.Counter[str] = collections.Counter()
for rid in sample:
    pack = client.get(f"/api/runs/{rid}/evidence-pack")
    if pack.status_code != 200:
        failed += 1
        print("pack HTTP", pack.status_code, rid)
        continue
    folder = Path(tempfile.mkdtemp(prefix="verity-pack-"))
    with zipfile.ZipFile(io.BytesIO(pack.content)) as z:
        z.extractall(folder)
    out = subprocess.run([sys.executable, "verify.py"], cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode == 0:
        passed += 1
    else:
        failed += 1
        print("pack verify FAILED", rid, [line for line in out.stdout.splitlines() if line.startswith("FAIL")][:3])
    for line in out.stdout.splitlines():
        if line.startswith("NOTE"):
            notes[line[:70]] += 1
    shutil.rmtree(folder, ignore_errors=True)
print(f"evidence packs from the restored store: {len(sample)} runs (12 oldest, 6 middle, 12 newest, hero): {passed} verify clean, {failed} fail")
for note, n in notes.most_common(4):
    print(f"   {n} x {note}")
print("snapshot kept at", snap)
