"""A failure a reader sees is said in plain words; what the server knows about it goes to its log.

Found by the journey audit (2026-10-09): with the model offline a visitor read "Ollama request failed: [WinError
10061] No connection could be made …", and an internal error printed the exception as raised. Raw exception text can
carry the model endpoint's address (which health deliberately never publishes), file paths and OS detail. The
invariant: a provider or internal failure recorded on a run names what failed and the error's class, never its text.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider
from app.retrieval import hybrid
from app.runs import service as run_service
from tests.support import upload_and_ask
from tests.test_model_endpoint import PINNED, tags

SECRET_URL = "https://model-7f3a.example.invalid"
RAW = "[WinError 10061] No connection could be made because the target machine actively refused it"


def _fail_with(error: Exception) -> Callable[..., httpx.Response]:
    def post(url: str, json: dict[str, Any], timeout: float, headers: dict[str, str] | None = None) -> httpx.Response:
        raise error

    return post


def _tags(url: str, timeout: float, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(200, json=tags(PINNED), request=httpx.Request("GET", url))


REQUEST = httpx.Request("POST", f"{SECRET_URL}/api/chat")
FAILURES = [
    (httpx.ConnectError(RAW, request=REQUEST), "not reachable"),
    (httpx.ReadTimeout(f"timed out reading {SECRET_URL}", request=REQUEST), "did not answer in time"),
    (httpx.HTTPStatusError(f"Server error '500' for url '{SECRET_URL}/api/chat'", request=REQUEST, response=httpx.Response(500, request=REQUEST)), "HTTP 500"),
]


@pytest.mark.parametrize(("error", "words"), FAILURES)
def test_a_model_failure_names_what_failed_and_not_its_text(error: Exception, words: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "ollama_url", SECRET_URL)
    monkeypatch.setattr(httpx, "get", _tags)
    monkeypatch.setattr(httpx, "post", _fail_with(error))
    with pytest.raises(ProviderError) as raised:
        OllamaProvider().generate_json("system", "user", {})
    message = str(raised.value)
    assert words in message and type(error).__name__ in message, message
    for leak in ("WinError", "10061", "example.invalid", "/api/chat"):
        assert leak not in message, (leak, message)

    with pytest.raises(ProviderError) as embedded:
        hybrid.ollama_embed(["a clause"])
    assert words in str(embedded.value) and "example.invalid" not in str(embedded.value) and "WinError" not in str(embedded.value)


def test_an_internal_failure_on_a_run_says_so_without_the_exception_text(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(r"could not open C:\Verity\public-data\documents\abc.part (WinError 32)")

    monkeypatch.setattr(run_service, "decide", broken)
    run = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)["run"]
    assert run["stage"] == "failed" and run["reason"] == "internal_error"
    assert "RuntimeError" in run["error"] and "Ask the question again" in run["error"], run["error"]
    for leak in ("Verity", "public-data", "WinError", ".part"):
        assert leak not in run["error"], (leak, run["error"])
