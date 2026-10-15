"""A section handle the model was not given is shown as such and lowers a pass (runs.prose, status.check_references).

Real run, 2026-10-15 (local qwen3:8b): the model wrote "This is found in sec_12.3." The handle names no section it was
handed, and the product dropped it, so the card read "This is found in.3." and the pass stood: an invented pointer
silently erased, and never seen by the check that lowers a pass citing a section the document does not have.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.runs.prose import UNRESOLVED
from tests.test_relations_oracle import OracleModel

QUOTE = "Customer may terminate any Cabinet Service for convenience by giving Provider ninety (90) days' written notice."
AGREEMENT = "\n\n".join(["COLOCATION AGREEMENT", "12. TERMINATION", f"12.1 {QUOTE}"])


def _ask(client: TestClient, monkeypatch: pytest.MonkeyPatch, conclusion: str) -> dict[str, Any]:
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = OracleModel({"topic": "Notice", "conclusion": conclusion, "observed": "90 days", "quotes": [QUOTE]})  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("colo.txt", AGREEMENT.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": f"Notice? {conclusion[-12:]}"})
    assert started.status_code == 202, started.text
    return client.get(f"/api/runs/{started.json()['id']}/detail").json()


def test_an_invented_handle_is_marked_and_lowers_the_pass(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    detail = _ask(client, monkeypatch, "The notice is ninety (90) days' written notice. This is found in sec_12.3.")
    finding = detail["findings"][0]
    assert finding["conclusion"].endswith(f"This is found in {UNRESOLVED}.")
    assert (finding["status"], finding["statusSource"]) == ("needs_review", "reference_check")
    # The reason names the failure as the reader sees it, not the internal handle (the raw output keeps that).
    assert "sec_" not in finding["statusReason"] and "names no section the model was given" in finding["statusReason"]
    assert UNRESOLVED in finding["statusReason"]
    assert "sec_12.3" in detail["rawOutput"]  # the model's own words are kept as it wrote them


def test_control_an_answer_with_no_handle_keeps_its_pass(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    detail = _ask(client, monkeypatch, "The notice is ninety (90) days' written notice.")
    assert detail["findings"][0]["status"] == "pass" and UNRESOLVED not in detail["findings"][0]["conclusion"]


@pytest.mark.parametrize("field", ["observed", "topic"])
def test_a_handle_the_model_was_not_given_lowers_the_pass_in_any_field(client: TestClient, monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    item = {"topic": "Notice", "conclusion": "The notice is ninety (90) days' written notice.", "observed": "90 days", "quotes": [QUOTE]}
    item[field] = f"{item[field]} (sec_12.3)"
    client.app.state.provider = OracleModel(item)  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("colo.txt", AGREEMENT.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": f"Notice in {field}?"})
    finding = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    assert (finding["status"], finding["statusSource"]) == ("needs_review", "reference_check")


def test_the_pack_keeps_the_models_own_words_and_checks_them_against_the_record(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The finding shows "[unidentified section]"; the pack also carries what the model wrote, so a reader of the pack can
    # see the handle that was replaced, and verify.py ties that text to the hash the run recorded when the model answered.
    detail = _ask(client, monkeypatch, "The notice is ninety (90) days' written notice. This is found in sec_12.3.")
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{detail['id']}/evidence-pack").content)) as pack:
        pack.extractall(tmp_path)
    record = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    (packed,) = json.loads((tmp_path / "findings.json").read_text(encoding="utf-8"))
    assert record["model_output"]["file"] == "model_output.txt" and record["model_output"]["sha256_recorded"]
    assert "sec_12.3" in (tmp_path / "model_output.txt").read_text(encoding="utf-8")
    assert packed["conclusion"].endswith(f"This is found in {UNRESOLVED}.") and packed["status_source"] == "reference_check"
    verified = subprocess.run([sys.executable, "verify.py"], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert verified.returncode == 0 and "PASS model output" in verified.stdout, verified.stdout + verified.stderr

    # An edited copy of the model's words fails, and says which file.
    (tmp_path / "model_output.txt").write_text(detail["rawOutput"].replace("sec_12.3", "sec_12"), encoding="utf-8")
    tampered = subprocess.run([sys.executable, "verify.py"], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert tampered.returncode == 1 and "FAIL model output" in tampered.stdout
