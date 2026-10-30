"""A retention pass holds the store's write lock for a bounded time, whatever expires in it (stress test, 2026-10-30,
ops 5).

One pass deleted every expired workspace, document and section in one transaction under the write lock: 4.8 s for
114 MB, 13 s for 342 MB, 130 s for 1.8 GB, and past the 30 s busy wait every other writer failed: uploads 503, new
visits 500, and run stage writes, whose runs then stuck. A pass now deletes a workspace in transactions each bounded by a
unit the store already bounds (its runs; one document, whole; its registration last) with a pause after each, and a pass
stopped part way is finished by the next.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app import db as db_module
from app.application import retention
from app.application.retention import purge_expired_workspaces
from app.db import SessionLocal
from app.models import Document, Run, VisitorWorkspace
from tests.test_quota_admission import _ask, _new_bytes, _new_visitor, windows_lifted
from tests.test_retention import end, triggers

pytestmark = pytest.mark.usefixtures(windows_lifted.__name__)


def _visitors_with_documents(public: TestClient, visitors: int, documents: int) -> list[str]:
    workspaces = []
    for _ in range(visitors):
        visitor = _new_visitor(public)
        ids = []
        for _ in range(documents):
            uploaded = visitor.post("/api/documents", files={"file": ("contract.txt", _new_bytes(), "text/plain")})
            assert uploaded.status_code == 201, uploaded.text
            ids.append(uploaded.json()["id"])
        assert _ask(visitor, ids[0], "What notice applies?") == 202
        workspaces.append(end(visitor))
    return workspaces


@contextmanager
def transactions_seen() -> Iterator[list[list[str]]]:
    """The statements of each transaction the purge's thread begins under the write lock."""
    seen: list[list[str]] = []
    purging = threading.current_thread()

    def note(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:  # noqa: ANN401
        if threading.current_thread() is not purging:
            return
        if statement.startswith("BEGIN IMMEDIATE"):
            seen.append([])
        elif seen:
            seen[-1].append(" ".join(statement.split()))

    event.listen(db_module.engine, "before_cursor_execute", note)
    try:
        yield seen
    finally:
        event.remove(db_module.engine, "before_cursor_execute", note)


def test_no_transaction_of_a_pass_deletes_more_than_one_document_or_one_workspace_s_runs(public: TestClient) -> None:
    workspaces = _visitors_with_documents(public, visitors=2, documents=3)
    with transactions_seen() as seen:
        report = purge_expired_workspaces(db_module.engine, gap_s=0.0)
    assert sorted(report.workspaces) == sorted(workspaces) and report.documents == 6
    assert max(sum(s.startswith("DELETE FROM documents") for s in statements) for statements in seen) == 1
    assert max(sum(s.startswith("DELETE FROM runs") for s in statements) for statements in seen) == 1
    assert len(seen) >= 2 * (1 + 3 + 1), "a transaction for the runs, one per document, one for the registration"


def test_a_writer_gets_the_lock_between_a_pass_s_transactions(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Each document's deletion is made slow, as a large one is: a writer that waits at most a second, arriving at any
    # moment of the pass, still gets the lock. In one transaction it waited for the whole pass.
    _visitors_with_documents(public, visitors=1, documents=4)
    database = str(db_module.engine.url.database)
    slow = threading.Event()

    def slow_delete(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:  # noqa: ANN401
        if statement.startswith("DELETE FROM documents"):
            slow.set()
            time.sleep(0.4)

    event.listen(db_module.engine, "before_cursor_execute", slow_delete)
    failures: list[str] = []
    purge = threading.Thread(target=lambda: purge_expired_workspaces(db_module.engine))
    purge.start()
    try:
        assert slow.wait(30)
        while purge.is_alive():
            writer = sqlite3.connect(database, timeout=1.0, isolation_level=None)
            try:
                writer.execute("BEGIN IMMEDIATE")
                writer.execute("COMMIT")
            except sqlite3.OperationalError as error:
                failures.append(str(error))
            finally:
                writer.close()
            time.sleep(0.05)
    finally:
        purge.join(60)
        event.remove(db_module.engine, "before_cursor_execute", slow_delete)
    assert failures == []


def test_a_pass_stopped_part_way_keeps_what_it_did_and_the_next_finishes(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    (workspace,) = _visitors_with_documents(public, visitors=1, documents=3)
    before = triggers()
    real = retention._unlink_original_if_unused
    calls = [0]

    def fails_on_the_second(connection: Any, sha256: str, media_type: str) -> int:  # noqa: ANN401
        calls[0] += 1
        if calls[0] == 2:
            raise RuntimeError("the disk filled up")
        return int(real(connection, sha256, media_type))

    monkeypatch.setattr(retention, "_unlink_original_if_unused", fails_on_the_second)
    with pytest.raises(RuntimeError, match="disk filled"):
        purge_expired_workspaces(db_module.engine, gap_s=0.0)
    assert triggers() == before, "the triggers are there after a failure part way"
    with SessionLocal() as session:
        assert session.query(Run).filter_by(workspace_id=workspace).count() == 0, "its runs went in their own transaction"
        assert session.query(Document).count() == 2, "the first document went; the one that failed is still whole"
        assert session.get(VisitorWorkspace, workspace) is not None, "still registered: the next pass finds it"
    monkeypatch.setattr(retention, "_unlink_original_if_unused", real)
    assert purge_expired_workspaces(db_module.engine, gap_s=0.0).workspaces == [workspace]
    with db_module.engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM documents")).scalar() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM visitor_workspaces")).scalar() == 0
