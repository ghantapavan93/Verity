"""The whole path with a fake provider: upload → guidance → run → verified finding → memo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support import CONTRACT, upload_and_ask


def test_full_path_produces_a_verified_finding_and_a_memo(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    run = result["run"]
    assert run["stage"] == "complete", run
    assert len(run["findings"]) == 1
    finding = run["findings"][0]
    # Code, not the model, set the status: 15 days against "at least 30".
    assert finding["status"] == "needs_review"
    # The model's section handle became the section's own label before the finding was stored.
    assert "sec_" not in finding["conclusion"] and finding["conclusion"].endswith("at least 30 days. §2")
    assert finding["evidenceKind"] == "passage"
    span = finding["spans"][0]
    assert span["verified"] is True
    section = next(s for s in result["document"]["sections"] if s["id"] == span["sectionId"])
    assert section["heading"] == "Termination for Convenience"
    assert section["text"][span["start"] : span["end"]] == span["quote"]

    detail = client.get(f"/api/runs/{result['run_id']}/detail").json()
    assert [s["stage"] for s in detail["stages"]] == ["reading", "finding_evidence", "checking", "verifying", "complete"]
    assert detail["promptHash"] and detail["documentSha256"] and detail["candidates"]
    # Stage details describe real work, recorded after each stage ran.
    details = {s["stage"]: s["detail"] for s in detail["stages"]}
    assert details["reading"].endswith("4 sections")
    assert "candidate section" in details["finding_evidence"]  # "1 candidate section" on this four-section contract
    assert details["checking"].startswith("model answered")
    assert details["verifying"] == "1 of 1 quote verified"
    assert detail["verifiedSpans"] == 1 and detail["totalSpans"] == 1 and detail["reason"] is None
    assert detail["documentName"] == "agreement.txt" and detail["documentParseMs"] is not None
    assert detail["promptVersion"] == "answer-v2"

    memo = client.post("/api/memos", json={"runId": result["run_id"]})
    assert memo.status_code == 201, memo.text
    html = client.get(memo.json()["htmlUrl"])
    assert html.status_code == 200 and "fifteen (15) days" in html.text
    docx = client.get(memo.json()["docxUrl"])
    assert docx.status_code == 200 and docx.content[:2] == b"PK"


def test_paraphrased_evidence_leaves_the_run_unresolved(client: TestClient) -> None:
    client.provider.paraphrase = True
    result = upload_and_ask(client, "Can the customer terminate for convenience?")
    run = result["run"]
    assert run["stage"] == "unresolved"
    assert run["findings"] == []
    assert run["reason"] == "citations_unverified" and "withheld" in run["note"]
    # The proposal is kept and handed over as withheld, with the quote that did not verify.
    assert len(run["withheld"]) == 1 and run["withheld"][0]["spans"][0]["verified"] is False
    detail = client.get(f"/api/runs/{result['run_id']}/detail").json()
    assert detail["findings"][0]["status"] == "unresolved"
    assert {s["stage"]: s["detail"] for s in detail["stages"]}["verifying"] == "0 of 1 quote verified · 1 finding withheld"
    assert detail["rawOutput"]
    memo = client.post("/api/memos", json={"runId": result["run_id"]})
    assert memo.status_code == 409


def test_invalid_model_output_is_a_failed_run_not_a_verdict(client: TestClient) -> None:
    client.provider.garbage = True
    result = upload_and_ask(client, "Can the customer terminate for convenience?")
    run = result["run"]
    assert run["stage"] == "failed" and run["reason"] == "invalid_output"
    assert "did not return a valid result after 2 attempts" in run["error"]
    assert run["findings"] == [] and run["note"] is None
    assert len(client.provider.calls) == 2
    assert client.post("/api/memos", json={"runId": result["run_id"]}).status_code == 409


def test_events_replay_the_recorded_stages(client: TestClient) -> None:
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    with client.stream("GET", f"/api/runs/{result['run_id']}/events") as response:
        body = "".join(response.iter_text())
    stages = [json.loads(line[6:])["stage"] for line in body.splitlines() if line.startswith("data: ")]
    assert stages[0] == "reading" and stages[-1] in ("complete", "unresolved")


def test_bad_upload_and_missing_run_are_clear(client: TestClient) -> None:
    rejected = client.post("/api/documents", files={"file": ("sheet.xlsx", b"x", "application/octet-stream")})
    assert rejected.status_code == 422
    assert client.get("/api/runs/nope").status_code == 404


def test_lists_for_the_documents_findings_and_runs_surfaces(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    documents = client.get("/api/documents").json()
    assert documents[0]["id"] == result["document"]["id"] and documents[0]["sections"] == 4
    assert documents[0]["findings"] == 1 and documents[0]["lastRunAt"].endswith("+00:00")
    assert result["document"]["createdAt"] and result["document"]["parseMs"] is not None

    runs = client.get("/api/runs").json()
    assert runs[0]["id"] == result["run_id"]
    assert runs[0]["stage"] == "complete" and runs[0]["findings"] == 1 and runs[0]["hasGuidance"] is True
    assert runs[0]["documentName"] == "agreement.txt" and runs[0]["createdAt"]
    # SQLite returns naive datetimes; the API must still say they are UTC.
    assert runs[0]["createdAt"].endswith("+00:00") and documents[0]["createdAt"].endswith("+00:00")

    findings = client.get("/api/findings").json()
    assert len(findings) == 1
    record = findings[0]
    assert record["runId"] == result["run_id"] and record["status"] == "needs_review" and record["verifiedSpans"] == 1
    assert record["citations"] == ["§2"]
    assert client.get("/api/findings", params={"documentId": "other"}).json() == []

    detail = client.get(f"/api/runs/{result['run_id']}/detail").json()
    assert detail["options"]["seed"] == 42 and detail["options"]["retrieval_k"] == 6
    assert detail["stages"][0]["at"].endswith("+00:00") and detail["finishedAt"].endswith("+00:00")
    span = detail["findings"][0]["spans"][0]
    assert span["method"] == "exact" and span["citedSectionLabel"].startswith("sec_")
    assert detail["findings"][0]["statusSource"] == "computed_days"


def test_unresolved_findings_stay_off_the_findings_list(client: TestClient) -> None:
    client.provider.paraphrase = True
    upload_and_ask(client, "Can the customer terminate for convenience?")
    assert client.get("/api/findings").json() == []
    assert client.get("/api/runs").json()[0]["findings"] == 0


def test_experiment_records_come_from_results_json(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config
    from app.api import engineering

    missing = tmp_path / "nowhere" / "results.json"
    monkeypatch.setattr(config.settings, "experiments_results", missing)
    unavailable = client.get("/api/engineering/experiments").json()
    assert unavailable["available"] is False and "not found" in unavailable["detail"]
    monkeypatch.setattr(config.settings, "experiments_url", "https://example.org/ivo-experiments/")

    results = tmp_path / "results.json"
    results.write_text(
        json.dumps(
            {
                "page": {"title": "Three ideas I tried to kill", "author": "P", "repo_url": None},
                "repo_head": "6ad9bd6",
                "generated_at": "2026-09-27T20:00:00+00:00",
                "board": [
                    {"id": "b1", "code": "B1", "title": "Word structural integrity", "date": "27 Sep 2026", "expected": "x", "gate": "g", "observed": "o"}
                ],
                "baselines": [{"id": "exp1", "code": "Baseline 1", "title": "Governing-issue resolver", "date": "25 Sep 2026", "gate": "g", "observed": "o"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config.settings, "experiments_results", results)
    loaded = client.get("/api/engineering/experiments").json()
    assert loaded["available"] is True and loaded["repoHead"] == "6ad9bd6"
    assert loaded["pageUrl"] == "https://example.org/ivo-experiments/"
    assert loaded["board"][0]["code"] == "B1" and loaded["baselines"][0]["expected"] == ""
    assert engineering.results_path() == results


def test_the_same_question_reuses_the_run(client: TestClient) -> None:
    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    body = {"documentId": result["document"]["id"], "guidanceId": None, "question": "What law governs this agreement?"}
    again = client.post("/api/runs", json=body)
    assert again.status_code == 200
    assert again.json()["id"] == result["run_id"] and again.json()["reused"] is True
    assert len(client.get("/api/runs").json()) == 1
    other = client.post("/api/runs", json={**body, "question": "Who are the parties?"})
    assert other.status_code == 202 and other.json()["reused"] is False and other.json()["id"] != result["run_id"]


def test_a_failed_run_is_retried_not_reused(client: TestClient) -> None:
    client.provider.garbage = True
    first = upload_and_ask(client, "Can the customer terminate for convenience?", with_guidance=False)
    assert first["run"]["stage"] == "failed"
    client.provider.garbage = False
    retry = client.post(
        "/api/runs", json={"documentId": first["document"]["id"], "guidanceId": None, "question": "Can the customer terminate for convenience?"}
    )
    assert retry.status_code == 202 and retry.json()["id"] != first["run_id"]
    assert client.get(f"/api/runs/{retry.json()['id']}").json()["stage"] == "complete"


def test_interrupted_runs_are_failed_on_restart_and_become_retryable(client: TestClient) -> None:
    from datetime import timedelta

    from app.analysis.service import load_prompt
    from app.application.recover_runs import recover_interrupted_runs, stale_after_seconds
    from app.application.start_run import compute_fingerprint, run_options
    from app.db import SessionLocal
    from app.models import Run, utcnow

    result = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    question = "Is there an arbitration clause?"
    with SessionLocal() as session:
        # A run caught mid-flight by a restart: written as in progress and never finished. (A finished
        # run cannot be edited back into flight; the database forbids it.)
        stuck = Run(
            document_id=result["document"]["id"],
            question=question,
            stage="checking",
            provider="fake",
            model="fake-1",
            prompt_version="answer-v2",
            prompt_hash=load_prompt().sha256,
            document_sha256=result["document"]["sha256"],
            fingerprint=compute_fingerprint(result["document"]["id"], None, question, load_prompt().sha256, run_options()),
        )
        session.add(stuck)
        session.commit()
        stuck_id = stuck.id
        assert recover_interrupted_runs(session) == 0, "a run that started moments ago may be another process's live work"
        stuck.created_at = utcnow() - timedelta(seconds=stale_after_seconds() + 1)
        session.commit()
        assert recover_interrupted_runs(session) == 1
    after = client.get(f"/api/runs/{stuck_id}").json()
    assert after["stage"] == "failed" and after["reason"] == "internal_error" and "restarted" in after["error"]
    retry = client.post("/api/runs", json={"documentId": result["document"]["id"], "guidanceId": None, "question": question})
    assert retry.status_code == 202 and retry.json()["id"] != stuck_id, "a failed run does not block its fingerprint"


def test_an_answer_without_any_quote_is_not_a_finding(client: TestClient) -> None:
    client.provider.no_evidence = True
    result = upload_and_ask(client, "Can the customer terminate for convenience?", with_guidance=False)
    run = result["run"]
    # Either the schema rejects the empty evidence list (a failed run) or the service withholds it; never a shown finding.
    assert run["findings"] == []
    assert run["stage"] in ("unresolved", "failed")
    if run["stage"] == "unresolved":
        assert run["reason"] == "insufficient_evidence" and "without quoting" in run["note"]


def test_the_same_bytes_are_one_document(client: TestClient) -> None:
    first = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")})
    second = client.post("/api/documents", files={"file": ("renamed.txt", CONTRACT.encode("utf-8"), "text/plain")})
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["reused"] is False and second.json()["reused"] is True
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["sections"] == second.json()["sections"]
    assert len(client.get("/api/documents").json()) == 1


def test_the_citation_record_counts_what_the_verifier_did(client: TestClient) -> None:
    upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    client.provider.paraphrase = True
    upload_and_ask(client, "Can the customer terminate for convenience?")
    record = client.get("/api/engineering/citations").json()
    assert (record["runs"], record["completeRuns"], record["unresolvedRuns"]) == (2, 1, 1)
    assert (record["findings"], record["withheldFindings"]) == (2, 1)
    assert (record["spans"], record["verifiedSpans"]) == (2, 1)
    assert record["byMethod"] == {"exact": 1}
    assert record["firstRunAt"] and record["lastRunAt"]


def test_a_finding_can_be_reviewed_idempotently_and_reversibly(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    finding_id = result["run"]["findings"][0]["id"]
    body = {"verdict": "confirmed", "reviewer": "A. Reviewer", "note": None}

    first = client.post(f"/api/findings/{finding_id}/review", json=body)
    assert first.status_code == 201 and first.json()["review"]["verdict"] == "confirmed"
    again = client.post(f"/api/findings/{finding_id}/review", json=body)
    assert again.status_code == 200, "repeating the same decision writes nothing"
    listed = client.get("/api/findings").json()
    assert listed[0]["review"]["reviewer"] == "A. Reviewer" and listed[0]["review"]["at"]
    assert client.get(f"/api/runs/{result['run_id']}").json()["findings"][0]["review"]["verdict"] == "confirmed"
    assert client.get("/api/documents").json()[0]["reviewedFindings"] == 1

    cleared = client.post(f"/api/findings/{finding_id}/review", json={"verdict": "cleared", "reviewer": "A. Reviewer"})
    assert cleared.status_code == 201 and cleared.json()["review"] is None
    assert client.get("/api/findings").json()[0]["review"] is None
    assert client.post(f"/api/findings/{finding_id}/review", json={"verdict": "cleared", "reviewer": "A. Reviewer"}).status_code == 200
    assert client.get("/api/documents").json()[0]["reviewedFindings"] == 0

    dismissed = client.post(
        f"/api/findings/{finding_id}/review", json={"verdict": "dismissed", "reviewer": "B. Reviewer", "note": "Out of scope for this deal"}
    )
    assert dismissed.status_code == 201 and dismissed.json()["review"]["note"] == "Out of scope for this deal"
    memo = client.post("/api/memos", json={"runId": result["run_id"]}).json()
    assert "Dismissed by B. Reviewer" in client.get(memo["htmlUrl"]).text

    assert client.post("/api/findings/nope/review", json=body).status_code == 404
    client.provider.paraphrase = True
    withheld = upload_and_ask(client, "Can the customer terminate for convenience?")
    withheld_id = withheld["run"]["withheld"][0]["id"]
    assert client.post(f"/api/findings/{withheld_id}/review", json=body).status_code == 409, "a withheld finding is not an answer to adjudicate"
