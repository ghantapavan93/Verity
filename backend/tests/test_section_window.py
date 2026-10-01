"""The section window is a run option. By default nothing is recorded and every earlier run keeps its fingerprint
and its reconstruction; under a wider window the prompt, the verifier's bound, the reconstruction, the explanation
and the pack all use the run's own recorded value. Measured before it existed: 6 of 111 CUAD-30 expert spans lie
beyond 5,000 characters in their section (docs/RETRIEVAL.md)."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import config
from app.analysis.service import MAX_SECTION_CHARS_IN_PROMPT, window_of
from app.application.reconstruct_input import reconstruct_input
from app.db import SessionLocal
from tests.support import CONTRACT, GUIDANCE

QUESTION = "How much notice does the customer need to give to terminate for convenience?"
FILLER = ("The parties record their mutual intentions in this paragraph, which carries no operative term. " * 60).strip()  # ~5,700 characters


def long_contract() -> str:
    """The test contract with the termination sentence pushed past the default window inside its section."""
    marker = "Customer may terminate this Agreement for convenience"
    assert marker in CONTRACT
    text = CONTRACT.replace(marker, FILLER + "\n\n" + marker, 1)
    assert text.index(marker) - text.index("2. Termination for Convenience") > MAX_SECTION_CHARS_IN_PROMPT
    return text


def ask(client: TestClient, text: str) -> dict[str, Any]:
    uploaded = client.post("/api/documents", files={"file": ("long-agreement.txt", text.encode("utf-8"), "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    guidance = client.post("/api/guidance", json={"text": GUIDANCE}).json()["id"]
    started = client.post("/api/runs", json={"documentId": uploaded.json()["id"], "guidanceId": guidance, "question": QUESTION})
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    out: dict[str, Any] = client.get(f"/api/runs/{run_id}/detail").json()
    return out


def test_window_of_defaults_for_runs_recorded_before_the_option() -> None:
    assert window_of(None) == MAX_SECTION_CHARS_IN_PROMPT
    assert window_of({"model": "qwen3:8b"}) == MAX_SECTION_CHARS_IN_PROMPT
    assert window_of({"section_window": 6000}) == 6000
    assert window_of({"section_window": "6000"}) == 6000


def test_the_default_window_is_recorded_and_an_old_run_reads_back_at_the_old_window(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    detail = ask(client, CONTRACT)
    assert detail["options"]["section_window"] == config.settings.section_window == 6000, "the measured default is on the record"
    assert client.get(f"/api/runs/{detail['id']}/explanation").json()["reconstruction"]["windowChars"] == 6000
    monkeypatch.setattr(config.settings, "section_window", MAX_SECTION_CHARS_IN_PROMPT)
    old = ask(client, CONTRACT + "\n\nA second copy for a second run.")
    assert "section_window" not in old["options"], "a run at the old window keeps the fingerprint every old run has"
    assert client.get(f"/api/runs/{old['id']}/explanation").json()["reconstruction"]["windowChars"] == MAX_SECTION_CHARS_IN_PROMPT


def test_a_wider_window_reaches_a_quote_the_default_cuts_off(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "section_window", 6000)
    detail = ask(client, long_contract())
    assert detail["options"]["section_window"] == 6000
    assert detail["stage"] == "complete", detail
    span = detail["findings"][0]["spans"][0]
    assert span["verified"] is True and span["start"] > MAX_SECTION_CHARS_IN_PROMPT, "the quote lies beyond the default window and was still located"
    run_id = str(detail["id"])

    explanation = client.get(f"/api/runs/{run_id}/explanation").json()
    assert explanation["reconstruction"]["windowChars"] == 6000 and explanation["reconstruction"]["reconstructable"] is True
    long_candidate = next(c for c in explanation["retrieval"] if c["characters"] > MAX_SECTION_CHARS_IN_PROMPT)
    assert long_candidate["truncated"] is False and long_candidate["sliceEnd"] == long_candidate["characters"]
    assert explanation["findings"][0]["sourceMatches"][0]["insideModelVisibleContext"] is True

    with SessionLocal() as session:
        rebuilt = reconstruct_input(session, run_id)
    assert rebuilt.matches, rebuilt.problem
    assert rebuilt.user is not None and "Customer may terminate this Agreement for convenience" in rebuilt.user

    pack = client.get(f"/api/runs/{run_id}/evidence-pack")
    assert pack.status_code == 200
    record = json.loads(zipfile.ZipFile(io.BytesIO(pack.content)).read("run.json"))
    assert record["verifier"]["window_chars"] == 6000 and record["model_input"]["prompt_window_chars"] == 6000
