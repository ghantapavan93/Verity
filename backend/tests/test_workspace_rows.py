"""A public workspace adds no row once it has ended, by any path, and what one left behind is deleted (stress test,
2026-10-30, concurrency 4 and journeys 1).

A version statement was the one row keyed by a workspace that skipped quotas.admit(workspace_open): a statement let in
just before its workspace ended, and committed after the purge, left two rows for a workspace no purge would list
again. They counted as uses of both documents, so two visitors' shared contracts and their files outlived every holder;
the documents were then left with no grant, which the public API's start counts as an owner record, and it refused to
start. Three things now hold the class: the statement is written through admit like every other workspace row; the
store itself refuses a row for a public workspace that is not listed, on every table keyed by a workspace, derived from
the models so a new table is covered; and the purge deletes the rows of public workspaces that are not listed, so a store
that already holds such rows heals.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app import db as db_module
from app.api.access import workspace_for
from app.application import versions
from app.application.retention import purge_expired_workspaces
from app.db import Base, SessionLocal
from app.main import refuse_a_store_with_owner_records
from app.models import Document, DocumentAccess, DocumentVersion
from tests.support import CONTRACT
from tests.test_anonymous import Visitor, arrive
from tests.test_retention import end

REVISED = CONTRACT.replace("fifteen (15) days", "thirty (30) days")


def _upload(visitor: Visitor, text_: str, name: str) -> str:
    response = visitor.post("/api/documents", files={"file": (name, text_.encode("utf-8"), "text/plain")})
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


def _counts() -> dict[str, int]:
    with db_module.engine.connect() as connection:
        return {
            table: int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
            for table in ("documents", "document_access", "document_versions", "visitor_workspaces")
        }


def test_a_statement_held_across_its_workspace_s_purge_writes_nothing_and_leaves_nothing(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    first, _ = arrive(public, address="198.51.100.31")
    second, _ = arrive(public, address="198.51.100.32")
    earlier, later = _upload(first, CONTRACT, "v1.txt"), _upload(first, REVISED, "v2.txt")
    assert (_upload(second, CONTRACT, "v1.txt"), _upload(second, REVISED, "v2.txt")) == (earlier, later)  # both rows shared
    checked, purged = threading.Event(), threading.Event()
    calls = [0]
    real = versions.require_document

    def held(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        found = real(*args, **kwargs)
        calls[0] += 1
        if calls[0] == 2:  # both documents checked: the statement is let in
            checked.set()
            assert purged.wait(30)
        return found

    monkeypatch.setattr(versions, "require_document", held)
    answer: dict[str, Any] = {}
    stating = threading.Thread(target=lambda: answer.update(r=first.post(f"/api/documents/{later}/supersedes", json={"previousDocumentId": earlier})))
    stating.start()
    assert checked.wait(30)
    workspace = end(first)
    assert purge_expired_workspaces(db_module.engine).workspaces == [workspace]
    purged.set()
    stating.join(30)
    assert answer["r"].status_code == 401 and "nothing was added" in answer["r"].json()["detail"]
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(DocumentVersion).where(DocumentVersion.workspace_id == workspace)) == 0
    end(second)
    purge_expired_workspaces(db_module.engine)
    assert _counts() == {"documents": 0, "document_access": 0, "document_versions": 0, "visitor_workspaces": 0}
    refuse_a_store_with_owner_records()  # the public API starts again over its own store


def _workspace_tables() -> list[str]:
    return sorted(t.name for t in Base.metadata.sorted_tables if "workspace_id" in t.columns and t.name != "visitor_workspaces")


def test_every_table_keyed_by_a_workspace_is_guarded() -> None:
    # Derived from the models: a table added later with a workspace_id is guarded without anyone remembering.
    assert set(_workspace_tables()) == {name.removeprefix("trg_").removesuffix("_only_open_workspaces") for name, _ in db_module.workspace_guards()}


ROWS = {
    "document_access": "INSERT INTO document_access (workspace_id, document_id, created_at) VALUES (:w, :d, '2026-10-30 00:00:00')",
    "document_versions": "INSERT INTO document_versions (workspace_id, lineage_id, document_id, created_at) VALUES (:w, 'line', :d, '2026-10-30 00:00:00')",
    "guidance": "INSERT INTO guidance (id, text, sha256, source, created_at, workspace_id) VALUES (:id, 'x', 'h', 'pasted', '2026-10-30 00:00:00', :w)",
    "runs": "INSERT INTO runs (id, document_id, question, stage, provider, model, prompt_version, prompt_hash, options_json, document_sha256, "
    "candidates_json, created_at, workspace_id) VALUES (:id, :d, 'q', 'reading', 'fake', 'fake-1', 'v', 'h', '{}', 'abc', '[]', '2026-10-30 00:00:00', :w)",
}


@pytest.mark.parametrize("table", sorted(ROWS))
def test_the_store_refuses_a_row_for_a_public_workspace_that_is_not_listed(public: TestClient, table: str) -> None:
    assert sorted(ROWS) == _workspace_tables(), "a table keyed by a workspace has no row here to try"
    visitor, _ = arrive(public, address="198.51.100.40")
    document_id = _upload(visitor, CONTRACT, "c.txt")
    listed = workspace_for(visitor.subject)
    with pytest.raises(IntegrityError, match="not open"), db_module.engine.begin() as connection:
        connection.execute(text(ROWS[table]), {"w": "pw-0000000000000000", "d": document_id, "id": "row-unlisted"})
    # Controls: the listed workspace, and a workspace that is not a public one (the owner's, an invited reader's).
    with db_module.engine.begin() as connection:
        if table != "document_access":
            connection.execute(text(ROWS[table]), {"w": listed, "d": document_id, "id": "row-listed"})
        connection.execute(text(ROWS[table]), {"w": "ws-0000000000000000", "d": document_id, "id": "row-owner"})


def test_a_store_already_holding_rows_of_unlisted_workspaces_heals_at_the_next_purge(public: TestClient) -> None:
    first, _ = arrive(public, address="198.51.100.51")
    earlier, later = _upload(first, CONTRACT, "v1.txt"), _upload(first, REVISED, "v2.txt")
    # Rows a statement wrote after its workspace was purged, before the store refused them: the guard is lifted to make
    # them, as an older store holds them.
    with db_module.engine.begin() as connection:
        for name, _ in db_module.workspace_guards():
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {name}")
        for document_id, supersedes in ((earlier, None), (later, earlier)):
            connection.execute(
                text(
                    "INSERT INTO document_versions (workspace_id, lineage_id, document_id, supersedes_document_id, created_at) "
                    "VALUES ('pw-gone000000000000', 'line', :d, :s, '2026-10-01 00:00:00')"
                ),
                {"d": document_id, "s": supersedes},
            )
    db_module.ensure_immutability(db_module.engine)
    end(first)
    purge_expired_workspaces(db_module.engine)
    assert _counts() == {"documents": 0, "document_access": 0, "document_versions": 0, "visitor_workspaces": 0}
    refuse_a_store_with_owner_records()


def test_a_public_upload_of_bytes_no_one_holds_any_more_is_granted(public: TestClient) -> None:
    # A row with no grant is curated in an owner's store; in the public store it is only ever left behind, and an upload
    # of its bytes was answered 200 with a document its uploader could then neither read nor ask about.
    first, _ = arrive(public, address="198.51.100.61")
    document_id = _upload(first, CONTRACT, "c.txt")
    with db_module.engine.begin() as connection:
        connection.execute(text("DELETE FROM document_access WHERE document_id = :d"), {"d": document_id})
    second, _ = arrive(public, address="198.51.100.62")
    assert _upload(second, CONTRACT, "c.txt") == document_id
    assert second.get(f"/api/documents/{document_id}").status_code == 200
    with SessionLocal() as session:
        assert session.get(DocumentAccess, (workspace_for(second.subject), document_id)) is not None
        assert session.get(Document, document_id) is not None


def test_a_write_that_skips_the_open_check_is_refused_by_the_store_and_told_so(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Defence in depth: should a path ever write without quotas.workspace_open, the store refuses the row, and the
    # visitor is told what the check would have said, not a 500.
    from app.application import quotas

    first, _ = arrive(public, address="198.51.100.71")
    second, _ = arrive(public, address="198.51.100.72")
    earlier, later = _upload(first, CONTRACT, "v1.txt"), _upload(first, REVISED, "v2.txt")
    _upload(second, CONTRACT, "v1.txt"), _upload(second, REVISED, "v2.txt")
    workspace = workspace_for(first.subject)
    with db_module.engine.begin() as connection:
        connection.execute(text("DELETE FROM visitor_workspaces WHERE workspace_id = :w"), {"w": workspace})  # purged under it
    from app.api import access

    monkeypatch.setattr(access, "_session_serves_here", lambda subject: True)  # its session still let in, as before a purge
    monkeypatch.setattr(versions, "workspace_open", lambda _workspace: ())
    monkeypatch.setattr(versions, "require_document", lambda *args, **kwargs: None)
    answer = first.post(f"/api/documents/{later}/supersedes", json={"previousDocumentId": earlier})
    assert answer.status_code == 401 and answer.json()["detail"] == quotas.VISIT_ENDED
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(DocumentVersion).where(DocumentVersion.workspace_id == workspace)) == 0
