"""The exact model input of a run is a function of the record: it can be rebuilt and it hashes to what the
checking stage wrote. A prompt file rewritten in place is caught, not repaired."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.application.reconstruct_input as reconstruct_module
from app.analysis.service import MAX_SECTION_CHARS_IN_PROMPT, PromptPackage, load_prompt
from app.application.reconstruct_input import reconstruct_input
from app.db import SessionLocal
from app.hashing import sha256_text
from tests.support import upload_and_ask


def test_the_model_input_is_rebuilt_from_the_record_and_hashes_to_what_was_recorded(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    with SessionLocal() as session:
        rebuilt = reconstruct_input(session, result["run_id"])
    assert rebuilt.matches, rebuilt.problem
    assert rebuilt.user is not None and rebuilt.system is not None
    assert rebuilt.user.startswith("QUESTION: How much notice") and "LEGAL GUIDANCE: We can accept" in rebuilt.user
    assert rebuilt.input_sha256 == rebuilt.recorded_input_sha256 == sha256_text(load_prompt("answer-v2").sha256 + rebuilt.user)
    # Every candidate the model saw is a slice with its own hash; the fixture's sections are short, so none is truncated.
    assert rebuilt.slices and all(s.start == 0 and not s.truncated and s.end <= MAX_SECTION_CHARS_IN_PROMPT for s in rebuilt.slices)
    assert [s.rank for s in rebuilt.slices] == list(range(1, len(rebuilt.slices) + 1))
    assert "sec_" in rebuilt.slices[0].label


def test_a_prompt_rewritten_since_the_run_is_reported_not_repaired(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    original = load_prompt("answer-v2")

    def rewritten(version: str | None = None) -> PromptPackage:
        text = original.system + "\n\nA rule added after the run."
        return PromptPackage(version=original.version, system=text, sha256=sha256_text(text))

    monkeypatch.setattr(reconstruct_module, "load_prompt", rewritten)
    with SessionLocal() as session:
        rebuilt = reconstruct_input(session, result["run_id"])
    assert not rebuilt.matches and rebuilt.problem is not None and "rewritten since the run" in rebuilt.problem
    assert rebuilt.user is None, "no input is offered when the prompt it was built with is gone"


def test_a_run_that_never_reached_the_model_has_nothing_to_rebuild(client: TestClient) -> None:
    client.provider.fail_always = True
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    with SessionLocal() as session:
        rebuilt = reconstruct_input(session, result["run_id"])
    # The checking stage was entered (its input hash recorded) before the provider failed, so the input still rebuilds.
    assert rebuilt.recorded_input_sha256 is not None and rebuilt.matches, rebuilt.problem
