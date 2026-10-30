"""Deleting a public visitor's workspace once it has ended (DECISIONS.md, 2026-10-09).

The public demo store (WORKBENCH_ANONYMOUS_SESSIONS, its own WORKBENCH_DATA_DIR) promises visitors that what they add
is deleted when their workspace ends. Everything else in this codebase keeps a finished run forever, and the database
refuses to delete one (db.immutability_triggers). This is the one, scoped exception:

- only workspaces listed in visitor_workspaces, and only once they have ended, are ever candidates: an owner store
  lists none, so there is nothing here it can delete;
- a workspace with a run still in progress is left for the next pass;
- a workspace is deleted in transactions each bounded by a unit the store already bounds: its runs and what hangs from
  them, then each document it held, whole, then its registration, last, so a pass stopped anywhere is finished by the
  next. One pass held the write lock for everything that expired in its hour, past the 30 s every other writer waits:
  13 s for 342 MB, 130 s for 1.8 GB, and every write in that window failed (stress test, 2026-10-30, ops 5). Each
  transaction is followed by a pause, so other writers get the lock between them;
- where runs are deleted, the triggers are dropped, the rows deleted and the same triggers created again, in that one
  transaction: a failure part way leaves its rows and the triggers as they were;
- an original is deleted inside the transaction that deletes the last document row naming its bytes (another visitor may
  hold the same bytes), and the sweep deletes each file it finds no row for under the lock too: decided after a commit,
  an upload could keep the file it saw and lose it a moment later. A memo is deleted by the name it was written under.
  A sweep removes files no row names any more, so a crash cannot keep a visitor's file past its end;
- a visit that began after the clock now reads (models.issued_in_future) is counted from now, its life kept whole: the
  wall clock ran ahead when it was made, or stepped back since. A visit made while the clock ran 30 days ahead kept its
  end 37 days out once the clock was corrected, and lived to real day 37 (stress test, 2026-10-30, time 3). The two
  cases cannot be told apart on the wall clock, so neither is cut short: a step back deletes nothing, and a visit lives
  at most its days plus the time the clock ran ahead plus one pass;
- one file a pass cannot remove (another handle holds it, as Windows refuses; it vanished since the folder was listed)
  is kept for the next pass, counted and logged, and the pass goes on: the first PermissionError ended the pass, so every
  file after it, the memos, the drafts, the handoff files and the purge's checkpoint waited an hour (stress test,
  2026-10-30, time 6). The checkpoint runs whatever the pass met;
- a file is abandoned, for the sweep, when this process has seen it unchanged for the grace by its monotonic clock, or,
  while the wall clock has not stepped since the process started, when its mtime is past the grace: by mtime alone, a
  forward step of over an hour took a partial upload being written for abandoned (the same review).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path, PureWindowsPath

from sqlalchemy import Connection, Engine, text

from ..config import settings
from ..db import PUBLIC_WORKSPACE_LIKE, immutability_triggers, workspace_tables
from ..ingest.bounded import HANDOFF_PREFIX, handoff_folder
from ..ingest.readers import SUFFIX_OF
from ..models import CLOCK_SKEW, TERMINAL_STAGES, utcnow

log = logging.getLogger(__name__)

# A file younger than this is never swept: an upload writes its bytes before its row commits.
SWEEP_GRACE = timedelta(hours=1)
# How far the wall clock may move against this process's monotonic clock (drift, a slewed correction) before the sweep
# stops trusting file times; past it, a file goes only once this process has seen it unchanged for the grace.
WALL_STEP_TOLERANCE = timedelta(minutes=5)
_monotonic = time.monotonic
# The wall clock's reading less the monotonic clock's, when this process started: a step since moves it.
_WALL_AT_START = time.time() - time.monotonic()
# What each candidate file was when this process first saw it as it is now: (size, mtime) and the monotonic instant.
_seen: dict[Path, tuple[tuple[int, int], float]] = {}
_reported_step = 0.0
# The pause after each of a pass's transactions: at least this, or as long as the transaction held the lock, at most the
# second bound.
PURGE_GAP_S, PURGE_GAP_MAX_S = 0.05, 1.0


@dataclass
class PurgeReport:
    workspaces: list[str] = field(default_factory=list)
    skipped_in_progress: list[str] = field(default_factory=list)
    kept: int = 0  # files that could not be removed this pass, left for the next
    counted_from_now: list[str] = field(default_factory=list)  # visits that began after the clock's reading (_reanchor)
    runs: int = 0
    documents: int = 0
    files: int = 0
    checkpointed: bool = False


def _ids(connection: Connection, sql: str, **params: object) -> list[str]:
    return [str(row[0]) for row in connection.execute(text(sql), params)]


def _in(column: str, values: list[str]) -> tuple[str, dict[str, object]]:
    names = [f"v{i}" for i in range(len(values))]
    return f"{column} IN ({', '.join(':' + n for n in names)})", dict(zip(names, values, strict=True))


# How SQLite keeps these columns: naive UTC text, compared as that text.
STORED_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def _stored(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(STORED_FORMAT)


def _read_stored(text_value: object) -> datetime:
    value = text_value if isinstance(text_value, datetime) else datetime.fromisoformat(str(text_value))
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _reanchor(engine: Engine, now: datetime, report: PurgeReport, gap_s: float) -> None:
    """Visits that began after ``now`` by more than the skew are moved to begin now, each keeping its own length of life
    (not today's setting: lowering the retention days must not shorten a visit already made). Decided again under the
    lock, where they are moved."""
    ahead = {"ahead": _stored(now + CLOCK_SKEW)}
    query = "SELECT workspace_id, created_at, expires_at FROM visitor_workspaces WHERE created_at > :ahead"
    with engine.connect() as connection:
        if connection.execute(text(query + " LIMIT 1"), ahead).first() is None:
            return
    with _locked(engine, gap_s) as connection:
        rows = connection.execute(text(query), ahead).all()
        for workspace, created, expires in rows:
            began = _read_stored(created)
            moved = {"w": workspace, "c": _stored(now), "e": _stored(now + (_read_stored(expires) - began))}
            connection.execute(text("UPDATE visitor_workspaces SET created_at = :c, expires_at = :e WHERE workspace_id = :w"), moved)
            report.counted_from_now.append(str(workspace))
        latest = max((_read_stored(row[1]) for row in rows), default=now)
    if report.counted_from_now:
        # A clock fault made visible rather than silent: the hours say how far it was off.
        log.warning(
            "retention: %d visit(s) began up to %.1f h after the clock now reads; each is counted from now",
            len(report.counted_from_now),
            (latest - now).total_seconds() / 3600,
        )


def purge_expired_workspaces(engine: Engine, now: datetime | None = None, gap_s: float = PURGE_GAP_S) -> PurgeReport:
    report = PurgeReport()
    instant = now or utcnow()
    _reanchor(engine, instant, report, gap_s)
    moment = _stored(instant)
    with engine.connect() as connection:
        # Candidates are read without the lock; each is decided again under it, where it is deleted.
        expired = _ids(connection, "SELECT workspace_id FROM visitor_workspaces WHERE expires_at <= :now", now=moment)
        # Rows of public workspaces no longer listed: written past an earlier purge before the store refused them
        # (db.workspace_guards), or left by a pass that stopped before its last step. Purged like an ended workspace,
        # first, so they no longer keep the documents they name, and a store that holds them heals (stress test,
        # 2026-10-30).
        unlisted = " UNION ".join(
            f"SELECT workspace_id FROM {table} WHERE workspace_id LIKE :public AND workspace_id NOT IN (SELECT workspace_id FROM visitor_workspaces)"
            for table in workspace_tables()
        )
        candidates = sorted(set(_ids(connection, unlisted, public=PUBLIC_WORKSPACE_LIKE)) - set(expired)) + expired
    try:
        for workspace in candidates:
            _purge_workspace(engine, workspace, moment, report, gap_s)
    finally:
        _checkpoint(engine, report)
    log.info(
        "retention purged workspaces=%d runs=%d documents=%d files=%d kept=%d skipped_in_progress=%d checkpointed=%s",
        len(report.workspaces),
        report.runs,
        report.documents,
        report.files,
        report.kept,
        len(report.skipped_in_progress),
        report.checkpointed,
    )
    return report


def _checkpoint(engine: Engine, report: PurgeReport) -> None:
    # secure_delete zeroes what the rows held in the pages they leave; the write-ahead log still holds the frames written
    # before, until a checkpoint copies the zeroed pages back and truncates it. A reader holding an old snapshot can keep
    # the checkpoint from finishing (checkpointed=False); every hourly pass checkpoints, whether or not it purged. It does
    # not wait for that reader: writers queue behind a waiting checkpoint, so it gives up at once and the next pass retries.
    with engine.connect() as connection:
        waits = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()
        connection.exec_driver_sql("PRAGMA busy_timeout=0")
        try:
            busy, _log, _done = connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").one()
        finally:
            connection.exec_driver_sql(f"PRAGMA busy_timeout={int(waits or 0)}")
        report.checkpointed = busy == 0


@contextmanager
def _locked(engine: Engine, gap_s: float) -> Iterator[Connection]:
    """One bounded transaction under the write lock, begun before anything is read: python's sqlite3 begins none before
    DDL, so without it the DROP TRIGGERs would commit on their own and a failure after them would leave the store without
    its immutability triggers (triage review, 2026-10-09). After it, a pause as long as it held the lock, between
    PURGE_GAP_S and PURGE_GAP_MAX_S: SQLite's busy wait polls, it is not a queue, and transactions back to back starved a
    writer past its 30 s wait although the lock was released between them (measured: forty one-second holds failed a
    writer; with a 50 ms gap it was in after 0.54 s)."""
    started = time.monotonic()
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        yield connection
    time.sleep(min(PURGE_GAP_MAX_S, max(gap_s, time.monotonic() - started)))


def _purge_workspace(engine: Engine, workspace: str, moment: str, report: PurgeReport, gap_s: float) -> None:
    """One workspace, in transactions each bounded by a unit the store already bounds: its runs and what hangs from
    them (bounded by its questions), then each document it held, whole (one reading of at most 25 MB), then its row in
    visitor_workspaces, the resume key: a pass stopped anywhere is finished by the next, from what is left."""
    finished = ", ".join(repr(s) for s in TERMINAL_STAGES)
    memo_files: list[str] = []
    with _locked(engine, gap_s) as connection:
        if connection.execute(text("SELECT 1 FROM visitor_workspaces WHERE workspace_id = :w AND expires_at > :now"), {"w": workspace, "now": moment}).first():
            return  # not ended after all
        if connection.execute(text(f"SELECT 1 FROM runs WHERE workspace_id = :w AND stage NOT IN ({finished}) LIMIT 1"), {"w": workspace}).first():
            report.skipped_in_progress.append(workspace)
            return
        # The documents the workspace held, and those its version statements name: a document a statement alone kept past
        # its holders' purge has no grant left, and is let go below once nothing else uses it.
        held = _ids(
            connection,
            "SELECT document_id FROM document_access WHERE workspace_id = :w UNION SELECT document_id FROM document_versions "
            "WHERE workspace_id = :w UNION SELECT supersedes_document_id FROM document_versions WHERE workspace_id = :w "
            "AND supersedes_document_id IS NOT NULL",
            w=workspace,
        )
        runs = _ids(connection, "SELECT id FROM runs WHERE workspace_id = :w", w=workspace)
        if runs:
            # A finished run's rows refuse deletion (db.immutability_triggers): the triggers are dropped and created again
            # inside this transaction, so a failure part way puts them back with everything else.
            triggers = immutability_triggers()
            for name, _statement in triggers:
                connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {name}")
            where, params = _in("run_id", runs)
            memo_files = [str(r[0]) for r in connection.execute(text(f"SELECT docx_path FROM memos WHERE {where}"), params)]
            findings = _ids(connection, f"SELECT id FROM findings WHERE {where}", **params)
            if findings:
                fwhere, fparams = _in("finding_id", findings)
                connection.execute(text(f"DELETE FROM evidence_spans WHERE {fwhere}"), fparams)
                connection.execute(text(f"DELETE FROM finding_reviews WHERE {fwhere}"), fparams)
            for table in ("memos", "batch_items", "findings", "run_stages"):
                connection.execute(text(f"DELETE FROM {table} WHERE {where}"), params)
            rwhere, rparams = _in("id", runs)
            connection.execute(text(f"DELETE FROM runs WHERE {rwhere}"), rparams)
            for _name, statement in triggers:
                connection.exec_driver_sql(statement)
        connection.execute(text("DELETE FROM guidance WHERE workspace_id = :w"), {"w": workspace})
        connection.execute(text("DELETE FROM document_versions WHERE workspace_id = :w"), {"w": workspace})
    report.runs += len(runs)
    for recorded in memo_files:
        _count(report, _remove(settings.data_dir / "memos" / PureWindowsPath(recorded).name))  # a memo's file is its own
    for document_id in held:
        with _locked(engine, gap_s) as connection:
            connection.execute(text("DELETE FROM document_access WHERE workspace_id = :w AND document_id = :d"), {"w": workspace, "d": document_id})
            still_used = connection.execute(
                text(
                    "SELECT 1 FROM document_access WHERE document_id = :d UNION ALL SELECT 1 FROM runs WHERE document_id = :d "
                    "UNION ALL SELECT 1 FROM document_versions WHERE document_id = :d OR supersedes_document_id = :d "
                    "UNION ALL SELECT 1 FROM batch_items WHERE document_id = :d LIMIT 1"
                ),
                {"d": document_id},
            ).first()
            if still_used:
                continue  # another workspace holds the same bytes, under its own name
            row = connection.execute(text("SELECT sha256, media_type FROM documents WHERE id = :d"), {"d": document_id}).first()
            # No finished run reads it (still_used): the triggers on sections and documents do not apply.
            connection.execute(text("DELETE FROM sections WHERE document_id = :d"), {"d": document_id})
            connection.execute(text("DELETE FROM documents WHERE id = :d"), {"d": document_id})
            report.documents += 1
            if row is not None:
                _count(report, _unlink_original_if_unused(connection, str(row[0]), str(row[1])))
    with _locked(engine, gap_s) as connection:
        connection.execute(text("DELETE FROM document_access WHERE workspace_id = :w"), {"w": workspace})
        connection.execute(text("DELETE FROM visitor_workspaces WHERE workspace_id = :w"), {"w": workspace})
    report.workspaces.append(workspace)


def _count(report: PurgeReport, removed: bool | None) -> None:
    if removed:
        report.files += 1
    elif removed is None:
        report.kept += 1


def _unlink_original_if_unused(connection: Connection, sha256: str, media_type: str) -> bool | None:
    """Delete the original of these bytes when no document row names them, inside the caller's transaction under the
    write lock: decided after its commit, an upload that found the row first kept the file it saw and the purge then
    deleted it, leaving a live row with no original (stress test, 2026-10-30, concurrency 1). An upload decides reuse
    under the same lock (application/ingest_document.py), so the two never interleave."""
    if connection.execute(text("SELECT 1 FROM documents WHERE sha256 = :s LIMIT 1"), {"s": sha256}).first():
        return False
    return _remove(settings.data_dir / "documents" / f"{sha256}{SUFFIX_OF.get(media_type, '')}")


class _Abandoned:
    """Whether a file is past the grace, judged once per pass. A file is abandoned when this process has seen it unchanged
    (its size and mtime) for the grace by the monotonic clock; or, while the wall clock has not stepped since the process
    started, when its mtime is past the grace by the wall clock. By mtime alone, after a forward step of over an hour, a
    partial upload being written was abandoned (stress test, 2026-10-30, time 6); and after a step back, an abandoned file
    looked young until the clock caught up. After a step, a file goes once this process has seen it for the grace."""

    def __init__(self, now: datetime) -> None:
        global _reported_step
        self.seen_at = _monotonic()
        self.cutoff = now.timestamp() - SWEEP_GRACE.total_seconds()
        step = now.timestamp() - self.seen_at - _WALL_AT_START
        self.stepped = abs(step) > WALL_STEP_TOLERANCE.total_seconds()
        self.examined: set[Path] = set()
        if self.stepped and abs(step - _reported_step) > WALL_STEP_TOLERANCE.total_seconds():
            _reported_step = step
            log.warning("retention: the wall clock is %.0f s off its reading against this process's clock at start; files are judged by what it saw", step)

    def __call__(self, path: Path, status: os.stat_result) -> bool:
        shape = (status.st_size, status.st_mtime_ns)
        self.examined.add(path)
        first = _seen.get(path)
        if first is None or first[0] != shape:
            first = _seen[path] = (shape, self.seen_at)
        if self.seen_at - first[1] >= SWEEP_GRACE.total_seconds():
            return True
        return not self.stepped and status.st_mtime < self.cutoff

    def forget_the_rest(self) -> None:
        for path in [p for p in _seen if p not in self.examined]:
            del _seen[path]


def sweep_orphaned_files(engine: Engine, now: datetime | None = None) -> int:
    """Files in the public store that no row names any more, past SWEEP_GRACE (_Abandoned): what a crash would leave, an
    upload's partial file left by a crash before its rename (no row ever names a partial, and none is still being written
    after the grace), a memo's draft, and a reading's handed-over file. A file it cannot remove is kept for the next pass
    (_remove). Returns how many it removed."""
    abandoned = _Abandoned(now or utcnow())
    outcomes: list[bool | None] = []
    with engine.connect() as connection:
        hashes = {str(r[0]) for r in connection.execute(text("SELECT sha256 FROM documents"))}
        memos = {PureWindowsPath(str(r[0])).name for r in connection.execute(text("SELECT docx_path FROM memos"))}

    def unnamed_under_the_lock(path: Path) -> bool | None:
        # Decided again under the write lock, one file at a time: an upload of these bytes may have stored them since the
        # names were read (stress test, 2026-10-30, concurrency 1).
        with _locked(engine, PURGE_GAP_S) as connection:
            if connection.execute(text("SELECT 1 FROM documents WHERE sha256 = :s LIMIT 1"), {"s": path.name.split(".")[0]}).first():
                return False
            return _remove(path)

    for path in _listed(settings.data_dir / "documents", "*"):
        if path.name.endswith(".part"):
            outcomes.append(_remove_if(path, abandoned))
        elif path.name.split(".")[0] not in hashes:
            outcomes.append(_remove_if(path, abandoned, then=unnamed_under_the_lock))
    for path in _listed(settings.data_dir / "memos", "*"):
        if path.name not in memos:
            outcomes.append(_remove_if(path, abandoned))
    # A memo is written in memos/pending/<token>/ and moved out before its row exists (create_memo); a process killed in
    # between leaves the visitor's draft there, below the loop above (cloud readiness review, 2026-10-12). No request
    # writes a draft for longer than the grace.
    for folder in _listed(settings.data_dir / "memos" / "pending", "*"):
        outcomes.append(_remove_draft(folder, abandoned))
    # A file handed to a reading's child (ingest/bounded.py) lives for the reading, at most seconds; one older than the
    # grace was left by a process killed mid-reading. The API's start empties the folder too.
    for path in _listed(handoff_folder(settings.data_dir), f"{HANDOFF_PREFIX}*"):
        outcomes.append(_remove_if(path, abandoned))
    abandoned.forget_the_rest()
    if None in outcomes:
        log.warning("retention sweep kept %d file(s) it could not remove; the next pass tries again", outcomes.count(None))
    return outcomes.count(True)


def _listed(folder: Path, pattern: str) -> list[Path]:
    try:
        return list(folder.glob(pattern))
    except OSError as error:
        log.warning("retention could not list %s this pass: %s", folder.name, type(error).__name__)
        return []


def _remove_draft(folder: Path, abandoned: _Abandoned) -> bool | None:
    """A pending memo folder whose files and the folder itself are all abandoned, removed with them."""
    try:
        if not stat.S_ISDIR(folder.stat().st_mode):
            return False
        drafts = [p for p in folder.rglob("*") if stat.S_ISREG(p.stat().st_mode)]
        seen = [abandoned(p, p.stat()) for p in [folder, *drafts]]  # each one judged, so each one's clock starts
        if not all(seen):
            return False
    except FileNotFoundError:
        return False
    except OSError as error:
        log.warning("retention kept a draft in memos/pending this pass: %s", type(error).__name__)
        return None
    removed = [_remove(p) for p in drafts]
    shutil.rmtree(folder, ignore_errors=True)
    return None if None in removed else True


def forget_process_state() -> None:
    """Drop what this process derived from documents and kept beyond a request, after every retention pass, a failed one
    included: readings again (trust_run), clause numbers, replacement starts, the defined terms' patterns and every
    pattern re compiled from document text. Kept, a deleted visitor's defined terms and prose were still reachable in
    the process after the purge (stress test, 2026-10-30, privacy 2). Unreachable is not erased: freed memory is not
    zeroed, and only a restart of the process drops it."""
    from ..runs import links
    from . import clause_location, start_run, trust_run

    trust_run.forget_readings()
    with clause_location._clause_numbers_lock:
        clause_location._clause_numbers.clear()
    with start_run._STARTS_LOCK:
        start_run._STARTS.clear()
    links._use_of.cache_clear()
    re.purge()


def _remove_if(path: Path, abandoned: Callable[[Path, os.stat_result], bool], then: Callable[[Path], bool | None] | None = None) -> bool | None:
    """Remove ``path`` if it is a file and abandoned: its stat, the decision and the unlink inside one guard, so a file
    renamed after the folder was listed (6 of 1,102 passes against a busy writer ended there) or refused is kept, never
    raised. True when removed; False when kept on purpose or already gone; None when the system refused it. ``then``,
    when given, makes the last decision and removes it (under the store's lock)."""
    try:
        status = path.stat()
        if not stat.S_ISREG(status.st_mode) or not abandoned(path, status):
            return False
    except FileNotFoundError:
        return False
    except OSError as error:
        log.warning("retention kept a file in %s this pass: %s", path.parent.name, type(error).__name__)
        return None
    return then(path) if then is not None else _remove(path)


def _remove(path: Path) -> bool | None:
    """Unlink ``path``: True when removed, False when already gone, None when the system refused, logged and kept for the
    next pass. Windows refuses to delete a file another handle holds (a pack being read, a trust re-read, an antivirus
    scan); that PermissionError ended the whole pass (stress test, 2026-10-30, time 6)."""
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as error:
        log.warning("retention kept a file in %s this pass: %s", path.parent.name, type(error).__name__)
        return None
