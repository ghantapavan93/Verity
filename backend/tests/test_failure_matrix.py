"""The failure matrix: what the system does when something goes wrong. One test per row.

Rows proven elsewhere: invalid model output → failed run, never a finding (test_api_flow);
fabricated quote → finding withheld (test_api_flow); one changed digit → verifier rejects
(test_spans); duplicate POST → the same run (test_api_flow); SSE replays recorded stages
(test_api_flow); reload restores a finished run from the URL (useUrlState.test.tsx).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db as db_module
from app.analysis import service as analysis_service
from app.application import ingest_document as ingest_module
from app.application.start_run import start_run
from app.ingest import PARSER_VERSION
from app.runs.service import execute_run
from tests.support import CONTRACT, upload_and_ask


def test_provider_unavailable_is_a_failed_run_that_says_why(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_service, "PROVIDER_RETRY_DELAY_S", 0.0)
    client.provider.fail_always = True
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    run = result["run"]
    assert run["stage"] == "failed" and run["reason"] == "provider_error" and "not reachable" in run["error"]
    assert run["findings"] == [] and run["withheld"] == []
    assert len(client.provider.calls) == 2, "one retry, then the failure is the run's"
    stages = {s["stage"]: s for s in client.get(f"/api/runs/{result['run_id']}/detail").json()["stages"]}
    assert stages["checking"]["status"] == "failed" and stages["checking"]["errorCode"] == "provider_error"
    assert stages["failed"]["status"] == "failed" and stages["failed"]["completedAt"]


def test_a_transient_provider_failure_is_retried_once_and_recorded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_service, "PROVIDER_RETRY_DELAY_S", 0.0)
    client.provider.fail_once = True
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    assert result["run"]["stage"] == "complete"
    stages = {s["stage"]: s for s in client.get(f"/api/runs/{result['run_id']}/detail").json()["stages"]}
    assert stages["checking"]["attempt"] == 2 and "attempt 2" in stages["checking"]["detail"]


def test_every_stage_row_is_closed_with_timing_status_and_hashes(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    stages = client.get(f"/api/runs/{result['run_id']}/detail").json()["stages"]
    assert [s["stage"] for s in stages] == ["reading", "finding_evidence", "checking", "verifying", "complete"]
    for row in stages:
        assert row["status"] == "ok" and row["completedAt"] and row["durationMs"] is not None, row
    for row in stages[:-1]:
        assert len(row["inputHash"]) == 64 and len(row["outputHash"]) == 64, row["stage"]
    assert stages[0]["inputHash"] == result["document"]["sha256"], "reading consumes the document by hash"
    assert stages[2]["outputHash"] == stages[3]["inputHash"], "verifying consumes exactly what the model produced"


def test_malformed_and_empty_files_are_refused_at_the_boundary(client: TestClient) -> None:
    docx = client.post("/api/documents", files={"file": ("broken.docx", b"PK\x03\x04 this is not a package", "application/octet-stream")})
    assert docx.status_code == 422 and "not a readable .docx" in docx.json()["detail"]
    pdf = client.post("/api/documents", files={"file": ("broken.pdf", b"%PDF-1.4 garbage without a trailer", "application/pdf")})
    assert pdf.status_code == 422 and "not a readable PDF" in pdf.json()["detail"]
    empty = client.post("/api/documents", files={"file": ("empty.txt", b"", "text/plain")})
    assert empty.status_code == 422 and "no readable text" in empty.json()["detail"]


def test_an_oversized_upload_is_refused_before_parsing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_module, "MAX_UPLOAD_BYTES", 100)
    refused = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")})
    assert refused.status_code == 413


def test_a_memo_is_written_once_per_run(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    first = client.post("/api/memos", json={"runId": result["run_id"]})
    second = client.post("/api/memos", json={"runId": result["run_id"]})
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"] and first.json()["docxSha256"] == second.json()["docxSha256"]


def test_a_finished_run_cannot_be_changed_or_deleted_in_the_database(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    run_id = result["run_id"]
    statements = (
        "UPDATE runs SET note = 'edited' WHERE id = :id",
        "DELETE FROM runs WHERE id = :id",
        "UPDATE findings SET status = 'pass' WHERE run_id = :id",
        "DELETE FROM findings WHERE run_id = :id",
        "UPDATE run_stages SET detail = 'edited' WHERE run_id = :id",
        "UPDATE evidence_spans SET verified = 0 WHERE finding_id IN (SELECT id FROM findings WHERE run_id = :id)",
    )
    for statement in statements:
        with pytest.raises(IntegrityError, match="immutable"), db_module.engine.begin() as connection:
            connection.execute(text(statement), {"id": run_id})
    assert client.get(f"/api/runs/{run_id}").json()["stage"] == "complete"


def test_a_prompt_change_is_a_new_run_and_the_old_one_is_untouched(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    before = client.get(f"/api/runs/{result['run_id']}/detail").json()
    with db_module.SessionLocal() as session:
        started = start_run(session, result["document"]["id"], None, result["run"]["question"], client.provider, prompt_version="answer-v1")
        assert started.created and started.run.id != result["run_id"]
        execute_run(session, started.run.id, client.provider)
        other = client.get(f"/api/runs/{started.run.id}").json()
    assert other["promptVersion"] == "answer-v1" and other["promptHash"] != before["promptHash"]
    assert client.get(f"/api/runs/{result['run_id']}/detail").json() == before


def test_the_reader_version_travels_with_the_document(client: TestClient) -> None:
    uploaded = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    assert uploaded["parserVersion"] == PARSER_VERSION
