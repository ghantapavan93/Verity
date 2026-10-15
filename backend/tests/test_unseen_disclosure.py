"""What a status rests on is said where the status is shown: whether code compared a period, and what the model never saw.

Policy-v8 has a pass name the sections its quote's sentence points at that the model was not handed, whether or not
code compared a period. The interface headed every reason on a model's status "Code compared", so a pass resting on a
section nobody read was shown under "Code compared: the sentence points at §9, which was not handed to the model"; the
memo printed no reason at all; the evidence pack carried none (release integration, 2026-10-13). The invariant: a
surface says code compared only when it did, and every surface that shows a status shows what it was set without.
runs.status.basis reads both from the record; the status itself does not change.
"""

from __future__ import annotations

import io
import itertools
import json
import zipfile
from typing import get_args

import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient

from app import config
from app.analysis.schema import StatusHint
from app.policy.durations import observed_fact, parse_rule
from app.policy.proof import unseen_reason
from app.runs.status import basis, decide
from tests.test_pass_gate import ROADS, TOPIC


@pytest.mark.parametrize("unseen", [(), ("§14.3",), ("§14.3", "Schedule B")])
def test_basis_says_code_compared_exactly_when_it_compared_a_period(unseen: tuple[str, ...]) -> None:
    """Over every road `decide` has, every hint: compared is what the inputs allowed, read independently of any wording
    (a rule in the guidance, a period in the quote, a hint that is not "not found"); unseen is code's sentence whenever
    decide wrote one, a pass always among them (test_pass_gate), and nothing otherwise."""
    for (guidance, quote), hint in itertools.product(ROADS, get_args(StatusHint)):
        decision = decide(hint, None, None, guidance is not None, True, quotes=[quote], guidance=guidance, topic=TOPIC, dependencies=unseen, passages=[quote])
        comparable = guidance is not None and parse_rule(guidance, TOPIC) is not None and observed_fact(quote) is not None and hint != "missing"
        grounds = basis(decision.source, decision.reason)
        if decision.source in ("model_hint", "computed_days"):
            assert grounds.code_compared == comparable, (guidance, quote, hint, decision)
        written = bool(unseen) and unseen_reason(unseen) in (decision.reason or "")
        assert grounds.unseen == (unseen_reason(unseen) if written else None), (guidance, quote, hint, decision)
        if decision.status == "pass" and unseen:
            assert written, "a pass always names what the model did not see"


def test_basis_reads_the_wordings_of_earlier_policies_and_the_not_found_reason() -> None:
    v6 = (
        "the contract provides 90 calendar days; the guidance requires at least 90 calendar days, but code does not confirm that as a pass: "
        "the quoted passage refers to §14.3, which the model was not handed"
    )
    assert basis("model_hint", v6).code_compared and basis("model_hint", v6).unseen == "the quoted passage refers to §14.3, which the model was not handed"
    not_found = (
        "the model reported the point as not found, so the quoted passage is the closest provision read, not the contract's position; code compared no periods"
    )
    assert not basis("model_hint", not_found).code_compared and basis("model_hint", not_found).unseen is None
    assert basis("model_hint", None) == basis("no_evidence", None) and not basis("no_evidence", None).code_compared


CONTRACT_POINTING_AWAY = """SERVICES AGREEMENT

1. Term

This Agreement commences on the Effective Date and continues for twelve (12) months.

2. Termination for Convenience

Subject to Sections 7, 8 and 9, Customer may terminate this Agreement for convenience upon fifteen (15) days’ written notice to Provider.

3. Governing Law

This Agreement is governed by the laws of the State of Delaware.

7. Records

Provider keeps books for audit.

8. Insurance

Provider maintains commercial general liability cover.

9. Minimum Commitment

Customer may not terminate for convenience during the first year of the Term.
"""


def test_every_surface_says_a_pass_rests_on_a_section_the_model_never_read(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the termination section is ranked; since retrieval-v2 the two sections it names first (§7, §8) are handed after
    # it (runs.links, two at most), and §9, the one that bears on the answer, is still never read.
    monkeypatch.setattr(config.settings, "retrieval_k", 1)
    uploaded = client.post("/api/documents", files={"file": ("pointing.txt", CONTRACT_POINTING_AWAY.encode("utf-8"), "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    started = client.post(
        "/api/runs", json={"documentId": uploaded.json()["id"], "guidanceId": None, "question": "What notice period applies to termination for convenience?"}
    )
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    expected = "the sentence points at §9, which was not handed to the model"
    assert (finding["status"], finding["statusSource"]) == ("pass", "model_hint"), "the status is the model's, unchanged"
    assert finding["codeCompared"] is False and finding["unseenReason"] == expected, finding

    memo = client.post("/api/memos", json={"runId": run_id}).json()
    html = client.get(f"/api/memos/{memo['id']}/html").text
    assert "Not shown to the model." in html and expected in html
    docx = client.get(f"/api/memos/{memo['id']}/docx")
    text = "\n".join(p.text for p in DocxDocument(io.BytesIO(docx.content)).paragraphs)
    assert "Not shown to the model." in text and expected in text

    pack = client.get(f"/api/runs/{run_id}/evidence-pack")
    assert pack.status_code == 200, pack.text
    with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
        packed = json.loads(archive.read("findings.json"))[0]
    assert packed["code_compared"] is False and packed["unseen_reason"] == expected and packed["status_reason"] == expected


def test_control_a_compared_pass_says_code_compared_and_names_nothing_unseen(client: TestClient) -> None:
    from tests.support import upload_and_ask

    run_id = upload_and_ask(client, "What notice period applies to termination for convenience?")["run_id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert finding["codeCompared"] is True and finding["unseenReason"] is None, finding
