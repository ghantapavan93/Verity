"""A memo describes a run and the review state of its findings. The run cannot change; the reviews can, so a
later review earns a new memo and the earlier one stays what it was (found while tracing, 2026-09-29)."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from tests.support import upload_and_ask


def _custom_property(client: TestClient, docx_url: str, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(client.get(docx_url).content)) as package:
        custom = package.read("docProps/custom.xml").decode("utf-8")
    start = custom.index(f'name="{name}"')
    value_start = custom.index("<vt:lpwstr>", start) + len("<vt:lpwstr>")
    return custom[value_start : custom.index("</vt:lpwstr>", value_start)]


def test_a_review_after_the_memo_earns_a_new_memo_and_keeps_the_old_one(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    run = client.get(f"/api/runs/{result['run_id']}").json()
    first = client.post("/api/memos", json={"runId": result["run_id"]})
    assert first.status_code == 201 and first.json()["reviewHead"] == run["reviewHead"]
    again = client.post("/api/memos", json={"runId": result["run_id"]})
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"], "the same review state is the same memo"
    assert _custom_property(client, first.json()["docxUrl"], "workbench_review_head") == run["reviewHead"]

    finding_id = run["findings"][0]["id"]
    assert client.post(f"/api/findings/{finding_id}/review", json={"verdict": "confirmed", "reviewer": "A. Reviewer", "note": None}).status_code == 201
    reviewed = client.get(f"/api/runs/{result['run_id']}").json()
    assert reviewed["reviewHead"] != run["reviewHead"], "a review changes the run's review state"

    second = client.post("/api/memos", json={"runId": result["run_id"]})
    assert second.status_code == 201 and second.json()["id"] != first.json()["id"] and second.json()["reviewHead"] == reviewed["reviewHead"]
    assert "Confirmed by A. Reviewer" in client.get(second.json()["htmlUrl"]).text
    assert "Confirmed by A. Reviewer" not in client.get(first.json()["htmlUrl"]).text, "the earlier memo is what it was"
    assert client.get(first.json()["docxUrl"]).status_code == 200 and client.get(second.json()["docxUrl"]).status_code == 200
    assert first.json()["docxSha256"] != second.json()["docxSha256"]

    # An undo is a review too: the head moves on, and the memo written under the confirmed state is not reused.
    assert client.post(f"/api/findings/{finding_id}/review", json={"verdict": "cleared", "reviewer": "A. Reviewer", "note": None}).status_code == 201
    third = client.post("/api/memos", json={"runId": result["run_id"]})
    assert third.status_code == 201 and third.json()["id"] not in {first.json()["id"], second.json()["id"]}
