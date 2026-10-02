"""One row per (bytes, reader), one memo per run, whatever two concurrent first requests do. Found while tracing on
2026-09-29: the lookups ran before the inserts with nothing in the database to refuse the second row."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

import app.application.create_memo as memo_module
import app.application.ingest_document as ingest_module
from app.db import SessionLocal
from app.hashing import sha256_file
from app.ingest import PARSER_VERSION
from app.models import Document, Memo
from tests.support import CONTRACT, upload_and_ask


def _miss_on_second_call(monkeypatch: pytest.MonkeyPatch, module: object, name: str) -> None:
    """The lookup misses once, on its second call: exactly what a request sees when another request inserted the row
    between its lookup and its insert."""
    real = getattr(module, name)
    calls = {"n": 0}

    def lookup(*args: object) -> object:
        calls["n"] += 1
        return None if calls["n"] == 2 else real(*args)

    monkeypatch.setattr(module, name, lookup)


def test_the_database_keeps_one_document_per_bytes_and_reader(client: TestClient) -> None:
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    with SessionLocal() as session:
        session.add(Document(name="again.txt", media_type="text/plain", sha256=result["document"]["sha256"], parser_version=PARSER_VERSION))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(Memo(run_id=result["run_id"], review_head="h1", docx_path="x", docx_sha256="y", html=""))
        session.commit()
        session.add(Memo(run_id=result["run_id"], review_head="h1", docx_path="x2", docx_sha256="y2", html=""))
        with pytest.raises(IntegrityError):
            session.commit()


def test_a_concurrent_first_upload_is_handed_the_row_that_won(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _miss_on_second_call(monkeypatch, ingest_module, "stored_document")
    files = {"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")}
    first = client.post("/api/documents", files=files)
    assert first.status_code == 201
    second = client.post("/api/documents", files=files)  # its lookup misses; its insert loses; it gets the winner
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"] and second.json()["reused"] is True
    assert len(client.get("/api/documents").json()) == 1
    original = ingest_module.original_path(Document(name="agreement.txt", sha256=first.json()["sha256"]))
    assert original.read_bytes() == CONTRACT.encode("utf-8")


def test_a_concurrent_first_memo_is_handed_the_memo_that_won_with_its_file_intact(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _miss_on_second_call(monkeypatch, memo_module, "stored_memo")
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    first = client.post("/api/memos", json={"runId": result["run_id"]})
    assert first.status_code == 201
    second = client.post("/api/memos", json={"runId": result["run_id"]})
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"]
    with SessionLocal() as session:
        memo = session.get(Memo, first.json()["id"])
        assert memo is not None
        path = Path(memo.docx_path)
        assert path.exists() and sha256_file(path) == memo.docx_sha256, "the loser did not overwrite the winner's file"
        assert [p.name for p in path.parent.rglob("*.docx")] == [path.name], "the loser's file was removed, here and under pending"
