"""Opening a contract wakes a hosted model that sleeps when idle, so the question finds it awake; and the wake-up is
bounded, because each one costs a cold start whether or not a question follows.

Invariants: a deployment that does not wake its model never sends a wake-up; one wake-up at a time; none while the model
is answering or answered recently; at most the day's allowance, all readers together; a wake-up loads the model with
exactly the settings an answer uses, or the first answer would load it again; and the route spends nothing for a
request without a session, from another origin, while paused or after the day's questions are spent.
"""

from __future__ import annotations

import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import model as model_api
from app.application import wake_model
from app.application.wake_model import ModelWaker
from app.errors import TooManyRequests
from app.providers import admission
from app.providers import ollama as ollama_module
from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider
from tests.test_access import ORIGIN
from tests.test_anonymous import arrive, public  # noqa: F401 - the deployment's settings, as a fixture


class Clock:
    def __init__(self) -> None:
        self.now = 10_000.0
        self.day = date(2026, 10, 13)

    def __call__(self) -> float:
        return self.now


class Wakes:
    """A wake-up that records itself and can be held open, as a cold start holds the real one."""

    def __init__(self) -> None:
        self.count = 0
        self.release = threading.Event()
        self.release.set()
        self.fail = False

    def __call__(self) -> None:
        self.count += 1
        self.release.wait(5)
        if self.fail:
            raise ProviderError("the model endpoint could not confirm its build (ConnectError)")
        ollama_module._heard()


@pytest.fixture
def waking(monkeypatch: pytest.MonkeyPatch) -> tuple[ModelWaker, Wakes, Clock]:
    monkeypatch.setattr(config.settings, "model_wakeup", True)
    monkeypatch.setattr(config.settings, "provider", "ollama")
    monkeypatch.setattr(config.settings, "model_wakeups_per_day", 3)
    monkeypatch.setattr(config.settings, "model_awake_s", 240)
    monkeypatch.setattr(ollama_module, "_last_answer", None)
    clock, wakes = Clock(), Wakes()
    monkeypatch.setattr(ollama_module, "_clock", clock)
    return ModelWaker(wake=wakes, clock=clock, today=lambda: clock.day), wakes, clock


def settle(waker: ModelWaker) -> None:
    thread = waker._thread
    if thread is not None:
        thread.join(5)


# ---------------------------------------------------------------------------- the bounds


def test_control_a_deployment_that_does_not_wake_its_model_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    wakes = Wakes()
    monkeypatch.setattr(config.settings, "model_wakeup", False)
    assert ModelWaker(wake=wakes).request() == "off"
    monkeypatch.setattr(config.settings, "model_wakeup", True)
    monkeypatch.setattr(config.settings, "provider", "replay")
    assert ModelWaker(wake=wakes).request() == "off"
    assert wakes.count == 0


def test_one_wake_up_at_a_time_however_many_readers_open_a_contract(waking: tuple[ModelWaker, Wakes, Clock]) -> None:
    waker, wakes, _ = waking
    wakes.release.clear()  # a cold start in progress
    answers = [waker.request() for _ in range(5)]
    assert answers == ["waking"] * 5 and wakes.count == 1
    wakes.release.set()
    settle(waker)
    assert waker.request() == "awake" and wakes.count == 1


def test_a_model_that_answered_recently_is_left_alone_and_one_that_went_back_to_sleep_is_woken(waking: tuple[ModelWaker, Wakes, Clock]) -> None:
    waker, wakes, clock = waking
    ollama_module._heard()  # a question was answered just now
    assert waker.request() == "awake" and wakes.count == 0
    clock.now += 239
    assert waker.request() == "awake" and wakes.count == 0
    clock.now += 2  # past the window: the endpoint may have scaled to zero
    assert waker.request() == "waking"
    settle(waker)
    assert wakes.count == 1


def test_a_model_answering_now_is_left_alone(waking: tuple[ModelWaker, Wakes, Clock], monkeypatch: pytest.MonkeyPatch) -> None:
    waker, wakes, _ = waking
    monkeypatch.setattr(admission, "_in_flight", 1)
    assert waker.request() == "awake" and wakes.count == 0


def test_the_days_wake_ups_are_bounded_for_all_readers_together_and_the_bound_is_renewed_each_day(waking: tuple[ModelWaker, Wakes, Clock]) -> None:
    waker, wakes, clock = waking
    for _ in range(3):
        assert waker.request() == "waking"
        settle(waker)
        clock.now += 300  # asleep again before the next reader
    assert waker.request() == "limit" and wakes.count == 3
    clock.day += timedelta(days=1)
    assert waker.request() == "waking"
    settle(waker)
    assert wakes.count == 4


def test_a_failed_wake_up_is_logged_counted_and_changes_nothing_else(waking: tuple[ModelWaker, Wakes, Clock], caplog: pytest.LogCaptureFixture) -> None:
    waker, wakes, _ = waking
    wakes.fail = True
    assert waker.request() == "waking"
    settle(waker)
    assert "model wake-up failed" in caplog.text and ollama_module.last_answer() is None
    assert waker.request() == "waking"  # not taken for awake; the next reader may try again, within the day's bound
    settle(waker)
    assert wakes.count == 2


# ---------------------------------------------------------------------------- what a wake-up sends


class Endpoint:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        self.gets: list[str] = []
        self.fail = False

    def get(self, url: str, timeout: float, headers: dict[str, str] | None = None, follow_redirects: bool = False) -> httpx.Response:
        self.gets.append(url)
        return httpx.Response(200, json={"models": [{"name": "qwen3:8b", "digest": "500a1f067a9fdeadbeef"}]}, request=httpx.Request("GET", url))

    def post(self, url: str, json: dict[str, Any], timeout: float, headers: dict[str, str] | None = None, follow_redirects: bool = False) -> httpx.Response:
        self.posts.append((url, json, dict(headers or {})))
        if self.fail:
            return httpx.Response(503, text="no capacity", request=httpx.Request("POST", url))
        body = {"response": "ok"} if url.endswith("/api/generate") else {"model": "qwen3:8b", "message": {"content": '{"findings": []}'}}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Endpoint:
    server = Endpoint()
    monkeypatch.setattr(httpx, "get", server.get)
    monkeypatch.setattr(httpx, "post", server.post)
    monkeypatch.setattr(config.settings, "ollama_url", "https://model.example.invalid")
    monkeypatch.setattr(config.settings, "ollama_headers", {"Modal-Key": "key-for-tests", "Modal-Secret": "secret-for-tests"})
    monkeypatch.setattr(config.settings, "model_digest", "500a1f067a9f")
    monkeypatch.setattr(ollama_module, "_last_answer", None)
    return server


def test_a_wake_up_loads_the_model_with_the_settings_an_answer_uses(endpoint: Endpoint) -> None:
    provider = OllamaProvider()
    provider.wake()
    provider.generate_json("system", "user", {"type": "object"})
    (wake_url, wake, wake_headers), (chat_url, chat, _) = endpoint.posts
    assert wake_url.endswith("/api/generate") and chat_url.endswith("/api/chat")
    # The context window, seed and temperature are what Ollama loads the model with: the same, or the answer reloads it.
    assert {k: v for k, v in wake["options"].items() if k != "num_predict"} == chat["options"] == provider.options()
    assert wake["options"]["num_predict"] == 1 and wake["model"] == chat["model"] and wake["think"] is False
    assert wake_headers == config.settings.ollama_headers
    assert len(endpoint.gets) == 2  # the pinned build is confirmed before the wake-up, as before every answer
    assert ollama_module.last_answer() is not None


def test_a_wake_up_the_endpoint_refuses_is_an_error_and_not_an_answer(endpoint: Endpoint) -> None:
    endpoint.fail = True
    with pytest.raises(ProviderError, match="could not be woken"):
        OllamaProvider().wake()
    assert ollama_module.last_answer() is None


# ---------------------------------------------------------------------------- the route


@pytest.fixture
def route(public: TestClient, monkeypatch: pytest.MonkeyPatch, waking: tuple[ModelWaker, Wakes, Clock]) -> tuple[TestClient, ModelWaker, Wakes]:  # noqa: F811
    waker, wakes, _ = waking
    monkeypatch.setattr(model_api, "waker", waker)
    return public, waker, wakes


def test_a_reader_with_a_session_wakes_the_model(route: tuple[TestClient, ModelWaker, Wakes]) -> None:
    client, waker, wakes = route
    visitor, _ = arrive(client)
    assert visitor.post("/api/model/wake").json() == {"state": "waking"}
    settle(waker)
    assert wakes.count == 1 and visitor.post("/api/model/wake").json() == {"state": "awake"}


def test_no_session_another_origin_or_a_read_wakes_nothing(route: tuple[TestClient, ModelWaker, Wakes]) -> None:
    client, _, wakes = route
    client.cookies.clear()
    assert client.post("/api/model/wake", headers={"Origin": ORIGIN}).status_code in (401, 403)
    visitor, _ = arrive(client)
    visitor.headers["Origin"] = "https://elsewhere.example"
    assert visitor.post("/api/model/wake").status_code == 403
    visitor.headers["Origin"] = ORIGIN
    assert visitor.get("/api/model/wake").status_code == 405
    assert wakes.count == 0


def test_nothing_is_woken_while_questions_are_paused_or_after_the_days_questions_are_spent(
    route: tuple[TestClient, ModelWaker, Wakes], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, wakes = route
    visitor, _ = arrive(client)
    (config.settings.data_dir / "public.paused").write_text("", encoding="utf-8")
    assert visitor.post("/api/model/wake").json() == {"state": "off"}
    (config.settings.data_dir / "public.paused").unlink()

    def spent(session: object) -> None:
        raise TooManyRequests("Today's run budget for this workbench is spent", retry_after=3600)

    monkeypatch.setattr(model_api, "refuse_past_daily_budget", spent)
    assert visitor.post("/api/model/wake").json() == {"state": "limit"}
    assert wakes.count == 0


def test_control_the_process_shares_one_waker() -> None:
    assert model_api.waker is wake_model.waker


def test_a_reader_who_has_asked_all_of_todays_questions_wakes_nothing(route: tuple[TestClient, ModelWaker, Wakes], monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, wakes = route
    visitor, _ = arrive(client)
    monkeypatch.setattr(config.settings, "anonymous_max_runs_per_day", 0)
    assert visitor.post("/api/model/wake").json() == {"state": "limit"}
    monkeypatch.setattr(config.settings, "anonymous_max_runs_per_day", 5)  # control: with questions left it wakes
    assert visitor.post("/api/model/wake").json() == {"state": "waking"}
    settle(model_api.waker)
    assert wakes.count == 1
