"""What the one operator reads in the log: why a run ended, why a request was refused, the model's time apart from the
queue's, and which model build answered (ops audit, 2026-10-19).

Before this, an unverified quote and an answer with no evidence both ended on the same "stage=unresolved … status=ok"
line, five different limits answered a bare 429, the checking stage's time mixed the queue with the model, and an Ollama
update or a model pull changed answers with no line saying so. Each test asks the log the question an operator would.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.errors import Busy, TooManyRequests
from app.providers.ollama import OllamaProvider
from tests.support import upload_and_ask
from tests.test_relations_oracle import OracleModel


def _lines(caplog: pytest.LogCaptureFixture, needle: str) -> list[str]:
    return [record.getMessage() for record in caplog.records if needle in record.getMessage()]


def test_a_finished_run_says_why_it_ended(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    client.app.state.provider = OracleModel(  # type: ignore[attr-defined]
        {"conclusion": "Thirty days.", "quotes": ["a sentence this contract does not contain anywhere"]}
    )
    with caplog.at_level(logging.INFO, logger="app.runs.service"):
        run_id = upload_and_ask(client, "What notice applies to termination for convenience?", with_guidance=False)["run_id"]
    (ended,) = _lines(caplog, f"run_id={run_id} document_id=")[-1:]
    assert "stage=unresolved" in ended and ended.endswith("reason=citations_unverified"), ended


def test_control_a_stage_that_does_not_end_the_run_names_no_reason(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.runs.service"):
        run_id = upload_and_ask(client, "What notice applies to termination for convenience?")["run_id"]
    moving = [line for line in _lines(caplog, f"run_id={run_id} document_id=") if "stage=complete" not in line]
    assert moving and not [line for line in moving if "reason=" in line]


def test_the_model_time_and_the_queue_time_are_one_line(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.runs.service"):
        run_id = upload_and_ask(client, "What notice applies to termination for convenience?")["run_id"]
    (line,) = _lines(caplog, f"run_id={run_id} model_ms=")
    fields = dict(pair.split("=", 1) for pair in line.split())
    assert {"model_ms", "queue_ms", "queue_depth", "attempts", "rounds"} <= fields.keys()
    assert float(fields["model_ms"]) >= 0 and float(fields["queue_ms"]) >= 0


@pytest.mark.parametrize("error", [TooManyRequests("This workspace has started its runs for today.", 60), Busy("The store is busy.", 2)])
def test_a_refusal_names_what_refused(client: TestClient, caplog: pytest.LogCaptureFixture, error: Exception) -> None:
    def refuse() -> None:
        raise error

    client.app.add_api_route("/api/test-refusal", refuse)  # type: ignore[attr-defined]
    with caplog.at_level(logging.WARNING, logger="app"):
        response = client.get("/api/test-refusal")
    assert response.status_code in (429, 503) and response.headers.get("retry-after")
    (line,) = _lines(caplog, "refused path=/api/test-refusal")
    assert f"kind={type(error).__name__}" in line and str(error) in line


class _Answer:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body

    def json(self) -> dict[str, Any]:
        return self.body

    def raise_for_status(self) -> None:
        return None


def test_the_model_build_is_named_at_start(monkeypatch: pytest.MonkeyPatch) -> None:
    answers: dict[str, dict[str, Any]] = {
        "/api/version": {"version": "0.40.6"},
        "/api/tags": {"models": [{"name": "qwen3:8b", "digest": "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41"}]},
    }
    provider = OllamaProvider(model="qwen3:8b", base_url="http://127.0.0.1:11434")
    monkeypatch.setattr(provider, "_send", lambda method, url, timeout, payload=None: _Answer(answers[url.removeprefix(provider.base_url)]))
    assert provider.describe_build() == "server_version=0.40.6 model=qwen3:8b build=500a1f067a9f"


def test_control_a_model_server_that_is_down_is_named_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider(model="qwen3:8b", base_url="http://127.0.0.1:11434")

    def down(method: str, url: str, timeout: float, payload: dict[str, Any] | None = None) -> _Answer:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(provider, "_send", down)
    assert provider.describe_build() == "model endpoint not reachable at start (ConnectError)"
