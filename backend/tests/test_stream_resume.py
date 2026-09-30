"""The record is the sequence: a client that reconnects to the event stream says which stored event it last saw and is
replayed only what follows; the replay provider can hold an answer back so a browser can refresh mid-run."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.providers.replay as replay_module
from app.providers.base import Generation
from app.providers.replay import ReplayProvider, request_key, save_answers
from tests.support import upload_and_ask


def _events(client: TestClient, run_id: str, headers: dict[str, str] | None = None, query: str = "") -> list[tuple[str | None, dict[str, Any]]]:
    with client.stream("GET", f"/api/runs/{run_id}/events{query}", headers=headers or {}) as response:
        body = "".join(response.iter_text())
    events: list[tuple[str | None, dict[str, Any]]] = []
    event_id: str | None = None
    for line in body.splitlines():
        if line.startswith("id: "):
            event_id = line[4:]
        elif line.startswith("data: "):
            events.append((event_id, json.loads(line[6:])))
            event_id = None
    return events


def test_stored_stage_events_carry_ids_and_a_reconnect_is_replayed_only_what_it_missed(client: TestClient) -> None:
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    events = _events(client, result["run_id"])
    stored = [(event_id, data) for event_id, data in events if not data.get("final")]
    assert [data["stage"] for _, data in stored] == ["reading", "finding_evidence", "checking", "verifying", "complete"]
    ids = [int(event_id) for event_id, _ in stored if event_id is not None]
    assert len(ids) == len(stored) and ids == sorted(ids), "every stored stage row is an event with its own increasing id"
    assert events[-1][1] == {"runId": result["run_id"], "stage": "complete", "final": True}

    resumed = _events(client, result["run_id"], headers={"Last-Event-ID": str(ids[2])})
    assert [data["stage"] for _, data in resumed if not data.get("final")] == ["verifying", "complete"], "only what came after the last seen event"
    assert resumed[-1][1]["final"] is True

    by_query = _events(client, result["run_id"], query=f"?after={ids[-1]}")
    assert [data for _, data in by_query] == [{"runId": result["run_id"], "stage": "complete", "final": True}], "nothing to replay, still the final word"


def test_the_replay_provider_holds_a_recorded_answer_back_when_the_question_asks_it_to(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "replay.json"
    system, user = "system prompt", "QUESTION: What is the limitation of liability?\n\nLEGAL GUIDANCE: none supplied"
    save_answers(
        path,
        {
            request_key(system, user): {
                "model": "qwen3:8b",
                "text": '{"findings": []}',
                "input_tokens": 10,
                "output_tokens": 3,
                "latency_ms": 5.0,
                "recorded_at": "2026-09-29T00:00:00+00:00",
                "user_head": "QUESTION: What is the limitation of liability?",
            }
        },
    )
    replay = ReplayProvider(path)
    started = time.monotonic()
    monkeypatch.setattr(replay_module, "DELAY_SECONDS", 0.5)
    generation = replay.generate_json(system, "QUESTION: What is the limitation of liability? [[zzdelay]]\n\nLEGAL GUIDANCE: none supplied", {})
    assert isinstance(generation, Generation) and generation.text == '{"findings": []}'
    assert time.monotonic() - started >= 0.5, "the answer was held back"
    assert replay.generate_json(system, user, {}).text == generation.text, "without the marker the same request is answered at once"
    nonced = replay.generate_json(system, "QUESTION: What is the limitation of liability? [[zzdelay:kqzv]]\n\nLEGAL GUIDANCE: none supplied", {})
    assert nonced.text == generation.text, "a nonce changes the question, not the recorded answer it maps to"
