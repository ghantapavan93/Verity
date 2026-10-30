"""A sentence the reader cut across two parts of a clause is read whole (policy-v17, wave 2 of the stress test).

The reader stores a clause longer than its cap as parts ("Termination for Convenience (part 2)"). Since reader v16 a
long paragraph is cut where a passage ends, and only where none is within reach at a space; there one sentence runs from
part 1 into part 2. The status checks read a quote's sentence in its own section's text, and `_sentence_bounds` takes a
text's edge for a sentence end, so "Except for the first sixty (60) calendar days of the Initial Term," at the head of
the sentence in part 1 was never seen beside a quote in part 2, and the answer that left it out kept its pass.

The rule (`runs.service.reading_of`): a quote's sentence is read in its section with the parts of the same clause it runs
on into; a part that ends a passage ends its sentence, and nothing is joined across it. Controls: a section that is no
part, and parts cut where a passage ends, read as before.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Section
from app.providers.base import Generation
from app.runs.service import reading_of
from app.runs.status import enclosing_sentences, left_out_condition
from tests.test_relations_oracle import _BLOCK

CONDITION = "Except for the first sixty (60) calendar days of the Initial Term"
FILLER = "the Customer and the Provider each acknowledge and agree that the arrangements described here continue " * 70
QUOTE = "Customer may terminate this Agreement for convenience on thirty (30) days written notice to Provider."
CLAUSE = f"{CONDITION}, {FILLER}and {QUOTE}"
AGREEMENT = (
    "SERVICES AGREEMENT\n\n1. Term\n\nThis Agreement continues for twelve (12) months.\n\n2. Termination for Convenience\n\n"
    f"{CLAUSE}\n\n3. Governing Law\n\nThis Agreement is governed by the laws of Delaware.\n"
)


def _section(id: str, ordinal: int, heading: str, text: str, number: str = "2") -> Section:
    return Section(id=id, ordinal=ordinal, number=number, heading=heading, text=text)


def test_a_sentence_cut_at_a_space_is_read_across_the_parts() -> None:
    head, tail = CLAUSE[:5999].rsplit(" ", 1)[0], CLAUSE[len(CLAUSE[:5999].rsplit(" ", 1)[0]) + 1 :]
    parts = [_section("p1", 2, "Termination for Convenience (part 1)", head), _section("p2", 3, "Termination for Convenience (part 2)", tail)]
    whole, at = reading_of(parts, parts[1])
    start = at + tail.index(QUOTE)
    assert whole[at:] == tail and left_out_condition(whole, start, start + len(QUOTE)) is not None
    assert enclosing_sentences(whole, start, start + len(QUOTE)).startswith(CONDITION)
    # Read from part 1, the sentence runs on into part 2.
    first, at_first = reading_of(parts, parts[0])
    assert at_first == 0 and first.endswith(QUOTE)


def test_controls_a_part_that_ends_a_passage_ends_its_sentence() -> None:
    parts = [
        _section("p1", 2, "Fees (part 1)", "Except as set out in Schedule 2, fees are due monthly."),
        _section("p2", 3, "Fees (part 2)", "Customer may terminate on thirty (30) days written notice."),
    ]
    assert reading_of(parts, parts[1]) == (parts[1].text, 0) and reading_of(parts, parts[0]) == (parts[0].text, 0)
    # Parts grouped at paragraph breaks (a cover page's table rows, Recording 6c's g25): a break ends a sentence.
    rows = [
        _section("t1", 2, "Order Form (part 1)", "General Cap | other than 1x the Fees\n\nPayment terms | 30 days"),
        _section("t2", 3, "Order Form (part 2)", "Unlimited Claims | indemnification\n\nNotices | email"),
    ]
    assert reading_of(rows, rows[1]) == (rows[1].text, 0)
    alone = [_section("s1", 1, "Fees", "fees are due monthly"), _section("s2", 2, "Termination", "Customer may terminate", number="3")]
    assert reading_of(alone, alone[1]) == (alone[1].text, 0)


class Trimming:
    """Quotes the end of the long sentence, from part 2, and answers without the condition at its head."""

    name = "trimming"
    model = "scripted-trimming"

    def healthy(self) -> tuple[bool, str]:
        return True, "scripted"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        label = next(label for label, body in _BLOCK.findall(user) if QUOTE in body)
        finding = {
            "topic": "Termination for Convenience",
            "conclusion": "Customer may terminate for convenience on 30 days' written notice.",
            "status_hint": "pass",
            "evidence": [{"section_id": label, "quote": QUOTE}],
            "guidance_reference": None,
            "observed": "30 days",
            "required": None,
            "suggested_position": None,
        }
        payload = {"findings": [finding], "insufficient_evidence": False, "note": None}
        return Generation(text=json.dumps(payload), input_tokens=10, output_tokens=10, latency_ms=1.0, model=self.model)


def test_through_the_run_the_condition_in_the_part_before_lowers_the_pass(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = Trimming()  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("long.txt", AGREEMENT.encode("utf-8"), "text/plain")}).json()
    headings = [s["heading"] for s in client.get(f"/api/documents/{document['id']}").json()["sections"]]
    assert "Termination for Convenience (part 2)" in headings, "the reader no longer cuts this clause into parts; the test pins nothing"
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": "Can Customer terminate for convenience?"})
    assert started.status_code == 202, started.text
    finding = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    assert finding["spans"][0]["verified"] is True
    assert (finding["status"], finding["statusSource"], finding["decidedBy"]) == ("needs_review", "position_check", "code")
    assert CONDITION in finding["statusReason"]
