"""One account of each finding (runs.account): who set its status and what code raised about it, read the same way by
the answer card, the findings list, the memo and the evidence pack.

The authority review of 2026-10-14 (outside the repository) found the
surfaces disagreeing: a pass whose recorded reason said "code does not confirm that as a pass" was printed under "No
automated check flagged a finding"; the model's own words were printed as "Legal guidance."; the findings list let a
person confirm a finding without showing what code had raised. Each case is reproduced here with a scripted model.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from fastapi.testclient import TestClient

from app.memo.service import FLAGS_HEAD, NO_FLAGS
from app.providers.base import Generation
from tests.support import FakeProvider, upload_and_ask
from tests.test_memo_restraint import memo_html

QUESTION = "How much notice does the customer need to give to terminate for convenience?"
TWO_PERIODS = "Termination for convenience needs at least 10 days' notice. Enterprise agreements require at least 30 days' notice."


class PassProvider(FakeProvider):
    """The model calls the clause a pass, and refers to a guidance sentence the guidance does not contain."""

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        payload = json.loads(super().generate_json(system, user, schema).text)
        finding = payload["findings"][0]
        finding.update(status_hint="pass", observed="15 days' written notice", required="at least 10 days")
        finding["guidance_reference"] = "Termination needs 7 days' notice for every customer."
        finding["conclusion"] = finding["conclusion"].split(";")[0].replace(" [", ". [") if "[" in finding["conclusion"] else finding["conclusion"]
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def _ask_with(client: TestClient, guidance: str) -> str:
    client.app.state.provider = PassProvider()  # type: ignore[attr-defined]
    from tests.support import CONTRACT

    document = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    saved = client.post("/api/guidance", json={"text": guidance}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": saved["id"], "question": QUESTION})
    assert started.status_code == 202, started.text
    return str(started.json()["id"])


def test_a_pass_code_does_not_confirm_is_flagged_everywhere_with_codes_words(client: TestClient) -> None:
    run_id = _ask_with(client, TWO_PERIODS)
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert (finding["status"], finding["statusSource"]) == ("pass", "model_hint")
    assert "code does not confirm that as a pass" in finding["statusReason"]
    # The card's account.
    assert finding["decidedBy"] == "model" and finding["flagged"] is True
    assert any(concern.startswith("code does not confirm the pass: ") for concern in finding["concerns"])
    # The findings list's.
    listed = next(f for f in client.get("/api/findings").json() if f["id"] == finding["id"])
    assert listed["flagged"] is True and listed["concerns"] == finding["concerns"]
    # The memo's: flagged, with code's words, never "no automated check flagged".
    html = memo_html(client, run_id)
    assert f"{FLAGS_HEAD} (1)" in html and NO_FLAGS.split(".")[0] not in html
    assert "code does not confirm the pass: " in html and "Why flagged." in html


def test_the_models_reference_to_the_guidance_is_never_printed_as_guidance(client: TestClient) -> None:
    run_id = _ask_with(client, TWO_PERIODS)
    html = memo_html(client, run_id)
    assert "Legal guidance." not in html
    assert "The model's reference to the guidance." in html and "not found in the guidance: the model&#x27;s words" in html
    assert "The model's reading.</strong> observed 15 days&#x27; written notice · required at least 10 days" in html


def test_control_a_reference_the_guidance_does_contain_is_said_to_be_found(client: TestClient) -> None:
    run_id = upload_and_ask(client, QUESTION)["run_id"]  # the scripted model quotes the guidance's own words
    html = memo_html(client, run_id)
    assert "at 30 days&#x27; notice or more (found in the guidance)" in html


def test_control_a_finding_code_lowered_is_codes_and_flagged_with_its_reason(client: TestClient) -> None:
    run_id = upload_and_ask(client, QUESTION)["run_id"]  # 15 days against 30: a shortfall code computes
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert (finding["status"], finding["decidedBy"], finding["flagged"]) == ("needs_review", "code", True)
    assert finding["concerns"] == [f"code: {finding['statusReason']}"]


def test_control_a_plain_answer_with_nothing_raised_is_not_flagged(client: TestClient) -> None:
    run_id = upload_and_ask(client, QUESTION, with_guidance=False)["run_id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert finding["status"] == "pass" and finding["flagged"] is False and finding["concerns"] == []
    assert NO_FLAGS in memo_html(client, run_id).replace("&#x27;", "'")


def test_the_evidence_pack_carries_the_account_and_the_models_own_words(client: TestClient) -> None:
    run_id = _ask_with(client, TWO_PERIODS)
    pack = client.get(f"/api/runs/{run_id}/evidence-pack")
    assert pack.status_code == 200
    with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
        name = next(n for n in archive.namelist() if n.endswith("findings.json"))
        findings = json.loads(archive.read(name))
        readme = archive.read(next(n for n in archive.namelist() if n.endswith("README.txt"))).decode("utf-8")
    record = findings[0] if isinstance(findings, list) else findings["findings"][0]
    assert record["decided_by"] == "model" and record["flagged"] is True and record["concerns"]
    assert record["model"]["guidance_reference"] == "Termination needs 7 days' notice for every customer."
    assert record["model"]["observed"] == "15 days' written notice"
    assert "decided_by" in readme and "concerns" in readme
