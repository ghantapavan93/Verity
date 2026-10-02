"""Phases 7, 11, 16: SQLite under concurrent writers, the run executor and admission queue, and query scale."""

from __future__ import annotations

import sqlite3
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from harness import CONTRACT, Report, ScriptedProvider, Store
from sqlalchemy import event

from app.providers.admission import AdmissionController, AdmittedProvider

ONLY = set(sys.argv[1:])


def timed(fn):  # type: ignore[no-untyped-def]
    t0 = time.perf_counter()
    out = fn()
    return out, (time.perf_counter() - t0) * 1000


def fan(n: int, fn) -> list[tuple[int, float]]:  # type: ignore[no-untyped-def]
    barrier = threading.Barrier(n)

    def one(i: int) -> tuple[int, float]:
        barrier.wait()
        resp, ms = timed(lambda: fn(i))
        return resp.status_code, ms

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(one, range(n)))


def summary(results: list[tuple[int, float]]) -> str:
    codes: dict[int, int] = {}
    for code, _ in results:
        codes[code] = codes.get(code, 0) + 1
    ms = sorted(m for _, m in results)
    return f"codes {codes} · p50 {statistics.median(ms):.0f} ms · max {ms[-1]:.0f} ms"


# ------------------------------------------------------------------------------- Phase 7
if not ONLY or "7" in ONLY:
    r = Report("Phase 7 - SQLite concurrency")
    s = Store()
    with s.engine.connect() as c:
        pragmas = {p: c.exec_driver_sql(f"pragma {p}").scalar() for p in ("journal_mode", "foreign_keys", "busy_timeout", "synchronous")}
    r.note("pragmas on an application connection", "INFO", str(pragmas))
    r.note(
        "connection pool",
        "INFO",
        f"{type(s.engine.pool).__name__} size {s.engine.pool.size()} overflow {getattr(s.engine.pool, '_max_overflow', '?')} timeout {getattr(s.engine.pool, '_timeout', '?')} s",
    )
    doc = s.upload()
    gid = s.guidance()
    for n in (5, 20):
        res = fan(n, lambda i: s.client.post("/api/guidance", json={"text": f"Guidance number {n}-{i}: at least {30 + i} days' notice."}))
        ok = all(code in (200, 201) for code, _ in res)
        count = sqlite3.connect(s.db_path).execute("select count(*) from guidance where text like ?", (f"Guidance number {n}-%",)).fetchone()[0]
        r.check(f"{n} concurrent guidance writes: none lost, none refused", ok and count == n, f"{summary(res)} · rows {count}")
        res = fan(n, lambda i: s.ask(doc["id"], f"Question {n}-{i}: on what notice may a party terminate for convenience?", gid))
        ok = all(code == 202 for code, _ in res)
        r.check(f"{n} concurrent distinct run starts: all accepted", ok, summary(res))
    time.sleep(1.5)
    runs = s.client.get("/api/runs").json()
    done = [x for x in runs if x["stage"] == "complete"]
    r.check("every started run reached a terminal record", len(done) == 25, f"{len(done)} complete of {len(runs)}")
    stages = sqlite3.connect(s.db_path).execute("select run_id, count(*) from run_stages group by run_id").fetchall()
    r.check("every run has its five stage rows (no lost stage write)", all(n == 5 for _, n in stages), f"{sorted({n for _, n in stages})}")
    finding_ids = [f["id"] for f in s.client.get("/api/findings").json()]
    for n in (5, 20):
        res = fan(n, lambda i: s.client.post(f"/api/findings/{finding_ids[i]}/review", json={"verdict": "confirmed", "reviewer": f"R{n}-{i}", "note": None}))
        r.check(f"{n} concurrent reviews on {n} findings: all recorded", all(code == 201 for code, _ in res), summary(res))
    run_ids = [x["id"] for x in done]
    for n in (5, 20):
        res = fan(n, lambda i: s.client.post("/api/memos", json={"runId": run_ids[i]}))
        r.check(f"{n} concurrent memos on {n} runs: all written", all(code in (200, 201) for code, _ in res), summary(res))
    memo_rows = sqlite3.connect(s.db_path).execute("select docx_path from memos").fetchall()
    from pathlib import Path

    r.check("every memo row has its file", all(Path(p[0]).is_file() for p in memo_rows), f"{len(memo_rows)} memos")

    # A writer that holds the write lock: what do other writers see, and after how long?
    for hold_s in (2.0, 8.0):
        holder = sqlite3.connect(s.db_path, timeout=30, isolation_level=None)
        holder.execute("BEGIN IMMEDIATE")
        holder.execute(
            "insert into guidance (id, text, sha256, source, created_at) values (?, ?, ?, 'pasted', '2026-01-01 00:00:00')",
            (f"held{int(hold_s)}", f"held {hold_s}", f"h{hold_s}"),
        )
        out: list[tuple[int, float]] = []

        def blocked(i: int) -> None:
            resp, ms = timed(lambda: s.client.post("/api/guidance", json={"text": f"Written while the lock was held {hold_s} s, writer {i}."}))
            out.append((resp.status_code, ms))

        ts = [threading.Thread(target=blocked, args=(i,)) for i in range(5)]
        [t.start() for t in ts]
        reader, read_ms = timed(lambda: s.client.get("/api/runs"))
        time.sleep(hold_s)
        holder.execute("ROLLBACK")
        holder.close()
        [t.join() for t in ts]
        r.note(
            f"5 writers while another connection holds the write lock for {hold_s:.0f} s",
            "INFO",
            f"{summary(out)} · a read meanwhile: HTTP {reader.status_code} in {read_ms:.0f} ms",
        )
        gone = sqlite3.connect(s.db_path).execute("select count(*) from guidance where id = ?", (f"held{int(hold_s)}",)).fetchone()[0]
        r.check(f"the holder's rolled-back row is gone ({hold_s:.0f} s)", gone == 0)
        landed = (
            sqlite3.connect(s.db_path)
            .execute("select count(*) from guidance where text like ?", (f"Written while the lock was held {hold_s} s%",))
            .fetchone()[0]
        )
        succeeded = sum(1 for code, _ in out if code in (200, 201))
        r.check(
            f"every writer that was answered 2xx has its row, every other has none ({hold_s:.0f} s)",
            landed == succeeded,
            f"{succeeded} answered 2xx, {landed} rows",
        )
    r.done()

# ------------------------------------------------------------------------------- Phase 11
if not ONLY or "11" in ONLY:
    r = Report("Phase 11 - executor, admission queue, retries")
    for n in (5, 20, 64, 80):
        inner = ScriptedProvider()
        inner.delay_s = 0.05
        controller = AdmissionController(limit=1)
        s = Store(provider=AdmittedProvider(inner, controller, "interactive"))
        doc = s.upload()
        gid = s.guidance()
        t0 = time.perf_counter()
        res = fan(n, lambda i: s.ask(doc["id"], f"Distinct question {i}: on what notice may a party terminate for convenience?", gid))
        accept_ms = sorted(m for _, m in res)
        deadline = time.time() + 120
        while time.time() < deadline:
            con = sqlite3.connect(s.db_path)
            by_stage = dict(con.execute("select stage, count(*) from runs group by 1").fetchall())
            con.close()
            if sum(v for k, v in by_stage.items() if k in ("complete", "failed", "unresolved")) == n:
                break
            time.sleep(0.1)
        wall = time.perf_counter() - t0
        snap = controller.snapshot()
        ok = by_stage.get("complete", 0) == n and len(inner.calls) == n and all(code == 202 for code, _ in res)
        r.check(
            f"{n} distinct runs at admission limit 1: all complete, one model call each",
            ok,
            f"stages {by_stage} · model calls {len(inner.calls)} · accept p50 {statistics.median(accept_ms):.0f} / max {accept_ms[-1]:.0f} ms · wall {wall:.1f} s · max queue wait {snap['recent'].get('interactive', {}).get('queue_wait_ms_max', 0):.0f} ms",
        )
    # Duplicate asks, retries and a failing provider: how many model calls does one logical request cost?
    inner = ScriptedProvider()
    inner.delay_s = 0.3
    s = Store(provider=AdmittedProvider(inner, AdmissionController(limit=1), "interactive"))
    doc = s.upload()
    gid = s.guidance()
    res = fan(12, lambda i: s.ask(doc["id"], "The same question from twelve tabs: what is the notice period?", gid))
    ids = {s.client.get("/api/runs").json()[0]["id"]}
    time.sleep(0.8)
    r.check(
        "12 identical asks while the run is in flight: one run, one model call",
        len(inner.calls) == 1 and len(s.client.get("/api/runs").json()) == 1,
        f"calls {len(inner.calls)} codes {sorted({c for c, _ in res})}",
    )
    again = s.ask(doc["id"], "The same question from twelve tabs: what is the notice period?", gid)
    r.check(
        "asking again after it completed reuses the run: still one model call",
        again.status_code == 200 and again.json().get("reused") is True and len(inner.calls) == 1,
        f"HTTP {again.status_code} calls {len(inner.calls)}",
    )

    inner2 = ScriptedProvider()
    inner2.fail_next = 1
    s2 = Store(provider=AdmittedProvider(inner2, AdmissionController(limit=1), "interactive"))
    import app.analysis.service as analysis

    analysis.PROVIDER_RETRY_DELAY_S = 0.05
    doc = s2.upload()
    gid = s2.guidance()
    run = s2.wait(s2.ask(doc["id"], "One provider timeout, then an answer.", gid).json()["id"])
    r.check(
        "one provider failure: retried once, the run completes, two calls",
        run["stage"] == "complete" and len(inner2.calls) == 2,
        f"{run['stage']} calls {len(inner2.calls)}",
    )
    inner2.fail_next = 99
    before = len(inner2.calls)
    failed = s2.wait(s2.ask(doc["id"], "A provider that stays down.", gid).json()["id"])
    r.check(
        "a provider that stays down: two calls, then an honest failed run",
        failed["stage"] == "failed" and len(inner2.calls) - before == 2,
        f"{failed['stage']} · {failed.get('error', '')[:70]} · calls {len(inner2.calls) - before}",
    )
    # Polling and stream reads of a failed run must not start work.
    for _ in range(10):
        s2.client.get(f"/api/runs/{failed['id']}")
        s2.client.get(f"/api/runs/{failed['id']}/events")
    r.check("ten polls and ten stream opens of the failed run start no model call", len(inner2.calls) - before == 2)
    retry = s2.wait(s2.ask(doc["id"], "A provider that stays down.", gid).json()["id"])
    r.check(
        "the user's retry is a new run with its own two calls: no storm",
        retry["id"] != failed["id"] and len(inner2.calls) - before == 4,
        f"calls for 2 logical requests: {len(inner2.calls) - before}",
    )
    inner2.fail_next = 0
    inner2.garbage = True
    before = len(inner2.calls)
    bad = s2.wait(s2.ask(doc["id"], "A model that never returns the schema.", gid).json()["id"])
    r.check(
        "output that is never the schema: two calls, failed as invalid_output",
        bad["stage"] == "failed" and len(inner2.calls) - before == 2,
        f"{bad['stage']} calls {len(inner2.calls) - before}",
    )
    r.done()

# ------------------------------------------------------------------------------- Phase 16
if not ONLY or "16" in ONLY:
    r = Report("Phase 16 - query scale")
    s = Store()
    statements = {"n": 0}

    @event.listens_for(s.engine, "before_cursor_execute")
    def count(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        statements["n"] += 1

    old_doc = s.upload(CONTRACT + "\n5. Old Document\n\nThis copy is the older document.\n", name="older.txt")
    gid = s.guidance()
    for i in range(10):
        s.wait(s.ask(old_doc["id"], f"Old document question {i}: on what notice may a party terminate for convenience?", gid).json()["id"])
    doc = s.upload()
    made = 10

    def grow(target: int) -> None:
        nonlocal_made = made
        with ThreadPoolExecutor(max_workers=2) as pool:  # two clients: eight against a zero-latency model starved a writer past the 5 s busy timeout
            list(
                pool.map(
                    lambda i: s.ask(doc["id"], f"Scale question {i}: on what notice may a party terminate for convenience?", gid), range(nonlocal_made, target)
                )
            )
        deadline = time.time() + 600
        while time.time() < deadline:
            con = sqlite3.connect(s.db_path)
            n = con.execute("select count(*) from runs where stage in ('complete', 'failed', 'unresolved')").fetchone()[0]
            con.close()
            if n >= target:
                return
            time.sleep(0.2)
        raise TimeoutError(target)

    for target in (200, 500, 1000, 5000):
        grow(target)
        con = sqlite3.connect(s.db_path)
        r.note(f"store at {target}", "INFO", str(dict(con.execute("select stage, count(*) from runs group by 1").fetchall())))
        con.close()
        made = target
        line = []
        for path in ("/api/runs", "/api/findings", f"/api/findings?documentId={old_doc['id']}", f"/api/findings?documentId={doc['id']}"):
            statements["n"] = 0
            resp, ms = timed(lambda: s.client.get(path))
            line.append(
                f"{path.split('?')[0].replace('/api/', '')}{'?doc' if '?' in path else ''}: {len(resp.json())} rows, {statements['n']} SQL, {ms:.0f} ms"
            )
            if "documentId=" + old_doc["id"] in path:
                r.check(
                    f"at {target} runs the older document's 10 findings are still returned (filter before the cap)",
                    len(resp.json()) == 10,
                    f"{len(resp.json())} rows",
                )
        r.note(f"at {target} complete runs", "INFO", " | ".join(line))
    statements["n"] = 0
    one, ms = timed(lambda: s.client.get(f"/api/runs/{s.client.get('/api/runs').json()[0]['id']}"))
    r.note("GET one run at 5000", "INFO", f"{statements['n']} SQL, {ms:.0f} ms")
    r.done()
