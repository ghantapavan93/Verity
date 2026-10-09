"""The public store deletes a visitor's workspace once it has ended, and nothing else (application/retention.py).

The one place a finished run is ever deleted. What is held to: only registered, ended visitor workspaces go; a
workspace still running a question waits; identical bytes another visitor holds stay theirs; the immutability triggers
come back exactly as they were and still refuse; files go only when nothing names them; the owner's and the curated
record are never candidates; an ended session opens nothing and a new visit gets a new workspace.
"""

from __future__ import annotations

import os
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


def test_the_owner_and_the_curated_record_are_never_candidates(public: TestClient) -> None:  # noqa: F811
    curated = make_curated(public)
    invited = work(Reviewer(public, "reviewer-a"))
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


def test_the_corpus_tools_are_not_a_visitors(public: TestClient) -> None:  # noqa: F811
    visitor, _ = arrive(public)
    for path in ("/api/engineering/goldens", "/api/engineering/families", "/api/batches"):
        assert visitor.get(path).status_code == 404, path
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
