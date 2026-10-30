"""Phases 5, 6, 8, 19: memo crash-atomicity, review identity, review concurrency, time and ordering."""

from __future__ import annotations

import pathlib
import sqlite3
import threading
from datetime import UTC, datetime

from harness import Report, Store

# ---------------------------------------------------------------- Phase 5: memo filesystem/DB atomicity
r = Report("Phase 5 - memo atomicity")
s = Store()
run = s.complete_run()
r.check(
    "hero-shaped run completes on the scripted model",
    run["stage"] == "complete",
    f"{run['stage']} · {[(f['status'], f['statusSource']) for f in run['findings']]}",
)
span = run["findings"][0]["spans"][0]
r.check("wrong cited section is relocated, not trusted", span["method"].startswith("relocated:") and span["verified"], span["method"])
r.check(
    "code decides needs_review against the model's pass",
    run["findings"][0]["status"] == "needs_review" and run["findings"][0]["statusSource"] == "computed_days",
    run["findings"][0].get("statusReason", ""),
)

original_replace = pathlib.Path.replace
state = {"armed": True}


def failing_replace(self: pathlib.Path, target):  # type: ignore[no-untyped-def]
    if state["armed"] and str(target).endswith(".docx"):
        state["armed"] = False
        raise OSError("injected: the process died between the commit and the move")
    return original_replace(self, target)


pathlib.Path.replace = failing_replace  # type: ignore[method-assign]
first = s.client.post("/api/memos", json={"runId": run["id"]})
pathlib.Path.replace = original_replace  # type: ignore[method-assign]
r.note("first POST with the move failing", "INFO", f"HTTP {first.status_code}")
db = sqlite3.connect(s.db_path)
rows = db.execute("select id, docx_path, docx_sha256 from memos where run_id = ?", (run["id"],)).fetchall()
r.note("memo rows after the injected failure", "INFO", f"{len(rows)} row(s)")
dangling = [row for row in rows if not pathlib.Path(row[1]).exists()]
r.check("no memo row points at a missing DOCX", not dangling, f"{len(dangling)} dangling: {[pathlib.Path(d[1]).name for d in dangling]}")
second = s.client.post("/api/memos", json={"runId": run["id"]})
r.note("retry POST", "INFO", f"HTTP {second.status_code}")
if second.status_code in (200, 201):
    memo = second.json()
    docx = s.client.get(memo["docxUrl"])
    r.check("the retried memo's DOCX downloads", docx.status_code == 200 and docx.content[:2] == b"PK", f"HTTP {docx.status_code}")
    if docx.status_code == 200:
        import hashlib

        r.check("recorded sha256 equals the served bytes", hashlib.sha256(docx.content).hexdigest() == memo["docxSha256"])
    html = s.client.get(memo["htmlUrl"])
    r.check("the memo's HTML is served", html.status_code == 200 and "Termination" in html.text, f"HTTP {html.status_code}")
else:
    r.check("the retried memo is usable", False, second.text[:160])
leftovers = [p.name for p in (s.dir / "memos").rglob("*") if p.is_file()]
r.note("files under memos/ afterwards", "INFO", ", ".join(leftovers))
r.done()

# ---------------------------------------------------------------- concurrent first memo (must stay correct)
r = Report("Phase 5b - concurrent memo creation and review-head revisions")
s2 = Store()
run2 = s2.complete_run()
results: list[tuple[int, str]] = []


def make_memo() -> None:
    resp = s2.client.post("/api/memos", json={"runId": run2["id"]})
    results.append((resp.status_code, resp.json().get("id", resp.text[:80]) if resp.status_code < 500 else resp.text[:80]))


threads = [threading.Thread(target=make_memo) for _ in range(12)]
[t.start() for t in threads]
[t.join() for t in threads]
ids = {i for code, i in results if code in (200, 201)}
r.check(
    "12 concurrent first requests share one memo",
    len(ids) == 1 and all(code in (200, 201) for code, _ in results),
    f"codes {sorted(c for c, _ in results)} ids {len(ids)}",
)
memo_id = next(iter(ids)) if ids else ""
docx = s2.client.get(f"/api/memos/{memo_id}/docx")
import hashlib

recorded = sqlite3.connect(s2.db_path).execute("select docx_sha256 from memos where id = ?", (memo_id,)).fetchone()
r.check(
    "the winner's file is intact and matches its recorded hash",
    docx.status_code == 200 and recorded is not None and hashlib.sha256(docx.content).hexdigest() == recorded[0],
)
fid = run2["findings"][0]["id"]
s2.client.post(f"/api/findings/{fid}/review", json={"verdict": "confirmed", "reviewer": "A", "note": None})
after = s2.client.post("/api/memos", json={"runId": run2["id"]})
r.check("a review after the memo earns a new memo", after.status_code == 201 and after.json()["id"] != memo_id, f"HTTP {after.status_code}")
old = s2.client.get(f"/api/memos/{memo_id}/docx")
r.check("the earlier memo is still served unchanged", old.status_code == 200 and hashlib.sha256(old.content).hexdigest() == recorded[0])
r.note("files under memos/", "INFO", ", ".join(p.name for p in (s2.dir / "memos").rglob("*") if p.is_file()))
r.done()

# ---------------------------------------------------------------- Phases 6 + 8: review identity and concurrency
r = Report("Phases 6 + 8 - review identity and concurrency")
s3 = Store()
run3 = s3.complete_run()
fid = run3["findings"][0]["id"]
spoof = s3.client.post(
    f"/api/findings/{fid}/review",
    json={"verdict": "confirmed", "reviewer": "General Counsel", "note": None},
    headers={"Cf-Access-Authenticated-User-Email": "someone.else@example.com"},
)
shown = s3.client.get(f"/api/runs/{run3['id']}").json()["findings"][0]["review"]
r.note(
    "a review posted with any name and an Access header",
    "INFO",
    f"HTTP {spoof.status_code}; recorded reviewer = {shown['reviewer']!r}; the Access email is not read or stored",
)
cols = [c[1] for c in sqlite3.connect(s3.db_path).execute("pragma table_info(finding_reviews)")]
r.note("finding_reviews columns", "INFO", ", ".join(cols))

s4 = Store()
run4 = s4.complete_run()
fid = run4["findings"][0]["id"]
codes: list[tuple[str, int]] = []
barrier = threading.Barrier(2)


def decide(who: str, verdict: str) -> None:
    barrier.wait()
    resp = s4.client.post(f"/api/findings/{fid}/review", json={"verdict": verdict, "reviewer": who, "note": None})
    codes.append((who, resp.status_code))


ta = threading.Thread(target=decide, args=("Reviewer A", "confirmed"))
tb = threading.Thread(target=decide, args=("Reviewer B", "dismissed"))
ta.start()
tb.start()
ta.join()
tb.join()
con = sqlite3.connect(s4.db_path)
rows = con.execute("select id, verdict, reviewer, created_at from finding_reviews where finding_id = ? order by id", (fid,)).fetchall()
r.check(
    "A confirms and B dismisses at once: both events are kept",
    len(rows) == 2 and {x[1] for x in rows} == {"confirmed", "dismissed"},
    f"{codes} rows {[(x[0], x[1], x[2]) for x in rows]}",
)
current = s4.client.get(f"/api/runs/{run4['id']}").json()["findings"][0]["review"]
r.check(
    "the current decision is the last committed row (highest id)",
    bool(rows) and current["verdict"] == rows[-1][1] and current["reviewer"] == rows[-1][2],
    f"current {current['verdict']} by {current['reviewer']}",
)
record = next(f for f in s4.client.get("/api/findings").json() if f["id"] == fid)["review"]
r.check("run view and findings record agree on the current decision", record == current)
memo = s4.client.post("/api/memos", json={"runId": run4["id"]}).json()
html = s4.client.get(memo["htmlUrl"]).text
r.check(
    "the memo written now names the current decision",
    (current["reviewer"] in html) and (("Confirmed" in html) if current["verdict"] == "confirmed" else ("Dismissed" in html)),
    "",
)

s5 = Store()
run5 = s5.complete_run()
fid = run5["findings"][0]["id"]
barrier2 = threading.Barrier(8)
codes2: list[int] = []


def same() -> None:
    barrier2.wait()
    codes2.append(s5.client.post(f"/api/findings/{fid}/review", json={"verdict": "confirmed", "reviewer": "Same Person", "note": None}).status_code)


ts = [threading.Thread(target=same) for _ in range(8)]
[t.start() for t in ts]
[t.join() for t in ts]
n = sqlite3.connect(s5.db_path).execute("select count(*) from finding_reviews where finding_id = ?", (fid,)).fetchone()[0]
r.note(
    "the same reviewer and verdict, 8 at once",
    "INFO",
    f"codes {sorted(codes2)}; rows written {n} (1 = idempotent under the race, >1 = duplicate identical events)",
)
state_after = s5.client.get(f"/api/runs/{run5['id']}").json()["findings"][0]["review"]
r.check("the visible state is the one decision regardless", state_after["verdict"] == "confirmed" and state_after["reviewer"] == "Same Person")
r.done()

# ---------------------------------------------------------------- Phase 19: time and ordering
r = Report("Phase 19 - time and ordering")
s6 = Store()
run6 = s6.complete_run()
fid = run6["findings"][0]["id"]
for verdict in ("confirmed", "dismissed", "confirmed", "cleared", "dismissed"):
    s6.client.post(f"/api/findings/{fid}/review", json={"verdict": verdict, "reviewer": "T", "note": None})
con = sqlite3.connect(s6.db_path)
rows = con.execute("select id, verdict, created_at from finding_reviews where finding_id = ? order by id", (fid,)).fetchall()
same_second = len({x[2][:19] for x in rows}) < len(rows)
r.note("five reviews in a row", "INFO", f"{[x[1] for x in rows]}; share a second: {same_second}; stored as {rows[0][2]!r}")
cur = s6.client.get(f"/api/runs/{run6['id']}").json()["findings"][0]["review"]
r.check("latest is decided by row id, not by timestamp", cur["verdict"] == "dismissed")
r.check("the API returns the time with an explicit UTC offset", cur["at"].endswith("+00:00"), cur["at"])
stored = datetime.fromisoformat(rows[-1][2]).replace(tzinfo=UTC)
r.check("the returned instant equals the stored UTC instant", datetime.fromisoformat(cur["at"]) == stored)
# A clock that goes backwards: insert a row dated in the past with a higher id; the higher id must still win.
con.execute(
    "insert into finding_reviews (finding_id, verdict, reviewer, note, created_at) values (?, 'confirmed', 'Clock', null, '2001-01-01 00:00:00.000000')", (fid,)
)
con.commit()
cur2 = s6.client.get(f"/api/runs/{run6['id']}").json()["findings"][0]["review"]
r.check(
    "a later row with an earlier timestamp is still the current decision",
    cur2["reviewer"] == "Clock",
    f"{cur2['verdict']} by {cur2['reviewer']} at {cur2['at']}",
)
# The memo's review date: stored naive UTC must not be read as local time.
con.execute(
    "insert into finding_reviews (finding_id, verdict, reviewer, note, created_at) values (?, 'confirmed', 'Evening', null, '2026-10-02 02:30:00.000000')",
    (fid,),
)
con.commit()
memo = s6.client.post("/api/memos", json={"runId": run6["id"]}).json()
html = s6.client.get(memo["htmlUrl"]).text
import re

where = re.search(r"Evening[^<]{0,80}", html)
local_date = stored.astimezone().tzinfo
expected_local = datetime(2026, 10, 2, 2, 30, tzinfo=UTC).astimezone().strftime("%d %B %Y")
r.note(
    "memo line for a review stored at 2026-10-02 02:30 UTC",
    "INFO",
    f"{where.group(0) if where else 'not found'} | local zone {local_date} | correct local date {expected_local}",
)
r.check("the memo shows the review's date in local time from UTC, not the UTC wall-clock read as local", bool(where) and expected_local in where.group(0), "")
r.done()
