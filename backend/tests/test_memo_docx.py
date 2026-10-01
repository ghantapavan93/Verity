"""The Word memo is a traceable document: its properties name the run, every citation links to a
sources table inside the file, and every source links back to the run and finding in the workbench."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from app.memo.service import status_label
from tests.support import upload_and_ask


def test_the_docx_memo_carries_its_record_and_its_links(client: TestClient) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    memo = client.post("/api/memos", json={"runId": result["run_id"]}).json()
    data = client.get(memo["docxUrl"]).content
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        names = set(package.namelist())
        assert "docProps/custom.xml" in names, "the custom-properties part is written"
        custom = package.read("docProps/custom.xml").decode("utf-8")
        assert 'name="workbench_run_id"' in custom and result["run_id"] in custom
        assert result["document"]["sha256"] in custom and "workbench_prompt_hash" in custom
        core = package.read("docProps/core.xml").decode("utf-8")
        assert "Contract Workbench" in core and "agreement.txt" in core and "python-docx" not in core
        body = package.read("word/document.xml").decode("utf-8")
        assert 'w:name="src_1"' in body and 'w:anchor="src_1"' in body, "the citation links to its bookmarked source row"
        assert "Observed language" in body and "Sources" in body
        rels = package.read("word/_rels/document.xml.rels").decode("utf-8")
        assert 'TargetMode="External"' in rels and f"run={result['run_id']}" in rels and "finding=" in rels
        assert "custom-properties+xml" in package.read("[Content_Types].xml").decode("utf-8")

    html = client.get(memo["htmlUrl"]).text
    assert "href='#src-1'" in html and "id='src-1'" in html and f"run={result['run_id']}" in html
    assert "Required —" not in html and "Observed —" not in html


def test_a_pass_is_within_guidance_only_when_the_run_had_guidance() -> None:
    assert status_label("pass", True) == "Within guidance"
    assert status_label("pass", True, "model_hint") == "Within guidance (model's view)", "a pass the model hinted is labelled as its view"
    assert status_label("pass", False, "model_hint") == "Answered"
    assert status_label("pass", False) == "Answered"
    assert status_label("needs_review", False) == "Needs review" and status_label("missing", True) == "Not found"
