"""Two sentences a visitor reads, said right (blind contract stress test, 2026-10-16).

(1) Counts agree with their nouns. The reading stage said "1 pages · 16 sections" for a one-page reading. The invariant:
every count the run's stages print is followed by its noun in the number it takes ("1 page", "1 section").

(2) No exception's class name reaches a visitor. With the model endpoint down the answer read "The model could not
answer: the model endpoint is not reachable (ConnectError)", and /api/health, which is public, said the same. The class
is for whoever reads the server log, where it is written beside the plain sentence. The invariant: a message composed
from an exception that a visitor can read (a run's error, /api/health, an engineering record's detail) names what
happened in words and never the class; the log line carries the class.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.providers.base import Generation, ProviderError, failed_call
from app.providers.ollama import OllamaProvider
from tests.support import FakeProvider, upload_and_ask

CLASS_NAME = ("ConnectError", "ReadTimeout", "HTTPStatusError", "RequestError", "JSONDecodeError", "KeyError", "ValueError", "Exception")


def _visible(text: str) -> None:
    assert not any(name in text for name in CLASS_NAME), text


def test_a_one_page_one_section_reading_is_counted_in_the_singular(client: TestClient) -> None:
    from tests.test_running_lines import text_pdf

    pdf = text_pdf([["1. Term", "", "This Agreement lasts one year."]])
    document = client.post("/api/documents", files={"file": ("one.pdf", pdf, "application/pdf")}).json()
    client.app.state.provider = FakeProvider()  # type: ignore[attr-defined]
    run_id = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": "How long is the term?"}).json()["id"]
    stages = client.get(f"/api/runs/{run_id}/detail").json()["stages"]
    reading = next(s for s in stages if s["stage"] == "reading" and s.get("detail"))
    assert reading["detail"].startswith("1 page · ") and " pages" not in reading["detail"], reading["detail"]


def test_a_many_section_reading_keeps_the_plural(client: TestClient) -> None:
    stages = client.get(f"/api/runs/{upload_and_ask(client, 'What is the notice period?')['run_id']}/detail").json()["stages"]
    reading = next(s for s in stages if s["stage"] == "reading" and s.get("detail"))
    assert reading["detail"].endswith(" sections"), reading["detail"]


def test_a_failed_model_calls_class_goes_to_the_log(caplog: pytest.LogCaptureFixture) -> None:
    """test_failure_words holds the sentence (what failed, never the text or the class); here, the log keeps the class."""
    request = httpx.Request("POST", "http://127.0.0.1:9/api/chat")
    for error in (httpx.ConnectError("refused", request=request), httpx.RequestError("other", request=request)):
        with caplog.at_level(logging.WARNING):
            sentence = failed_call("The model could not answer", error)
        _visible(sentence)
        assert type(error).__name__ in caplog.text


def test_an_unreachable_endpoint_is_said_in_words_by_health_and_by_the_answer(caplog: pytest.LogCaptureFixture) -> None:
    provider = OllamaProvider(base_url="http://127.0.0.1:9", model="qwen3:8b")
    ok, detail = provider.healthy()
    assert not ok
    _visible(detail)
    with caplog.at_level(logging.WARNING), pytest.raises(ProviderError) as raised:
        provider.generate_json("system", "user", {"type": "object"})
    _visible(str(raised.value))
    assert "ConnectError" in caplog.text


def test_an_unreadable_engineering_record_names_no_class(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from app.api.engineering import load_contract_state, load_experiments

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        details = [load_experiments(broken).detail or "", load_contract_state(broken).detail or ""]
    for detail in details:
        _visible(detail)
        assert detail.endswith("unreadable")
    assert "JSONDecodeError" in caplog.text


def test_a_server_failure_names_no_class_to_the_reader(client: TestClient) -> None:
    class Broken(FakeProvider):
        def generate_json(self, system: str, user: str, schema: dict[str, object]) -> Generation:
            raise KeyError("a bug")

    client.app.state.provider = Broken()  # type: ignore[attr-defined]
    run = upload_and_ask(client, "What is the notice period?")["run"]
    assert run["stage"] == "failed"
    _visible(run["error"])
    assert run["error"].startswith("The server failed while answering this question")
