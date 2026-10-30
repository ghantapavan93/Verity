"""The files the store keeps beside SQLite hold the bytes their rows name, across a crash, a purge and a race
(stress test, 2026-10-30, ops 4 and concurrency 1).

An original was written and renamed with no flush, and a file standing under a document's hash was trusted by its name
alone: zeroed by a crash, every later upload of the same bytes kept it, every pack of the document failed its hash for
good and the backup certified it. And whether a document or its file still existed was decided outside the write lock,
on both sides: the purge deleted the file after its commit, and an upload decided reuse before taking the lock, so an
upload during a purge was a 500 (its grant on a deleted row), or a live row lost its original.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app import config
from app import db as db_module
from app.application import ingest_document as ingest_module
from app.application import quotas, trust_run
from app.application.ingest_document import coverage_of, write_durable
from app.application.retention import purge_expired_workspaces, sweep_orphaned_files
from app.db import SessionLocal
from app.hashing import sha256_bytes, sha256_file
from app.models import Document, utcnow
from tests.support import CONTRACT
from tests.test_anonymous import arrive
from tests.test_retention import end

BYTES = CONTRACT.encode("utf-8")


def _original(document_id: str) -> Path:
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        return ingest_module.original_path(document)


def _upload(client: TestClient, body: bytes = BYTES) -> Any:  # noqa: ANN401
    return client.post("/api/documents", files={"file": ("contract.txt", body, "text/plain")})


# ---------------------------------------------------------------------------- damaged originals


@pytest.mark.parametrize("damage", ["zeroed", "truncated", "emptied", "flipped"])
def test_an_upload_of_its_bytes_makes_a_damaged_original_whole(client: TestClient, damage: str) -> None:
    document_id = _upload(client).json()["id"]
    original = _original(document_id)
    data = original.read_bytes()
    damaged = {
        "zeroed": bytes(len(data)),  # what NTFS reads past a crash that kept the size and lost the data
        "truncated": data[: len(data) // 2],
        "emptied": b"",
        "flipped": data[:10] + bytes([data[10] ^ 1]) + data[11:],
    }[damage]
    original.write_bytes(damaged)
    assert _upload(client).status_code == 200, "the same bytes are the same document"
    assert sha256_file(original) == sha256_bytes(BYTES)


def test_control_a_whole_original_is_not_written_again(client: TestClient) -> None:
    document_id = _upload(client).json()["id"]
    original = _original(document_id)
    before = original.stat().st_mtime_ns
    time.sleep(0.05)
    assert _upload(client).status_code == 200
    assert original.stat().st_mtime_ns == before


def test_a_damaged_original_is_never_read_as_the_document(client: TestClient) -> None:
    document_id = _upload(client).json()["id"]
    original = _original(document_id)
    with db_module.engine.begin() as connection:  # a reading from before coverage was kept: rebuilt from the original
        connection.execute(text("UPDATE documents SET coverage_json = NULL WHERE id = :d"), {"d": document_id})
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None and coverage_of(document) is not None  # control: whole, it is read
        original.write_bytes(bytes(original.stat().st_size))
        assert coverage_of(document) is None
    trust_run.forget_readings()
    assert trust_run._read_again(original, "contract.txt", "any", sha256_bytes(BYTES)) is None
    original.write_bytes(BYTES)
    assert trust_run._read_again(original, "contract.txt", "any", sha256_bytes(BYTES)) is not None, "the damage was not kept"


def test_an_original_reaches_the_disk_before_it_takes_its_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(ingest_module.os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(ingest_module.os, "replace", lambda a, b: (order.append("replace"), real_replace(a, b))[1])
    target = tmp_path / "documents" / f"{sha256_bytes(BYTES)}.txt"
    write_durable(target, BYTES, sha256_bytes(BYTES))
    assert order[:2] == ["fsync", "replace"] and target.read_bytes() == BYTES
    assert [p.name for p in target.parent.iterdir()] == [target.name], "no partial is left"


def test_a_backup_refuses_a_damaged_original_unless_told_to_list_it(client: TestClient, tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import backup

    document_id = _upload(client).json()["id"]
    original = _original(document_id)
    assert backup.create(config.settings.data_dir, tmp_path / "whole", database="test.db")["files"]  # control
    original.write_bytes(bytes(original.stat().st_size))
    with pytest.raises(backup.BackupError, match="do not hold the bytes"):
        backup.create(config.settings.data_dir, tmp_path / "refused", database="test.db")
    listed = backup.create(config.settings.data_dir, tmp_path / "listed", database="test.db", accept_damaged=True)
    assert listed["damaged"] == [f"documents/{original.name}"]


# ---------------------------------------------------------------------------- an upload during a purge


def test_an_upload_of_bytes_a_purge_is_deleting_is_stored_whole(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    holder, _ = arrive(public, address="198.51.100.81")
    body = BYTES + b"\nHeld only by a workspace that has ended."
    assert _upload_as(holder, body).status_code == 201
    later, _ = arrive(public, address="198.51.100.82")  # before the purge: a visit writes too
    end(holder)
    reached, release = threading.Event(), threading.Event()
    purge_thread: list[threading.Thread] = []

    def hold(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:  # noqa: ANN401
        if purge_thread and threading.current_thread() is purge_thread[0] and statement.startswith("DELETE FROM documents"):
            reached.set()
            assert release.wait(30)

    waiting = threading.Event()
    real_write_locked = quotas.write_locked

    @contextmanager
    def noted(session: Any) -> Iterator[None]:  # noqa: ANN401
        waiting.set()  # the upload is about to wait for the purge's lock
        with real_write_locked(session):
            yield

    monkeypatch.setattr(quotas, "write_locked", noted)
    event.listen(db_module.engine, "before_cursor_execute", hold)
    try:
        purge = threading.Thread(target=lambda: purge_expired_workspaces(db_module.engine, gap_s=0.0))
        purge_thread.append(purge)
        purge.start()
        assert reached.wait(30), "the purge is inside its transaction"
        answer: dict[str, Any] = {}
        uploading = threading.Thread(target=lambda: answer.update(r=_upload_as(later, body)))
        uploading.start()
        assert waiting.wait(30)
        time.sleep(0.3)  # it now waits on the lock the purge holds
        release.set()
        purge.join(30)
        uploading.join(30)
    finally:
        event.remove(db_module.engine, "before_cursor_execute", hold)
    assert answer["r"].status_code == 201, answer["r"].text
    document_id = answer["r"].json()["id"]
    assert later.get(f"/api/documents/{document_id}").status_code == 200
    assert sha256_file(_original(document_id)) == sha256_bytes(body), "the row has its original"


def _upload_as(visitor: Any, body: bytes) -> Any:  # noqa: ANN401
    return visitor.post("/api/documents", files={"file": ("contract.txt", body, "text/plain")})


def test_the_sweep_leaves_a_file_an_upload_stored_since_it_looked(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.application import retention

    folder = config.settings.data_dir / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    sha = sha256_bytes(b"stored meanwhile")
    orphan = folder / f"{sha}.txt"
    orphan.write_bytes(b"stored meanwhile")
    then = time.time() - 7200
    os.utime(orphan, (then, then))
    real_locked = retention._locked

    @contextmanager
    def stored_first(engine: Any, gap_s: float) -> Iterator[Any]:  # noqa: ANN401
        with SessionLocal() as session:  # an upload of these bytes commits its row after the sweep read the names
            session.add(Document(name="document.txt", media_type="text/plain", sha256=sha, parser_version="x", created_at=utcnow()))
            session.commit()
        with real_locked(engine, gap_s) as connection:
            yield connection

    monkeypatch.setattr(retention, "_locked", stored_first)
    sweep_orphaned_files(db_module.engine)
    assert orphan.exists(), "a row names it now"
