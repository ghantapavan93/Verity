"""A backup is the rollback: a code rollback cannot undo what a newer reader wrote. A backup taken while the API writes is
consistent, a restore checks every hash before it is trusted, and the restored store keeps its history immutable.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db as db_module
from tests.support import upload_and_ask


def load_script() -> ModuleType:
    """The backup is a script, loaded by path so that the tests exercise the file the deploy notes name."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "backup.py"
    spec = importlib.util.spec_from_file_location("backup", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


backup_script = load_script()
BackupError = backup_script.BackupError
counts, create, restore, sha256_file, verify = (
    backup_script.counts,
    backup_script.create,
    backup_script.restore,
    backup_script.sha256_file,
    backup_script.verify,
)
DB = "test.db"  # the name the test fixture gives its database (conftest); a deployment's is workbench.db


def stored(client: TestClient, data_dir: Path) -> dict[str, str]:
    """A store with a document, a finished run, a review and a memo, as an invited reviewer leaves it."""
    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    finding = result["run"]["findings"][0]["id"]
    assert client.post(f"/api/findings/{finding}/review", json={"verdict": "confirmed", "reviewer": "A", "note": None}).status_code == 201
    assert client.post("/api/memos", json={"runId": result["run_id"]}).status_code == 201
    (data_dir / "memos" / "pending").mkdir(parents=True, exist_ok=True)
    (data_dir / "memos" / "pending" / "half-written.docx").write_bytes(b"not a record yet")
    return {"run": result["run_id"], "document": result["document"]["id"]}


def test_a_backup_taken_during_a_write_restores_whole_and_immutable(client: TestClient, tmp_path: Path) -> None:
    ids = stored(client, tmp_path)
    # Another writer holds an open transaction while the backup runs: the backup has what was committed, nothing half done.
    writer = sqlite3.connect(tmp_path / DB, isolation_level=None)
    writer.execute("BEGIN")
    writer.execute("CREATE TABLE in_flight (x)")
    writer.execute("INSERT INTO in_flight VALUES (1)")
    try:
        manifest = create(tmp_path, tmp_path / "backup", DB)
    finally:
        writer.execute("ROLLBACK")
        writer.close()
    assert manifest["integrity_check"] == "ok" and manifest["counts"]["runs"] == 1 and manifest["counts"]["finding_reviews"] == 1
    files = manifest["files"]
    assert isinstance(files, dict)
    assert not any("pending" in name for name in files), "a memo being written is not a record"
    documents = [name for name in files if name.startswith("documents/")]
    assert documents and all(Path(name).stem == files[name]["sha256"] for name in documents), "an original is named by its own hash"

    restored = restore(tmp_path / "backup", tmp_path / "restored")
    assert restored["counts"] == counts(tmp_path / "restored" / DB)
    engine = db_module.make_engine(f"sqlite:///{(tmp_path / 'restored' / DB).as_posix()}")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE name = 'in_flight'")).scalar() == 0
        with pytest.raises(IntegrityError, match="immutable"):
            connection.execute(text("UPDATE runs SET question = 'rewritten' WHERE id = :id"), {"id": ids["run"]})
    engine.dispose()


def test_a_changed_or_missing_file_refuses_the_restore(client: TestClient, tmp_path: Path) -> None:
    stored(client, tmp_path)
    backup = tmp_path / "backup"
    create(tmp_path, backup, DB)
    original = next((backup / "documents").iterdir())
    original.write_bytes(original.read_bytes() + b" ")
    with pytest.raises(BackupError, match="does not match its recorded sha256"):
        restore(backup, tmp_path / "restored")
    assert not (tmp_path / "restored").exists(), "nothing is written when the backup cannot be trusted"
    original.unlink()
    with pytest.raises(BackupError, match="missing"):
        verify(backup)


def test_controls_a_restore_never_writes_over_a_store_and_a_backup_needs_a_database(client: TestClient, tmp_path: Path) -> None:
    stored(client, tmp_path)
    backup = tmp_path / "backup"
    create(tmp_path, backup, DB)
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "workbench.db").write_bytes(b"someone's store")
    with pytest.raises(BackupError, match="not empty"):
        restore(backup, occupied)
    assert (occupied / "workbench.db").read_bytes() == b"someone's store"
    with pytest.raises(BackupError, match=r"no workbench\.db"):
        create(tmp_path / "nothing-here", tmp_path / "backup-2")
    assert sha256_file(backup / DB) == verify(backup)["files"][DB]["sha256"]
