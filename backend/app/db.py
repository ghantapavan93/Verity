"""SQLite through SQLAlchemy 2. One file, one process; enough for the first slice and honest
about it: a second datastore is added when a measurement needs one."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry
from sqlalchemy.schema import CreateIndex

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None) -> Engine:
    target = url or settings.sqlite_url
    connect_args = {"check_same_thread": False} if target.startswith("sqlite") else {}
    engine = create_engine(target, connect_args=connect_args, future=True)
    if target.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

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


def ensure_immutability(target_engine: Engine) -> None:
    """A finished run, its stages, its findings and their spans cannot be updated or deleted: the
    database refuses, not just the code. Reviews and memos are separate rows, so adjudicating a
    finding or writing a memo never touches the record it is about. SQLite only; Postgres would
    carry the same rule as a trigger function."""
    if target_engine.url.get_backend_name() != "sqlite":
        return
    with target_engine.begin() as connection:
        for _name, statement in immutability_triggers():
            connection.exec_driver_sql(statement)


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
