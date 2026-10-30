"""Once a quote is verified, code reads the contract, never the model's spelling of it (policy-v17).

The stress test of 2026-10-30 (hostile model; verifier finding 1): a quote verifies through what a tier of the verifier
forgives (a zero-width space, a direction mark, a byte-order mark, a typeset dash, case, punctuation), and every status
check then read the model's own string. "upon 9\\u200b0 days' written notice" verified over the contract's "90 days" and
was code's shortfall of "0 calendar days"; "15 d\\u200eays" over "15 days" hid code's own shortfall, and the memo said
no automated check flagged anything; "forty\\u2011five (45)" over "forty-five (45)" was "internally inconsistent".

The invariant: for any verified span, the status is what the same run decides for a verbatim quote of the text it was
found at. The model's string stays on the span as what it proposed.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Section
from app.providers.base import Generation
from app.runs.service import located_text
from app.verify.spans import locate
from tests.support import FakeProvider

GUIDANCE = "Termination for convenience requires at least 30 days' written notice."
QUESTION = "On what notice may either party terminate for convenience?"
_ASKED = itertools.count()  # each run its own question: the same inputs would hand back the first run (runs.versions)


def _contract(clause: str) -> str:
    return (
        "SERVICES AGREEMENT\n\n1. Term\n\nThis Agreement commences on the Effective Date and continues for twelve (12) months.\n\n"
        f"2. Termination for Convenience\n\n{clause}\n\n3. Governing Law\n\nThis Agreement is governed by the laws of the State of Delaware.\n"
    )


class Spelling(FakeProvider):
    """Quotes §2 as written in ``quote``, and proposes a pass."""

    def __init__(self, quote: str) -> None:
        super().__init__()
        self.quote = quote

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        label = re.search(r"\[(sec_\d+)\] 2 Termination", user)
        assert label, "§2 was not handed to the model"
        finding = {
            "topic": "Termination for Convenience",
            "conclusion": "Either party may terminate for convenience on written notice, which meets the guidance.",
            "status_hint": "pass",
            "evidence": [{"section_id": label.group(1), "quote": self.quote}],
            "guidance_reference": None,
            "observed": None,
            "required": None,
            "suggested_position": None,
        }
        payload = {"findings": [finding], "insufficient_evidence": False, "note": None}
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def _decided(client: TestClient, clause: str, quote: str) -> tuple[bool, str, str, str | None]:
    client.app.state.provider = Spelling(quote)  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("contract.txt", _contract(clause).encode("utf-8"), "text/plain")}).json()
    guidance = client.post("/api/guidance", json={"text": GUIDANCE}).json()["id"]
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": guidance, "question": f"{QUESTION} ({next(_ASKED)})"})
    assert started.status_code == 202, started.text
    finding = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    return finding["spans"][0]["verified"], finding["status"], finding["statusSource"], finding["statusReason"]


NINETY = "Either party may terminate this Agreement for convenience on 90 days' written notice to the other party."
FIFTEEN = "Either party may terminate this Agreement for convenience on fifteen (15) days' written notice to the other party."
RANGED = "Either party may terminate this Agreement for convenience on 10-60 days' written notice to the other party."
FORTY_FIVE = "Either party may terminate this Agreement for convenience on forty-five (45) days' written notice to the other party."

# The model's spellings of each clause that a tier forgives, each changing a number as the model's string reads it.
SPELLINGS = [
    (NINETY, NINETY.replace("90", "9\u200b0")),
    (NINETY, NINETY.replace("90", "9\u200e0")),
    (NINETY, NINETY.replace("90", "9\ufeff0")),
    (NINETY, NINETY.replace("90", "9\u200f0")),
    (FIFTEEN, FIFTEEN.replace("(15) days", "(1\u200b5) d\u200eays")),
    (FIFTEEN, FIFTEEN.replace("days", "da\u200bys")),
    (FORTY_FIVE, FORTY_FIVE.replace("forty-five", "forty–five")),
    (FORTY_FIVE, FORTY_FIVE.replace("forty-five", "forty—five")),
    (FORTY_FIVE, FORTY_FIVE.replace("forty-five", "forty−five")),
    # The typed tier forgives punctuation: read as the model wrote it, "10 60 days" is sixty days alone.
    (RANGED, RANGED.replace("10-60", "10 60")),
]


@pytest.mark.parametrize(("clause", "spelled"), SPELLINGS, ids=[ascii(s)[30:70] for _, s in SPELLINGS])
def test_a_verified_quote_is_decided_as_the_text_it_was_found_at(client: TestClient, clause: str, spelled: str) -> None:
    honest = _decided(client, clause, clause)
    hostile = _decided(client, clause, spelled)
    assert hostile[0] is True, "the spelling no longer verifies; this test then pins nothing"
    assert hostile == honest


def test_controls_the_honest_quotes_are_decided_as_before(client: TestClient) -> None:
    assert _decided(client, NINETY, NINETY)[1:3] == ("pass", "model_hint")
    assert _decided(client, FIFTEEN, FIFTEEN)[1:3] == ("needs_review", "computed_days")
    assert _decided(client, FORTY_FIVE, FORTY_FIVE)[1:3] == ("pass", "model_hint")


def test_a_quote_found_past_its_sections_label_reads_the_heading_it_carries() -> None:
    """The reader split "… Customer one hundred / eighty (180) days' written notice." across a heading and its text (a
    recorded qwen3:8b run, m3 §7.2); the model quoted the sentence whole and the verifier found it once the label was set
    aside. Read without the heading, the located text says "eighty (180)", which is internally inconsistent."""
    section = Section(
        ordinal=7, number="7.2", heading="Termination by Customer. Provider shall give Customer one hundred", text="eighty (180) days' written notice."
    )
    quote = "7.2 Termination by Customer. Provider shall give Customer one hundred eighty (180) days' written notice."
    found = locate(quote, section.text, f"{section.number} {section.heading}")
    assert found is not None and found.method.startswith("unprefixed:")
    assert "one hundred eighty (180) days" in located_text(section, found)
    # A quote found inside the text reads the text only.
    inside = locate("eighty (180) days' written notice", "Notice: eighty (180) days' written notice.")
    assert inside is not None and located_text(Section(ordinal=1, number="1", heading="Notice", text="Notice: eighty (180) days' written notice."), inside) == (
        "eighty (180) days' written notice"
    )
