"""A version statement's outcome does not depend on a statement about another document landing at the same moment:
concurrent statements end as if made one after the other. Found by the QA campaign of 2026-10-08: two later versions of
one base, stated at once, ended 201 and 409 "placed in a line of versions by another request", although the refused
document was in no line; made one after the other, both are accepted."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.application.versions as versions_module
from app.models import DocumentVersion
from tests.support import CONTRACT


def upload(client: TestClient, text: str, name: str) -> str:
    response = client.post("/api/documents", files={"file": (name, text.encode("utf-8"), "text/plain")})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _stale_once(monkeypatch: pytest.MonkeyPatch, document_id: str) -> None:
    """The lookup of ``document_id``'s place misses once: what a request sees when another request opened that
    document's line between its lookup and its insert."""
    real = versions_module._placed
    missed = {"done": False}

    def placed(session: Session, workspace: str, looked_up: str) -> DocumentVersion | None:
        if looked_up == document_id and not missed["done"]:
            missed["done"] = True
            return None
        return real(session, workspace, looked_up)

    monkeypatch.setattr(versions_module, "_placed", placed)


def test_a_statement_that_loses_the_race_to_open_the_line_is_the_one_after_it(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    base = upload(client, CONTRACT, "base.txt")
    first = upload(client, CONTRACT + "\nFirst amendment.\n", "first.txt")
    second = upload(client, CONTRACT + "\nSecond amendment.\n", "second.txt")
    assert client.post(f"/api/documents/{first}/supersedes", json={"previousDocumentId": base}).status_code == 201
    _stale_once(monkeypatch, base)  # the second statement still believes the base opens no line
    said = client.post(f"/api/documents/{second}/supersedes", json={"previousDocumentId": base})
    assert said.status_code == 201, said.text
    line = client.get(f"/api/documents/{base}/versions").json()
    assert [v["documentId"] for v in line] == [base, first, second]
    assert len({v["lineageId"] for v in line}) == 1


def test_controls_a_real_conflict_is_still_refused_and_a_repeat_is_the_same_statement(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    base = upload(client, CONTRACT, "base.txt")
    other = upload(client, CONTRACT + "\nOther.\n", "other.txt")
    later = upload(client, CONTRACT + "\nLater.\n", "later.txt")
    assert client.post(f"/api/documents/{later}/supersedes", json={"previousDocumentId": base}).status_code == 201
    _stale_once(monkeypatch, later)  # even when the lookup of the later document misses once
    assert client.post(f"/api/documents/{later}/supersedes", json={"previousDocumentId": other}).status_code == 409
    assert client.post(f"/api/documents/{later}/supersedes", json={"previousDocumentId": base}).status_code == 200
