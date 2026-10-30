"""One look at the deployment: is the API answering, which model build is loaded, how much room the store has, whether
it passes its own check, how much of the day's run budget is spent, whether a run is stuck, and what each supervisor last wrote.

    .venv/Scripts/python scripts/status.py                                  # the owner's store (backend/data)
    .venv/Scripts/python scripts/status.py --data-dir <public store> --public  # the public demo's store and floor

Read-only throughout: the store is opened with SQLite's mode=ro, the supervisor logs are read once and closed (never
held open: a reader holding api.supervisor.log ended the supervisor on 2026-10-11), and nothing is started, stopped or
written. Each line is `name  ok|PROBLEM  detail`; the exit code is 1 when any line is a problem. docs/TROUBLESHOOTING.md
says what to do about each.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import Engine, create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.health import MIN_FREE_BYTES  # noqa: E402
from app.config import settings  # noqa: E402
from app.ingest import PARSER_VERSION  # noqa: E402
from app.models import TERMINAL_STAGES, Document, Run, RunStage, as_utc  # noqa: E402
from app.runs.versions import SEMANTIC_VERSIONS, compare_version  # noqa: E402

TIMEOUT_S = 5.0
# A run whose stage has made no progress for longer than this is worth a look; recovery declares it failed later
# (application/recover_runs.stale_after_seconds), and only on a read of runs or a restart.
STUCK_AFTER = timedelta(minutes=15)
LAST_LINE_BYTES = 4096
# The public site's ceiling on new runs a day, as deploy/supervise.ps1 sets it inside the API's own process; the
# operator's shell does not have it (a test holds the two equal).
PUBLIC_MAX_RUNS_PER_DAY = 200


def read_only(database: Path) -> Engine:
    """The store, opened so that no statement through it can write (SQLite's mode=ro)."""
    return create_engine(f"sqlite:///file:{database.as_posix()}?mode=ro&uri=true")


def line(name: str, ok: bool, detail: str) -> bool:
    print(f"{name:<10}{'ok' if ok else 'PROBLEM':<9}{detail}")
    return ok


def get_json(url: str) -> Any:  # noqa: ANN401 - each endpoint answers its own shape
    response = httpx.get(url, timeout=TIMEOUT_S)
    response.raise_for_status()
    return response.json()


def check_api(api: str) -> bool:
    try:
        health = get_json(f"{api}/api/health")
    except (httpx.HTTPError, ValueError) as error:
        return line("api", False, f"not answering at {api} ({type(error).__name__}): is the API supervisor running?")
    return line("api", bool(health.get("ok")), f"{health.get('detail', '')} (fault: {health.get('fault') or 'none'})")


def check_model() -> bool:
    base = settings.ollama_url.rstrip("/")
    try:
        version = get_json(f"{base}/api/version").get("version", "unknown")
        tags = get_json(f"{base}/api/tags").get("models", [])
        loaded = get_json(f"{base}/api/ps").get("models", [])
    except (httpx.HTTPError, ValueError) as error:
        return line("model", False, f"Ollama not answering at {base} ({type(error).__name__}): start Ollama")
    pulled = next((m for m in tags if m.get("name") in (settings.model, f"{settings.model}:latest")), None)
    if pulled is None:
        return line("model", False, f"{settings.model} is not pulled (server {version}): ollama pull {settings.model}")
    build = str(pulled.get("digest", ""))[:12]
    pinned = settings.model_digest
    if pinned and not build.startswith(pinned[:12]):
        return line("model", False, f"{settings.model} build {build} is not the pinned {pinned[:12]} (server {version})")
    awake = next((m for m in loaded if m.get("name") == pulled.get("name")), None)
    state = f"loaded until {awake.get('expires_at', '?')[:19]}" if awake else "not loaded: the first answer pays the load"
    return line("model", True, f"{settings.model} build {build}, server {version}; {state}")


def check_disk(data_dir: Path, public: bool) -> bool:
    floor = settings.public_min_free_bytes if public else MIN_FREE_BYTES
    if not data_dir.is_dir():
        return line("disk", False, f"no data directory at {data_dir}")
    free = shutil.disk_usage(data_dir).free
    gib = 1024**3
    return line("disk", free >= floor, f"{free / gib:.1f} GiB free; writes pause below {floor / gib:.2f} GiB")


def check_runs(database: Path, ceiling: int) -> bool:
    if not database.exists():
        return line("runs", False, f"no store at {database}")
    engine = read_only(database)
    now = datetime.now(UTC)
    day = datetime(now.year, now.month, now.day, tzinfo=UTC)
    with Session(engine) as session:
        today = session.scalar(select(func.count(Run.id)).where(Run.workspace_id.isnot(None), Run.created_at >= day)) or 0
        open_runs = session.execute(
            select(Run.created_at, func.max(RunStage.at))
            .outerjoin(RunStage, RunStage.run_id == Run.id)
            .where(Run.stage.notin_(TERMINAL_STAGES))
            .group_by(Run.id)
        ).all()
    engine.dispose()
    since = [now - as_utc(latest or created) for created, latest in open_runs]
    budget = f"{today} of {ceiling} today" if ceiling else f"{today} today (no daily ceiling set)"
    stuck = [age for age in since if age > STUCK_AFTER]
    oldest = f", oldest without progress {int(max(since).total_seconds() // 60)} min" if since else ""
    warning = f"; {len(stuck)} without progress for over {int(STUCK_AFTER.total_seconds() // 60)} min" if stuck else ""
    ok = not stuck and (not ceiling or today < ceiling)
    return line("runs", ok, f"{budget}; {len(open_runs)} open{oldest}{warning}")


def check_rules(database: Path) -> bool:
    """How many runs and documents the store holds under rules this build does not know, as after the documented rollback
    to an older build. They open, and nothing of them is re-checked by the older rules (runs.versions.compare_version);
    an older build's own pack checker may fail their spans. Named here rather than refused at start: the rollback is the
    emergency path, and a build that refused the store would leave no site at all (stress test, 2026-10-30)."""
    if not database.exists():
        return line("rules", False, f"no store at {database}")
    engine = read_only(database)
    with Session(engine) as session:
        recorded = session.scalars(select(Run.options_json)).all()
        readers = session.execute(select(Document.parser_version, func.count(Document.id)).group_by(Document.parser_version)).all()
    engine.dispose()
    unknown: set[str] = set()
    runs = 0
    for options_json in recorded:
        options = json.loads(options_json or "{}")
        names = {f"{name} {options.get(name)}" for name, current in SEMANTIC_VERSIONS.items() if compare_version(options.get(name), current) == "unknown"}
        runs += bool(names)
        unknown |= names
    documents = 0
    for version, count in readers:
        if compare_version(version, PARSER_VERSION) == "unknown":
            documents += count
            unknown.add(f"reader {version}")
    if not unknown:
        return line("rules", True, "every run and document recorded under rules this build knows")
    return line(
        "rules",
        False,
        f"{runs} run(s) and {documents} document(s) recorded under rules this build does not know ({', '.join(sorted(unknown))}): "
        "they open but are not re-checked; roll forward, or export their packs from a build that knows them",
    )


def check_tunnel(metrics: str) -> bool:
    try:
        response = httpx.get(f"{metrics}/ready", timeout=TIMEOUT_S)
    except httpx.HTTPError as error:
        return line("tunnel", False, f"cloudflared metrics not answering at {metrics} ({type(error).__name__})")
    try:
        connections = response.json().get("readyConnections")  # JSON, though cloudflared labels it text/plain
    except ValueError:
        connections = None
    ok = response.status_code == 200 and connections != 0
    return line("tunnel", ok, f"cloudflared {response.status_code}, {connections if connections is not None else '?'} connections to the edge")


def last_line(path: Path) -> str:
    """The file's last line, read once from its end and closed."""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - LAST_LINE_BYTES))
        tail = handle.read().decode("utf-8-sig", errors="replace")
    lines = [text for text in tail.splitlines() if text.strip()]
    return lines[-1].strip() if lines else ""


OLLAMA_LOG = Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "server.log"


def check_cache(server_log: Path) -> bool:
    """Whether the model server keeps a host-RAM prompt cache, as its last model load logged it. With one, an answer depends
    on what was asked before it (docs/CASEBOOK.md, case 6): the deployment turns it off (deploy/README.md)."""
    if not server_log.exists():
        return line("cache", True, f"not checked: no model server log at {server_log}")
    last = ""
    with server_log.open("rb") as handle:  # read once, a line at a time, and closed
        for raw in handle:
            if b"prompt cache is" in raw:
                last = raw.decode("utf-8", errors="replace")
    if not last:
        return line("cache", True, "not checked: the model has not been loaded since the server started")
    if "prompt cache is disabled" in last:
        return line("cache", True, "host-RAM prompt cache off at the last model load")
    return line("cache", False, "host-RAM prompt cache on: answers depend on what was asked before; set LLAMA_ARG_CACHE_RAM=0 and restart Ollama")


def check_store(database: Path) -> bool:
    """PRAGMA quick_check through the read-only engine: it reads every table and index, where the runs line reads two.
    A damaged page in any other table was never seen here (stress test, 2026-10-30, ops 3)."""
    if not database.exists():
        return line("store", False, f"no {database.name} in the data directory")
    engine = read_only(database)
    try:
        with engine.connect() as connection:
            found = [str(row[0]) for row in connection.exec_driver_sql("PRAGMA quick_check")]
    except Exception as error:  # noqa: BLE001 - a store that cannot even be checked is the problem this line names
        return line("store", False, f"quick_check could not run: {type(error).__name__}")
    finally:
        engine.dispose()
    ok = found == ["ok"]
    return line("store", ok, "quick_check ok" if ok else f"quick_check: {len(found)} problem(s), first: {found[0][:120] if found else '?'}")


def check_supervisor(logs: Path, tag: str) -> bool:
    path = logs / f"{tag}.supervisor.log"
    if not path.exists():
        return line(f"{tag} sup", False, f"no {path.name}: is supervision installed (deploy/install-supervision.ps1)?")
    last = last_line(path)
    stopped = "supervisor exiting" in last or "not restarting" in last or "supervisor not started" in last
    return line(f"{tag} sup", not stopped, last[:160])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir)
    parser.add_argument("--public", action="store_true", help="the store is the public demo's: its own disk floor")
    parser.add_argument("--metrics", default="http://127.0.0.1:20241", help="cloudflared's metrics address")
    parser.add_argument("--logs", type=Path, default=BACKEND / "data" / "logs" / "deploy")
    parser.add_argument("--ollama-log", type=Path, default=OLLAMA_LOG, help="the model server's log, for its prompt cache")
    parser.add_argument("--max-runs-per-day", type=int, default=None, help="the day's ceiling; --public uses the public site's")
    args = parser.parse_args(argv)
    ceiling = PUBLIC_MAX_RUNS_PER_DAY if args.public else settings.max_runs_per_day
    results = [
        check_api(args.api.rstrip("/")),
        check_model(),
        check_cache(args.ollama_log),
        check_disk(args.data_dir, args.public),
        check_store(args.data_dir / "workbench.db"),
        check_runs(args.data_dir / "workbench.db", args.max_runs_per_day if args.max_runs_per_day is not None else ceiling),
        check_rules(args.data_dir / "workbench.db"),
        check_tunnel(args.metrics.rstrip("/")),
        check_supervisor(args.logs, "api"),
        check_supervisor(args.logs, "web"),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
