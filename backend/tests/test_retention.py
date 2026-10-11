"""The public store deletes a visitor's workspace once it has ended, and nothing else (application/retention.py).

The one place a finished run is ever deleted. What is held to: only registered, ended visitor workspaces go; a
workspace still running a question waits; identical bytes another visitor holds stay theirs; the immutability triggers
come back exactly as they were and still refuse; files go only when nothing names them; the owner's and the curated
record are never candidates; an ended session opens nothing and a new visit gets a new workspace.
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import config
from app import db as db_module
from app.api.access import workspace_for
from app.application.retention import purge_expired_workspaces, sweep_orphaned_files
from app.application.start_run import start_run
from app.db import SessionLocal
from app.models import Document, DocumentAccess, Memo, Run, VisitorWorkspace, utcnow
from tests.support import CONTRACT
from tests.test_anonymous import Visitor, arrive, public  # noqa: F401  (the fixture)
from tests.test_workspaces import QUESTION, Reviewer, make_curated, work


def end(visitor: Visitor) -> str:
    """Move a visitor's workspace past its end, as seven days would."""
    workspace = workspace_for(visitor.subject)
    with SessionLocal() as session:
        row = session.get(VisitorWorkspace, workspace)
        assert row is not None
        row.expires_at = utcnow() - timedelta(minutes=1)
        session.commit()
    return workspace


def triggers() -> dict[str, str]:
    with db_module.engine.connect() as connection:
        return {str(r[0]): str(r[1]) for r in connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"))}


def test_an_ended_workspace_goes_with_everything_it_held(public: TestClient) -> None:  # noqa: F811
    a, _ = arrive(public)
    ids = work(cast(Reviewer, a))
    with SessionLocal() as session:
        document = session.get(Document, ids["document"])
        memo = session.get(Memo, ids["memo"])
        assert document is not None and memo is not None
        original = config.settings.data_dir / "documents" / f"{document.sha256}.txt"
        memo_path = config.settings.data_dir / "memos" / Path(memo.docx_path).name
    assert original.is_file() and memo_path.is_file()
    workspace = end(a)
    report = purge_expired_workspaces(db_module.engine)
    assert report.workspaces == [workspace] and report.runs == 1 and report.documents == 1
    with SessionLocal() as session:
        assert session.query(Run).filter(Run.workspace_id == workspace).count() == 0
        assert session.query(DocumentAccess).filter(DocumentAccess.workspace_id == workspace).count() == 0
        assert session.get(Document, ids["document"]) is None and session.get(VisitorWorkspace, workspace) is None
        for table in ("findings", "evidence_spans", "finding_reviews", "memos", "run_stages", "sections", "guidance"):
            assert session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0, table
    assert not original.exists() and not memo_path.exists()
    # The ended session opens nothing, and the next visit is a new subject in a new workspace, never the old id.
    assert a.get("/api/documents").status_code == 401
    again, response = arrive(public, cookie=a.cookie)
    assert response.status_code == 200 and workspace_for(again.subject) != workspace
    assert again.get("/api/documents").json() == []


def test_bytes_another_visitor_holds_stay_theirs(public: TestClient) -> None:  # noqa: F811
    a, _ = arrive(public)
    b, _ = arrive(public, address="198.51.100.8")
    document = a.post("/api/documents", files={"file": ("a-name.txt", CONTRACT.encode(), "text/plain")}).json()
    b.post("/api/documents", files={"file": ("b-name.txt", CONTRACT.encode(), "text/plain")})
    run_b = b.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": QUESTION}).json()["id"]
    end(a)
    report = purge_expired_workspaces(db_module.engine)
    assert report.documents == 0, "B still holds the bytes"
    assert b.get(f"/api/documents/{document['id']}").json()["name"] == "b-name.txt"
    assert b.get(f"/api/runs/{run_b}").status_code == 200
    with SessionLocal() as session:
        stored = session.get(Document, document["id"])
        assert stored is not None and stored.name == "document.txt", "the shared row never carried a visitor's file name"
        assert (config.settings.data_dir / "documents" / f"{stored.sha256}.txt").is_file()


def test_the_triggers_come_back_exactly_and_still_refuse(public: TestClient) -> None:  # noqa: F811
    a, _ = arrive(public)
    b, _ = arrive(public, address="198.51.100.8")
    work(cast(Reviewer, a))
    kept = work(cast(Reviewer, b), contract=CONTRACT + "\nAnother clause.")
    before = triggers()
    assert len(before) == 12
    end(a)
    assert purge_expired_workspaces(db_module.engine).runs == 1
    assert triggers() == before, "the same triggers, byte for byte"
    with pytest.raises(IntegrityError, match="immutable"), db_module.engine.begin() as connection:
        connection.execute(text("DELETE FROM runs WHERE id = :r"), {"r": kept["run"]})


def test_a_purge_that_fails_part_way_leaves_the_triggers_and_the_rows(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """The drop, the deletes and the recreation are one transaction under the write lock: a failure after the triggers
    were dropped puts them back with everything else (python's sqlite3 does not begin a transaction before DDL)."""
    from app.application import retention

    a, _ = arrive(public)
    ids = work(cast(Reviewer, a))
    workspace = end(a)
    before = triggers()

    def broken(column: str, values: list[str]) -> tuple[str, dict[str, object]]:
        raise RuntimeError("the disk filled up")

    monkeypatch.setattr(retention, "_in", broken)
    with pytest.raises(RuntimeError, match="disk filled"):
        purge_expired_workspaces(db_module.engine)
    assert triggers() == before, "every immutability trigger is still there"
    with SessionLocal() as session:
        assert session.get(Run, ids["run"]) is not None and session.get(VisitorWorkspace, workspace) is not None


def test_a_workspace_with_a_question_in_progress_waits(public: TestClient) -> None:  # noqa: F811
    a, _ = arrive(public)
    document = a.post("/api/documents", files={"file": ("a.txt", CONTRACT.encode(), "text/plain")}).json()
    workspace = workspace_for(a.subject)
    with SessionLocal() as session:
        run = start_run(session, document["id"], None, QUESTION, public.provider, workspace=workspace).run
        assert run.stage not in ("complete", "unresolved", "failed")
    end(a)
    report = purge_expired_workspaces(db_module.engine)
    assert report.workspaces == [] and report.skipped_in_progress == [workspace]
    with SessionLocal() as session:
        assert session.get(VisitorWorkspace, workspace) is not None and session.get(Document, document["id"]) is not None


def test_the_owner_and_the_curated_record_are_never_candidates(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    curated = make_curated(public)
    # An invited reader's record, made as an owner instance makes it (a public one refuses invited readers).
    monkeypatch.setattr(config.settings, "anonymous_sessions", False)
    invited = work(Reviewer(public, "reviewer-a"))
    monkeypatch.setattr(config.settings, "anonymous_sessions", True)
    visitor, _ = arrive(public)
    work(cast(Reviewer, visitor), contract=CONTRACT + " A visitor's own clause.")
    end(visitor)
    purge_expired_workspaces(db_module.engine, now=utcnow() + timedelta(days=3650))
    with SessionLocal() as session:
        for run_id in (curated["run"], invited["run"]):
            assert session.get(Run, run_id) is not None, run_id
        for document_id in (curated["document"], invited["document"]):
            assert session.get(Document, document_id) is not None, document_id


def test_the_sweep_removes_only_old_files_no_row_names(public: TestClient) -> None:  # noqa: F811
    a, _ = arrive(public)
    a.post("/api/documents", files={"file": ("a.txt", CONTRACT.encode(), "text/plain")})
    folder = config.settings.data_dir / "documents"
    named = next(folder.glob("*.txt"))
    orphan_old, orphan_young = folder / ("f" * 64 + ".txt"), folder / ("e" * 64 + ".txt")
    for path in (orphan_old, orphan_young):
        path.write_text("left behind", encoding="utf-8")
    hours_ago = time.time() - 2 * 3600
    for path in (orphan_old, named):
        os.utime(path, (hours_ago, hours_ago))
    assert sweep_orphaned_files(db_module.engine) == 1
    assert not orphan_old.exists() and orphan_young.exists() and named.exists()


def test_the_sweep_removes_old_partial_writes_whatever_hash_they_carry(public: TestClient) -> None:  # noqa: F811
    """A crash between writing an upload's partial file and renaming it leaves visitor bytes no row will ever name:
    past the grace no upload is still writing them, so they go too (an audit finding, 2026-10-09)."""
    a, _ = arrive(public)
    a.post("/api/documents", files={"file": ("a.txt", CONTRACT.encode(), "text/plain")})
    folder = config.settings.data_dir / "documents"
    named = next(folder.glob("*.txt"))
    old_of_named, old_orphan, young = (
        folder / f"{named.name}.0a1b2c3d.part",
        folder / ("d" * 64 + ".txt.11111111.part"),
        folder / f"{named.name}.22222222.part",
    )
    for path in (old_of_named, old_orphan, young):
        path.write_text("a visitor's partial bytes", encoding="utf-8")
    hours_ago = time.time() - 2 * 3600
    for path in (old_of_named, old_orphan, named):
        os.utime(path, (hours_ago, hours_ago))
    assert sweep_orphaned_files(db_module.engine) == 2
    assert not old_of_named.exists() and not old_orphan.exists()
    assert young.exists() and named.exists(), "control: a write in progress and a named file stay"


def test_the_corpus_tools_are_not_a_visitors(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    visitor, _ = arrive(public)
    for path in ("/api/engineering/goldens", "/api/engineering/families", "/api/batches"):
        assert visitor.get(path).status_code == 404, path
    monkeypatch.setattr(config.settings, "anonymous_sessions", False)  # an owner instance, where invited readers work
    invited = Reviewer(public, "reviewer-a")
    assert invited.get("/api/batches").status_code == 200, "control: an invited reader still has them"


def test_a_public_run_never_touches_the_owner_store(public: TestClient) -> None:  # noqa: F811
    owner = config.BACKEND_DIR / "data"
    snapshot = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in owner.rglob("*") if p.is_file()} if owner.exists() else {}
    assert config.settings.data_dir != owner
    visitor, _ = arrive(public)
    work(cast(Reviewer, visitor))
    end(visitor)
    purge_expired_workspaces(db_module.engine)
    sweep_orphaned_files(db_module.engine)
    after = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in owner.rglob("*") if p.is_file()} if owner.exists() else {}
    assert after == snapshot


def test_the_public_process_refuses_a_store_with_owner_records(public: TestClient) -> None:  # noqa: F811
    """Pointing the public API at the owner's store (curated or invited records in it) stops it at start."""
    make_curated(public)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="Refusing to start"), TestClient(create_app(provider=public.provider)):
        pass


def test_an_ended_workspaces_text_does_not_survive_in_the_store_files(public: TestClient) -> None:  # noqa: F811
    # Release trust review, 2026-10-11: SQLite leaves a deleted row's bytes in the database file's free pages, and in the
    # write-ahead log, until something overwrites them. The rows went; the contract's text could stay on disk
    # indefinitely, which is not what "deleted 7 days after your first visit" says.
    marker = "Clause 99. The Licensee shall paint every warehouse vermilion quokka-7f3a."
    a, _ = arrive(public)
    b, _ = arrive(public, address="198.51.100.9")
    work(cast(Reviewer, a), contract=CONTRACT + "\n\n" + marker + "\n")
    # Control: a visitor whose workspace has not ended keeps every byte of theirs.
    kept = b.post("/api/documents", files={"file": ("b.txt", (CONTRACT + "\n\nClause 98. Wombat-c41d stays.\n").encode(), "text/plain")})
    assert kept.status_code in (200, 201), kept.text
    store = Path(str(db_module.engine.url.database))
    with db_module.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    assert b"quokka-7f3a" in store.read_bytes()  # control: the text is on disk while the workspace lives
    end(a)
    purge_expired_workspaces(db_module.engine)
    for path in (store, store.with_name(store.name + "-wal")):
        if path.exists():
            assert b"quokka-7f3a" not in path.read_bytes(), path.name
    with db_module.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    assert b"Wombat-c41d" in store.read_bytes()
    assert [d["name"] for d in b.get("/api/documents").json()] == ["b.txt"]


def test_a_checkpoint_a_reader_held_up_is_finished_by_the_next_hourly_pass(public: TestClient) -> None:  # noqa: F811
    # Review of 8037873 (N4): a visitor reading while a purge ends leaves the ended text in the database file, because
    # the checkpoint cannot copy the zeroed pages over it. The next hourly pass must finish that even when no other
    # workspace has expired, or the text stays until one does.
    marker = "Clause 99. The Licensee shall paint every warehouse vermilion quokka-7f3a."
    a, _ = arrive(public)
    work(cast(Reviewer, a), contract=CONTRACT + "\n\n" + marker + "\n")
    store = Path(str(db_module.engine.url.database))
    with db_module.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    end(a)
    reader = sqlite3.connect(store, timeout=0)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT count(*) FROM documents").fetchone()  # a snapshot from before the purge
        started = time.monotonic()
        held_up = purge_expired_workspaces(db_module.engine)
        assert held_up.workspaces and not held_up.checkpointed
        # Review of 39ade6e: a checkpoint waiting out the busy timeout for the reader blocks every writer meanwhile, now
        # every hour; it gives up at once and the next pass retries.
        assert time.monotonic() - started < 2
        assert b"quokka-7f3a" in store.read_bytes()  # control: the reader really kept the text in the file
    finally:
        reader.close()
    with db_module.engine.connect() as connection:  # control: the pooled connection still waits for writers as before
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() > 0
    quiet = purge_expired_workspaces(db_module.engine)
    assert quiet.workspaces == [] and quiet.checkpointed
    for path in (store, store.with_name(store.name + "-wal")):
        if path.exists():
            assert b"quokka-7f3a" not in path.read_bytes(), path.name
