"""Phase 29: one journey over real HTTP against a real server process on an isolated store, with failures injected
along the way. Success is not "nothing failed": it is that every failure became an honest state."""

from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import httpx

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = pathlib.Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
PORT = 8031
BASE = f"http://127.0.0.1:{PORT}"
DATA = pathlib.Path(tempfile.mkdtemp(prefix="verity-chaos-"))
ENV = {
    **os.environ,
    "WORKBENCH_DATA_DIR": str(DATA),
    "PYTHONPATH": str(HERE),
    "WORKBENCH_APP_URL": "http://localhost:3999",
    "WORKBENCH_CORS_ORIGINS": "http://localhost:3999",
}
CONTRACT = """SERVICES AGREEMENT

1. Term

This Agreement commences on the Effective Date and continues for twelve (12) months.

2. Termination for Convenience

Either party may terminate this Agreement for convenience upon sixty (60) days' written notice to the other party. On termination, Customer pays all Fees accrued.

3. Governing Law

This Agreement is governed by the laws of the State of Delaware.
"""
GUIDANCE = "We require at least 90 days' written notice for termination for convenience. Anything shorter needs review."
steps: list[tuple[str, bool, str]] = []


def step(name: str, ok: bool, detail: str = "") -> None:
    steps.append((name, ok, detail))
    print(f"{'HONEST' if ok else 'BROKEN'}  {name}" + (f"  - {detail}" if detail else ""), flush=True)


def start() -> subprocess.Popen[bytes]:
    log = open(DATA / "server.log", "ab")  # noqa: SIM115 - the server process owns the handle for its life
    p = subprocess.Popen(
        [str(PY), "-m", "uvicorn", "chaos_app:app", "--host", "127.0.0.1", "--port", str(PORT)], cwd=HERE, env=ENV, stdout=log, stderr=subprocess.STDOUT
    )
    for _ in range(80):
        try:
            if httpx.get(f"{BASE}/api/health", timeout=5).status_code == 200:
                return p
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise SystemExit("server did not start")


def calls() -> list[str]:
    path = DATA / "calls.log"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def wait(c: httpx.Client, run_id: str, timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = c.get(f"/api/runs/{run_id}").json()
        if run["stage"] in ("complete", "failed", "unresolved"):
            return run
        time.sleep(0.2)
    raise TimeoutError(run_id)


server = start()
c = httpx.Client(base_url=BASE, timeout=60)
doc = c.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode(), "text/plain")}).json()
gid = c.post("/api/guidance", json={"text": GUIDANCE}).json()["id"]
step("fresh store: upload and guidance", bool(doc.get("id")) and bool(gid), f"document {doc['id']}, {len(doc['sections'])} sections")

# ---- Ask, with a duplicate Ask from a second tab while it is in flight
Q1 = "May either party terminate for convenience, and on what notice? [[slow]]"
body = {"documentId": doc["id"], "guidanceId": gid, "question": Q1}
first = c.post("/api/runs", json=body)
second = c.post("/api/runs", json=body)
run1 = first.json()["id"]
step(
    "duplicate Ask from a second tab reuses the run",
    first.status_code == 202 and second.status_code == 200 and second.json()["id"] == run1 and second.json()["reused"] is True,
    f"{first.status_code}/{second.status_code}",
)

# ---- SSE: read a little, lose the connection, recover by polling, then reconnect with Last-Event-ID
seen: list[str] = []
last_id = None
with c.stream("GET", f"/api/runs/{run1}/events", timeout=30) as stream:
    for line in stream.iter_lines():
        if line.startswith("id:"):
            last_id = line.split(":", 1)[1].strip()
        if line.startswith("data:"):
            seen.append(json.loads(line[5:])["stage"])
        if len(seen) >= 3:
            break  # the connection is dropped here, mid-run
mid = c.get(f"/api/runs/{run1}").json()
step(
    "stream lost mid-run; a poll (a refresh) sees the run still in flight, not an answer",
    mid["stage"] == "checking" and not mid["findings"],
    f"stream saw {seen}, poll says {mid['stage']}",
)
done1 = wait(c, run1)
step("polling carries the run to its recorded end", done1["stage"] == "complete", done1["stage"])
replay = c.get(f"/api/runs/{run1}/events", headers={"Last-Event-ID": str(last_id)}).text
replayed = [json.loads(line[5:])["stage"] for line in replay.splitlines() if line.startswith("data:")]
step(
    "reconnect with Last-Event-ID replays only what was missed and ends",
    replayed[-1] == "complete" and "reading" not in replayed and '"final": true' in replay,
    f"after id {last_id}: {replayed}",
)
step("one logical question so far cost one model call", len(calls()) == 1, f"{len(calls())} call(s)")

# ---- the model was plausible and wrong; provenance and policy say so
f = done1["findings"][0]
span = f["spans"][0]
step(
    "wrong cited section: the quote is relocated and says so",
    span["verified"] and span["method"] == "relocated:exact" and span["citedSectionLabel"] != "",
    f"cited {span['citedSectionLabel']}, found by {span['method']}",
)
step(
    "deterministic policy disagrees with the model's 'pass'",
    f["status"] == "needs_review" and f["statusSource"] == "computed_days",
    f"{f['status']} / {f['statusSource']}: {f['statusReason']}",
)

# ---- process death on another run, restart, recovery, retry
Q2 = "What notice is required to end the agreement early? [[slow]]"
run2 = c.post("/api/runs", json={"documentId": doc["id"], "guidanceId": gid, "question": Q2}).json()["id"]
for _ in range(40):
    if c.get(f"/api/runs/{run2}").json()["stage"] == "checking":
        break
    time.sleep(0.1)
server.kill()
server.wait()
server = start()
dead = c.get(f"/api/runs/{run2}").json()
step(
    "process killed during the model call: after restart the run is failed, with the cause named",
    dead["stage"] == "failed" and "no longer exists" in (dead.get("error") or ""),
    (dead.get("error") or "")[:110],
)
tail = c.get(f"/api/runs/{run2}/events").text
step("the dead run's stream ends at once with its final event", '"stage": "failed", "final": true' in tail)
still = c.get(f"/api/runs/{run1}").json()
step("the finished run is untouched by the crash", still["stage"] == "complete" and still["findings"][0]["id"] == f["id"])
retry = c.post("/api/runs", json={"documentId": doc["id"], "guidanceId": gid, "question": Q2})
run2b = retry.json()["id"]
done2 = wait(c, run2b)
step(
    "retry of the same question is a new run and completes",
    retry.status_code == 202 and run2b != run2 and done2["stage"] == "complete",
    f"{run2} failed, {run2b} {done2['stage']}",
)
step("model calls: 1 + 1 (killed) + 1 (retry), no storm", len(calls()) == 3, f"{len(calls())} call(s)")

# ---- a provider that is down: an honest failed run, bounded calls
Q3 = "Is there a cure period? [[outage]]"
down = wait(c, c.post("/api/runs", json={"documentId": doc["id"], "guidanceId": gid, "question": Q3}).json()["id"])
step(
    "provider outage: a failed run that says so, never a verdict",
    down["stage"] == "failed" and down["reason"] == "provider_error" and not down["findings"],
    f"{down['reason']}: {(down.get('error') or '')[:70]}",
)
step("the outage cost two calls (one retry), not more", len(calls()) == 5, f"{len(calls())} call(s) in total")

# ---- review, then two reviewers at once
fid = f["id"]
r1 = c.post(f"/api/findings/{fid}/review", json={"verdict": "confirmed", "reviewer": "First Reviewer", "note": None})
step("review recorded", r1.status_code == 201 and r1.json()["review"]["verdict"] == "confirmed")
barrier = threading.Barrier(2)
codes: list[int] = []


def decide(who: str, verdict: str) -> None:
    barrier.wait()
    with httpx.Client(base_url=BASE, timeout=30) as other:
        codes.append(other.post(f"/api/findings/{fid}/review", json={"verdict": verdict, "reviewer": who, "note": None}).status_code)


threads = [threading.Thread(target=decide, args=("Reviewer A", "confirmed")), threading.Thread(target=decide, args=("Reviewer B", "dismissed"))]
[t.start() for t in threads]
[t.join() for t in threads]
import sqlite3

rows = sqlite3.connect(DATA / "workbench.db").execute("select id, verdict, reviewer from finding_reviews where finding_id = ? order by id", (fid,)).fetchall()
current = c.get(f"/api/runs/{run1}").json()["findings"][0]["review"]
step(
    "two reviewers at once: every event kept, the last committed is the current decision",
    len(rows) == 3 and current["reviewer"] == rows[-1][2] and current["verdict"] == rows[-1][1],
    f"codes {codes}; rows {[(r[1], r[2]) for r in rows]}; current: {current['verdict']} by {current['reviewer']}",
)

# ---- memo, interrupted, retried
(DATA / "fail-memo-once").write_text("x")
broken = c.post("/api/memos", json={"runId": run1})
memo_rows = sqlite3.connect(DATA / "workbench.db").execute("select count(*) from memos").fetchone()[0]
step(
    "memo interrupted while its file was being put in place: an error, and no memo row",
    broken.status_code == 500 and memo_rows == 0,
    f"HTTP {broken.status_code}, {memo_rows} row(s)",
)
memo = c.post("/api/memos", json={"runId": run1})
docx = c.get(memo.json()["docxUrl"]) if memo.status_code == 201 else None
step(
    "memo retry: written, and its bytes hash to what the record says",
    memo.status_code == 201 and docx is not None and hashlib.sha256(docx.content).hexdigest() == memo.json()["docxSha256"],
    f"HTTP {memo.status_code}",
)
html = c.get(memo.json()["htmlUrl"]).text
step("the memo names the decision that is current", current["reviewer"] in html)

# ---- evidence pack, tampered, rejected
pack = c.get(f"/api/runs/{run1}/evidence-pack")
folder = pathlib.Path(tempfile.mkdtemp(prefix="verity-chaos-pack-"))
with zipfile.ZipFile(io.BytesIO(pack.content)) as z:
    z.extractall(folder)
clean = subprocess.run([sys.executable, "verify.py"], cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace")
step("evidence pack verifies itself", clean.returncode == 0, clean.stdout.strip().splitlines()[-1])
sections = folder / "sections.json"
sections.write_text(sections.read_text(encoding="utf-8").replace("sixty (60) days", "ninety (90) days"), encoding="utf-8")
bad = subprocess.run([sys.executable, "verify.py"], cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace")
step("tampered pack is rejected", bad.returncode == 1, "; ".join(line for line in bad.stdout.splitlines() if line.startswith("FAIL"))[:160])

# ---- restart, reopen by URL, reconstruct the exact input
server.kill()
server.wait()
server = start()
reopened = c.get(f"/api/runs/{run1}").json()
explanation = c.get(f"/api/runs/{run1}/explanation").json()
rebuilt = explanation["reconstruction"]
step(
    "after a restart the run reopens by its id with the same finding, review and status",
    reopened["stage"] == "complete"
    and reopened["findings"][0]["status"] == "needs_review"
    and reopened["findings"][0]["review"]["reviewer"] == current["reviewer"],
)
step(
    "the exact model input is rebuilt from the record and hashes to what the run recorded",
    rebuilt["reconstructable"] is True and bool(rebuilt.get("recordedInputSha256")),
    f"window {rebuilt.get('windowChars')}, hash {str(rebuilt.get('recordedInputSha256'))[:16]}",
)
stages = sqlite3.connect(DATA / "workbench.db").execute("select stage, count(*) from runs group by 1").fetchall()
step("no run is left in flight", all(s in ("complete", "failed", "unresolved") for s, _ in stages), str(dict(stages)))
server.kill()
server.wait()
broken_steps = [s for s in steps if not s[1]]
print(f"\n{len(steps) - len(broken_steps)}/{len(steps)} steps ended in an honest state; store {DATA}")
sys.exit(1 if broken_steps else 0)
