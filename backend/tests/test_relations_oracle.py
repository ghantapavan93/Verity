"""The contract's replacement and precedence statements, held to an oracle written before the code (policy-v11).

`fixtures/relations_oracle.json` (sha256 e8b59a0e…) was written by an independent author from the product contract alone
(outside the repository), without reading this code: 34 short agreements
and 82 decisions across ten families. They are full replacements, historical questions, five kinds of mere mention,
limited replacements, precedence, conflicts with no ranking, exceptions, altered quotes, documents with no relation and
an instruction aimed at a reviewer. Its labels are never edited to make this pass.

Every decision goes through the product end to end: the agreement is uploaded and read by the real reader, the scripted
model quotes the oracle's passages, and the real verifier, policy and account decide. Every section is handed to the
model (retrieval is replaced by "all of them"): the subject here is what follows from the statements, not which sections
rank, and a section retrieval left out would leave its quote unverified and the decision untested.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.providers.base import Generation
from app.runs import service

ORACLE = json.loads((Path(__file__).parent / "fixtures" / "relations_oracle.json").read_text(encoding="utf-8"))
DECISIONS = [pytest.param(case, i, id=f"{case['id']}-{i}") for case in ORACLE for i in range(len(case["decisions"]))]
_BLOCK = re.compile(r"\[(sec_\d+)\][^\n]*\n(.*?)(?=\n\n\[sec_\d+\]|\Z)", re.S)


class OracleModel:
    """Answers with the oracle's finding, quoting from whichever handed section holds each passage."""

    name = "oracle"
    model = "scripted-oracle"

    def __init__(self, finding: dict[str, Any]) -> None:
        self.finding = finding

    def healthy(self) -> tuple[bool, str]:
        return True, "scripted"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        blocks = _BLOCK.findall(user)
        evidence = [{"section_id": next((label for label, body in blocks if quote in body), blocks[0][0]), "quote": quote} for quote in self.finding["quotes"]]
        payload = {
            "findings": [
                {
                    "topic": self.finding.get("topic") or "Answer",
                    "conclusion": self.finding["conclusion"],
                    "status_hint": "pass",
                    "evidence": evidence,
                    "guidance_reference": None,
                    "observed": self.finding.get("observed"),
                    "required": None,
                    "suggested_position": None,
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=10, output_tokens=10, latency_ms=1.0, model=self.model)


def label_of(finding: dict[str, Any]) -> str:
    """The oracle's label for what the product recorded: the relation notes, and the status code set from them."""
    effects = {note["effect"] for note in finding["relations"]}
    if effects & {"replaced", "old_value"}:  # since policy-v16 an old_value note sets the status too
        assert (finding["status"], finding["statusSource"], finding["decidedBy"]) == ("needs_review", "position_check", "code")
    if "replaced" in effects:
        assert all(span["verified"] for span in finding["spans"]), "a replaced quote stays verified"
        return "needs_review_replaced"
    if "scoped" in effects:
        return "scoped_concern"
    if "precedence" in effects:
        return "precedence_concern"
    # What the oracle has no label for (a time the question names; an answer quoting the replacement with only the replaced
    # values, which since policy-v16 lowers a pass) is never read as context: a decision that raised one fails its label.
    for effect in ("dated", "old_value"):
        if effect in effects:
            return f"{effect}_concern"
    assert effects <= {"context"}, effects
    return "context_only" if effects else "no_concern"


def decide(client: TestClient, case: dict[str, Any], index: int, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(service, "_retrieve", lambda sections, question, guidance, frozen: (list(sections), "lexical_match", {}))
    decision = case["decisions"][index]
    client.app.state.provider = OracleModel(decision["finding"])  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": (f"{case['id']}.txt", case["document"].encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": decision["question"]})
    assert started.status_code == 202, started.text
    detail: dict[str, Any] = client.get(f"/api/runs/{started.json()['id']}/detail").json()
    return detail


@pytest.mark.parametrize(("case", "index"), DECISIONS)
def test_each_decision_is_what_the_contract_says(client: TestClient, monkeypatch: pytest.MonkeyPatch, case: dict[str, Any], index: int) -> None:
    detail = decide(client, case, index, monkeypatch)
    finding = detail["findings"][0]
    expected = case["decisions"][index]["expected"]
    assert label_of(finding) == expected, (case["decisions"][index]["why"], [n["sentence"] for n in finding["relations"]])


@pytest.mark.parametrize("case", [pytest.param(c, id=c["id"]) for c in ORACLE])
def test_each_document_records_the_statements_it_makes_and_none_it_does_not(client: TestClient, monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]) -> None:
    detail = decide(client, case, 0, monkeypatch)
    recorded = detail["relations"] or []
    for expected in case.get("expected_relations", []):
        match = [
            r
            for r in recorded
            if r["kind"] == expected["kind"]
            and expected["statement_excerpt"] in r["statement"]["text"]
            and (expected["kind"] != "replaces" or r["target"] == expected.get("target"))
            and (expected["kind"] != "replaces" or (r["scope"] is None) == (expected.get("scope") is None))
        ]
        assert match, (expected, [(r["kind"], r["target"], r["scope"], r["statement"]["text"][:120]) for r in recorded])
    replaced = {r["target"] for r in recorded if r["kind"] == "replaces"}
    assert not replaced & set(case.get("must_not_relate", [])), (case.get("must_not_relate"), replaced)
