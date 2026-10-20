"""What a read costs the store: a fixed number of queries whatever the number of rows, and no contract text read that
the answer does not show (backend audit, 2026-10-19).

The findings list asked five queries a row (2,252 for a full list), the runs list two, every read of a run asked once
per open run whether it had stalled, and the page's poll of a working run read the whole contract to place findings the
run did not have yet. Each test counts the statements the store is sent, the measure the audit used.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app import db as db_module
from app.application import clause_location
from app.application.clause_location import ClauseLocator, clause_numbers_by_document
from app.application.recover_runs import recover_interrupted_runs
from app.db import SessionLocal
from app.models import Document, Run
from tests.support import CONTRACT, upload_and_ask
from tests.test_run_endings import _run_in_flight


@contextmanager
def statements() -> Iterator[list[str]]:
    sent: list[str] = []

    def note(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:  # noqa: ANN401
        sent.append(" ".join(statement.split()))

    event.listen(db_module.engine, "before_cursor_execute", note)
    try:
        yield sent
    finally:
        event.remove(db_module.engine, "before_cursor_execute", note)


def ask(client: TestClient, first: int, count: int) -> list[str]:
    return [
        upload_and_ask(client, f"What notice applies to termination for convenience, case {i}?", with_guidance=bool(i % 2))["run_id"]
        for i in range(first, first + count)
    ]


def cost(client: TestClient, path: str) -> int:
    with statements() as sent:
        response = client.get(path)
    assert response.status_code == 200, response.text
    return len(sent)


@pytest.mark.parametrize("path", ["/api/findings", "/api/runs"])
def test_a_list_costs_the_same_queries_for_two_rows_and_twelve(client: TestClient, path: str) -> None:
    ask(client, 0, 2)
    few = cost(client, path)
    ask(client, 2, 10)
    many = cost(client, path)
    assert len(client.get(path).json()) == 12
    assert many == few, f"{path}: {few} queries for 2 rows, {many} for 12"


def test_control_the_counter_sees_the_list_queries(client: TestClient) -> None:
    ask(client, 0, 2)
    with statements() as sent:
        client.get("/api/findings")
    assert any("FROM findings" in statement for statement in sent)


def test_a_run_still_working_is_read_without_its_contract(client: TestClient) -> None:
    run_id = _run_in_flight(client, "Is there an arbitration clause?")
    with statements() as sent:
        assert client.get(f"/api/runs/{run_id}").json()["stage"] == "checking"
    assert not [statement for statement in sent if "FROM sections" in statement]


def test_control_a_run_with_findings_reads_the_sections_that_place_them(client: TestClient) -> None:
    run_id = ask(client, 0, 1)[0]
    with statements() as sent:
        client.get(f"/api/runs/{run_id}")
    assert [statement for statement in sent if "FROM sections" in statement]


def test_the_stall_check_costs_the_same_queries_for_one_open_run_and_five(client: TestClient) -> None:
    def check() -> int:
        with SessionLocal() as session, statements() as sent:
            assert recover_interrupted_runs(session) == 0, "a run that started moments ago is not stalled"
        return len(sent)

    first = _run_in_flight(client, "Is there an arbitration clause?")
    one = check()
    with SessionLocal() as session:
        stuck = session.get(Run, first)
        assert stuck is not None
        for i in range(4):
            session.add(
                Run(
                    document_id=stuck.document_id,
                    question=f"{stuck.question} ({i})",
                    stage="checking",
                    provider=stuck.provider,
                    model=stuck.model,
                    prompt_version=stuck.prompt_version,
                    prompt_hash=stuck.prompt_hash,
                    document_sha256=stuck.document_sha256,
                    fingerprint=f"{stuck.fingerprint}-{i}",
                )
            )
        session.commit()
    assert check() == one


def test_clause_numbers_by_document_are_the_locators(client: TestClient) -> None:
    other = CONTRACT.replace("3. Governing Law", "3. Governing Law\n\n3.1 Venue. Courts of Delaware.")
    ids = [upload_and_ask(client, "What law governs?", with_guidance=False)["document"]["id"]]
    ids.append(client.post("/api/documents", files={"file": ("other.txt", other.encode(), "text/plain")}).json()["id"])
    clause_location._clause_numbers.clear()
    with SessionLocal() as session:
        listed = clause_numbers_by_document(session, [*ids, *ids])
        for document_id in ids:
            document = session.get(Document, document_id)
            assert document is not None
            assert listed[document_id] == ClauseLocator(document.sections).clause_numbers
    assert listed[ids[0]] != listed[ids[1]]


def test_a_cached_reading_is_found_without_reading_the_text(client: TestClient) -> None:
    document_id = upload_and_ask(client, "What law governs?", with_guidance=False)["document"]["id"]
    clause_location._clause_numbers.clear()
    with SessionLocal() as session, statements() as cold:
        clause_numbers_by_document(session, [document_id])
    with SessionLocal() as session, statements() as warm:
        clause_numbers_by_document(session, [document_id])
    assert [statement for statement in cold if "sections.text" in statement], "control: a cold cache reads the text"
    assert not [statement for statement in warm if "sections.text" in statement]
