"""Defects found by the hostile review of 2026-10-01, each held by a test: a document name is a name, not a path; a memo
survives control characters; a page count or a heading number cannot overflow into a 500; the experiments record names
no absolute path; a live owner's run is not declared stale while it waits for the model; a paragraph longer than a
section is split rather than kept whole."""

from __future__ import annotations

import io
import zipfile
from datetime import timedelta

from fastapi.testclient import TestClient

from app.application.recover_runs import recover_interrupted_runs
from app.db import SessionLocal
from app.ingest import ingest
from app.ingest.sections import MAX_SECTION_CHARS
from app.models import Run, RunStage, utcnow
from tests.support import CONTRACT, upload_and_ask


def test_a_document_name_with_path_parts_is_stored_as_its_base_name(client: TestClient) -> None:
    uploaded = client.post("/api/documents", files={"file": ("../../evil.txt", CONTRACT.encode("utf-8"), "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["name"] == "evil.txt"
    started = client.post("/api/runs", json={"documentId": uploaded.json()["id"], "guidanceId": None, "question": "What law governs this agreement?"})
    pack = client.get(f"/api/runs/{started.json()['id']}/evidence-pack")
    names = zipfile.ZipFile(io.BytesIO(pack.content)).namelist()
    assert "document/evil.txt" in names and all(".." not in n for n in names)


def test_a_memo_survives_control_characters_in_the_guidance_and_the_question(client: TestClient) -> None:
    uploaded = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")})
    guidance = client.post("/api/guidance", json={"text": "We can accept termination for convenience at 30\x0c days' notice or more.\x01"})
    assert guidance.status_code == 201, guidance.text
    started = client.post(
        "/api/runs",
        json={
            "documentId": uploaded.json()["id"],
            "guidanceId": guidance.json()["id"],
            "question": "How much notice\x0b does the customer need to give to terminate for convenience?",
        },
    )
    assert started.status_code == 202, started.text
    run = client.get(f"/api/runs/{started.json()['id']}").json()
    assert run["stage"] == "complete", run
    memo = client.post("/api/memos", json={"runId": run["id"]})
    assert memo.status_code == 201, memo.text
    assert client.get(memo.json()["docxUrl"]).status_code == 200


def test_an_absurd_heading_number_or_page_count_is_a_422_not_a_500(client: TestClient) -> None:
    text = "1" * 4301 + " Term\n\nThis Agreement commences on the Effective Date.\n\n2. Fees\n\nFees are due monthly."
    response = client.post("/api/documents", files={"file": ("numbers.txt", text.encode("utf-8"), "text/plain")})
    assert response.status_code in (201, 422), response.text
    if response.status_code == 201:
        assert all(len(s["number"]) <= 64 for s in response.json()["sections"])


def test_the_experiments_record_names_no_absolute_path(client: TestClient) -> None:
    body = client.get("/api/engineering/experiments").json()
    source = body.get("source") or ""
    assert ":\\" not in source and not source.startswith("/"), source


def test_a_run_whose_owner_is_alive_here_is_not_stale_while_it_waits(client: TestClient) -> None:
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    with SessionLocal() as session:
        run = session.get(Run, result["run_id"])
        assert run is not None and run.stage == "complete"
        # Rewind the record into a run that is still checking, opened by this process, an hour ago.
        session.execute(__import__("sqlalchemy").text("DROP TRIGGER IF EXISTS trg_runs_no_update_when_finished"))
        session.execute(__import__("sqlalchemy").text("DROP TRIGGER IF EXISTS trg_run_stages_no_update_when_finished"))
        session.execute(__import__("sqlalchemy").text("DROP TRIGGER IF EXISTS trg_run_stages_no_delete_when_finished"))
        session.query(RunStage).filter_by(run_id=run.id).filter(RunStage.stage != "reading").delete()
        run.stage = "checking"
        run.reason = None
        run.finished_at = None
        from app.runs.owner import this_process

        stage = RunStage(
            run_id=run.id, stage="checking", at=utcnow() - timedelta(hours=1), detail="against the question", status="running", owner=this_process().render()
        )
        session.add(stage)
        session.commit()
        recovered = recover_interrupted_runs(session, stale_after_s=60)
        session.refresh(run)
        assert recovered == 0 and run.stage == "checking", "a run whose process is alive on this host waits for its model call"


def test_a_paragraph_longer_than_a_section_is_split_not_kept_whole() -> None:
    sentence = "The Supplier shall provide the Services in accordance with the Specification and the Service Levels. "
    paragraph = (sentence * 200).strip()  # about 20,000 characters, no blank line
    parsed = ingest("long.txt", f"1. Services\n\n{paragraph}\n\n2. Fees\n\nFees are due monthly.".encode())
    assert all(len(s.text) <= MAX_SECTION_CHARS for s in parsed.sections), [len(s.text) for s in parsed.sections]
    assert sum(1 for s in parsed.sections if s.number == "1") >= 4
    assert "".join(s.text for s in parsed.sections if s.number == "1").replace(" ", "") == paragraph.replace(" ", "")
