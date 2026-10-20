"""The model's queue is bounded and visible (backend audit, 2026-10-19).

One GPU answers one call at a time. Each public workspace could have two questions being answered, but nothing bounded
every visitor's together: thirty visitors queued sixty questions, the last half an hour from an answer, and the page
said only that most answers take under two minutes. Past the bound a question is now refused at once, with nothing
started and a time to try again; a question that is waiting says how many are ahead of it.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from starlette.requests import Request

from app import config
from app.api import runs as runs_api
from app.db import SessionLocal
from app.models import TERMINAL_STAGES, Run
from app.runs.events import bus
from tests.test_anonymous import Visitor
from tests.test_mission_security import HeldProvider
from tests.test_quota_admission import QUESTIONS, _ask, _with_document
from tests.test_run_endings import _run_in_flight


def _open_runs() -> int:
    with SessionLocal() as session:
        return int(session.scalar(select(func.count(Run.id)).where(Run.stage.notin_(TERMINAL_STAGES))) or 0)


def _held(visitor: Visitor, document_id: str, question: str, open_before: int) -> threading.Thread:
    """Start a question the held provider keeps in flight; return once its run exists and is unfinished."""
    asking = threading.Thread(target=lambda: _ask(visitor, document_id, question))
    asking.start()
    deadline = time.monotonic() + 10
    while _open_runs() == open_before:
        assert time.monotonic() < deadline, "the held question never started"
        time.sleep(0.02)
    return asking


@pytest.fixture
def held(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> HeldProvider:
    monkeypatch.setattr(config.settings, "public_max_runs_in_flight", 1)
    provider = HeldProvider()
    public.app.state.provider = provider  # type: ignore[attr-defined]
    return provider


def test_past_the_bound_a_question_is_refused_at_once_and_starts_nothing(public: TestClient, held: HeldProvider) -> None:
    first, first_document = _with_document(public)
    second, second_document = _with_document(public)
    asking = _held(first, first_document, QUESTIONS[0], 0)
    try:
        refused = second.post("/api/runs", json={"documentId": second_document, "guidanceId": None, "question": QUESTIONS[0]})
        assert refused.status_code == 503 and refused.headers["Retry-After"] == "60"
        assert "Nothing was started" in refused.json()["detail"]
        assert _open_runs() == 1
    finally:
        held.release.set()
        asking.join(timeout=30)
    assert _ask(second, second_document, QUESTIONS[0]) == 202  # control: an answer that arrived frees the queue


def test_control_the_projects_own_runs_are_not_held_to_the_public_bound(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "public_max_runs_in_flight", 0)
    from tests.support import upload_and_ask

    assert upload_and_ask(client, "What notice applies to termination for convenience?")["run"]["stage"] == "complete"


def test_a_waiting_question_says_how_many_are_ahead_and_the_count_falls(public: TestClient, held: HeldProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "public_max_runs_in_flight", 2)
    first, first_document = _with_document(public)
    second, second_document = _with_document(public)
    asking = [_held(first, first_document, QUESTIONS[0], 0), _held(second, second_document, QUESTIONS[0], 1)]
    try:
        (ahead_of_first,) = [r["id"] for r in first.get("/api/runs").json()]
        (ahead_of_second,) = [r["id"] for r in second.get("/api/runs").json()]
        assert first.get(f"/api/runs/{ahead_of_first}").json()["ahead"] == 0
        assert second.get(f"/api/runs/{ahead_of_second}").json()["ahead"] == 1
    finally:
        held.release.set()
        for thread in asking:
            thread.join(timeout=30)
    ended = second.get(f"/api/runs/{ahead_of_second}").json()
    assert ended["stage"] == "complete" and ended["ahead"] is None  # control: an ended run is ahead of nothing and behind nothing


def _queued_behind(run_id: str) -> str:
    """Another unfinished run on the same document, started after ``run_id``."""
    with SessionLocal() as session:
        first = session.get(Run, run_id)
        assert first is not None
        behind = Run(
            document_id=first.document_id,
            question=f"{first.question} (behind)",
            stage="checking",
            provider=first.provider,
            model=first.model,
            prompt_version=first.prompt_version,
            prompt_hash=first.prompt_hash,
            document_sha256=first.document_sha256,
            fingerprint=f"{first.fingerprint}-behind",
        )
        session.add(behind)
        session.commit()
        return behind.id


async def _first_queue_event(run_id: str) -> dict[str, object]:
    bus.bind_loop(asyncio.get_running_loop())
    request = Request({"type": "http", "method": "GET", "path": f"/api/runs/{run_id}/events", "headers": [], "query_string": b""})
    response = await runs_api.run_events(run_id, request)
    async for chunk in response.body_iterator:
        text = chunk if isinstance(chunk, str) else bytes(chunk).decode("utf-8")
        if text.startswith("event: queue"):
            payload: dict[str, object] = json.loads(text.split("data: ", 1)[1])
            return payload
    raise AssertionError("the stream ended without saying where the run stands")


def test_the_stream_says_how_many_are_ahead_at_once_and_at_every_heartbeat(client: TestClient) -> None:
    first = _run_in_flight(client, "Is there an arbitration clause?")
    behind = _queued_behind(first)
    assert asyncio.run(asyncio.wait_for(_first_queue_event(behind), timeout=10)) == {"runId": behind, "ahead": 1}
    assert asyncio.run(asyncio.wait_for(_first_queue_event(first), timeout=10)) == {"runId": first, "ahead": 0}
    assert runs_api._in_the_record(behind) == (None, 1)  # what each heartbeat reads
    with SessionLocal() as session:
        session.execute(text("UPDATE runs SET stage = 'failed', reason = 'internal_error', error = 'ended elsewhere' WHERE id = :id"), {"id": first})
        session.commit()
    assert runs_api._in_the_record(behind) == (None, 0)  # the queue moved
    assert runs_api._in_the_record(first) == ("failed", None)  # control: an ended run ends the stream instead
