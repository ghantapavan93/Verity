"""A number the answer states that no quote states is said, by code, beside the answer.

Found by the holdout audit (2026-10-09, run 629e5e921f5048d5): the answer "one (1) day of service credit" stood on a
quote that stops before the credit, and the card showed the quote as found word for word. A located quote proves where
it is, not what the answer says; a value the answer states and no quote carries is the part of that gap code can see.

The invariant: every value the answer states (digits, number words before a unit, money, percentages) that no verified
quote, nor the reader's own question or guidance, states is reported, by value, not by spelling; a reference ("§6.4",
"Sections 2, 11, and 13", "regulation 72(9)", "sec_7", an enumerator "(2)") is not a value. It is a disclosure: it
changes no status, and its absence claims nothing (a quote can state the right number for the wrong band: AD7).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.runs.values import unquoted_values
from tests.support import upload_and_ask


def test_the_audits_service_credit_is_reported() -> None:
    answer = "The customer receives one (1) day of service credit for the first sixty (60) minutes of downtime during Normal Business Hours."
    quote = "If the Service is unavailable for more than sixty minutes outside of Normal Business Hours ("
    question = "What service credit does the customer receive for the first sixty minutes of downtime during Normal Business Hours?"
    assert unquoted_values(answer, [quote], [question]) == ["one (1) day"]


def test_a_value_a_quote_states_in_any_spelling_is_not_reported() -> None:
    cases = [
        ("Notice is 30 days.", "on thirty days' notice"),
        ("Notice is thirty (30) days.", "on 30 days' notice"),
        ("The fee is $1,500.", "a fee of USD 1500.00"),
        ("Late payments accrue 5% interest.", "interest at five percent per month"),
        ("The term is two years.", "for a term of 2 years"),
        ("Notice must be 60 days.", "upon thirty (60) days' written notice"),  # a quote is read whole, contradictions and all
    ]
    for answer, quote in cases:
        assert unquoted_values(answer, [quote], []) == [], (answer, quote)


def test_references_handles_and_enumerators_are_not_values() -> None:
    answer = (
        "Excluded are (1) Unlimited Claims and (2) Increased Claims under Sections 2, 11, and 13, §6.4 and Section 8.1(a); see sec_7 "
        "and Cloud Service Agreement (part 1), and regulation 72(9) of the Regulations, as stated in.3."
    )
    assert unquoted_values(answer, ["Unlimited Claims are excluded."], []) == []


def test_the_readers_own_numbers_are_not_reported() -> None:
    answer = "The contract allows 45 days, short of the 60 days the guidance requires."
    assert unquoted_values(answer, ["within forty-five (45) days"], ["Notice must be at least 60 days."]) == []


def test_money_percentages_and_computed_totals_are_reported_as_written() -> None:
    assert unquoted_values("The total payable is $78,600.00.", ["Fees are $6,000 per month for 12 months, plus onboarding of $6,600."], []) == ["$78,600.00"]
    assert unquoted_values("Customer may terminate after 45 days.", ["If Provider cannot resolve the issue, Customer may terminate."], []) == ["45 days"]
    assert unquoted_values("The cap is 2.5 times the fees.", ["The cap is twice the fees."], []) == ["2.5 times"]


def test_a_right_number_in_the_wrong_band_is_not_claimed_as_caught() -> None:
    """Control (AD7): the table quote states 5% and 10%; presence is all this checks, so nothing is reported."""
    quote = "99.0% to 99.49% | 5% of the monthly fee 98.0% to 98.99% | 10% of the monthly fee"
    assert unquoted_values("A credit of 5% applies at 98.7% availability.", [quote], ["What credit applies at 98.7%?"]) == []


@pytest.mark.parametrize("hostile", ["9" * 5000, "one and " * 3000, "§" + "1." * 4000])
def test_hostile_answers_are_read_in_linear_time(hostile: str) -> None:
    import time

    started = time.perf_counter()
    unquoted_values(hostile, [hostile[:100]], [])
    assert time.perf_counter() - started < 1.0


def test_the_run_detail_carries_them_on_a_passage_finding(client: TestClient) -> None:
    run_id = upload_and_ask(client, "What notice period applies to termination for convenience?")["run_id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert "unquotedValues" in finding and isinstance(finding["unquotedValues"], list)
    quoted = " ".join(s["quote"] for s in finding["spans"] if s["verified"])
    for value in finding["unquotedValues"]:
        assert value not in quoted, value
