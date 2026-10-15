"""Two defects the security review of 2026-10-14 reproduced (outside the
repository), each with its fix's test and a control.

1. One visitor held the model queue: thirty questions started from two sessions on one address, and a second visitor's
   one question was model call 31 of 31. The model answers one call at a time, first come first served, so the bound is
   on what a public workspace has being answered at once (application/quotas.run_quotas).
2. X-Request-ID was logged as given: a caller wrote whole forged lines into the log. It is kept only when it is an id.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config
from app.api import access
from app.db import SessionLocal
from app.models import TERMINAL_STAGES, Run
from app.providers.base import Generation
from tests.support import FakeProvider
from tests.test_anonymous import Visitor
from tests.test_quota_admission import QUESTIONS, _ask, _with_document


class HeldProvider(FakeProvider):
    """Answers only when released: a question it is answering stays in flight, as on a busy GPU."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        assert self.release.wait(timeout=30), "the held answer was never released"
        return super().generate_json(system, user, schema)


def _in_flight(workspace: str) -> int:
    with SessionLocal() as session:
        return int(session.scalar(select(func.count(Run.id)).where(Run.workspace_id == workspace, Run.stage.notin_(TERMINAL_STAGES))) or 0)


def _ask_while_one_is_held(public: TestClient, visitor: Visitor, document_id: str) -> tuple[threading.Thread, list[int]]:
    """Start a question that the held provider keeps in flight; return once its run exists and is unfinished."""
    codes: list[int] = []
    asking = threading.Thread(target=lambda: codes.append(_ask(visitor, document_id, QUESTIONS[0])))
    asking.start()
    workspace = access.workspace_for(visitor.subject)
    deadline = time.monotonic() + 10
    while _in_flight(workspace) == 0:
        assert time.monotonic() < deadline, "the held question never started"
        time.sleep(0.02)
    return asking, codes


def test_a_workspace_cannot_queue_more_questions_than_its_in_flight_bound(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_max_runs_in_flight", 1)
    provider = HeldProvider()
    public.app.state.provider = provider  # type: ignore[attr-defined]
    visitor, document_id = _with_document(public)
    asking, codes = _ask_while_one_is_held(public, visitor, document_id)
    try:
        refused = visitor.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": QUESTIONS[1]})
        assert refused.status_code == 429 and "being answered" in refused.json()["detail"] and refused.headers["Retry-After"] == "30"
    finally:
        provider.release.set()
        asking.join(timeout=30)
    assert codes == [202]
    assert _ask(visitor, document_id, QUESTIONS[1]) == 202  # control: an answer that arrived frees the queue


def test_control_one_visitors_queue_does_not_hold_another(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_max_runs_in_flight", 1)
    provider = HeldProvider()
    public.app.state.provider = provider  # type: ignore[attr-defined]
    busy, busy_document = _with_document(public)
    other, other_document = _with_document(public)
    asking, codes = _ask_while_one_is_held(public, busy, busy_document)
    try:
        answering: list[int] = []
        second = threading.Thread(target=lambda: answering.append(_ask(other, other_document, QUESTIONS[0])))
        second.start()
        deadline = time.monotonic() + 10
        while _in_flight(access.workspace_for(other.subject)) == 0:
            assert time.monotonic() < deadline, "the other visitor's question was refused or never started"
            time.sleep(0.02)
    finally:
        provider.release.set()
        asking.join(timeout=30)
        second.join(timeout=30)
    assert codes == [202] and answering == [202]


@pytest.mark.parametrize("offered", ["x method=DELETE path=/api/documents/all status=200", "a" * 65, "id\nforged", ""])
def test_a_request_id_that_is_not_an_id_is_replaced(client: TestClient, offered: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        response = client.get("/api/documents", headers={"X-Request-ID": offered} if offered else {})
    given = response.headers["X-Request-ID"]
    assert given != offered and len(given) == 12 and given.isalnum()
    assert all(offered not in record.getMessage() for record in caplog.records if offered)


def test_control_an_id_a_caller_gives_is_kept(client: TestClient) -> None:
    assert client.get("/api/documents", headers={"X-Request-ID": "trace-7f3a-01"}).headers["X-Request-ID"] == "trace-7f3a-01"
