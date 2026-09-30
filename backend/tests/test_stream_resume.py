"""The record is the sequence: a client that reconnects to the event stream says which stored event it last saw and is
replayed only what follows."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

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
