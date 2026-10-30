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
  A sweep removes files no row names any more, so a crash cannot keep a visitor's file past its end.
"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path, PureWindowsPath

from sqlalchemy import Connection, Engine, text

from ..config import settings
from ..db import PUBLIC_WORKSPACE_LIKE, immutability_triggers, workspace_tables
from ..ingest.bounded import HANDOFF_PREFIX, handoff_folder
from ..ingest.readers import SUFFIX_OF
from ..models import TERMINAL_STAGES, utcnow

log = logging.getLogger(__name__)

# A file younger than this is never swept: an upload writes its bytes before its row commits.
SWEEP_GRACE = timedelta(hours=1)
# The pause after each of a pass's transactions: at least this, or as long as the transaction held the lock, at most the
# second bound.
PURGE_GAP_S, PURGE_GAP_MAX_S = 0.05, 1.0


@dataclass
class PurgeReport:
    workspaces: list[str] = field(default_factory=list)
    skipped_in_progress: list[str] = field(default_factory=list)
    runs: int = 0
    documents: int = 0
    files: int = 0
    checkpointed: bool = False


def _ids(connection: Connection, sql: str, **params: object) -> list[str]:
    return [str(row[0]) for row in connection.execute(text(sql), params)]


def _in(column: str, values: list[str]) -> tuple[str, dict[str, object]]:
    names = [f"v{i}" for i in range(len(values))]
    return f"{column} IN ({', '.join(':' + n for n in names)})", dict(zip(names, values, strict=True))


def purge_expired_workspaces(engine: Engine, now: datetime | None = None, gap_s: float = PURGE_GAP_S) -> PurgeReport:
    report = PurgeReport()
    # SQLite keeps these as naive UTC text, "YYYY-MM-DD HH:MM:SS.ffffff"; compared as that text.
    moment = (now or utcnow()).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
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
    for workspace in candidates:
        _purge_workspace(engine, workspace, moment, report, gap_s)
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
    log.info(
        "retention purged workspaces=%d runs=%d documents=%d files=%d skipped_in_progress=%d checkpointed=%s",
        len(report.workspaces),
        report.runs,
        report.documents,
        report.files,
        len(report.skipped_in_progress),
        report.checkpointed,
    )
    return report


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
        report.files += _unlink(settings.data_dir / "memos" / PureWindowsPath(recorded).name)  # a memo's file is its own
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
                report.files += _unlink_original_if_unused(connection, str(row[0]), str(row[1]))
    with _locked(engine, gap_s) as connection:
        connection.execute(text("DELETE FROM document_access WHERE workspace_id = :w"), {"w": workspace})
        connection.execute(text("DELETE FROM visitor_workspaces WHERE workspace_id = :w"), {"w": workspace})
    report.workspaces.append(workspace)


def _unlink_original_if_unused(connection: Connection, sha256: str, media_type: str) -> int:
    """Delete the original of these bytes when no document row names them, inside the caller's transaction under the
    write lock: decided after its commit, an upload that found the row first kept the file it saw and the purge then
    deleted it, leaving a live row with no original (stress test, 2026-10-30, concurrency 1). An upload decides reuse
    under the same lock (application/ingest_document.py), so the two never interleave."""
    if connection.execute(text("SELECT 1 FROM documents WHERE sha256 = :s LIMIT 1"), {"s": sha256}).first():
        return 0
    return _unlink(settings.data_dir / "documents" / f"{sha256}{SUFFIX_OF.get(media_type, '')}")


def sweep_orphaned_files(engine: Engine, now: datetime | None = None) -> int:
    """Files in the public store that no row names any more, older than SWEEP_GRACE: what a crash would leave, an
    upload's partial file left by a crash before its rename (no row ever names a partial, and none is still being written
    after the grace), a memo's draft, and a reading's handed-over file."""
    cutoff = (now or utcnow()).timestamp() - SWEEP_GRACE.total_seconds()
    removed = 0
    with engine.connect() as connection:
        hashes = {str(r[0]) for r in connection.execute(text("SELECT sha256 FROM documents"))}
        memos = {PureWindowsPath(str(r[0])).name for r in connection.execute(text("SELECT docx_path FROM memos"))}
    for path in (settings.data_dir / "documents").glob("*"):
        if not (path.is_file() and path.stat().st_mtime < cutoff):
            continue
        if path.name.endswith(".part"):
            removed += _unlink(path)
        elif path.name.split(".")[0] not in hashes:
            # Decided again under the write lock, one file at a time: an upload of these bytes may have stored them since
            # the names were read (stress test, 2026-10-30, concurrency 1).
            with _locked(engine, PURGE_GAP_S) as connection:
                if not connection.execute(text("SELECT 1 FROM documents WHERE sha256 = :s LIMIT 1"), {"s": path.name.split(".")[0]}).first():
                    removed += _unlink(path)
    for path in (settings.data_dir / "memos").glob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff and path.name not in memos:
            removed += _unlink(path)
    # A memo is written in memos/pending/<token>/ and moved out before its row exists (create_memo); a process killed in
    # between leaves the visitor's draft there, below the loop above (cloud readiness review, 2026-10-12). No request
    # writes a draft for longer than the grace.
    for folder in (settings.data_dir / "memos" / "pending").glob("*"):
        drafts = [p for p in folder.rglob("*") if p.is_file()] if folder.is_dir() else []
        if folder.is_dir() and all(p.stat().st_mtime < cutoff for p in [folder, *drafts]):
            removed += sum(_unlink(p) for p in drafts)
            shutil.rmtree(folder, ignore_errors=True)
    # A file handed to a reading's child (ingest/bounded.py) lives for the reading, at most seconds; one older than the
    # grace was left by a process killed mid-reading. The API's start empties the folder too.
    for path in handoff_folder(settings.data_dir).glob(f"{HANDOFF_PREFIX}*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            removed += _unlink(path)
    return removed


def _unlink(path: Path) -> int:
    try:
        path.unlink()
        return 1
    except FileNotFoundError:
        return 0
