"""Liveness does not queue behind the request threads, and no one network holds them (stress test, 2026-10-30).

Every route declared `def` runs on one shared pool of request threads (anyio's default limiter, forty tokens), and
/api/health was one of them. One visitor, one network, sent 120 GETs of its own run at once, which no window limits:
the pool was full, health waited up to 21 s behind them, past both the cloud probe's 5 s and the supervisor's 10 s,
and three missed probes restart the API, failing every visitor's runs in flight. Two places held the class: health
answers on the event loop, and in the public store a network has at most a few requests in flight at once.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from anyio import to_thread
from fastapi.testclient import TestClient
from httpx import Response

from app.api import runs as runs_api
from tests.test_anonymous import Visitor, arrive


def _set_request_threads(tokens: int) -> int:
    limiter = to_thread.current_default_thread_limiter()
    before = int(limiter.total_tokens)
    limiter.total_tokens = tokens
    return before


@contextmanager
def request_threads_held(client: TestClient, monkeypatch: pytest.MonkeyPatch, tokens: int = 2, get: Callable[[str], Response] | None = None) -> Iterator[None]:
    """Every request thread held by a sync route that waits: the pool shrunk to ``tokens`` and that many GET /api/runs
    parked inside it, as 120 slow reads held all forty. ``get`` sends them (a visitor's, in the public store)."""
    release = threading.Event()
    entered = threading.Semaphore(0)

    def parked(session: object, stale_after_s: float | None = None) -> int:
        entered.release()
        release.wait(20)
        return 0

    monkeypatch.setattr(runs_api, "recover_interrupted_runs", parked)
    before = client.portal.call(_set_request_threads, tokens)  # type: ignore[union-attr]
    send = get or client.get
    holders = [threading.Thread(target=lambda: send("/api/runs")) for _ in range(tokens)]
    for holder in holders:
        holder.start()
    try:
        for _ in range(tokens):
            assert entered.acquire(timeout=10), "the parked reads never reached their route"
        yield
    finally:
        release.set()
        for holder in holders:
            holder.join(20)
        client.portal.call(_set_request_threads, before)  # type: ignore[union-attr]


def _within(seconds: float, call: Callable[[], Response]) -> Response | None:
    """The answer to ``call`` if it comes within ``seconds``; None if it is still waiting then."""
    answer: list[Response] = []
    thread = threading.Thread(target=lambda: answer.append(call()))
    thread.start()
    thread.join(seconds)
    return answer[0] if answer else None


def test_health_answers_while_every_request_thread_is_held(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    with request_threads_held(client, monkeypatch):
        answer = _within(5.0, lambda: client.get("/api/health"))
        assert answer is not None, "health waited behind the request threads"
        assert answer.status_code == 200 and answer.json()["ok"] is True


def test_health_answers_a_public_visitor_and_the_supervisor_while_every_thread_is_held(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    visitor, _ = arrive(public)
    with request_threads_held(public, monkeypatch, get=Visitor(public, visitor.cookie).get):
        for ask in (lambda: visitor.get("/api/health"), lambda: public.get("/api/health")):  # past the gate, and before it
            answer = _within(5.0, ask)
            assert answer is not None, "health waited behind the request threads"
            assert answer.status_code == 200


def test_control_a_sync_route_still_waits_for_a_request_thread(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # What the held pool does to every other route: the test above is about health, not a pool that never fills.
    with request_threads_held(client, monkeypatch):
        assert _within(1.0, lambda: client.get("/api/documents")) is None


def test_health_probes_the_model_off_the_request_threads(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # The model's probe is a network call: it runs on a thread of its own, never one a held pool has no room for.
    from app.api import health

    health._probes.clear()
    seen: list[str] = []

    class Probed:
        name, model = "ollama", "qwen3:8b"

        def healthy(self) -> tuple[bool, str]:
            seen.append(threading.current_thread().name)
            time.sleep(0.05)
            return True, "qwen3:8b ready"

    client.app.state.provider = Probed()  # type: ignore[attr-defined]
    with request_threads_held(client, monkeypatch):
        answer = _within(5.0, lambda: client.get("/api/health"))
    assert answer is not None and answer.json()["detail"] == "qwen3:8b ready"
    assert seen and all(name.startswith("health-probe") for name in seen)


def visitor_on(public: TestClient, address: str) -> Visitor:
    visitor, response = arrive(public, address=address)
    assert response.status_code == 200
    visitor.headers["CF-Connecting-IP"] = address
    return visitor


# ---------------------------------------------------------------------------- what one network holds at once


@contextmanager
def reads_parked(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[threading.Semaphore, threading.Event]]:
    """GET /api/runs waits inside its route until released: a slow read, held as long as the test likes."""
    release = threading.Event()
    entered = threading.Semaphore(0)

    def parked(session: object, stale_after_s: float | None = None) -> int:
        entered.release()
        release.wait(20)
        return 0

    monkeypatch.setattr(runs_api, "recover_interrupted_runs", parked)
    try:
        yield entered, release
    finally:
        release.set()


def _send_all(calls: list[Callable[[], Response]]) -> tuple[list[threading.Thread], list[Response]]:
    answers: list[Response] = []
    threads = [threading.Thread(target=lambda c=call: answers.append(c())) for call in calls]
    for thread in threads:
        thread.start()
    return threads, answers


def test_a_network_past_its_requests_in_flight_is_refused_at_the_door(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config
    from app.api import in_flight

    monkeypatch.setattr(config.settings, "public_requests_per_network", 2)
    monkeypatch.setattr(in_flight, "IN_FLIGHT_WAIT_S", 0.3)
    visitor = visitor_on(public, "203.0.113.7")
    same_network = visitor_on(public, "203.0.113.7")  # a second browser on that network
    other = visitor_on(public, "198.51.100.9")
    with reads_parked(monkeypatch) as (entered, release):
        threads, _ = _send_all([lambda: visitor.get("/api/runs") for _ in range(2)])
        for _ in range(2):
            assert entered.acquire(timeout=10)
        refused = _within(5.0, lambda: same_network.get("/api/documents"))
        assert refused is not None and refused.status_code == 503 and refused.headers["Retry-After"]
        assert "nothing was done" in refused.json()["detail"]
        # Control: another network is let in, and health is never counted.
        assert other.get("/api/documents").status_code == 200
        assert visitor.get("/api/health").status_code == 200
        release.set()
        for thread in threads:
            thread.join(20)
    assert visitor.get("/api/documents").status_code == 200  # its requests ended: the network has its turns back
    assert in_flight.in_flight() == {}  # nothing is kept for a network once its last request ends


def test_one_past_the_bound_waits_for_a_turn_rather_than_failing(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setattr(config.settings, "public_requests_per_network", 1)
    visitor = visitor_on(public, "203.0.113.8")
    with reads_parked(monkeypatch) as (entered, release):
        threads, _ = _send_all([lambda: visitor.get("/api/runs")])
        assert entered.acquire(timeout=10)
        threading.Timer(0.3, release.set).start()  # the held read ends inside the wait
        waited = _within(5.0, lambda: visitor.get("/api/documents"))
        for thread in threads:
            thread.join(20)
    assert waited is not None and waited.status_code == 200


def test_every_route_but_health_and_streams_is_counted(public: TestClient) -> None:
    # The bound is at the door, so a route added later is counted without anyone remembering.
    from app.api.in_flight import _STREAM, _UNCOUNTED

    for route in public.app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        sample = re.sub(r"\{[^}]+\}", "x", path)
        counted = sample not in _UNCOUNTED and not _STREAM.fullmatch(sample)
        assert counted or path in ("/api/health", "/api/runs/{run_id}/events"), path


def test_control_the_owner_store_is_not_bounded_at_the_door(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setattr(config.settings, "public_requests_per_network", 1)
    with reads_parked(monkeypatch) as (entered, release):
        threads, answers = _send_all([lambda: client.get("/api/runs") for _ in range(3)])
        for _ in range(3):
            assert entered.acquire(timeout=10), "the owner's reads were held at the door"
        release.set()
        for thread in threads:
            thread.join(20)
    assert [a.status_code for a in answers] == [200, 200, 200]


# ---------------------------------------------------------------------------- live event streams


def test_a_workspace_past_its_open_streams_is_told_to_follow_by_polling(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config
    from app.api import in_flight
    from tests.test_network_windows import _visitor_with_run

    monkeypatch.setattr(config.settings, "public_streams_per_workspace", 2)
    visitor, _, run_id = _visitor_with_run(public)
    workspace = access_workspace(visitor)
    key = f"workspace:{workspace}"
    monkeypatch.setitem(in_flight._streams_of, key, 2)  # two of its streams open
    refused = visitor.get(f"/api/runs/{run_id}/events")
    assert refused.status_code == 429 and refused.headers["Retry-After"]
    in_flight._streams_of[key] = 1
    seen: list[int] = []
    real_subscribe = runs_api.bus.subscribe

    def subscribed(run: str) -> object:
        seen.append(in_flight.streams_open()[key])  # counted while the stream is open
        return real_subscribe(run)

    monkeypatch.setattr(runs_api.bus, "subscribe", subscribed)
    assert visitor.get(f"/api/runs/{run_id}/events").status_code == 200
    assert seen == [2]
    assert in_flight.streams_open()[key] == 1  # the stream's end gives its place back
    del in_flight._streams_of[key]


def test_a_network_past_its_open_streams_is_refused_whatever_workspace_it_opens(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config
    from app.api import in_flight
    from tests.test_network_windows import _visitor_with_run

    monkeypatch.setattr(config.settings, "public_streams_per_network", 1)
    visitor, _, run_id = _visitor_with_run(public)
    monkeypatch.setitem(in_flight._streams_of, "network:testclient", 1)
    assert visitor.get(f"/api/runs/{run_id}/events").status_code == 429
    del in_flight._streams_of["network:testclient"]


def access_workspace(visitor: Visitor) -> str:
    from app.api.access import workspace_for

    return workspace_for(visitor.subject)
