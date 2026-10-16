"""A quote that leaves its own sentence's condition out does not support a pass that leaves it out too (policy-v14).

Found by the blind contract stress test (2026-10-16, runs 64174e2fdf2c42b7 and d496e40e68c5453a, real qwen3:8b, DOCX and
PDF alike): asked "Can Customer terminate for convenience on 30 days notice?", the model answered "Customer may terminate
for convenience with 30 days' written notice" and quoted "Customer may terminate for convenience by giving Provider at
least thirty (30) calendar days of written notice." The quote is found word for word; its sentence opens "Except for the
first sixty (60) calendar days of the Initial Term,". The quote is the shortest passage that carries the point (prompt
rule 1), so a quote that starts after the exception is a verified substring, and the answer, which drops it too, stood as
the model's pass.

The invariant: a pass may not rest on a verified quote whose own sentence, outside the quoted words, carries a condition
or an exception (`policy.proof.CARVE_OUT`: except, unless, subject to, provided that, notwithstanding, other than, …)
that the answer does not state. Read from the stored section text around the located span, before or after it, never
across a sentence end. The answer states the condition when it carries a condition word and a word of the condition
itself ("except during the first 60 days"). Which condition governs, and whether it applies here, stays a reading.

Not lowered (controls): a quote that includes the condition; a condition in another sentence; a bare "if"; an answer
that states the condition; a status other than a pass.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.providers.base import Generation
from app.runs.status import Decision, check_conditions, left_out_condition
from tests.support import FakeProvider
from tests.test_unquoted_values import assert_linear

SECTION = (
    "5.1 Customer Convenience. Except for the first sixty (60) calendar days of the Initial Term, Customer may terminate for "
    "convenience by giving Provider at least thirty (30) calendar days of written notice. No notice under this Section 5.1 "
    "acts as a non-renewal notice unless it separately satisfies Section 4.2."
)
TRIMMED = "Customer may terminate for convenience by giving Provider at least thirty (30) calendar days of written notice."
ANSWER = "Customer may terminate for convenience with 30 days' written notice."
PASS = Decision("pass", "model_hint")


def _span(text: str, quote: str) -> tuple[int, int]:
    start = text.index(quote)
    return start, start + len(quote)


def test_the_blind_tests_quote_leaves_out_the_first_sixty_days() -> None:
    assert left_out_condition(SECTION, *_span(SECTION, TRIMMED)) == "Except for the first sixty (60) calendar days of the Initial Term"


@pytest.mark.parametrize(
    ("text", "quote", "condition"),
    [
        # After the quote, in the same sentence.
        (
            "Provider may suspend access on ten (10) days' notice, unless Customer has paid the undisputed amount.",
            "Provider may suspend access on ten (10) days' notice",
            "unless Customer has paid the undisputed amount",
        ),
        (
            "Customer may assign this Agreement, provided that the assignee assumes every obligation in writing.",
            "Customer may assign this Agreement",
            "provided that the assignee assumes every obligation in writing",
        ),
        (
            "Subject to Section 9.2, Provider will defend Customer against a third-party claim.",
            "Provider will defend Customer against a third-party claim",
            "Subject to Section 9.2",
        ),
        (
            "Notwithstanding the foregoing, either party may terminate immediately on written notice.",
            "either party may terminate immediately on written notice",
            "Notwithstanding the foregoing",
        ),
        (
            "Fees are due within twenty-one (21) days, other than fees under a disputed invoice.",
            "Fees are due within twenty-one (21) days",
            "other than fees under a disputed invoice",
        ),
        (SECTION, "No notice under this Section 5.1 acts as a non-renewal notice", "unless it separately satisfies Section 4.2"),
    ],
)
def test_every_left_out_condition_word_before_or_after_the_quote_is_read(text: str, quote: str, condition: str) -> None:
    assert left_out_condition(text, *_span(text, quote)) == condition


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        (SECTION, "Except for the first sixty (60) calendar days of the Initial Term, Customer may terminate for convenience"),  # included
        (
            "Customer may terminate on thirty (30) days' notice. This right does not apply unless approved.",
            "Customer may terminate on thirty (30) days' notice",
        ),
        ("If Customer requests it, Provider will provide a copy within ten (10) days.", "Provider will provide a copy within ten (10) days"),  # bare "if"
        (TRIMMED, TRIMMED),  # the whole sentence
    ],
)
def test_controls_leave_out_no_condition_of_their_own_sentence(text: str, quote: str) -> None:
    assert left_out_condition(text, *_span(text, quote)) is None


def test_the_pass_is_lowered_unless_the_answer_states_the_condition() -> None:
    condition = "Except for the first sixty (60) calendar days of the Initial Term"
    lowered = check_conditions(PASS, ANSWER, [condition])
    assert (lowered.status, lowered.source) == ("needs_review", "position_check")
    assert lowered.reason == f"the quote leaves out of its sentence “{condition}”, and the answer does not state it"
    stated = "Customer may terminate for convenience on 30 days' written notice, except during the first 60 days of the Initial Term."
    assert check_conditions(PASS, stated, [condition]) == PASS
    # A condition word alone, about something else, does not state this condition.
    other = "Customer may terminate for convenience on 30 days' written notice unless Customer is in breach."
    assert check_conditions(PASS, other, [condition]).status == "needs_review"
    review = Decision("needs_review", "position_check", "earlier reason")
    assert check_conditions(review, ANSWER, [condition]) == review
    assert check_conditions(PASS, ANSWER, []) == PASS


@settings(max_examples=60, deadline=None)
@given(
    lead=st.sampled_from(
        ["Except for the first year", "Unless otherwise agreed", "Subject to Section 3", "Notwithstanding Section 7", "If requested", "On request"]
    ),
    days=st.integers(min_value=1, max_value=365),
)
def test_property_a_trimmed_lead_in_is_reported_exactly_when_it_is_a_condition(lead: str, days: int) -> None:
    quote = f"Provider may terminate on {days} days' notice"
    text = f"{lead}, {quote}."
    condition = left_out_condition(text, *_span(text, quote))
    is_condition = lead.split()[0] in ("Except", "Unless", "Subject", "Notwithstanding")
    assert (condition == lead) if is_condition else condition is None


@pytest.mark.parametrize(("unit", "repeats"), [("unless ", 20000), ("a, ", 20000)])
def test_hostile_sentences_are_read_in_linear_time(unit: str, repeats: int) -> None:
    assert_linear(lambda text: left_out_condition(text, len(text) // 2, len(text) // 2 + 1), unit, repeats)


# ---------------------------------------------------------------------------- through the run


CONTRACT = f"""CONVENIENCE TEST AGREEMENT
5. Termination
{SECTION}
6. Governing Law
This Agreement is governed by the laws of the State of Delaware.
"""


class TrimmingProvider(FakeProvider):
    """Quotes §5.1 from "Customer may terminate", or whole, and answers without the exception."""

    def __init__(self, quote: str) -> None:
        super().__init__()
        self.quote = quote

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        label = re.search(r"\[(sec_\d+)\] 5 Termination", user)
        assert label, "§5 was not handed to the model"
        payload = {
            "findings": [
                {
                    "topic": "Termination for Convenience",
                    "conclusion": ANSWER,
                    "status_hint": "pass",
                    "evidence": [{"section_id": label.group(1), "quote": self.quote}],
                    "guidance_reference": None,
                    "observed": "30 days",
                    "required": None,
                    "suggested_position": None,
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def _ask(client: TestClient, quote: str) -> dict[str, Any]:
    client.app.state.provider = TrimmingProvider(quote)  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("convenience.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    question = "Can Customer terminate for convenience on 30 days notice?"
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": question})
    assert started.status_code == 202, started.text
    detail: dict[str, Any] = client.get(f"/api/runs/{started.json()['id']}/detail").json()
    return detail


def test_the_blind_tests_trimmed_quote_is_needs_review_set_by_code_through_the_run(client: TestClient) -> None:
    finding = _ask(client, TRIMMED)["findings"][0]
    assert finding["spans"][0]["verified"] is True
    assert (finding["status"], finding["statusSource"], finding["decidedBy"]) == ("needs_review", "position_check", "code")
    assert "Except for the first sixty (60) calendar days of the Initial Term" in finding["statusReason"]


def test_control_the_whole_sentence_quoted_leaves_the_models_answer(client: TestClient) -> None:
    whole = "Except for the first sixty (60) calendar days of the Initial Term, " + TRIMMED
    finding = _ask(client, whole)["findings"][0]
    assert (finding["status"], finding["statusSource"]) == ("pass", "model_hint")
