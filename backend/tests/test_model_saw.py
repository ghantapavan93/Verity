"""What the model was handed is what the record says it was handed, or the run does not answer.

Two ways the record could say more than happened, both found by tracing an upload end to end on 2026-10-02:

* a prompt larger than the context window. Left to its default the model server cuts the prompt and answers anyway
  (it answered "30 days" where the cut text said 47); the run's input hash would then name a message the model never
  fully read. The request now forbids the cut, the refusal becomes a failed run with the reason, and it is not retried.
* a question none of whose words occur in the document. The opening sections are handed over instead, and the stage
  used to read "6 candidate sections" as if they had been chosen. It now says what happened.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.analysis.schema import ANALYSIS_SCHEMA
from app.analysis.service import analyze, load_prompt
from app.providers.base import ContextOverflow, Generation, ProviderError
from app.providers.ollama import OllamaProvider

from .support import upload_and_ask

REFUSAL = (
    '{"error":"{\\"error\\":{\\"code\\":400,\\"message\\":\\"request (20695 tokens) exceeds the available context size (16384 tokens), '
    'try increasing it\\",\\"type\\":\\"exceed_context_size_error\\",\\"n_prompt_tokens\\":20695,\\"n_ctx\\":16384}}"}'
)


def test_the_model_server_is_told_not_to_cut_the_prompt_and_its_refusal_is_a_context_overflow(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict[str, Any]] = []

    def refuse(url: str, json: dict[str, Any], timeout: float) -> httpx.Response:
        sent.append(json)
        return httpx.Response(400, text=REFUSAL, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", refuse)
    with pytest.raises(ContextOverflow) as refused:
        OllamaProvider().generate_json("system", "user", ANALYSIS_SCHEMA)
    assert sent[0]["truncate"] is False and sent[0]["shift"] is False, "the server may neither cut the prompt nor shift it out while answering"
    assert "20,695 tokens" in str(refused.value) and "16,384" in str(refused.value)
    assert isinstance(refused.value, ProviderError), "to the run it is a provider failure, with its own sentence"


def test_any_other_refusal_stays_an_ordinary_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: httpx.Response(400, text='{"error":"model not found"}', request=httpx.Request("POST", url)))
    with pytest.raises(ProviderError) as failed:
        OllamaProvider().generate_json("system", "user", ANALYSIS_SCHEMA)
    assert not isinstance(failed.value, ContextOverflow)


class Overflowing:
    name, model = "fake", "fake-1"

    def __init__(self) -> None:
        self.calls = 0

    def healthy(self) -> tuple[bool, str]:
        return True, "fake"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        self.calls += 1
        raise ContextOverflow("The question, the guidance and the sections handed to the model come to 20,695 tokens; its context window holds 16,384.")


def test_a_prompt_that_does_not_fit_is_not_sent_twice() -> None:
    provider = Overflowing()
    with pytest.raises(ContextOverflow):
        analyze(provider, load_prompt("answer-v2"), "QUESTION: anything", retry_delay_s=0)
    assert provider.calls == 1, "the same prompt is the same size the second time"


def test_a_run_whose_prompt_does_not_fit_fails_with_the_reason_and_shows_no_finding(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    overflowing = Overflowing()
    monkeypatch.setattr(client.provider, "generate_json", overflowing.generate_json)
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    run = result["run"]
    assert run["stage"] == "failed" and run["reason"] == "provider_error" and run["findings"] == []
    assert "context window holds 16,384" in run["error"]
    assert overflowing.calls == 1


def test_the_run_says_how_many_sections_the_model_was_handed(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    detail = client.get(f"/api/runs/{result['run_id']}/detail").json()
    assert result["run"]["sectionsRead"] == len(detail["candidates"]) >= 1


def test_a_question_that_matches_nothing_is_said_to_have_matched_nothing(client: TestClient) -> None:
    client.provider.no_evidence = True  # the model, handed sections that were not chosen for the question, finds nothing
    result = upload_and_ask(client, "zzqx wvvk", with_guidance=False)
    detail = client.get(f"/api/runs/{result['run_id']}/detail").json()
    stages = {s["stage"]: s["detail"] for s in detail["stages"]}
    assert stages["finding_evidence"].startswith("retrieval ranked no section for this question; the opening ")
    assert "candidate section" not in stages["finding_evidence"]
    # And as a field, so no projection has to read the sentence to know.
    assert detail["retrievalMode"] == "opening_fallback" and detail["sectionsRequested"] == 6
    assert client.get(f"/api/runs/{result['run_id']}/explanation").json()["retrievalMode"] == "opening_fallback"
    assert result["run"]["stage"] != "complete", "sections that were not chosen for the question produced no answer"
