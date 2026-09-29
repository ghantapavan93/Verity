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


def ensure_immutability(target_engine: Engine) -> None:
    """A finished run, its stages, its findings and their spans cannot be updated or deleted: the
    database refuses, not just the code. Reviews and memos are separate rows, so adjudicating a
    finding or writing a memo never touches the record it is about. SQLite only; Postgres would
    carry the same rule as a trigger function."""
    if target_engine.url.get_backend_name() != "sqlite":
        return
    from .models import TERMINAL_STAGES

    finished = "(" + ", ".join(repr(stage) for stage in TERMINAL_STAGES) + ")"
    run_of_row = {
        "runs": "OLD.stage",
        "run_stages": "(SELECT stage FROM runs WHERE id = OLD.run_id)",
        "findings": "(SELECT stage FROM runs WHERE id = OLD.run_id)",
        "evidence_spans": "(SELECT r.stage FROM runs r JOIN findings f ON f.run_id = r.id WHERE f.id = OLD.finding_id)",
    }
    with target_engine.begin() as connection:
        for table, stage_of in run_of_row.items():
            for action in ("UPDATE", "DELETE"):
                connection.exec_driver_sql(
                    f"CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{action.lower()}_when_finished "
                    f"BEFORE {action} ON {table} WHEN {stage_of} IN {finished} "
                    f"BEGIN SELECT RAISE(ABORT, 'a finished run is immutable ({table})'); END"
                )


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
