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

import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.runs.values import unquoted_values, value_choices
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


def test_attachment_pointers_are_not_values() -> None:
    """Triage, 2026-10-09: "Exhibit 10.1" was listed as a value in "none of the quotes"."""
    for answer in (
        "Under Attachment 10.1, fees are due in 45 days.",
        "Per Rider 3, fees are due in 45 days.",
        "Exhibit No. 10.1 sets fees due in 45 days.",
        "As set out in Exhibit 10.1, fees are due in 45 days.",
        "Addendum 2 and Annex 4.2 set fees due in 45 days.",
    ):
        assert unquoted_values(answer, ["forty-five days"], []) == [], answer
    assert unquoted_values("Exhibit 10.1 caps fees at 12%.", ["Fees are capped."], []) == ["12%"], "control: the value beside a pointer is still read"


def test_magnitude_words_are_part_of_the_value() -> None:
    """Triage: "$1.5 million" was listed against a quote of "$1,500,000"."""
    assert unquoted_values("The cap is $1.5 million.", ["liability capped at $1,500,000"], []) == []
    assert unquoted_values("The cap is $1,500,000.", ["capped at USD 1.5 million"], []) == []
    assert unquoted_values("The cap is $2.5 million.", ["liability capped at $1,500,000"], []) == ["$2.5 million"], "control"


def test_a_date_is_one_value_shown_as_written() -> None:
    """Triage: "January 1, 2024" was listed as "1" and "2024"; a day of the month is never shown as a bare number."""
    assert unquoted_values("The term runs two years from January 1, 2024.", ["for two (2) years"], []) == ["January 1, 2024"]
    assert unquoted_values("The term starts on January 1, 2024.", ["commencing on the 1st day of January, 2024"], []) == []
    assert unquoted_values("The term starts on 1 January 2024.", ["Effective Date: January 1, 2024"], []) == []
    assert unquoted_values("Renewal is due in March 2025.", ["renews each March"], []) == ["March 2025"]
    # Numeric dates (triage): ISO and unambiguous slash dates are one value; an ambiguous one is set aside, never split.
    assert unquoted_values("Signed 2024-01-01 for 3 years.", ["for three (3) years"], []) == ["2024-01-01"]
    assert unquoted_values("Signed 2024-01-01 for 3 years.", ["dated January 1, 2024, for three years"], []) == []
    assert unquoted_values("Signed 13/01/2024 for 3 years.", ["for three years"], []) == ["13/01/2024"]
    assert unquoted_values("Signed 01/13/2024 for 3 years.", ["January 13, 2024; three years"], []) == []
    assert unquoted_values("Signed 01/02/2024 for 3 years.", ["for three years"], []) == [], "day and month ambiguous: set aside"
    assert unquoted_values("Signed 2024/01/13 for 3 years.", ["for three years"], []) == ["2024/01/13"]
    assert unquoted_values("Signed 2024.01.13 for 3 years.", ["dated January 13, 2024 for three years"], []) == []
    for ambiguous in ("1/2/24", "13/1/24", "3-4-25"):
        assert unquoted_values(f"Signed {ambiguous} for 3 years.", ["for three years"], []) == [], ambiguous


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


# (repeated unit, repeats): about 12 KB each; the scaling check reads 1x and 4x (about 50 KB).
HOSTILE = [
    ("9", 12_500),
    ("one and ", 1_500),
    ("one ", 3_125),  # security audit, 2026-10-09: 13.3 s at 50 KB, and every other request waited behind it
    ("twenty-one ", 1_125),
    ("thirty (30) ", 1_000),
    ("1.", 5_000),
    ("Sections 1, ", 1_000),
]


def read_time(read: Callable[[str], object], text: str) -> float:
    best = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        read(text)
        best = min(best, time.perf_counter() - started)
    return best


def assert_linear(read: Callable[[str], object], unit: str, repeats: int) -> None:
    """Four times the input costs about four times the time; a quadratic read costs sixteen. The ratio, not a
    wall-clock bound, so a busy machine cannot fail it and a quadratic one cannot pass it."""
    small, big = read_time(read, unit * repeats), read_time(read, unit * repeats * 4)
    assert big < 8 * small + 0.02, (unit, repeats, small, big)


@pytest.mark.parametrize(("unit", "repeats"), HOSTILE, ids=[f"hostile-{i}" for i in range(len(HOSTILE))])
def test_hostile_answers_and_quotes_are_read_in_linear_time(unit: str, repeats: int) -> None:
    """Every finding read runs this, in the API's process: a long answer or quote must not stall other requests."""
    assert_linear(lambda text: unquoted_values(text, [text], [text]), unit, repeats)


def test_the_run_detail_carries_them_on_a_passage_finding(client: TestClient) -> None:
    run_id = upload_and_ask(client, "What notice period applies to termination for convenience?")["run_id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert "unquotedValues" in finding and isinstance(finding["unquotedValues"], list)
    quoted = " ".join(s["quote"] for s in finding["spans"] if s["verified"])
    for value in finding["unquotedValues"]:
        assert value not in quoted, value


# Bug hunt and review, 2026-10-09: statements the check made that were not true.
def test_a_glued_magnitude_is_part_of_the_value_or_the_value_is_set_aside() -> None:
    """ "$1.5M" was reported as "$1", a value the answer never states."""
    assert unquoted_values("The cap is $1.5M.", ["capped at $1,500,000"], []) == []
    assert unquoted_values("The cap is $2.5bn.", ["capped at $2,500,000,000"], []) == []
    assert unquoted_values("The cap is $1,500K.", ["capped at $1,500,000"], []) == []
    assert unquoted_values("The cap is $3M.", ["capped at $1,500,000"], []) == ["$3M"], "control: a different value"
    assert "$1" not in unquoted_values("The cap is $1.5Q.", ["capped at $1,500,000"], [])


def test_a_comma_that_is_not_thousands_grouping_is_not_dropped() -> None:
    """ "1,5%" (a European 1.5%) was read as 15%: unreadable, so set aside, never another value."""
    assert unquoted_values("The rate is 1,5%.", ["15% or 20%"], []) == []
    assert value_choices("The rate is 1,5%.", ["15% or 20%"], []) == []


def test_the_tail_of_a_pointer_is_not_a_value() -> None:
    """ "sec_1,500" left ",500" behind as the value 500."""
    assert unquoted_values("See sec_1,500 for the fee.", ["a fee"], []) == []


def test_dash_dates_are_one_value() -> None:
    assert unquoted_values("Signed 2024–01–01.", ["for three years"], []) == ["2024–01–01"]
    assert unquoted_values("Signed 2024–01–01.", ["dated January 1, 2024"], []) == []


def test_a_value_of_another_kind_does_not_count_as_quoted() -> None:
    """Review R2: an answer of "5%" over "within 5 business days … a credit of 10%" was told nothing; the 5 in the
    quote is days. A value with a kind (percent, money, duration) is quoted only by a value of that kind."""
    quote = "Provider will respond within 5 business days and pay a credit of 10% of the monthly fee"
    assert unquoted_values("The credit is 5%.", [quote], []) == ["5%"]
    assert unquoted_values("The credit is 10%.", [quote], []) == [], "control"
    assert unquoted_values("Respond within 5 days.", [quote], []) == [], "control: 5 business days is 5 days of the same family"
    assert unquoted_values("Section 5 applies.", [quote], []) == [], "control: a pointer"


def test_a_quantity_after_a_pointer_is_still_a_value() -> None:
    """Bug hunt #9: a pointer list ("Sections 1, 2 and 3") swallowed the quantity after it: "Under Section 4.2, 90 days"."""
    assert unquoted_values("Under Section 4.2, 90 days' notice applies.", ["thirty (30) days' notice"], []) == ["90 days"]
    assert unquoted_values("Sections 1, 2 and 3 apply.", ["no values"], []) == [], "control: a list of pointers"


def test_a_pointer_in_the_question_is_not_a_value_the_question_names() -> None:
    """Review R1: a question "Under Section 10, what credit applies?" set 10% aside as the reader's own value."""
    quote = "a credit of 5% below 99.9%, or 10% below 99.0%"
    choices = value_choices("The credit is 10%.", [quote], ["Under Section 10, what credit applies at 98.5%?"])
    assert [c.answer for c in choices] == ["10%"]
