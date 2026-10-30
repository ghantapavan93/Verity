"""SQLite through SQLAlchemy 2. One file, one process; enough for the first slice and honest
about it: a second datastore is added when a measurement needs one."""

from __future__ import annotations

import functools
import logging
import re
import sqlite3
import threading
import time
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import ExceptionContext
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, NullPool
from sqlalchemy.schema import CreateIndex

from .config import settings
from .errors import Busy

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# What the engine met that the file system cannot show (stress test, 2026-10-30, ops 3: a damaged page answered 500 on
# every read of its table while health said ok). By SQLite's error name, with when it was first met. A damaged file
# (CORRUPT, NOTADB) is reported until the process starts again: a later commit elsewhere in a damaged file succeeds while
# the damage stays. An I/O error, a read-only or full store, a file that cannot be opened, until the next successful
# commit. A lost race for the write lock (BUSY, "locked") is contention, not a fault, and is not noted.
DAMAGED = ("SQLITE_CORRUPT", "SQLITE_NOTADB")
PASSING = ("SQLITE_IOERR", "SQLITE_READONLY", "SQLITE_FULL", "SQLITE_CANTOPEN")
# Kept per engine, the store the process serves being `engine` below.
_faults: weakref.WeakKeyDictionary[Engine, dict[str, float]] = weakref.WeakKeyDictionary()
_faults_lock = threading.Lock()


def note_store_error(error: BaseException, target: Engine | None = None) -> None:
    name = str(getattr(error, "sqlite_errorname", "") or "")
    if name.startswith(DAMAGED) or name.startswith(PASSING):
        with _faults_lock:
            _faults.setdefault(target or engine, {}).setdefault(name, time.time())


def _committed(target: Engine) -> None:
    with _faults_lock:
        held = _faults.get(target)
        if held is not None:
            for name in [n for n in held if not n.startswith(DAMAGED)]:
                del held[name]


def store_faults(target: Engine | None = None) -> dict[str, float]:
    """What the engine has met and not since seen pass, by SQLite's error name, with when it was first met."""
    with _faults_lock:
        return dict(_faults.get(target or engine, {}))


def store_fault(target: Engine | None = None) -> str | None:
    return next(iter(sorted(store_faults(target))), None)


def make_engine(url: str | None = None) -> Engine:
    target = url or settings.sqlite_url
    sqlite = target.startswith("sqlite")
    # A writer waits up to 30 s for another's transaction instead of failing at Python's default 5 s: ingesting a
    # 28,000-section contract holds the write lock for seconds (cloud rehearsal, 2026-10-12: three uploads beside it
    # failed with "database is locked").
    connect_args: dict[str, object] = {"check_same_thread": False, "timeout": 30} if sqlite else {}
    # A SQLite connection is a file handle, opened for each session rather than drawn from a fixed pool: a run holds its
    # session for its whole life, the wait for the one model included, and questions asked together held the default
    # pool's 15 connections, so every other request waited 30 s for one and failed (the same rehearsal).
    pooling: dict[str, object] = {"poolclass": NullPool} if sqlite else {}
    # An error SQLAlchemy raises prints the statement's bound values, a contract's sections and quotes among them, and a
    # failed run is logged with its exception (runs/service.py): the values stay out of the message (cloud readiness
    # review, 2026-10-12).
    engine = create_engine(target, connect_args=connect_args, future=True, hide_parameters=True, **pooling)
    if sqlite:

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            # A deleted row's bytes are overwritten, not left in free pages: the public store promises that what a
            # visitor added is gone when their workspace ends (application/retention.py; release review, 2026-10-11).
            cursor.execute("PRAGMA secure_delete=ON")
            cursor.close()

        @event.listens_for(engine, "handle_error")
        def _noted(context: ExceptionContext) -> None:
            note_store_error(context.original_exception, engine)

        @event.listens_for(engine, "commit")
        def _cleared(_connection: object) -> None:
            _committed(engine)

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def init_db(target_engine: Engine | None = None) -> None:
    from . import models  # noqa: F401  (registers the tables)

    target = target_engine or engine
    Base.metadata.create_all(target)
    ensure_columns(target)
    ensure_checks(target)
    ensure_immutability(target)


# Indexes a later model replaced; dropped so the replacement can be created. Never a data change.
SUPERSEDED_INDEXES: dict[str, tuple[str, ...]] = {"memos": ("ux_memos_run_id", "ux_memos_run_review")}


def ensure_columns(target_engine: Engine) -> None:
    """Add columns that the models gained since the file was created. Additive only; SQLite has
    no cheap way to drop or retype, and nothing here needs it."""
    if target_engine.url.get_backend_name() != "sqlite":
        return
    with target_engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            existing = {row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
            if not existing:
                continue
            for column in table.columns:
                if column.name not in existing:
                    column_type = column.type.compile(target_engine.dialect)
                    connection.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}')
            for index in table.indexes:
                connection.execute(CreateIndex(index, if_not_exists=True))
            for name in SUPERSEDED_INDEXES.get(table.name, ()):
                connection.exec_driver_sql(f'DROP INDEX IF EXISTS "{name}"')


class StoreDrift(RuntimeError):
    """The store holds rows a constraint the models declare refuses: it is not opened, and nothing in it was changed."""


def _normalised(sql: str) -> str:
    return " ".join(sql.split())


def check_bodies(table_sql: str) -> dict[str, str]:
    """Each named CHECK of a CREATE TABLE statement, by name, its body with whitespace normalised. The body is read to
    its own closing parenthesis, past any parenthesis or quote inside it."""
    checks = {}
    for match in re.finditer(r'CONSTRAINT\s+"?(\w+)"?\s+CHECK\s*\(', table_sql, re.IGNORECASE):
        depth, at, quote = 1, match.end(), ""
        while depth:
            character = table_sql[at]
            if quote:
                quote = "" if character == quote else quote  # a doubled quote closes and opens again
            elif character in "'\"":
                quote = character
            else:
                depth += {"(": 1, ")": -1}.get(character, 0)
            at += 1
        checks[match.group(1)] = _normalised(table_sql[match.end() : at - 1])
    return checks


def describe_store(connection: Any) -> dict[str, dict[str, Any]]:  # noqa: ANN401 - a SQLAlchemy or DB-API connection
    """What a store's schema says, table by table: its columns (type, NOT NULL, default, primary key), its foreign keys,
    its CHECKs by name and body, its indexes and its triggers by name and statement. One description for a store and for
    the models (a fresh store in memory), so the two can be compared whole."""
    run = connection.exec_driver_sql if hasattr(connection, "exec_driver_sql") else connection.execute
    tables = {str(name): str(sql) for name, sql in run("SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
    described: dict[str, dict[str, Any]] = {}
    for name, sql in tables.items():
        described[name] = {
            "columns": {str(c[1]): (str(c[2]).upper(), bool(c[3]), c[4], int(c[5])) for c in run(f'PRAGMA table_info("{name}")')},
            "foreign_keys": sorted((str(k[3]), str(k[2]), str(k[4]), str(k[6])) for k in run(f'PRAGMA foreign_key_list("{name}")')),
            "checks": check_bodies(sql),
            "indexes": {},
            "triggers": {},
        }
    for kind, name, table, sql in run("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE type IN ('index', 'trigger') AND sql IS NOT NULL"):
        if str(table) in described:
            described[str(table)]["indexes" if kind == "index" else "triggers"][str(name)] = _normalised(str(sql))
    return described


@functools.cache
def declared_tables() -> dict[str, str]:
    """Each table's CREATE statement as the models make it: a fresh store, built in memory."""
    from . import models  # noqa: F401  (registers the tables)

    memory = create_engine("sqlite://")
    Base.metadata.create_all(memory)
    with memory.connect() as connection:
        made = {str(name): str(sql) for name, sql in connection.exec_driver_sql("SELECT name, sql FROM sqlite_master WHERE type = 'table'")}
    memory.dispose()
    return made


def ensure_checks(target_engine: Engine) -> None:
    """A table whose CHECKs differ from the models', by name or by body, is rebuilt with the models' statement.

    SQLite cannot add or change a CHECK in place, and init_db only added columns: stores created by release-2026-10-02
    and before never gained ck_findings_status_source, and accepted every pair a fresh store refuses. A vocabulary
    widened under the same name would have been worse: the old store would refuse the new build's legitimate rows, in
    production only (stress test, 2026-10-30, store evolution 4). Comparing bodies covers added, widened and narrowed.
    A store that matches is only read (sqlite_master), never written."""
    if target_engine.url.get_backend_name() != "sqlite":
        return
    with target_engine.connect() as connection:
        stored = {str(name): str(sql) for name, sql in connection.exec_driver_sql("SELECT name, sql FROM sqlite_master WHERE type = 'table'")}
    for table, declared in declared_tables().items():
        if table in stored and check_bodies(stored[table]) != check_bodies(declared):
            _rebuild(target_engine, table, declared)


def _rebuild(target_engine: Engine, table: str, declared: str) -> None:
    """SQLite's documented procedure for a change ALTER TABLE cannot make (sqlite.org/lang_altertable.html, "Making
    Other Kinds Of Table Schema Changes"), in one transaction on one connection, with the two steps whose absence the
    stress test's skeptic reproduced:

    - foreign keys off before the transaction begins (inside one the PRAGMA does nothing, and make_engine turns them
      on): with them on, DROP TABLE findings deleted every evidence span and review by cascade, and foreign_key_check
      saw nothing wrong;
    - every trigger dropped first and put back after: another table's trigger names this one, and RENAME failed on it.

    Every row is checked against the models' CHECKs before anything changes, and the store is refused, its ids named,
    if any fails. No backup file is written beside the store: the transaction is all or nothing, and a copy of the
    public store would keep visitors' contracts past their retention (application/retention.py)."""
    raw = target_engine.raw_connection()
    connection = raw.driver_connection
    assert isinstance(connection, sqlite3.Connection)
    rebuilt = f"{table}__rebuilt"
    manual = connection.isolation_level
    connection.isolation_level = None  # the transaction below is begun and ended here, and nowhere else
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        try:
            stored_columns = [str(c[1]) for c in connection.execute(f'PRAGMA table_info("{table}")')]
            key = next((str(c[1]) for c in connection.execute(f'PRAGMA table_info("{table}")') if c[5] == 1), "rowid")
            refused = []
            for name, body in check_bodies(declared).items():
                ids = [str(row[0]) for row in connection.execute(f'SELECT "{key}" FROM "{table}" WHERE NOT ({body}) LIMIT 20')]
                if ids:
                    refused.append(f"{name} refuses {table} {', '.join(ids)}")
            dropped = [c for c in stored_columns if c not in Base.metadata.tables[table].columns]
            if dropped:
                refused.append(f"{table} holds column(s) the models no longer declare, which the rebuild would lose: {', '.join(dropped)}")
            if refused:
                raise StoreDrift(
                    f"The store's {table} table cannot take the models' constraints, so it was not opened and nothing was changed: {'; '.join(refused)}"
                )
            tables = [str(r[0]) for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
            before = {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tables}
            triggers = [(str(n), str(s)) for n, s in connection.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'")]
            indexes = [
                str(s) for (s,) in connection.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL", (table,))
            ]
            for name, _statement in triggers:
                connection.execute(f'DROP TRIGGER "{name}"')
            connection.execute(re.sub(rf'^CREATE TABLE\s+"?{table}"?(?=\s*\()', f'CREATE TABLE "{rebuilt}"', declared, count=1))
            columns = ", ".join(f'"{c}"' for c in stored_columns)
            connection.execute(f'INSERT INTO "{rebuilt}" ({columns}) SELECT {columns} FROM "{table}"')
            connection.execute(f'DROP TABLE "{table}"')
            connection.execute(f'ALTER TABLE "{rebuilt}" RENAME TO "{table}"')
            for statement in indexes:
                connection.execute(statement)
            for _name, statement in triggers:
                connection.execute(statement)
            after = {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tables}
            dangling = connection.execute("PRAGMA foreign_key_check").fetchall()
            if after != before or dangling:
                raise RuntimeError(
                    f"rebuilding {table} would change the store (rows {before} then {after}; {len(dangling)} dangling reference(s)): rolled back"
                )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        log.warning("rebuilt table %s with the models' constraints (%d rows)", table, before[table])
    finally:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.isolation_level = manual
        raw.close()


def immutability_triggers() -> list[tuple[str, str]]:
    """The triggers that make a finished run, its stages, its findings and their spans, and the text and document they
    read, refuse UPDATE and DELETE: (name, CREATE statement). The one definition, used to create them and by the public
    store's retention to put them back exactly as they were (application/retention.py)."""
    from .models import TERMINAL_STAGES

    finished = "(" + ", ".join(repr(stage) for stage in TERMINAL_STAGES) + ")"
    run_of_row = {
        "runs": "OLD.stage",
        "run_stages": "(SELECT stage FROM runs WHERE id = OLD.run_id)",
        "findings": "(SELECT stage FROM runs WHERE id = OLD.run_id)",
        "evidence_spans": "(SELECT r.stage FROM runs r JOIN findings f ON f.run_id = r.id WHERE f.id = OLD.finding_id)",
    }
    # A finished run's citations point into stored section text; that text and its document cannot change either.
    read_by_finished_run = {
        "sections": f"EXISTS (SELECT 1 FROM runs WHERE runs.document_id = OLD.document_id AND runs.stage IN {finished})",
        "documents": f"EXISTS (SELECT 1 FROM runs WHERE runs.document_id = OLD.id AND runs.stage IN {finished})",
    }
    conditions = {table: f"{stage_of} IN {finished}" for table, stage_of in run_of_row.items()} | read_by_finished_run
    triggers = []
    for table, condition in conditions.items():
        for action in ("UPDATE", "DELETE"):
            name = f"trg_{table}_no_{action.lower()}_when_finished"
            statement = (
                f"CREATE TRIGGER IF NOT EXISTS {name} "
                f"BEFORE {action} ON {table} WHEN {condition} "
                f"BEGIN SELECT RAISE(ABORT, 'a finished run is immutable ({table})'); END"
            )
            triggers.append((name, statement))
    return triggers


# A workspace an anonymous visit made: application/workspace.PUBLIC_PREFIX, which this bottom layer cannot import.
PUBLIC_WORKSPACE_LIKE = "pw-%"
WORKSPACE_NOT_OPEN = "a public workspace that is not open takes no row"


def refused_as_not_open(error: BaseException) -> bool:
    """The store's own refusal of a row for a public workspace that is not listed (workspace_guards)."""
    return WORKSPACE_NOT_OPEN in str(getattr(error, "orig", error))


def workspace_tables() -> list[str]:
    """Every table whose rows a workspace adds, read off the models (a workspace_id column), the registry of visitor
    workspaces itself apart: a table added later is in it without anyone remembering."""
    from . import models  # noqa: F401  (registers the tables)

    return sorted(t.name for t in Base.metadata.sorted_tables if "workspace_id" in t.columns and t.name != "visitor_workspaces")


def workspace_guards() -> list[tuple[str, str]]:
    """The triggers that refuse a row for a public workspace that is not listed in visitor_workspaces: (name, CREATE
    statement). A request let in before the purge cannot write after it (quotas.workspace_open says so for the rows
    written through quotas.admit); here the store says it for every row, whatever wrote it. A version statement written
    outside admit outlived its workspace's purge and kept two visitors' contracts for good (stress test, 2026-10-30).
    Listed is enough: a row written after the workspace ended, before its purge, is deleted with it by workspace id."""
    guards = []
    for table in workspace_tables():
        name = f"trg_{table}_only_open_workspaces"
        statement = (
            f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE INSERT ON {table} "
            f"WHEN NEW.workspace_id LIKE '{PUBLIC_WORKSPACE_LIKE}' "
            "AND NOT EXISTS (SELECT 1 FROM visitor_workspaces WHERE workspace_id = NEW.workspace_id) "
            f"BEGIN SELECT RAISE(ABORT, '{WORKSPACE_NOT_OPEN} ({table})'); END"
        )
        guards.append((name, statement))
    return guards


def ensure_immutability(target_engine: Engine) -> None:
    """A finished run, its stages, its findings and their spans cannot be updated or deleted: the
    database refuses, not just the code. Reviews and memos are separate rows, so adjudicating a
    finding or writing a memo never touches the record it is about. A public workspace that is not
    listed takes no row (workspace_guards). SQLite only; Postgres would carry the same rules as
    trigger functions."""
    if target_engine.url.get_backend_name() != "sqlite":
        return
    with target_engine.begin() as connection:
        for _name, statement in [*immutability_triggers(), *workspace_guards()]:
            connection.exec_driver_sql(statement)


@contextmanager
def write_locked(session: Session) -> Iterator[None]:
    """The session's next transaction, begun with SQLite's write lock (BEGIN IMMEDIATE) instead of at its first write: no
    other writer, in this process or another, can write between what is read inside it and its commit, so a count read
    here is still the count when the row it limits is committed. Commits on leaving; rolls back on any exception.

    Other writers wait for the lock (the 30 s busy wait, make_engine); readers do not (WAL). A lock not had by then is
    Busy, 503, with nothing written: it was an unhandled OperationalError, a 500 (war room W5 p6). Hold it briefly: read
    and parse before it, never inside. It must begin the transaction: a write already made in this session was made
    without the lock, so it is refused rather than silently included."""
    connection = session.connection()
    if connection.dialect.name != "sqlite":
        raise NotImplementedError("write_locked takes SQLite's write lock; another database needs its own (a table or advisory lock)")
    if getattr(connection.connection.driver_connection, "in_transaction", False):
        raise RuntimeError("write_locked must begin the transaction; this session has an uncommitted write")
    try:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    except OperationalError as error:
        session.rollback()
        if "locked" not in str(error.orig):
            raise
        raise Busy("The store is busy with another change, so nothing was written. Try again in a moment.", retry_after=5) from error
    try:
        yield
        session.commit()
    except BaseException:
        session.rollback()
        raise


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
