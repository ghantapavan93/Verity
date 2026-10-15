"""The primitive under every quota (application/quotas.admit over db.write_locked), without HTTP: a count and the write it
limits share one transaction no concurrent writer can interleave. War room F-13 / R10 (2026-10-13); the requests that
use it are tested in test_quota_admission.py."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.application.quotas import Quota, admit
from app.db import make_engine, write_locked
from app.errors import TooManyRequests

CAP = 3


@pytest.fixture
def store(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine: Engine = make_engine(f"sqlite:///{(tmp_path / 'lock.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE rows (trial INTEGER, writer INTEGER)"))
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _rows(session: Session, trial: int) -> int:
    return int(session.execute(text("SELECT COUNT(*) FROM rows WHERE trial = :t"), {"t": trial}).scalar_one())


def _quota(trial: int, pause_s: float = 0.0) -> Quota:
    def count(session: Session) -> int:
        counted = _rows(session, trial)
        time.sleep(pause_s)  # a reader that took its time between the count and the write: the window the race needs
        return counted

    return Quota(CAP, count, lambda: TooManyRequests("full", retry_after=60))


def _write(session: Session, trial: int, writer: int) -> int:
    session.execute(text("INSERT INTO rows VALUES (:t, :w)"), {"t": trial, "w": writer})
    return writer


def _released_together(store: sessionmaker[Session], trial: int, writers: int) -> list[str]:
    """Each writer on its own thread and session, all released at once; what happened to each, sorted."""
    go = threading.Barrier(writers)
    outcomes: list[str] = []
    guard = threading.Lock()

    def writer(index: int) -> None:
        go.wait()
        with store() as session:
            try:
                admit(session, [_quota(trial, 0.005)], partial(_write, session, trial, index))
                outcome = "written"
            except TooManyRequests:
                outcome = "refused"
            except Exception as error:  # noqa: BLE001 - a failure is an outcome the assertion refuses
                outcome = f"{type(error).__name__}: {error}"
        with guard:
            outcomes.append(outcome)

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(outcomes)


def test_property_writers_released_together_never_pass_the_quota(store: sessionmaker[Session]) -> None:
    """Twelve writers released together, ten times: exactly CAP rows each time, every other writer refused, none failed."""
    for trial in range(10):
        outcomes = _released_together(store, trial, 12)
        with store() as session:
            assert outcomes == ["refused"] * 9 + ["written"] * CAP and _rows(session, trial) == CAP, (trial, outcomes)


def test_control_one_writer_at_a_time_writes_exactly_the_quota(store: sessionmaker[Session]) -> None:
    outcomes = []
    for index in range(5):
        with store() as session:
            try:
                admit(session, [_quota(0)], partial(_write, session, 0, index))
                outcomes.append("written")
            except TooManyRequests:
                outcomes.append("refused")
    assert outcomes == ["written"] * CAP + ["refused"] * 2


def test_a_row_already_there_is_handed_back_and_spends_nothing(store: sessionmaker[Session]) -> None:
    with store() as session:
        for index in range(CAP):
            admit(session, [_quota(0)], partial(_write, session, 0, index))
        found, created = admit(session, [_quota(0)], lambda: _write(session, 0, 99), find=lambda: 1)
        assert (found, created) == (1, False) and _rows(session, 0) == CAP


def test_a_refusal_writes_nothing_and_lets_the_next_writer_in_at_once(store: sessionmaker[Session]) -> None:
    with store() as session:
        for index in range(CAP):
            admit(session, [_quota(0)], partial(_write, session, 0, index))
        with pytest.raises(TooManyRequests):
            admit(session, [_quota(0)], lambda: _write(session, 0, 99))
    began = time.perf_counter()
    with store() as other:
        admit(other, [_quota(1)], lambda: _write(other, 1, 0))
        assert _rows(other, 0) == CAP and _rows(other, 1) == 1
    assert time.perf_counter() - began < 1.0, "the refused writer still held the lock"


def test_the_lock_must_begin_the_transaction(store: sessionmaker[Session]) -> None:
    """A write already made in the session was made without the lock: it is refused rather than silently included."""
    with store() as session:
        _write(session, 0, 0)
        with pytest.raises(RuntimeError, match="must begin the transaction"), write_locked(session):
            pass
        session.rollback()
        with write_locked(session):  # control: a session that has only read takes the lock
            _write(session, 0, 1)
        assert _rows(session, 0) == 1


def test_a_write_lock_not_had_within_the_wait_is_busy_and_writes_nothing(tmp_path: Path) -> None:
    """War room W5 p6: past SQLite's busy wait the write answered an unhandled OperationalError, a 500. It is Busy, 503,
    with nothing written."""
    import sqlite3

    from sqlalchemy import create_engine

    from app.errors import Busy

    path = tmp_path / "busy.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"timeout": 0.2})
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE rows (trial INTEGER, writer INTEGER)"))
    holder = sqlite3.connect(path, timeout=0.2)
    holder.execute("BEGIN IMMEDIATE")
    try:
        with Session(engine) as session, pytest.raises(Busy), write_locked(session):
            _write(session, 0, 1)
    finally:
        holder.rollback()
        holder.close()
    with Session(engine) as session:
        assert _rows(session, 0) == 0
    engine.dispose()
