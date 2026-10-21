"""A model served from somewhere else is the model the deployment names, reached with its credentials, and never
substituted in silence. A cloud Ollama behind an authenticating proxy needs headers on every call; a tag named qwen3:8b
on another server can be another build, so a pinned digest is checked before the first answer and by health. Health
never publishes where the model lives.
"""

from __future__ import annotations

import http.server
import json as json_module
import threading
import time
from typing import Any

import httpx
import pytest

from app import config
from app.config import json_headers
from app.providers import ollama as ollama_module
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

    def get(self, url: str, timeout: float, headers: dict[str, str] | None = None, follow_redirects: bool = False) -> httpx.Response:
        self.calls.append((url, dict(headers or {})))
        if not self.reachable:
            raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))
        return httpx.Response(200, json=tags(self.digest), request=httpx.Request("GET", url))

    def post(self, url: str, json: dict[str, Any], timeout: float, headers: dict[str, str] | None = None, follow_redirects: bool = False) -> httpx.Response:
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
    assert {url.rsplit("/", 1)[1] for url, _ in endpoint.calls} == {"tags", "generate", "chat", "embed"}  # generate: the clean start
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
    assert [url.rsplit("/", 1)[1] for url, _ in endpoint.calls] == ["generate", "chat"]  # the clean start, the answer; no build check


class ServerlessEndpoint(http.server.ThreadingHTTPServer):
    """A model endpoint as Modal serves one, on a real socket: the list of models arrives only after a cold start, and an
    answer still running at the platform's request limit is a 303 to a URL that waits for the result."""

    cold_start_s = 0.6
    seen: list[tuple[str, str, str | None]]


class ServerlessHandler(http.server.BaseHTTPRequestHandler):
    server: ServerlessEndpoint

    def _send(self, status: int, body: dict[str, Any] | None = None, location: str | None = None) -> None:
        payload = json_module.dumps(body or {}).encode()
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self.server.seen.append(("GET", self.path, self.headers.get("Modal-Key")))
        if self.path == "/api/tags":
            time.sleep(self.server.cold_start_s)
            self._send(200, tags(PINNED))
        else:
            self._send(200, CHAT)

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.seen.append(("POST", self.path, self.headers.get("Modal-Key")))
        self._send(303, location="/result/abc")

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_a_cold_serverless_endpoint_answers_through_its_start_and_its_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Modal starts a container on the first request after it scaled to zero (a minute or more) and answers a request
    still running after 150 s with a 303 to a URL that waits for the result. The build check before an answer waited
    5 s and the answer did not follow a redirect: the first question after the GPU slept failed, and so did any answer
    longer than 150 s (cloud readiness review, 2026-10-12)."""
    server = ServerlessEndpoint(("127.0.0.1", 0), ServerlessHandler)
    server.seen = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(config.settings, "model_digest", PINNED)
        monkeypatch.setattr(config.settings, "ollama_headers", HEADERS)
        monkeypatch.setattr(ollama_module, "HEALTH_PROBE_TIMEOUT_S", 0.2)
        provider = OllamaProvider(base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout_s=10)
        ok, _ = provider.healthy()
        assert not ok, "control: health is a probe and does not wait out a cold start"
        assert provider.generate_json("system", "user", {"type": "object"}).text == '{"findings": []}'
        assert ("POST", "/api/chat", "key-for-tests") in server.seen
        assert ("GET", "/result/abc", "key-for-tests") in server.seen, "the redirect is followed with the credentials"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("raw", ['["Modal-Key", "x"]', "{not json", '{"Modal-Key": 7}'])
def test_credentials_that_are_not_a_json_object_of_strings_stop_the_start(raw: str) -> None:
    with pytest.raises(RuntimeError, match="WORKBENCH_OLLAMA_HEADERS"):
        json_headers(raw)
    assert json_headers("") == {}


def test_a_redirect_to_another_host_is_refused_and_the_credentials_never_go_there(monkeypatch: pytest.MonkeyPatch) -> None:
    """httpx keeps custom headers on a redirect to another host: Modal-Key and Modal-Secret went to it in the clear
    (security review, 2026-10-13). Only the endpoint's own scheme and host are followed."""
    sent: list[tuple[str, dict[str, str]]] = []

    def get(url: str, timeout: float, headers: dict[str, str] | None = None, follow_redirects: bool = False) -> httpx.Response:
        sent.append((url, dict(headers or {})))
        if url.startswith("https://model.example.invalid"):
            return httpx.Response(303, headers={"location": "http://elsewhere.example.invalid/steal"}, request=httpx.Request("GET", url))
        return httpx.Response(200, json=tags(PINNED), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(config.settings, "ollama_url", "https://model.example.invalid")
    monkeypatch.setattr(config.settings, "ollama_headers", HEADERS)
    monkeypatch.setattr(config.settings, "model_digest", PINNED)
    with pytest.raises(ProviderError, match="redirected to another host"):
        OllamaProvider()._check_build()
    assert [url for url, _ in sent] == ["https://model.example.invalid/api/tags"]


def test_the_access_secret_is_never_in_a_printed_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "access_secret", "secret-for-tests-" + "s" * 30)
    assert "secret-for-tests" not in repr(config.settings) and "secret-for-tests" not in str(config.settings)


def test_health_reports_a_refused_redirect_as_not_ok_instead_of_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    def get(url: str, timeout: float, headers: dict[str, str] | None = None, follow_redirects: bool = False) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://elsewhere.example.invalid/"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(config.settings, "ollama_url", "https://model.example.invalid")
    ok, detail = OllamaProvider().healthy()
    assert ok is False and "not reachable" in detail
