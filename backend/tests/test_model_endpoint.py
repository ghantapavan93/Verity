"""A model served from somewhere else is the model the deployment names, reached with its credentials, and never
substituted in silence. A cloud Ollama behind an authenticating proxy needs headers on every call; a tag named qwen3:8b
on another server can be another build, so a pinned digest is checked before the first answer and by health. Health
never publishes where the model lives.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app import config
from app.config import json_headers
from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider
from app.retrieval import hybrid

PINNED = "500a1f067a9f"
HEADERS = {"Modal-Key": "key-for-tests", "Modal-Secret": "secret-for-tests"}
CHAT = {"model": "qwen3:8b", "message": {"content": '{"findings": []}'}, "prompt_eval_count": 10, "eval_count": 5}


def tags(digest: str) -> dict[str, Any]:
    return {"models": [{"name": "qwen3:8b", "digest": f"{digest}deadbeef"}]}


class Endpoint:
    """A model server that records what it was sent."""

    def __init__(self, digest: str = PINNED, reachable: bool = True) -> None:
        self.digest, self.reachable = digest, reachable
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, timeout: float, headers: dict[str, str] | None = None) -> httpx.Response:
        self.calls.append((url, dict(headers or {})))
        if not self.reachable:
            raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))
        return httpx.Response(200, json=tags(self.digest), request=httpx.Request("GET", url))

    def post(self, url: str, json: dict[str, Any], timeout: float, headers: dict[str, str] | None = None) -> httpx.Response:
        self.calls.append((url, dict(headers or {})))
        if url.endswith("/api/embed"):
            return httpx.Response(200, json={"embeddings": [[0.0, 1.0] for _ in json["input"]]}, request=httpx.Request("POST", url))
        return httpx.Response(200, json=CHAT, request=httpx.Request("POST", url))


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Endpoint:
    server = Endpoint()
    monkeypatch.setattr(httpx, "get", server.get)
    monkeypatch.setattr(httpx, "post", server.post)
    monkeypatch.setattr(config.settings, "ollama_url", "https://model.example.invalid")
    return server


def test_every_call_to_the_model_endpoint_carries_its_credentials(endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "ollama_headers", HEADERS)
    provider = OllamaProvider()
    provider.healthy()
    provider.generate_json("system", "user", {"type": "object"})
    hybrid.ollama_embed(["a clause"])
    assert {url.rsplit("/", 1)[1] for url, _ in endpoint.calls} == {"tags", "chat", "embed"}
    assert all(sent == HEADERS for _, sent in endpoint.calls)


def test_health_never_publishes_where_the_model_lives_and_no_log_holds_the_credentials(
    endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(config.settings, "ollama_headers", HEADERS)
    endpoint.reachable = False
    with caplog.at_level("DEBUG"):
        ok, detail = OllamaProvider().healthy()
    assert not ok and "not reachable" in detail and "model.example" not in detail
    assert "secret-for-tests" not in caplog.text and "secret-for-tests" not in repr(config.settings)


def test_a_pinned_build_is_asked_again_before_every_answer(endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    """A serverless endpoint can be replaced under a long-lived API: a build that was right a run ago is asked again."""
    monkeypatch.setattr(config.settings, "model_digest", PINNED)
    provider = OllamaProvider()
    provider.generate_json("system", "user", {"type": "object"})
    endpoint.digest = "0123456789ab"
    with pytest.raises(ProviderError, match="not the pinned build"):
        provider.generate_json("system", "user", {"type": "object"})


def test_a_pinned_build_is_checked_by_health_and_before_the_first_answer(endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "model_digest", PINNED)
    endpoint.digest = "0123456789ab"  # the same tag, another build
    ok, detail = OllamaProvider().healthy()
    assert not ok and "not the pinned build" in detail
    with pytest.raises(ProviderError, match="not the pinned build"):
        OllamaProvider().generate_json("system", "user", {"type": "object"})
    assert not any(url.endswith("/api/chat") for url, _ in endpoint.calls), "nothing is asked of a build the deployment did not name"


def test_controls_the_pinned_build_answers_and_no_pin_checks_nothing(endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "model_digest", PINNED)
    assert OllamaProvider().healthy() == (True, "qwen3:8b ready")
    assert OllamaProvider().generate_json("system", "user", {"type": "object"}).text == '{"findings": []}'
    monkeypatch.setattr(config.settings, "model_digest", "")
    endpoint.calls.clear()
    OllamaProvider().generate_json("system", "user", {"type": "object"})
    assert [url.rsplit("/", 1)[1] for url, _ in endpoint.calls] == ["chat"]


@pytest.mark.parametrize("raw", ['["Modal-Key", "x"]', "{not json", '{"Modal-Key": 7}'])
def test_credentials_that_are_not_a_json_object_of_strings_stop_the_start(raw: str) -> None:
    with pytest.raises(RuntimeError, match="WORKBENCH_OLLAMA_HEADERS"):
        json_headers(raw)
    assert json_headers("") == {}
