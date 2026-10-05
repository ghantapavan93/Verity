"""Why this answer: the explanation of a run is a projection of the record and nothing else.

The model's proposal comes from the stored raw output by ordinal or is reported as not reconstructable; a
SourceMatch says whether its offsets lie inside the ContextSlice the model saw; the policy evaluation is the
recorded status, source and sentence; a reconstruction that fails is shown, not hidden.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.application.reconstruct_input as reconstruct_module
from app import config
from app.analysis.service import PromptPackage, load_prompt
from app.application.explain_run import PROPOSAL_NOT_RECONSTRUCTABLE
from app.db import SessionLocal
from app.hashing import sha256_text
from app.ingest import PARSER_VERSION
from app.models import Section
from tests.support import CONTRACT, upload_and_ask

QUESTION = "How much notice does the customer need to give to terminate for convenience?"

# Policy v3: a day comparison says what it did not establish.
SUBJECT = "; that the quoted period and the guidance concern the same point is the model's reading, not code's"


def explanation(client: TestClient, run_id: str) -> dict[str, Any]:
    response = client.get(f"/api/runs/{run_id}/explanation")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def finding_conclusion(out: dict[str, Any]) -> str:
    return str(out["findings"][0]["conclusion"])


def test_the_explanation_is_the_record_layer_by_layer(client: TestClient) -> None:
    result = upload_and_ask(client, QUESTION)
    out = explanation(client, result["run_id"])
    assert out["runId"] == result["run_id"] and out["stage"] == "complete"

    reading = out["reading"]
    assert reading["readerVersion"] == PARSER_VERSION and reading["sections"] == 4 and reading["documentSha256"] == sha256_text(CONTRACT)
    assert reading["coverage"]["source"] == "persisted" and reading["coverage"]["readerVersion"] == PARSER_VERSION
    assert reading["notRead"] == [], "a .txt reading has one part, the whole file, and it was read"
    assert reading["recordedSectionsHash"], "the reading stage's output hash names the sections' text"

    # Retrieval: rank is the order the model saw; every candidate carries the slice the prompt carried.
    assert [c["rank"] for c in out["retrieval"]] == list(range(1, len(out["retrieval"]) + 1))
    assert all(c["sliceStart"] == 0 and c["sliceEnd"] == c["characters"] and c["truncated"] is False for c in out["retrieval"])

    rebuilt = out["reconstruction"]
    assert rebuilt["reconstructable"] is True and rebuilt["problem"] is None
    assert rebuilt["recordedInputSha256"] == rebuilt["rebuiltInputSha256"]
    assert rebuilt["windowChars"] == config.settings.section_window == 6000 and rebuilt["charactersOutsideContext"] == 0
    assert rebuilt["hasGuidance"] is True and rebuilt["promptVersion"] == "answer-v2" and rebuilt["model"] == "fake-1"

    # The proposal is the model's own words, with the hint the model gave, not the finding's status.
    assert out["proposalsProblem"] is None and len(out["proposals"]) == 1
    proposal = out["proposals"][0]
    assert proposal["ordinal"] == 0 and proposal["statusHint"] == "pass"
    assert proposal["observed"] == "15 days' written notice" and proposal["required"] == "at least 30 days"
    cited = proposal["evidence"][0]["citedLabel"]
    assert cited.startswith("sec_") and proposal["conclusion"].endswith(f"[{cited}]"), "the proposal keeps the model's handle; the finding rewrote it"
    assert "sec_" not in finding_conclusion(out)

    finding = out["findings"][0]
    assert finding["ordinal"] == 0 and finding["status"] == "needs_review" and finding["shown"] is True
    match = finding["sourceMatches"][0]
    assert match["verified"] is True and match["method"] == "exact" and match["matchCount"] == 1 and match["relocated"] is False
    assert match["citedLabel"] == cited and match["locatedLabel"] == cited and match["locatedHeading"] == "§2 · Termination for Convenience"
    assert match["insideModelVisibleContext"] is True
    policy = finding["recordedPolicyEvaluation"]
    assert policy["status"] == "needs_review" and policy["statusSource"] == "computed_days" and policy["deterministic"] is True
    assert policy["statusReason"] == "the contract provides 15 calendar days; the guidance requires at least 30 calendar days" + SUBJECT

    repro = out["reproducibility"]
    assert repro["inputMatches"] is True and repro["recordedInputSha256"] == rebuilt["recordedInputSha256"]
    assert repro["evidencePackPath"] == f"/api/runs/{result['run_id']}/evidence-pack"


def test_a_quote_relocated_to_another_candidate_says_cited_and_located(client: TestClient) -> None:
    client.provider.cite_wrong_section = True
    result = upload_and_ask(client, QUESTION)
    out = explanation(client, result["run_id"])
    match = out["findings"][0]["sourceMatches"][0]
    assert match["verified"] is True and match["relocated"] is True and match["method"] == "relocated:exact"
    assert match["citedLabel"] != match["locatedLabel"], (match["citedLabel"], match["locatedLabel"])
    assert match["locatedHeading"] == "§2 · Termination for Convenience"
    # The proposal still carries the label the model wrote; the SourceMatch carries where the quote was found.
    assert out["proposals"][0]["evidence"][0]["citedLabel"] == match["citedLabel"]
    assert match["insideModelVisibleContext"] is True


def test_inside_the_model_visible_context_is_decided_by_the_slice_not_by_a_constant(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    result = upload_and_ask(client, QUESTION)
    before = explanation(client, result["run_id"])
    assert before["findings"][0]["sourceMatches"][0]["insideModelVisibleContext"] is True

    # If the slice the model saw had been shorter than the located span, the span would be outside it, whatever
    # the window constant says. The slice is the authority; the run itself is untouched.
    original = reconstruct_module.context_slice

    def shorter(label: str, section: Section, rank: int, window: int = 5000) -> reconstruct_module.ContextSlice:
        piece = original(label, section, rank, window)
        return reconstruct_module.ContextSlice(piece.label, piece.section_id, piece.rank, piece.start, min(piece.end, 10), True, piece.content_sha256)

    monkeypatch.setattr(reconstruct_module, "context_slice", shorter)
    after = explanation(client, result["run_id"])
    match = after["findings"][0]["sourceMatches"][0]
    assert match["start"] >= 0 and match["end"] > 10
    assert match["insideModelVisibleContext"] is False
    assert all(c["truncated"] is True and c["sliceEnd"] == 10 for c in after["retrieval"])


def test_a_status_taken_from_the_hint_says_there_was_no_policy_evaluation(client: TestClient) -> None:
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    out = explanation(client, result["run_id"])
    policy = out["findings"][0]["recordedPolicyEvaluation"]
    assert policy["statusSource"] == "model_hint" and policy["deterministic"] is False and policy["statusReason"] is None
    assert policy["summary"].startswith("no deterministic policy evaluation")
    assert out["proposals"][0]["statusHint"] == "pass" and out["findings"][0]["status"] == "pass"


def test_a_historical_run_whose_raw_output_does_not_fit_is_reported_not_guessed(client: TestClient) -> None:
    result = upload_and_ask(client, QUESTION)
    with SessionLocal() as session:
        # An older run whose stored output predates the shape the model is asked for today. The run is finished and
        # immutable, so the row is rewritten below the triggers, as a migration of the past would be.
        session.execute(text("DROP TRIGGER IF EXISTS trg_runs_no_update_when_finished"))
        session.execute(
            text("UPDATE runs SET raw_output = :raw WHERE id = :id"), {"raw": json.dumps({"answers": [{"text": "old shape"}]}), "id": result["run_id"]}
        )
        session.commit()
    out = explanation(client, result["run_id"])
    assert out["proposals"] == [] and out["proposalsProblem"] == PROPOSAL_NOT_RECONSTRUCTABLE
    # Everything the record still carries is still explained: the finding, its SourceMatch and its recorded status.
    assert out["findings"][0]["sourceMatches"][0]["verified"] is True
    assert out["findings"][0]["recordedPolicyEvaluation"]["statusSource"] == "computed_days"


def test_a_proposal_that_does_not_line_up_with_the_findings_is_not_correlated(client: TestClient) -> None:
    result = upload_and_ask(client, QUESTION)
    with SessionLocal() as session:
        session.execute(text("DROP TRIGGER IF EXISTS trg_runs_no_update_when_finished"))
        parsed = json.loads(session.execute(text("SELECT raw_output FROM runs WHERE id = :id"), {"id": result["run_id"]}).scalar_one())
        parsed["findings"].append(dict(parsed["findings"][0], topic="A second finding the record never stored"))
        session.execute(text("UPDATE runs SET raw_output = :raw WHERE id = :id"), {"raw": json.dumps(parsed), "id": result["run_id"]})
        session.commit()
    out = explanation(client, result["run_id"])
    assert out["proposals"] == [] and out["proposalsProblem"] == PROPOSAL_NOT_RECONSTRUCTABLE


def test_a_failed_reconstruction_is_shown_not_hidden(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    result = upload_and_ask(client, QUESTION)
    original = load_prompt("answer-v2")

    def rewritten(version: str | None = None) -> PromptPackage:
        rewritten_text = original.system + "\n\nA rule added after the run."
        return PromptPackage(version=original.version, system=rewritten_text, sha256=sha256_text(rewritten_text))

    monkeypatch.setattr(reconstruct_module, "load_prompt", rewritten)
    out = explanation(client, result["run_id"])
    rebuilt = out["reconstruction"]
    assert rebuilt["reconstructable"] is False and "rewritten since the run" in rebuilt["problem"]
    assert rebuilt["charactersOutsideContext"] is None
    assert all(c["truncated"] is None and c["sliceEnd"] is None for c in out["retrieval"]), "no slice is claimed for an input that could not be rebuilt"
    assert out["findings"][0]["sourceMatches"][0]["insideModelVisibleContext"] is None
    assert out["reproducibility"]["inputMatches"] is False
    # The proposal and the recorded status do not depend on the reconstruction.
    assert out["proposals"][0]["statusHint"] == "pass" and out["findings"][0]["recordedPolicyEvaluation"]["statusSource"] == "computed_days"


def test_an_unknown_run_is_a_404(client: TestClient) -> None:
    assert client.get("/api/runs/nope/explanation").status_code == 404
