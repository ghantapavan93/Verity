"""A memo is a row and a file, and a row must never point at a file that is not there.

The row used to be committed first and the file moved into place after it. Fault injection on 2026-10-02 failed the
move: the memo row stayed, its DOCX was never written, every retry was handed that memo, and the download was a 500.
The file is now in place before the row exists; these tests hold the order from both sides.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.application.create_memo import memo_file
from app.config import settings
from app.db import SessionLocal
from app.hashing import sha256_file
from app.memo.service import _review_line
from app.models import Finding, Memo

from .support import upload_and_ask

QUESTION = "How much notice does the customer need to give to terminate for convenience?"


def _memo_files() -> list[str]:
    return sorted(p.name for p in (settings.data_dir / "memos").rglob("*") if p.is_file())


def test_a_move_that_fails_leaves_no_memo_and_the_retry_is_whole(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    result = upload_and_ask(client, QUESTION)
    real_replace = Path.replace
    armed = {"on": True}

    def failing_replace(self: Path, target: str | Path) -> Path:
        if armed["on"] and str(target).endswith(".docx"):
            armed["on"] = False
            raise OSError("injected: the process died while the file was being put in place")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)
    with pytest.raises(OSError, match="injected"):
        client.post("/api/memos", json={"runId": result["run_id"]})
    with SessionLocal() as session:
        assert session.query(Memo).count() == 0, "no row was written for a file that never arrived"
    assert _memo_files() == [], "nothing is left behind, here or under pending"

    retry = client.post("/api/memos", json={"runId": result["run_id"]})
    assert retry.status_code == 201
    docx = client.get(retry.json()["docxUrl"])
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    with SessionLocal() as session:
        memo = session.get(Memo, retry.json()["id"])
        assert memo is not None and sha256_file(memo_file(memo)) == memo.docx_sha256 == retry.json()["docxSha256"]


def test_a_commit_that_fails_leaves_no_file_and_the_retry_is_whole(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    result = upload_and_ask(client, QUESTION)
    real_commit = Session.commit
    armed = {"on": True}

    def failing_commit(self: Session) -> None:
        if armed["on"] and any(isinstance(row, Memo) for row in self.new):
            armed["on"] = False
            raise OperationalError("INSERT INTO memos", {}, Exception("injected: database is locked"))
        real_commit(self)

    monkeypatch.setattr(Session, "commit", failing_commit)
    with pytest.raises(OperationalError):
        client.post("/api/memos", json={"runId": result["run_id"]})
    assert _memo_files() == [], "a file whose row did not go in is removed"
    with SessionLocal() as session:
        assert session.query(Memo).count() == 0

    retry = client.post("/api/memos", json={"runId": result["run_id"]})
    assert retry.status_code == 201 and client.get(retry.json()["docxUrl"]).status_code == 200
    assert len(_memo_files()) == 1


def test_a_memo_whose_file_is_gone_says_so_and_its_html_still_reads(client: TestClient) -> None:
    result = upload_and_ask(client, QUESTION)
    memo = client.post("/api/memos", json={"runId": result["run_id"]}).json()
    for path in (settings.data_dir / "memos").glob("*.docx"):
        path.unlink()
    missing = client.get(memo["docxUrl"])
    assert missing.status_code == 404 and missing.json() == {"detail": "memo file not found"}
    assert client.get(memo["htmlUrl"]).status_code == 200


def test_a_store_that_was_moved_serves_its_memos_from_where_it_is_now(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = upload_and_ask(client, QUESTION)
    memo = client.post("/api/memos", json={"runId": result["run_id"]}).json()
    restored = tmp_path / "restored"
    shutil.copytree(settings.data_dir / "memos", restored / "memos")
    shutil.rmtree(settings.data_dir / "memos")
    monkeypatch.setattr(settings, "data_dir", restored)  # the row still names the path it was written to
    docx = client.get(memo["docxUrl"])
    assert docx.status_code == 200 and docx.content[:2] == b"PK"


def test_a_review_is_dated_in_local_time_from_utc_not_from_the_utc_wall_clock() -> None:
    # SQLite hands the instant back without a zone. 02:30 UTC on the 2nd is still the 1st anywhere west of Greenwich.
    stored = datetime(2026, 10, 2, 2, 30)
    review = SimpleNamespace(verdict="confirmed", reviewer="A. Reviewer", note=None, created_at=stored)
    line = _review_line(cast(Finding, SimpleNamespace(review=review)))
    expected = stored.replace(tzinfo=UTC).astimezone().strftime("%d %B %Y")
    assert line == f"Confirmed by A. Reviewer on {expected}"
