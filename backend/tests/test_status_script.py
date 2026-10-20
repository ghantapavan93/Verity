"""The operator's one look (scripts/status.py) says what is wrong without changing anything (ops audit, 2026-10-19).

It reads the store with SQLite's mode=ro and reads each supervisor log once from its end: an operator's reader that held
api.supervisor.log ended the supervisor on 2026-10-11. Each test asks it a question an operator would, with a control.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal
from tests.test_run_endings import _run_in_flight

BACKEND = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("status_script", BACKEND / "scripts" / "status.py")
assert spec is not None and spec.loader is not None
status = importlib.util.module_from_spec(spec)
sys.modules["status_script"] = status
spec.loader.exec_module(status)


def test_a_run_that_has_not_moved_for_a_quarter_of_an_hour_is_a_problem(client: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_id = _run_in_flight(client, "Is there an arbitration clause?")
    with SessionLocal() as session:
        session.execute(text("UPDATE runs SET created_at = datetime('now', '-20 minutes') WHERE id = :id"), {"id": run_id})
        session.commit()
    assert status.check_runs(tmp_path / "test.db") is False
    assert "1 open, oldest without progress 20 min; 1 without progress for over 15 min" in capsys.readouterr().out


def test_control_a_run_that_just_started_is_not(client: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run_in_flight(client, "Is there an arbitration clause?")
    assert status.check_runs(tmp_path / "test.db") is True
    assert "1 open, oldest without progress 0 min" in capsys.readouterr().out


def test_the_store_is_opened_read_only(client: TestClient, tmp_path: Path) -> None:
    _run_in_flight(client, "Is there an arbitration clause?")
    before = (tmp_path / "test.db").stat().st_mtime_ns
    status.check_runs(tmp_path / "test.db")
    assert (tmp_path / "test.db").stat().st_mtime_ns == before


def test_a_supervisor_log_is_read_once_and_let_go(tmp_path: Path) -> None:
    log = tmp_path / "api.supervisor.log"
    log.write_text("2026-10-19T20:00:00 started api pid 1\n2026-10-19T20:05:00 api pid 1 did not answer (1 of 3)\n\n", encoding="utf-8-sig")
    assert status.last_line(log) == "2026-10-19T20:05:00 api pid 1 did not answer (1 of 3)"
    log.rename(tmp_path / "moved.log")  # Windows refuses to rename a file another handle still holds


def test_a_supervisor_that_stopped_is_a_problem(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "api.supervisor.log").write_text("2026-10-19T20:00:00 stop file present; supervisor exiting\n", encoding="utf-8")
    (tmp_path / "web.supervisor.log").write_text("2026-10-19T20:00:00 started web pid 2 (output web.x.out.log)\n", encoding="utf-8")
    assert status.check_supervisor(tmp_path, "api") is False
    assert status.check_supervisor(tmp_path, "web") is True  # control: one that is running
    assert "supervisor exiting" in capsys.readouterr().out
