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

from app.api import body_limit
from app.api.body_limit import SpoolFull
from app.application.explain_run import _queue_note
from app.errors import Busy, TooManyRequests
from app.models import RunStage
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


def test_an_unhandled_error_still_leaves_a_request_line(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    # uvicorn's access log is off in the deployment, so this line is the only one naming the request (fresh review).
    def broken() -> None:
        raise RuntimeError("a bug")

    client.app.add_api_route("/api/test-broken", broken)  # type: ignore[attr-defined]
    quiet = TestClient(client.app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="app"):
        assert quiet.get("/api/test-broken").status_code == 500
    (line,) = _lines(caplog, "path=/api/test-broken")
    assert "status=500" in line and "request_id=" in line


def test_a_body_refused_while_it_is_read_names_its_kind(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    def spool_full() -> None:
        raise SpoolFull()

    client.app.add_api_route("/api/test-spool", spool_full, methods=["POST"])  # type: ignore[attr-defined]
    with caplog.at_level(logging.WARNING, logger="app"):
        response = client.post("/api/test-spool")
    assert response.status_code == 503 and response.headers["retry-after"] == "5"
    (line,) = _lines(caplog, "refused path=/api/test-spool")
    assert "kind=SpoolFull" in line


def test_an_upload_refused_at_the_door_names_what_refused(client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(body_limit, "_gate_refusal", lambda scope: TooManyRequests("This demo workspace already holds 10 contracts.", 3600))
    with caplog.at_level(logging.WARNING, logger="app"):
        response = client.post("/api/documents", files={"file": ("agreement.txt", b"Terms.", "text/plain")})
    assert response.status_code == 429
    (line,) = _lines(caplog, "refused path=/api/documents")
    assert "kind=TooManyRequests" in line and "kind=body_limit" not in line


@pytest.mark.parametrize(
    ("detail", "note"),
    [
        ("model answered in 41 s · queued 12 s behind 3", "queued 12 s behind 3"),
        ("model answered in 69 s · attempt 2 · queued 12 s behind 3", "queued 12 s behind 3"),
        ("model answered in 69 s · attempt 2 · after a rejected first answer · queued 5 s behind 1", "queued 5 s behind 1"),
        ("model answered in 41 s · attempt 2", None),  # control: no wait, no note
    ],
)
def test_the_explanation_names_the_queue_wait_and_nothing_else(detail: str, note: str | None) -> None:
    # The explanation took everything after the first "·", so a retried answer showed "attempt 2 · queued 12 s behind 3"
    # as its queue wait (fresh review, 2026-10-21).
    assert _queue_note(RunStage(stage="checking", detail=detail)) == note


def test_a_missing_model_names_no_other_model_the_server_holds(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    # Health is answered to every visitor past the gate; the list of what else the model server holds is the operator's,
    # for the log (security audit, 2026-10-30).
    provider = OllamaProvider(model="qwen3:8b", base_url="http://127.0.0.1:11434")
    monkeypatch.setattr(provider, "_tags", lambda timeout: [{"name": "private-finetune:latest"}, {"name": "llama3:70b"}])
    with caplog.at_level(logging.WARNING, logger="app.providers.ollama"):
        ok, detail = provider.healthy()
    assert not ok and detail == "model qwen3:8b is not pulled"
    assert any("private-finetune:latest" in record.getMessage() for record in caplog.records)  # control: the operator still sees it


def test_health_asks_the_model_server_at_most_once_in_a_while(client: TestClient) -> None:
    # Every visitor's health check asked the model server for its whole list of models (security audit, 2026-10-30).
    calls: list[int] = []

    class Counting:
        name, model = "ollama", "qwen3:8b"

        def healthy(self) -> tuple[bool, str]:
            calls.append(1)
            return True, "qwen3:8b ready"

    client.app.state.provider = Counting()  # type: ignore[attr-defined]
    for _ in range(5):
        assert client.get("/api/health").json()["ok"] is True
    assert len(calls) == 1
