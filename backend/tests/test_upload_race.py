"""A new document and its uploader's grant are one transaction.

Found by an audit (2026-10-09): two visitors uploading the same new bytes at once; in 5 of 50 races one was told the
upload worked and then got 404 on it. The document row was committed, then the grant: a second request that read the
row in between saw a document with no grant, which the read rules call curated, so it was granted nothing. A crash in
the same gap left an ungranted row, and the public API refused to start on a store "holding owner records".
"""

from __future__ import annotations

import contextlib
import threading
from typing import Never

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db as db_module
from app.application import ingest_document as ingest_module
from tests.support import CONTRACT
from tests.test_anonymous import Visitor, arrive, public  # noqa: F401  (the fixture)


def _upload(name: str, visitor: Visitor, body: bytes, results: dict[str, tuple[int, str]]) -> None:
    try:
        response = visitor.post("/api/documents", files={"file": (f"{name}.txt", body, "text/plain")})
        results[name] = (response.status_code, str(response.json().get("id", "")))
    except Exception as error:  # noqa: BLE001 - a thread's failure is reported, not lost
        results[name] = (-1, repr(error))


def test_two_visitors_racing_the_same_new_bytes_both_can_read_them(public: TestClient) -> None:  # noqa: F811
    for round_ in range(12):
        a, _ = arrive(public, address=f"198.51.100.{round_}")
        b, _ = arrive(public, address=f"203.0.113.{round_}")
        body = f"{CONTRACT}\nRace round {round_}.".encode()
        results: dict[str, tuple[int, str]] = {}
        threads = [threading.Thread(target=_upload, args=(name, visitor, body, results)) for name, visitor in (("a", a), ("b", b))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for name, visitor in (("a", a), ("b", b)):
            status, document_id = results[name]
            assert status in (200, 201), (round_, name, status, document_id)
            assert visitor.get(f"/api/documents/{document_id}").status_code == 200, (round_, name, "told it worked, then refused")


def test_a_failure_while_granting_leaves_no_ungranted_document(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """The grant is written in the document's transaction: if it fails, neither is kept."""
    a, _ = arrive(public)

    def crash(*_args: object, **_kwargs: object) -> Never:
        raise RuntimeError("the process died here")

    monkeypatch.setattr(ingest_module, "grant_document", crash)
    with contextlib.suppress(RuntimeError):
        a.post("/api/documents", files={"file": ("a.txt", f"{CONTRACT}\nAnother.".encode(), "text/plain")})
    with db_module.engine.connect() as connection:
        ungranted = connection.execute(
            text("SELECT COUNT(*) FROM documents d WHERE NOT EXISTS (SELECT 1 FROM document_access g WHERE g.document_id = d.id)")
        ).scalar()
        documents = connection.execute(text("SELECT COUNT(*) FROM documents")).scalar()
    assert ungranted == 0 and documents == 0
