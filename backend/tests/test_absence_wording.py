"""What the product says when the model did not find a point, and when retrieval ranked nothing.

The model is handed a few sections (six by default). Prompt rule 8 tells it to word an absence as "not found in the
sections reviewed"; of 211 recorded "missing" findings on 2026-10-02, 53 worded it as a fact about the agreement
("The contract does not provide for termination for convenience"), and the product showed that sentence as the
finding. The model's sentence is still the record and is still shown, as the model's. What the product says in its
own voice, on the card, in the findings list, in the explanation, in the memo and in the pack, is only that the model
did not find the point in the sections it was given. And whether those sections were chosen for the question at all
is a field of the run, not a sentence on a stage."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import NOT_FOUND_CONCLUSION, Finding, Run
from app.providers.base import Generation
from tests.support import CONTRACT

ABSOLUTE = "The contract does not provide for an uptime commitment. No service levels apply."
CLOSEST = "This Agreement is governed by the laws of the State of Delaware."


def answer_with(client: TestClient, monkeypatch: pytest.MonkeyPatch, payload_for: Callable[[dict[str, str]], dict[str, Any]]) -> None:
    def generate(system: str, user: str, schema: dict[str, Any]) -> Generation:
        labels = {line.split("] ", 1)[1].strip(): line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[sec_")}
        return Generation(text=json.dumps(payload_for(labels)), input_tokens=10, output_tokens=10, latency_ms=1.0, model="fake-1")

    monkeypatch.setattr(client.provider, "generate_json", generate)


def ask(client: TestClient, question: str) -> dict[str, Any]:
    uploaded = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")})
    assert uploaded.status_code in (200, 201), uploaded.text
    started = client.post("/api/runs", json={"documentId": uploaded.json()["id"], "guidanceId": None, "question": question})
    assert started.status_code == 202, started.text
    detail: dict[str, Any] = client.get(f"/api/runs/{started.json()['id']}/detail").json()
    return detail


def missing_finding(labels: dict[str, str]) -> dict[str, Any]:
    return {
        "findings": [
            {
                "topic": "Uptime commitment",
                "conclusion": ABSOLUTE,
                "status_hint": "missing",
                "evidence": [{"section_id": labels["3 Governing Law"], "quote": CLOSEST}],
                "guidance_reference": None,
                "observed": None,
                "required": None,
                "suggested_position": None,
            }
        ],
        "insufficient_evidence": False,
        "note": None,
    }


def test_a_point_not_found_is_said_in_the_products_words_everywhere_and_in_the_models_only_as_the_models(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    answer_with(client, monkeypatch, missing_finding)
    detail = ask(client, "Which law governs, and does the Provider commit to an uptime percentage?")
    assert detail["stage"] == "complete", detail
    run_id = detail["id"]

    finding = detail["findings"][0]
    assert finding["status"] == "missing" and finding["evidenceKind"] == "coverage"
    assert finding["conclusion"] == NOT_FOUND_CONCLUSION == "The model did not find this in the sections it was given."
    assert finding["modelConclusion"] == ABSOLUTE, "the model's sentence is kept, and named as the model's"

    record = next(f for f in client.get("/api/findings").json() if f["runId"] == run_id)
    assert record["conclusion"] == NOT_FOUND_CONCLUSION

    explanation = client.get(f"/api/runs/{run_id}/explanation").json()
    assert explanation["findings"][0]["conclusion"] == NOT_FOUND_CONCLUSION
    assert explanation["proposals"][0]["conclusion"] == ABSOLUTE, "what the model proposed is still what it proposed"

    memo = client.post("/api/memos", json={"runId": run_id}).json()
    html = client.get(memo["htmlUrl"]).text
    assert NOT_FOUND_CONCLUSION in html and "does not provide for an uptime commitment" not in html
    assert (
        "Sections read" in html and "chosen by retrieval for the question" in html and "Nothing in this memo is a statement about the other sections." in html
    )

    pack = zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/evidence-pack").content))
    packed = json.loads(pack.read("findings.json"))[0]
    assert packed["conclusion"] == ABSOLUTE and packed["shown_conclusion"] == NOT_FOUND_CONCLUSION
    assert json.loads(pack.read("run.json"))["retrieval"] == {"mode": "lexical_match", "requested_k": 6, "returned": len(detail["candidates"])}
    assert "`conclusion` is the model's own sentence" in pack.read("README.txt").decode("utf-8")

    with SessionLocal() as session:  # the record itself is the model's sentence, untouched
        stored = session.query(Finding).filter_by(run_id=run_id).one()
        assert stored.conclusion == ABSOLUTE and stored.shown_conclusion == NOT_FOUND_CONCLUSION


def test_a_finding_the_model_did_find_keeps_its_own_conclusion(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def found(labels: dict[str, str]) -> dict[str, Any]:
        payload = missing_finding(labels)
        payload["findings"][0] |= {"topic": "Governing law", "conclusion": "Delaware law governs.", "status_hint": "pass"}
        return payload

    answer_with(client, monkeypatch, found)
    finding = ask(client, "Which law governs this agreement?")["findings"][0]
    assert finding["conclusion"] == finding["modelConclusion"] == "Delaware law governs."


def test_when_the_model_reports_nothing_to_quote_the_note_is_the_products_not_the_models(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    answer_with(client, monkeypatch, lambda labels: {"findings": [], "insufficient_evidence": True, "note": "The agreement contains no uptime commitment."})
    detail = ask(client, "Which law governs, and does the Provider commit to an uptime percentage?")
    assert (detail["stage"], detail["reason"]) == ("unresolved", "insufficient_evidence")
    assert detail["note"].startswith("The model did not find a passage that answers this in the sections it was given. Sections searched: ")
    assert "contains no uptime commitment" not in detail["note"]
    assert "contains no uptime commitment" in detail["rawOutput"], "the model's own note is still on the record, as its output"


def test_opening_sections_handed_over_for_want_of_a_match_are_called_that_in_every_projection(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def from_the_opening(labels: dict[str, str]) -> dict[str, Any]:
        payload = missing_finding(labels)
        payload["findings"][0] |= {"topic": "Governing law", "conclusion": "Delaware law governs.", "status_hint": "pass"}
        return payload

    answer_with(client, monkeypatch, from_the_opening)
    detail = ask(client, "zzqx wvvk")  # no word of it is in the agreement
    assert detail["stage"] == "complete" and detail["retrievalMode"] == "opening_fallback"
    assert (detail["sectionsRead"], detail["sectionsRequested"]) == (4, 6)
    run_id = detail["id"]
    assert client.get(f"/api/runs/{run_id}").json()["retrievalMode"] == "opening_fallback"
    assert client.get(f"/api/runs/{run_id}/explanation").json()["retrievalMode"] == "opening_fallback"
    html = client.get(client.post("/api/memos", json={"runId": run_id}).json()["htmlUrl"]).text
    assert "retrieval ranked no section for this question, so these are the opening sections, not ones chosen for it" in html
    assert "chosen by retrieval for the question" not in html
    pack = zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/evidence-pack").content))
    assert json.loads(pack.read("run.json"))["retrieval"]["mode"] == "opening_fallback"


def test_a_run_recorded_before_the_mode_was_a_field_claims_nothing_about_how_its_sections_were_chosen(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.memo.service import reading_line

    answer_with(client, monkeypatch, missing_finding)
    detail = ask(client, "Which law governs, and does the Provider commit to an uptime percentage?")
    with SessionLocal() as session:
        run = session.get(Run, detail["id"])
        assert run is not None and run.document.sections, "loaded before the run is detached"
        session.expunge(run)
        run.retrieval_mode = None  # as on every run recorded before 2026-10-02; the stored row is not touched
        assert "chosen by retrieval" not in reading_line(run) and "opening sections" not in reading_line(run)
        assert reading_line(run).endswith("Nothing in this memo is a statement about the other sections.")
