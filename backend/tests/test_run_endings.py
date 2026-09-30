"""How a run ends when something other than its own worker ends it: staleness recovery from another process,
a writer the bus cannot see, a worker whose database write fails. Found while tracing on 2026-09-29.

The stream tests drive the event generator directly: the HTTP test client buffers a streaming response until
the application finishes it, so an open stream cannot be observed through it."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api.runs as runs_api
from app.analysis.service import load_prompt
from app.application.recover_runs import recover_interrupted_runs
from app.application.start_run import compute_fingerprint, run_options
from app.db import SessionLocal
from app.models import Run
from app.providers.base import Generation
from app.runs.events import bus
from tests.support import upload_and_ask


def _run_in_flight(client: TestClient, question: str) -> str:
    """A run written as in progress by some process and never finished, on a document the client uploaded."""
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    with SessionLocal() as session:
        stuck = Run(
            document_id=result["document"]["id"],
            question=question,
            stage="checking",
            provider="fake",
            model="fake-1",
            prompt_version="answer-v2",
            prompt_hash=load_prompt().sha256,
            document_sha256=result["document"]["sha256"],
            fingerprint=compute_fingerprint(result["document"]["id"], None, question, load_prompt().sha256, run_options()),
        )
        session.add(stuck)
        session.commit()
        return stuck.id


async def _stream_until_final(run_id: str, act: Callable[[], None]) -> tuple[dict[str, Any], float]:
    """Open the event stream, run ``act`` once the stream is subscribed and waiting, and return the final event with
    the seconds it took to arrive after that."""
    bus.bind_loop(asyncio.get_running_loop())  # in the API process the bus is bound to the server's loop at startup
    request = Request({"type": "http", "method": "GET", "path": f"/api/runs/{run_id}/events", "headers": [], "query_string": b""})
    response = await runs_api.run_events(run_id, request)
    chunks = aiter(response.body_iterator)
    pending = asyncio.ensure_future(anext(chunks))  # the generator starts, subscribes and waits on the bus
    await asyncio.sleep(0.2)
    started = time.monotonic()
    act()
    chunk = await pending
    while True:
        chunk_text = chunk if isinstance(chunk, str) else bytes(chunk).decode("utf-8")
        for line in chunk_text.splitlines():
            if line.startswith("data: "):
                payload: dict[str, Any] = json.loads(line[6:])
                if payload.get("final"):
                    return payload, time.monotonic() - started
        chunk = await anext(chunks)


def test_the_stream_ends_when_the_record_says_the_run_ended_even_if_the_bus_never_heard(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runs_api, "HEARTBEAT_SECONDS", 0.05)
    run_id = _run_in_flight(client, "Is there an arbitration clause?")

    def ended_elsewhere() -> None:
        # Another process ends the run; nothing is published on this process's bus.
        with SessionLocal() as session:
            session.execute(text("UPDATE runs SET stage = 'failed', reason = 'internal_error', error = 'ended elsewhere' WHERE id = :id"), {"id": run_id})
            session.commit()

    final, _ = asyncio.run(asyncio.wait_for(_stream_until_final(run_id, ended_elsewhere), timeout=10))
    assert final == {"runId": run_id, "stage": "failed", "final": True}


def test_staleness_recovery_ends_an_open_stream_at_once(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runs_api, "HEARTBEAT_SECONDS", 30)
    run_id = _run_in_flight(client, "Is there an arbitration clause?")

    def recovered() -> None:
        with SessionLocal() as session:
            assert recover_interrupted_runs(session, stale_after_s=0) == 1

    final, elapsed = asyncio.run(asyncio.wait_for(_stream_until_final(run_id, recovered), timeout=10))
    assert final["stage"] == "failed" and final["final"] is True and final["detail"].startswith("Interrupted")
    assert elapsed < 5, f"the stream waited {elapsed:.1f} s for a heartbeat instead of hearing the recovery"


def test_a_worker_whose_run_was_ended_by_recovery_leaves_the_recovery_record_and_does_not_raise(client: TestClient) -> None:
    """Twenty concurrent runs on 2026-09-28 met this: recovery in another process ended a live run, the worker's next write hit
    the immutability trigger, and writing the failure into the same session raised again out of the background task."""
    original: Callable[[str, str, dict[str, Any]], Generation] = client.provider.generate_json

    def swept(system: str, user: str, schema: dict[str, Any]) -> Generation:
        with SessionLocal() as other:
            assert recover_interrupted_runs(other, stale_after_s=0) == 1, "another process declares the live run dead while the model answers"
        return original(system, user, schema)

    client.provider.generate_json = swept
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    run = result["run"]
    assert run["stage"] == "failed" and run["reason"] == "internal_error" and run["error"].startswith("Interrupted")
    stages = [s["stage"] for s in client.get(f"/api/runs/{result['run_id']}/detail").json()["stages"]]
    assert stages.count("failed") == 1 and stages[-1] == "failed", stages


def test_a_run_whose_process_is_gone_is_recovered_at_once_and_a_live_one_waits_for_staleness(client: TestClient) -> None:
    """The stage row names its process; a dead process on this host is proof, a live one or another host is not."""
    from app.models import RunStage
    from app.runs.owner import ProcessIdentity, this_process

    dead = ProcessIdentity(this_process().host, 4_000_000, "").render()  # no such pid
    run_id = _run_in_flight(client, "Is there an arbitration clause?")
    with SessionLocal() as session:
        first = session.get(Run, run_id)
        assert first is not None
        other = Run(
            document_id=first.document_id,
            question="Is there a most favoured nation clause?",
            stage="checking",
            provider="fake",
            model="fake-1",
            prompt_version="answer-v2",
            prompt_hash=load_prompt().sha256,
            document_sha256=first.document_sha256,
            fingerprint=compute_fingerprint(first.document_id, None, "Is there a most favoured nation clause?", load_prompt().sha256, run_options()),
        )
        session.add(other)
        session.commit()
        other_id = other.id
        session.add(RunStage(run_id=run_id, stage="checking", detail="against the question", status="running", owner=dead))
        session.add(RunStage(run_id=other_id, stage="checking", detail="against the question", status="running", owner=this_process().render()))
        session.commit()
        assert recover_interrupted_runs(session) == 1
    recovered = client.get(f"/api/runs/{run_id}").json()
    assert recovered["stage"] == "failed" and "no longer exists" in recovered["error"]
    assert client.get(f"/api/runs/{other_id}").json()["stage"] == "checking", "a live process's run is not touched"


def test_every_stage_row_a_worker_writes_names_its_process(client: TestClient) -> None:
    from app.models import RunStage
    from app.runs.owner import this_process

    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    with SessionLocal() as session:
        owners = {row.owner for row in session.query(RunStage).filter_by(run_id=result["run_id"])}
    assert owners == {this_process().render()}


def test_the_stage_writer_refuses_an_impossible_transition(client: TestClient) -> None:
    """The transition table is checked where stages are written; mutant M24 removes the check."""
    from app.runs.service import _set_stage
    from app.runs.transitions import IllegalTransition

    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    with SessionLocal() as session:
        run = session.get(Run, result["run_id"])
        assert run is not None and run.stage == "complete"
        with pytest.raises(IllegalTransition, match="finished"):
            _set_stage(session, run, "checking")
        session.rollback()
    assert client.get(f"/api/runs/{result['run_id']}").json()["stage"] == "complete"
