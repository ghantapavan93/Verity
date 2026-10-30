"""SQLite through SQLAlchemy 2. One file, one process; enough for the first slice and honest
about it: a second datastore is added when a measurement needs one."""

from __future__ import annotations

import threading
import time
import weakref
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import ExceptionContext
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, NullPool
from sqlalchemy.schema import CreateIndex

from .config import settings
from .errors import Busy


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
    ensure_immutability(target)


# Indexes a later model replaced; dropped so the replacement can be created. Never a data change.
SUPERSEDED_INDEXES: dict[str, tuple[str, ...]] = {"memos": ("ux_memos_run_id",)}


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
