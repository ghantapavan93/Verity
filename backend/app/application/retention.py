"""Deleting a public visitor's workspace once it has ended (DECISIONS.md, 2026-10-09).

The public demo store (WORKBENCH_ANONYMOUS_SESSIONS, its own WORKBENCH_DATA_DIR) promises visitors that what they add
is deleted when their workspace ends. Everything else in this codebase keeps a finished run forever, and the database
refuses to delete one (db.immutability_triggers). This is the one, scoped exception:

- only workspaces listed in visitor_workspaces, and only once they have ended, are ever candidates: an owner store
  lists none, so there is nothing here it can delete;
- a workspace with a run still in progress is left for the next pass;
- the triggers are dropped, the rows deleted and the same triggers created again, in one transaction: a failure part
  way leaves the store and its triggers as they were;
- files are deleted only after the transaction commits: an original only when no document row with its bytes remains
  (another visitor may hold the same bytes), a memo by the name it was written under. A sweep removes files no row
  names any more, so a crash between commit and unlink cannot keep a visitor's file past its end.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path, PureWindowsPath

from sqlalchemy import Connection, Engine, text

from ..config import settings
from ..db import immutability_triggers
from ..ingest.readers import SUFFIX_OF
from ..models import TERMINAL_STAGES, utcnow

log = logging.getLogger(__name__)

# A file younger than this is never swept: an upload writes its bytes before its row commits.
SWEEP_GRACE = timedelta(hours=1)


@dataclass
class PurgeReport:
    workspaces: list[str] = field(default_factory=list)
    skipped_in_progress: list[str] = field(default_factory=list)
    runs: int = 0
    documents: int = 0
    files: int = 0


def _ids(connection: Connection, sql: str, **params: object) -> list[str]:
    return [str(row[0]) for row in connection.execute(text(sql), params)]


def _in(column: str, values: list[str]) -> tuple[str, dict[str, object]]:
    names = [f"v{i}" for i in range(len(values))]
    return f"{column} IN ({', '.join(':' + n for n in names)})", dict(zip(names, values, strict=True))


def purge_expired_workspaces(engine: Engine, now: datetime | None = None) -> PurgeReport:
    report = PurgeReport()
    # SQLite keeps these as naive UTC text, "YYYY-MM-DD HH:MM:SS.ffffff"; compared as that text.
    moment = (now or utcnow()).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
    finished = tuple(TERMINAL_STAGES)
    deleted_documents: list[tuple[str, str]] = []  # (sha256, media_type)
    memo_files: list[str] = []
    with engine.begin() as connection:
        # One transaction under the write lock, begun before anything is read: python's sqlite3 begins none before
        # DDL, so without this the DROP TRIGGERs below would commit on their own and a failure after them would leave
        # the store without its immutability triggers (triage review, 2026-10-09).
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        expired = _ids(connection, "SELECT workspace_id FROM visitor_workspaces WHERE expires_at <= :now", now=moment)
        purgeable: list[str] = []
        for workspace in expired:
            running = connection.execute(
                text(f"SELECT 1 FROM runs WHERE workspace_id = :w AND stage NOT IN ({', '.join(repr(s) for s in finished)}) LIMIT 1"), {"w": workspace}
            ).first()
            (report.skipped_in_progress if running else purgeable).append(workspace)
        if not purgeable:
            return report
        triggers = immutability_triggers()
        for name, _statement in triggers:
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {name}")
        for workspace in purgeable:
            runs = _ids(connection, "SELECT id FROM runs WHERE workspace_id = :w", w=workspace)
            if runs:
                where, params = _in("run_id", runs)
                memo_files += [str(r[0]) for r in connection.execute(text(f"SELECT docx_path FROM memos WHERE {where}"), params)]
                findings = _ids(connection, f"SELECT id FROM findings WHERE {where}", **params)
                if findings:
                    fwhere, fparams = _in("finding_id", findings)
                    connection.execute(text(f"DELETE FROM evidence_spans WHERE {fwhere}"), fparams)
                    connection.execute(text(f"DELETE FROM finding_reviews WHERE {fwhere}"), fparams)
                for table in ("memos", "batch_items", "findings", "run_stages"):
                    connection.execute(text(f"DELETE FROM {table} WHERE {where}"), params)
                rwhere, rparams = _in("id", runs)
                connection.execute(text(f"DELETE FROM runs WHERE {rwhere}"), rparams)
                report.runs += len(runs)
            granted = _ids(connection, "SELECT document_id FROM document_access WHERE workspace_id = :w", w=workspace)
            connection.execute(text("DELETE FROM guidance WHERE workspace_id = :w"), {"w": workspace})
            connection.execute(text("DELETE FROM document_versions WHERE workspace_id = :w"), {"w": workspace})
            connection.execute(text("DELETE FROM document_access WHERE workspace_id = :w"), {"w": workspace})
            connection.execute(text("DELETE FROM visitor_workspaces WHERE workspace_id = :w"), {"w": workspace})
            for document_id in granted:
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
                connection.execute(text("DELETE FROM sections WHERE document_id = :d"), {"d": document_id})
                connection.execute(text("DELETE FROM documents WHERE id = :d"), {"d": document_id})
                if row is not None:
                    deleted_documents.append((str(row[0]), str(row[1])))
                report.documents += 1
            report.workspaces.append(workspace)
        for _name, statement in triggers:
            connection.exec_driver_sql(statement)
    # After the commit: a file goes only once no row needs it.
    with engine.connect() as connection:
        for sha256, media_type in deleted_documents:
            if connection.execute(text("SELECT 1 FROM documents WHERE sha256 = :s LIMIT 1"), {"s": sha256}).first():
                continue
            report.files += _unlink(settings.data_dir / "documents" / f"{sha256}{SUFFIX_OF.get(media_type, '')}")
    for recorded in memo_files:
        report.files += _unlink(settings.data_dir / "memos" / PureWindowsPath(recorded).name)
    log.info(
        "retention purged workspaces=%d runs=%d documents=%d files=%d skipped_in_progress=%d",
        len(report.workspaces),
        report.runs,
        report.documents,
        report.files,
        len(report.skipped_in_progress),
    )
    return report


def sweep_orphaned_files(engine: Engine, now: datetime | None = None) -> int:
    """Files in the public store that no row names any more, older than SWEEP_GRACE: what a crash between a purge's
    commit and its unlinks would leave."""
    cutoff = (now or utcnow()).timestamp() - SWEEP_GRACE.total_seconds()
    removed = 0
    with engine.connect() as connection:
        hashes = {str(r[0]) for r in connection.execute(text("SELECT sha256 FROM documents"))}
        memos = {PureWindowsPath(str(r[0])).name for r in connection.execute(text("SELECT docx_path FROM memos"))}
    for path in (settings.data_dir / "documents").glob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff and not path.name.endswith(".part") and path.name.split(".")[0] not in hashes:
            removed += _unlink(path)
    for path in (settings.data_dir / "memos").glob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff and path.name not in memos:
            removed += _unlink(path)
    return removed


def _unlink(path: Path) -> int:
    try:
        path.unlink()
        return 1
    except FileNotFoundError:
        return 0
