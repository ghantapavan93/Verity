"""Health and status.py see a store that fails, not only one the file system refuses (stress test, 2026-10-30, ops 3).

Both looked only at the file system (a missing folder, the read-only attribute, free space): with a damaged page,
health said ok and status.py said ok while every read of that table answered 500 and a new upload wrote into the damaged
file. Health now also reports what the engine met: a damaged file (SQLITE_CORRUPT, NOTADB) until the process starts
again, since a later commit succeeds on a damaged file while the damage stays; an I/O, read-only, full or unopenable
store until its next successful commit. Contention is not a fault: a lost race for the write lock leaves health ok.
status.py runs PRAGMA quick_check, which reads every table.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import db as db_module

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import status


def _failed(name: str) -> sqlite3.Error:
    error = sqlite3.DatabaseError(f"{name.lower()} as the engine met it")
    error.sqlite_errorname = name  # type: ignore[attr-defined]
    return error


@pytest.mark.parametrize("name", ["SQLITE_CORRUPT", "SQLITE_NOTADB", "SQLITE_IOERR_WRITE", "SQLITE_READONLY", "SQLITE_FULL", "SQLITE_CANTOPEN"])
def test_a_store_the_engine_failed_on_is_reported_as_the_store_s_fault(client: TestClient, name: str) -> None:
    db_module.note_store_error(_failed(name))
    body = client.get("/api/health").json()
    assert (body["ok"], body["fault"]) == (False, "store")


@pytest.mark.parametrize("name", ["SQLITE_IOERR_WRITE", "SQLITE_READONLY", "SQLITE_FULL", "SQLITE_CANTOPEN"])
def test_a_passing_fault_clears_at_the_next_successful_commit(client: TestClient, name: str) -> None:
    db_module.note_store_error(_failed(name))
    with db_module.engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS scratch (x INTEGER)"))
    assert client.get("/api/health").json()["fault"] == ""


def test_a_damaged_file_stays_reported_whatever_commits_after_it(client: TestClient) -> None:
    # A commit elsewhere in a damaged file succeeds while the damaged page keeps failing (the skeptic's probe).
    db_module.note_store_error(_failed("SQLITE_CORRUPT"))
    with db_module.engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS scratch (x INTEGER)"))
    assert client.get("/api/health").json()["fault"] == "store"


def test_control_contention_is_not_a_fault(client: TestClient) -> None:
    db_module.note_store_error(_failed("SQLITE_BUSY"))
    db_module.note_store_error(sqlite3.OperationalError("database is locked"))
    body = client.get("/api/health").json()
    assert (body["ok"], body["fault"]) == (True, "")


def test_the_engine_reports_what_it_met(client: TestClient, tmp_path: Path) -> None:
    # Through a real engine: a statement the file refuses (opened read-only underneath) is noted by the listener.
    database = tmp_path / "readonly.db"
    sqlite3.connect(database).execute("CREATE TABLE t (x INTEGER)").connection.close()
    engine = db_module.make_engine(f"sqlite:///file:{database.as_posix()}?mode=ro&uri=true")
    with pytest.raises(OperationalError, match="readonly"), engine.begin() as connection:
        connection.execute(text("INSERT INTO t VALUES (1)"))
    assert "SQLITE_READONLY" in db_module.store_faults(engine)
    assert db_module.store_fault() is None, "kept per engine: the store the process serves is not that one"


def _damaged_copy(tmp_path: Path) -> Path:
    database = tmp_path / "workbench.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE sections (id INTEGER PRIMARY KEY, text TEXT)")
    connection.executemany("INSERT INTO sections (text) VALUES (?)", [("clause " * 50,) for _ in range(2000)])
    connection.commit()
    connection.close()
    data = bytearray(database.read_bytes())
    page = 4096
    for offset in range(page * 5 + 100, page * 5 + 2100):  # inside a leaf page of the table, past the schema
        data[offset] = (offset * 7919) % 251
    database.write_bytes(bytes(data))
    return database


def test_status_prints_a_problem_for_a_store_that_fails_its_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean = tmp_path / "clean"
    clean.mkdir()
    connection = sqlite3.connect(clean / "workbench.db")
    connection.execute("CREATE TABLE t (x INTEGER)")
    connection.commit()
    connection.close()
    assert status.check_store(clean / "workbench.db") is True  # control
    damaged = tmp_path / "damaged"
    damaged.mkdir()
    assert status.check_store(_damaged_copy(damaged)) is False
    assert "PROBLEM" in capsys.readouterr().out
