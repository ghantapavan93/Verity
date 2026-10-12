"""The store under a burst of visitors: a request never waits on a connection pool, and a writer waits out another's long
write instead of failing.

Found by the cloud rehearsal (2026-10-12, nine visitors at once against the containerized stack): a run holds its session
for its whole life, the wait for the one model included (api/runs.py), so questions asked together held SQLAlchemy's
default pool of 5 + 10 connections; every other request then waited 30 s for one and failed, a run among them. And
ingesting a 28,000-section contract writes its sections in one transaction, for seconds; three uploads beside it failed
with "database is locked" after Python's default 5 s.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from sqlalchemy import text

from app import db as db_module


def test_connections_held_by_long_runs_never_starve_another_request(tmp_path: Path) -> None:
    engine = db_module.make_engine(f"sqlite:///{(tmp_path / 'pool.db').as_posix()}")
    held = []
    for _ in range(15):  # what SQLAlchemy's default pool holds at most
        connection = engine.connect()
        connection.execute(text("SELECT 1"))
        held.append(connection)
    answered: dict[str, int] = {}

    def one_more() -> None:
        with engine.connect() as connection:
            answered["value"] = int(connection.execute(text("SELECT 1")).scalar_one())

    thread = threading.Thread(target=one_more, daemon=True)
    thread.start()
    thread.join(timeout=3)
    got = answered.get("value")  # read before the held connections go back, which would free a pool for the thread
    for connection in held:
        connection.close()
    assert got == 1, "a sixteenth request waited for a pooled connection"


def test_a_writer_waits_for_a_long_write_instead_of_failing(tmp_path: Path) -> None:
    path = tmp_path / "busy.db"
    engine = db_module.make_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE notes (body TEXT)"))
    holder = sqlite3.connect(path, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO notes VALUES ('a long ingest')")
    outcome: dict[str, str] = {}

    def write() -> None:
        try:
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO notes VALUES ('another upload')"))
            outcome["result"] = "written"
        except Exception as error:  # noqa: BLE001 (the test reports whatever ended the write)
            outcome["result"] = f"{type(error).__name__}: {error}"

    thread = threading.Thread(target=write, daemon=True)
    thread.start()
    time.sleep(6)  # past Python's default 5 s busy timeout
    holder.execute("COMMIT")
    holder.close()
    thread.join(timeout=10)
    assert outcome.get("result") == "written"
