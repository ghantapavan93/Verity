"""A finding with a quote the verifier did not find stays withheld, whatever any later check says (stress test, 2026-10-30).

Mutation finding 2: `decide` returns ("unresolved", "no_evidence") for a finding with any unverified quote, and every
check after it (references, values, conditions, the replaced clause, the old value, settling findings together) must
return that unchanged, because every surface hides a finding by its status alone. Only `check_replaced` acts on a
status other than a pass, and removing its guard (mutant D18) passed every test: a hostile model that quoted a replaced
clause verbatim beside an invented sentence then had the invented sentence printed in the memo as the contract's words.
Nothing was broken; nothing pinned it. These tests do.
"""

from __future__ import annotations

import io
import json
import re
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.providers.base import Generation
from app.runs.status import (
    Decision,
    Grounds,
    check_conditions,
    check_old_value,
    check_references,
    check_replaced,
    check_values,
    settle_together,
)
from tests.test_relations_oracle import _BLOCK
from tests.test_relations_surfaces import AGREEMENT, OLD

UNRESOLVED = Decision("unresolved", "no_evidence")
INVENTED = "Distributor may renew this Agreement at any time by notice of ten (10) days."
TERM = "This Agreement runs for three (3) years from 1 March 2025."

_text = st.text(st.characters(codec="utf-8", exclude_categories=("Cs",)), max_size=80)


@settings(max_examples=300, deadline=None)
@given(_text, st.lists(_text, max_size=3), _text, _text, st.lists(_text, max_size=2), st.lists(_text, max_size=2))
def test_no_check_after_decide_changes_a_withheld_finding(
    conclusion: str, quotes: list[str], question: str, guidance: str, conditions: list[str], numbers: list[str]
) -> None:
    sentence = "the quoted clause 1.2 is text that §AMENDMENT NO. 1 replaces in full"
    assert check_references(UNRESOLVED, conclusion, numbers, ["sec_1"], numbers, ["sec_9"]) == UNRESOLVED
    assert check_values(UNRESOLVED, conclusion, quotes, question, guidance, numbers) == UNRESOLVED
    assert check_conditions(UNRESOLVED, conclusion, conditions) == UNRESOLVED
    assert check_replaced(UNRESOLVED, sentence) == UNRESOLVED
    assert check_old_value(UNRESOLVED, sentence) == UNRESOLVED
    short = Decision("needs_review", "computed_days", "the contract provides 10 calendar days; the guidance requires at least 30 calendar days")
    grounds = Grounds(tuple(quotes), tuple(quotes), (("s1", "1.2"),))
    assert settle_together([UNRESOLVED, short], [grounds, grounds], guidance)[0] == UNRESOLVED


class TwoFindings:
    """A hostile model: one finding quoting clause 1.1, one quoting the replaced clause 1.2 verbatim beside an invented
    sentence the contract does not hold."""

    name = "hostile"
    model = "scripted-hostile"

    def healthy(self) -> tuple[bool, str]:
        return True, "scripted"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        blocks = _BLOCK.findall(user)

        def cited(quote: str) -> str:
            return next((label for label, body in blocks if quote in body), blocks[0][0])

        def finding(topic: str, conclusion: str, quotes: list[str]) -> dict[str, Any]:
            evidence = [{"section_id": cited(q), "quote": q} for q in quotes]
            return {
                "topic": topic,
                "conclusion": conclusion,
                "status_hint": "pass",
                "evidence": evidence,
                "guidance_reference": None,
                "observed": None,
                "required": None,
                "suggested_position": None,
            }

        payload = {
            "findings": [
                finding("Term", "The Agreement runs for three years.", [TERM]),
                finding("Renewal notice", "Distributor may renew at any time on ten (10) days' notice.", [OLD, INVENTED]),
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=10, output_tokens=10, latency_ms=1.0, model=self.model)


def test_a_partly_verified_finding_beside_a_replaced_clause_is_withheld_on_every_surface(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = TwoFindings()  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("distribution.txt", AGREEMENT.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": "When must the distributor give notice to renew?"})
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]

    detail = client.get(f"/api/runs/{run_id}/detail").json()  # the audit view lists every finding
    renewal = next(f for f in detail["findings"] if f["topic"] == "Renewal notice")
    assert [s["verified"] for s in renewal["spans"]] == [True, False]
    assert (renewal["status"], renewal["statusSource"]) == ("unresolved", "no_evidence")
    assert "replaced" in {n["effect"] for n in renewal["relations"]}  # the relation is recorded, and sets nothing

    shown = client.get(f"/api/runs/{run_id}").json()
    assert [f["topic"] for f in shown["findings"]] == ["Term"] and [f["topic"] for f in shown["withheld"]] == ["Renewal notice"]
    assert [f["topic"] for f in client.get("/api/findings").json()] == ["Term"]

    memo = client.post("/api/memos", json={"runId": run_id}).json()
    html = client.get(f"/api/memos/{memo['id']}/html").text
    words = "\n".join(p.text for p in Document(io.BytesIO(client.get(f"/api/memos/{memo['id']}/docx").content)).paragraphs)
    for text in (html, words):
        assert "Renewal notice (withheld)" in re.sub(r"<[^>]+>", "", text)
        assert INVENTED not in text
