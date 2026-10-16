"""An answer that gives every party one value its evidence gives to only some is not a pass (policy-v14).

Found by the blind contract stress test (2026-10-16, run fecd095d319a4406, real qwen3:8b): asked "What notice must each
party give to prevent automatic renewal?", the model answered "Each party must give written notice at least 45 calendar
days before the current term ends" over a quote, found word for word, in which the Customer gives 45 days and the
Provider 60. Code saw the two values and said which one the answer used (`values.value_choices`), as a disclosure; the
status stayed the model's pass, so a wrong answer for the Provider read as an answer. The PDF reading of the same
contract gave "Each party … 45 calendar days … Customer … 45 days, and Provider … 60 days" (run 1731ecdb30414159): the
first sentence is the same generalisation, the second contradicts it.

The invariant: a pass may not give one value to every party ("each party", "both parties", "either party", "the
parties", "neither party", "both Customer and Provider") in a sentence of its conclusion when the finding's verified
passages state other values of that kind and none of them gives that value to every party. The check reads each sentence
of the conclusion on its own, so a later sentence that names the other value does not excuse the first. Which value
applies to whom stays a reading; code says only that the evidence does not give the value to every party.

Not lowered (controls): an answer that names one party; a sentence that gives every value the passages state; a value
the contract itself gives to every party ("Either party may terminate on thirty (30) days' notice"); a band table answered
without a party subject (still disclosed beside it, `test_value_choices`).
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
from app.runs.status import Decision, check_values
from app.runs.values import uniform_party_choices
from tests.support import FakeProvider
from tests.test_unquoted_values import assert_linear

NON_RENEWAL = (
    "To prevent the next automatic renewal, Customer must give written notice at least forty-five (45) calendar days "
    "before the current term ends; Provider must give written notice at least sixty (60) calendar days before that end."
)
DOCX_ANSWER = "Each party must give written notice at least 45 calendar days before the current term ends to prevent automatic renewal."
PDF_ANSWER = (
    "Each party must give written notice at least 45 calendar days before the current term ends to prevent automatic renewal. "
    "Customer must give notice of at least 45 days, and Provider must give notice of at least 60 days."
)
QUESTION = "What notice must each party give to prevent automatic renewal?"
PASS = Decision("pass", "model_hint")


def test_the_blind_tests_docx_answer_gives_every_party_the_customers_value() -> None:
    found = uniform_party_choices(DOCX_ANSWER, [NON_RENEWAL], [QUESTION])
    assert [(f.phrase, f.choice.answer) for f in found] == [("Each party", "45 calendar days")]
    assert found[0].choice.values == ["forty-five (45) calendar days", "sixty (60) calendar days"]


def test_a_later_sentence_naming_the_other_value_does_not_excuse_the_first() -> None:
    found = uniform_party_choices(PDF_ANSWER, [NON_RENEWAL], [QUESTION])
    assert [(f.phrase, f.choice.answer) for f in found] == [("Each party", "45 calendar days")]


@pytest.mark.parametrize(
    "answer",
    [
        "Both parties must give at least 45 calendar days' notice before the term ends.",
        "Either party must give written notice at least 45 calendar days before the current term ends.",
        "The parties must each give 45 calendar days' written notice.",
        "Both Customer and Provider must give 45 calendar days' notice before the term ends.",
        "Each of the parties must give written notice 45 calendar days before the current term ends.",
        "Neither party may give less than 45 calendar days' notice of non-renewal.",
    ],
)
def test_every_way_of_naming_every_party_is_read(answer: str) -> None:
    found = uniform_party_choices(answer, [NON_RENEWAL], [QUESTION])
    assert len(found) == 1 and found[0].choice.answer.startswith("45")


@pytest.mark.parametrize(
    ("answer", "quotes"),
    [
        # One party named: the choice is disclosed, not lowered.
        ("Customer must give written notice at least 45 calendar days before the current term ends.", [NON_RENEWAL]),
        # Every value the passages state, in the same sentence.
        ("Each party must give notice: Customer at least 45 calendar days and Provider at least 60 calendar days.", [NON_RENEWAL]),
        # The contract itself gives the value to every party; the other value is for something else.
        (
            "Either party may terminate on 30 days' written notice.",
            ["Either party may terminate on thirty (30) days' written notice; a party in breach may be terminated on ten (10) days' notice."],
        ),
        # A band answered with no party subject.
        ("A credit of 5% of the monthly fee applies.", ["99.0% to 99.49% | 5% of the monthly fee 98.0% to 98.99% | 10% of the monthly fee"]),
        # One value in the evidence: nothing to choose between.
        ("Each party must give 45 calendar days' notice.", ["Each party must give at least forty-five (45) calendar days' notice."]),
    ],
)
def test_controls_are_not_read_as_giving_every_party_one_value(answer: str, quotes: list[str]) -> None:
    assert uniform_party_choices(answer, quotes, [QUESTION]) == []


def test_the_pass_is_lowered_with_codes_reason_and_other_statuses_are_left_alone() -> None:
    lowered = check_values(PASS, DOCX_ANSWER, [NON_RENEWAL], QUESTION, None)
    assert (lowered.status, lowered.source) == ("needs_review", "position_check")
    assert lowered.reason == (
        "the answer gives 45 calendar days to each party; its passages state forty-five (45) calendar days, sixty (60) calendar days, "
        "and none gives 45 calendar days to every party"
    )
    review = Decision("needs_review", "position_check", "earlier reason")
    assert check_values(review, DOCX_ANSWER, [NON_RENEWAL], QUESTION, None) == review
    # Control: the same evidence, one party named.
    assert check_values(PASS, "Provider must give at least 60 calendar days' notice before that end.", [NON_RENEWAL], QUESTION, None) == PASS


@settings(max_examples=60, deadline=None)
@given(
    first=st.integers(min_value=2, max_value=400),
    second=st.integers(min_value=2, max_value=400),
    phrase=st.sampled_from(["Each party", "Both parties", "Either party", "The parties", "Neither party"]),
    named=st.booleans(),
)
def test_property_one_value_for_every_party_is_lowered_exactly_when_the_parties_differ(first: int, second: int, phrase: str, named: bool) -> None:
    quote = f"Customer must give at least {first} days' notice; Provider must give at least {second} days' notice."
    subject = "Customer" if named else phrase
    answer = f"{subject} must give at least {first} days' notice."
    lowered = check_values(PASS, answer, [quote], "How much notice must be given?", None)
    expected = "needs_review" if first != second and not named else "pass"
    assert lowered.status == expected


@pytest.mark.parametrize(("unit", "repeats"), [("Each party must give 45 days. ", 4000), ("each party ", 20000)])
def test_hostile_answers_are_read_in_linear_time(unit: str, repeats: int) -> None:
    assert_linear(lambda text: uniform_party_choices(text, [NON_RENEWAL]), unit, repeats)


# ---------------------------------------------------------------------------- through the run


CONTRACT = f"""RENEWAL TEST AGREEMENT
4. Subscription Term and Non-Renewal
4.2 Non-Renewal. {NON_RENEWAL}
5. Governing Law
This Agreement is governed by the laws of the State of Delaware.
"""


class RenewalProvider(FakeProvider):
    """Quotes §4.2 word for word and gives every party, or one party, the Customer's 45 days."""

    def __init__(self, conclusion: str) -> None:
        super().__init__()
        self.conclusion = conclusion

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        label = re.search(r"\[(sec_\d+)\] 4 Subscription Term and Non-Renewal", user)
        assert label, "§4 was not handed to the model"
        payload = {
            "findings": [
                {
                    "topic": "Notice for Non-Renewal",
                    "conclusion": self.conclusion,
                    "status_hint": "pass",
                    "evidence": [{"section_id": label.group(1), "quote": NON_RENEWAL}],
                    "guidance_reference": None,
                    "observed": "45 calendar days",
                    "required": None,
                    "suggested_position": None,
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def _ask(client: TestClient, conclusion: str) -> dict[str, Any]:
    client.app.state.provider = RenewalProvider(conclusion)  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("renewal.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": QUESTION})
    assert started.status_code == 202, started.text
    detail: dict[str, Any] = client.get(f"/api/runs/{started.json()['id']}/detail").json()
    return detail


def test_the_blind_tests_answer_is_needs_review_set_by_code_through_the_run(client: TestClient) -> None:
    finding = _ask(client, DOCX_ANSWER)["findings"][0]
    assert finding["spans"][0]["verified"] is True
    assert (finding["status"], finding["statusSource"], finding["decidedBy"]) == ("needs_review", "position_check", "code")
    assert "none gives 45 calendar days to every party" in finding["statusReason"]


def test_control_the_customers_value_for_the_customer_stays_the_models_answer(client: TestClient) -> None:
    finding = _ask(client, "Customer must give written notice at least 45 calendar days before the current term ends.")["findings"][0]
    assert (finding["status"], finding["statusSource"]) == ("pass", "model_hint")
