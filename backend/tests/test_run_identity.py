"""A run's identity carries the rules that decide its answer, and a run executes from what it recorded.

Two defects, both reproduced on 2026-10-02 before this file existed. After the status decision was fixed, a request
with the same document, guidance and question was still handed the run the old decision had made: 49 recorded runs
carried exactly the identity a new request would have. And a run created at six sections, executed after the
process's setting had become one, was handed one section with six on its record: execution read the environment, not
the run."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import config
from app import db as db_module
from app.analysis.service import load_prompt
from app.application.reconstruct_input import reconstruct_input
from app.application.start_run import compute_fingerprint, run_options, start_run
from app.db import SessionLocal
from app.goldens.service import Golden, run_for
from app.models import Document, EvidenceSpan, Finding, Run, Section
from app.providers.admission import AdmissionController, AdmittedProvider
from app.providers.base import Generation
from app.providers.ollama import OllamaProvider
from app.retrieval.lexical import RETRIEVAL_VERSION
from app.runs import service, versions
from app.runs.service import execute_run
from app.runs.status import POLICY_VERSION
from app.runs.versions import SEMANTIC_VERSIONS, stale_versions, without_versions
from app.verify.spans import VERIFIER_VERSION
from tests.support import CONTRACT, FakeProvider, upload_and_ask

QUESTION = "How much notice does the customer need to give to terminate for convenience?"


def test_the_versions_are_the_ones_the_rules_declare_and_every_run_records_them(client: TestClient) -> None:
    assert SEMANTIC_VERSIONS == {"policy_version": POLICY_VERSION, "verifier_version": VERIFIER_VERSION, "retrieval_version": RETRIEVAL_VERSION}
    result = upload_and_ask(client, QUESTION)
    options = client.get(f"/api/runs/{result['run_id']}/detail").json()["options"]
    assert {name: options[name] for name in SEMANTIC_VERSIONS} == SEMANTIC_VERSIONS


def test_the_same_request_is_reused_under_the_same_rules_and_asked_again_under_new_ones(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    first = upload_and_ask(client, QUESTION)
    body = {"documentId": first["document"]["id"], "guidanceId": client.post("/api/guidance", json={"text": "x"}).json()["id"], "question": QUESTION}
    body["guidanceId"] = client.get(f"/api/runs/{first['run_id']}/detail").json()["guidanceId"]
    again = client.post("/api/runs", json=body)
    assert again.status_code == 200 and again.json()["id"] == first["run_id"] and again.json()["reused"] is True
    recorded = client.get(f"/api/runs/{first['run_id']}/detail").json()

    for name in SEMANTIC_VERSIONS:  # each version alone makes the request a new run
        monkeypatch.setitem(versions.SEMANTIC_VERSIONS, name, SEMANTIC_VERSIONS[name] + "-next")
        fresh = client.post("/api/runs", json=body)
        assert fresh.status_code == 202 and fresh.json()["id"] != first["run_id"], name
        assert client.get(f"/api/runs/{fresh.json()['id']}/detail").json()["options"][name].endswith("-next")
        # Under those rules the new run is the one that is reused.
        assert client.post("/api/runs", json=body).json()["id"] == fresh.json()["id"]
        monkeypatch.undo()

    # The old run is what it was, field for field, and is once more the answer under the rules it was made with.
    assert client.get(f"/api/runs/{first['run_id']}/detail").json() == recorded
    assert client.post("/api/runs", json=body).json()["id"] == first["run_id"]


def started(client: TestClient, question: str = QUESTION) -> tuple[str, FakeProvider]:
    """A run created and not yet executed, with the provider it would be executed with."""
    uploaded = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")})
    assert uploaded.status_code in (200, 201), uploaded.text
    provider = FakeProvider()
    with SessionLocal() as session:
        run = start_run(session, uploaded.json()["id"], None, question, provider).run
        return run.id, provider


def test_a_run_created_under_other_rules_is_not_executed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id, provider = started(client)
    created_under = run_options()
    monkeypatch.setitem(versions.SEMANTIC_VERSIONS, "policy_version", "policy-v99")
    with SessionLocal() as session:
        execute_run(session, run_id, provider)
    run = client.get(f"/api/runs/{run_id}").json()
    assert (run["stage"], run["reason"]) == ("failed", "internal_error")
    assert f"policy version {POLICY_VERSION} then, policy-v99 now" in run["error"] and "ask again" in run["error"]
    assert provider.calls == [] and run["findings"] == [], "no model call and no finding under rules the run was not created for"
    assert stale_versions({}) != [], "a run that recorded no version is as stale as a run can be"
    assert stale_versions(created_under) == [f"policy version {POLICY_VERSION} then, policy-v99 now"]
    assert stale_versions(run_options()) == [], "a run created now is created under the rules that will execute it"


def test_a_run_executes_from_the_options_it_recorded_not_from_the_environment(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # A question three of the four sections share a word with, so how many are handed over depends on k.
    run_id, provider = started(client, "How does the customer terminate, when does the Agreement commence and which laws govern it?")
    with SessionLocal() as session:
        recorded = json.loads(session.get(Run, run_id).options_json)  # type: ignore[union-attr]
    assert recorded["retrieval_k"] == 6 and recorded["section_window"] == 6000 and "retrieval" not in recorded

    # The environment moves on before the worker gets to the run.
    monkeypatch.setattr(config.settings, "retrieval_k", 1)
    monkeypatch.setattr(config.settings, "section_window", 40)
    monkeypatch.setattr(config.settings, "retrieval_aliases", False)
    monkeypatch.setattr(config.settings, "retrieval", "hybrid")  # would call an embedding model that is not there
    monkeypatch.setattr(config.settings, "temperature", 0.9)
    with SessionLocal() as session:
        execute_run(session, run_id, provider)
        rebuilt = reconstruct_input(session, run_id)

    detail = client.get(f"/api/runs/{run_id}/detail").json()
    assert detail["stage"] == "complete", detail
    assert detail["options"] == recorded, "the record is what the run was created with"
    assert len(detail["candidates"]) >= 3 and detail["sectionsRequested"] == 6, "every section retrieval ranked, not the one the setting now asks for"
    assert detail["retrievalMode"] == "lexical_match"
    assert "upon fifteen (15) days’ written notice" in provider.calls[0], "the section was handed over whole, not cut at forty characters"
    assert rebuilt.matches, rebuilt.problem


class Bindable:
    """A provider with decoding settings of its own, as the Ollama one has."""

    name, model = "bindable", "default-model"

    def __init__(self, bound: Mapping[str, Any] | None = None) -> None:
        self.bound = bound
        self.inner = FakeProvider()

    def with_options(self, options: Mapping[str, Any]) -> Bindable:
        bound = Bindable(dict(options))
        BOUND.append(bound)
        return bound

    def healthy(self) -> tuple[bool, str]:
        return True, "ok"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        assert self.bound is not None, "the model was called through a provider that was never bound to the run's options"
        return self.inner.generate_json(system, user, schema)


BOUND: list[Bindable] = []


def test_the_model_is_called_with_the_decoding_settings_the_run_recorded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id, _ = started(client)
    monkeypatch.setattr(config.settings, "temperature", 0.9)
    monkeypatch.setattr(config.settings, "seed", 7)
    monkeypatch.setattr(config.settings, "num_ctx", 2048)
    BOUND.clear()
    with SessionLocal() as session:
        execute_run(session, run_id, Bindable())
    assert len(BOUND) == 1 and BOUND[0].bound == {"model": "qwen3:8b", "temperature": 0.0, "seed": 42, "num_ctx": 16384}
    assert client.get(f"/api/runs/{run_id}").json()["stage"] == "complete"


def test_an_ollama_provider_bound_to_a_run_keeps_that_runs_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    bound = OllamaProvider().with_options({"model": "qwen3:4b", "temperature": 0.0, "seed": 42, "num_ctx": 16384, "retrieval_k": 6})
    monkeypatch.setattr(config.settings, "temperature", 0.9)
    monkeypatch.setattr(config.settings, "num_ctx", 2048)
    assert bound.model == "qwen3:4b" and bound.options() == {"temperature": 0.0, "seed": 42, "num_ctx": 16384}
    assert OllamaProvider().options() == {"temperature": 0.9, "seed": 42, "num_ctx": 2048}, "an unbound provider is the process's defaults"
    controller = AdmissionController(limit=1)
    admitted = AdmittedProvider(OllamaProvider(), controller, "batch").with_options({"model": "qwen3:4b", "temperature": 0.0})
    assert (admitted.model, admitted.workload, admitted.controller) == ("qwen3:4b", "batch", controller)
    assert admitted.inner.options()["temperature"] == 0.0  # type: ignore[attr-defined]


def test_a_run_whose_alias_table_is_no_longer_the_codes_is_not_executed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id, provider = started(client)
    monkeypatch.setattr(service, "ALIASES_SHA256", "0" * 64)
    with SessionLocal() as session:
        execute_run(session, run_id, provider)
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["stage"] == "failed" and "alias table" in run["error"] and provider.calls == []


def test_the_golden_report_still_finds_a_recording_made_before_versions_and_prefers_one_made_since(client: TestClient) -> None:
    result = upload_and_ask(client, QUESTION, with_guidance=False)
    golden = Golden(id="gx", question="What law governs this agreement?", kind="present", sections=("3",), why="a recording to be found")
    prompt = load_prompt()
    with SessionLocal() as session:
        document = session.get(Document, result["document"]["id"])
        assert document is not None and run_for(session, document, golden, prompt) is None
        legacy_options = without_versions(run_options())
        assert not set(SEMANTIC_VERSIONS) & set(legacy_options)
        legacy = Run(
            document_id=document.id,
            question=golden.question,
            stage="complete",
            provider="fake",
            model="fake-1",
            prompt_version=prompt.version,
            prompt_hash=prompt.sha256,
            options_json=json.dumps(legacy_options, sort_keys=True),
            document_sha256=document.sha256,
            fingerprint=compute_fingerprint(document.id, None, golden.question, prompt.sha256, legacy_options),
        )
        session.add(legacy)
        session.commit()
        found = run_for(session, document, golden, prompt)
        assert found is not None and found.id == legacy.id, "the recording made before versions is what the report shows"
        # A request is never answered with it: it is not today's identity.
        current = start_run(session, document.id, None, golden.question, FakeProvider())
        assert current.created and current.run.id != legacy.id
        found = run_for(session, document, golden, prompt)
        assert found is not None and found.id == current.run.id, "a recording under today's rules supersedes it"


def test_a_store_made_before_policy_v2_upgrades_in_place_and_keeps_its_history(client: TestClient) -> None:
    """The schema and the rows as they were before 2026-10-02: no `retrieval_mode` column, a completed run with no
    version on its record, a pass that code computed. Proved on a copy of the real store too (DECISIONS.md)."""
    uploaded = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    prompt = load_prompt()
    legacy_options = without_versions(run_options())
    with SessionLocal() as session:
        section = session.query(Section).filter_by(document_id=uploaded["id"], number="2").one()
        quote = "Customer may terminate this Agreement for convenience upon fifteen (15) days’ written notice to Provider."
        old = Run(
            document_id=uploaded["id"],
            question=QUESTION,
            stage="complete",
            provider="ollama",
            model="qwen3:8b",
            prompt_version=prompt.version,
            prompt_hash=prompt.sha256,
            options_json=json.dumps(legacy_options, sort_keys=True),
            document_sha256=uploaded["sha256"],
            candidates_json=json.dumps([{"label": "sec_2", "section_id": section.id, "number": "2", "heading": section.heading}]),
            raw_output=json.dumps({"findings": [], "insufficient_evidence": False, "note": None}),
            fingerprint=compute_fingerprint(uploaded["id"], None, QUESTION, prompt.sha256, legacy_options),
            findings=[
                Finding(
                    ordinal=0,
                    topic="Termination for convenience",
                    status="pass",
                    status_source="computed_days",  # what code recorded before a pass had to be the model's too
                    conclusion="Customer may terminate on 15 days' notice.",
                    spans=[
                        EvidenceSpan(
                            ordinal=0,
                            section_id=section.id,
                            cited_section_label="sec_2",
                            start=section.text.index(quote),
                            end=section.text.index(quote) + len(quote),
                            quote=quote,
                            verified=True,
                            method="exact",
                        )
                    ],
                )
            ],
        )
        session.add(old)
        session.commit()
        old_id = old.id
    with db_module.engine.begin() as connection:
        connection.execute(text("ALTER TABLE runs DROP COLUMN retrieval_mode"))
        assert "retrieval_mode" not in {row[1] for row in connection.execute(text('PRAGMA table_info("runs")'))}
        recorded_row = connection.execute(text("SELECT * FROM runs WHERE id = :id"), {"id": old_id}).one()

    db_module.init_db(db_module.engine)  # what the application does when it starts

    with db_module.engine.begin() as connection:
        column = next(row for row in connection.execute(text('PRAGMA table_info("runs")')) if row[1] == "retrieval_mode")
        assert column[3] == 0, "nullable"
        upgraded_row = connection.execute(text("SELECT * FROM runs WHERE id = :id"), {"id": old_id}).one()
        assert tuple(upgraded_row)[: len(recorded_row)] == tuple(recorded_row) and upgraded_row[-1] is None, (
            "the old row is what it was, with nothing claimed for the new column"
        )
    detail = client.get(f"/api/runs/{old_id}/detail").json()
    assert (detail["stage"], detail["retrievalMode"], detail["options"]) == ("complete", None, legacy_options)
    assert (detail["findings"][0]["status"], detail["findings"][0]["statusSource"]) == ("pass", "computed_days"), "history reads as recorded"
    assert client.get(f"/api/runs/{old_id}/explanation").status_code == 200

    body = {"documentId": uploaded["id"], "guidanceId": None, "question": QUESTION}
    fresh = client.post("/api/runs", json=body)
    assert fresh.status_code == 202 and fresh.json()["id"] != old_id, "the same request under today's rules is a new run, not the old answer"
    again = client.post("/api/runs", json=body)
    assert again.status_code == 200 and again.json()["id"] == fresh.json()["id"] and again.json()["reused"] is True
    new = client.get(f"/api/runs/{fresh.json()['id']}/detail").json()
    assert {name: new["options"][name] for name in SEMANTIC_VERSIONS} == SEMANTIC_VERSIONS and new["retrievalMode"] == "lexical_match"
    assert client.get(f"/api/runs/{old_id}/detail").json() == detail, "and the old run is untouched by it"
