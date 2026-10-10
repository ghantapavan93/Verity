"""When a verified quote states several values of the kind the answer gives, code says so beside the quote.

Found by the evaluation workstream (2026-10-09): a service-credit table quoted word for word holds 5%, 10% and 25%, and
the answer chose 5% where the band gives 10% (AD7). Band answers were right in 2 of 6 on record, and each wrong one read
as a plain pass over a quote "found word for word"; the unquoted-value check names none of them, because the wrong value
is in the quote. Which value applies is a reading of the passage; code does not make it. What code can say, truly, is
that the passage offered several values of that kind and which one the answer used.

The invariant: for each answer value that is a percentage, money or a duration (and not stated by the reader's own
question or guidance), every verified quote that states two or more distinct values of that kind is disclosed with those
values (document order, at most 8, then a count) and the answer's value. It changes no status. Pre-registered predicate
and expected counts: C:/Temp/verity-qa/m3/impl/candidates-prereg.json (sha256 05de4533…).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.runs.values import value_choices
from tests.support import upload_and_ask
from tests.test_unquoted_values import HOSTILE

AD7_QUOTE = (
    "Monthly Availability | Service Credit 99.5% or higher | No credit 99.0% to 99.49% | 5% of the monthly fee "
    "98.0% to 98.99% | 10% of the monthly fee Below 98.0% | 25% of the monthly fee"
)


def test_the_band_table_is_disclosed_with_the_answers_choice() -> None:
    choices = value_choices(
        "A service credit of 5% of the monthly fee applies if monthly availability is 98.7%.",
        [AD7_QUOTE],
        ["What service credit applies if monthly availability is 98.7%?"],
    )
    assert len(choices) == 1
    choice = choices[0]
    assert choice.kind == "percent" and choice.answer == "5%"
    assert choice.values == ["99.5%", "99.0%", "99.49%", "5%", "98.0%", "98.99%", "10%", "25%"] and choice.more == 0


def test_a_right_answer_is_disclosed_the_same_way() -> None:
    """The line is true whichever value is right: it never says the answer is wrong."""
    choices = value_choices("A credit of 10% applies at 98.7%.", [AD7_QUOTE], ["Which credit applies at 98.7%?"])
    assert [c.answer for c in choices] == ["10%"]


def test_kinds_money_and_durations() -> None:
    fees = "Platform Professional: USD 48,000 per year. Data Connector Pack: USD 1,200 per month."
    assert [(c.kind, c.answer, c.values) for c in value_choices("The annual fee is $48,000.", [fees], [])] == [
        ("money", "$48,000", ["USD 48,000", "USD 1,200"])
    ]
    notice = "either party may terminate on thirty (30) days' notice, or on ninety (90) days' notice after the first year"
    choice = value_choices("Notice is thirty (30) days.", [notice], [])
    assert [(c.kind, c.answer, c.values) for c in choice] == [("duration", "thirty (30) days", ["thirty (30) days", "ninety (90) days"])]


def test_controls_that_must_not_fire() -> None:
    one_value = "Customer may terminate on thirty (30) days' notice."
    assert value_choices("Notice is 30 days.", [one_value], []) == [], "one value of the kind"
    assert value_choices("The credit is 5%.", ["Notice is 30 days, or 60 days for cause."], []) == [], "the quote's values are another kind"
    assert value_choices("At 98.7% the credit applies.", [AD7_QUOTE], ["What applies at 98.7%?"]) == [], "the answer's only value is the reader's own"
    assert value_choices("Notice is 30 days.", ["30 days or 30 days"], []) == [], "one distinct value, said twice"
    assert value_choices("The term runs two years from January 1, 2024.", ["from January 1, 2024 or March 1, 2024 for two years"], []) == [], (
        "dates are not a listed kind"
    )


def test_the_passages_are_read_together_and_long_lists_are_capped() -> None:
    """Pre-registration v2: the values a band table splits over two quotes are one choice (U3: 5% and 8%)."""
    choices = value_choices("A discount of 8% applies to 750 units.", ["500 to 999 5%", "1,000 to 4,999 8%"], ["What discount applies to 750 units?"])
    assert [(c.kind, c.answer, c.values) for c in choices] == [("percent", "8%", ["5%", "8%"])]
    many = " ".join(f"{n}% of the fee" for n in range(1, 13))
    capped = value_choices("The credit is 3%.", ["no values here", many], [])
    assert capped[0].values == [f"{n}%" for n in range(1, 9)] and capped[0].more == 4


def test_a_provision_that_overrides_another_is_one_choice() -> None:
    """C33: 30 days in 4.1 and, "notwithstanding Section 4.1", 90 days in 12.3."""
    quotes = [
        "4.1 Either party may terminate this Agreement for convenience upon thirty (30) days' prior written notice to the other party.",
        "12.3 Notwithstanding Section 4.1, neither party may terminate for convenience on less than ninety (90) days' prior written notice.",
    ]
    choices = value_choices("Notice is 30 days' prior written notice.", quotes, ["Does the notice meet our guidance?", "At least 60 days."])
    assert [(c.answer, c.values) for c in choices] == [("30 days", ["thirty (30) days", "ninety (90) days"])]


def test_a_quote_that_contradicts_itself_offers_both_values() -> None:
    """AD14: "thirty (60) days" states 30 and 60."""
    choices = value_choices("The notice period is 60 days.", ["upon thirty (60) days' written notice to Provider"], [])
    assert [c.values for c in choices] == [["thirty (60) days", "(60) days"]]


def test_the_readers_own_values_are_set_aside_on_both_sides() -> None:
    """C09: the question names "sixty minutes"; the passage's other duration alone is not a choice."""
    quote = "For the first sixty (60) minutes of Downtime during Normal Business Hours or the first four (4) hours outside"
    question = "What credit does the customer receive for the first sixty minutes of downtime?"
    assert value_choices("The customer receives one (1) day of credit.", [quote], [question]) == []


@pytest.mark.parametrize("hostile", HOSTILE, ids=[f"hostile-{i}" for i in range(len(HOSTILE))])
def test_hostile_text_is_read_in_linear_time(hostile: str) -> None:
    started = time.perf_counter()
    value_choices(hostile, [hostile], [hostile])
    assert time.perf_counter() - started < 0.5, len(hostile)


def test_the_run_detail_carries_them(client: TestClient) -> None:
    run_id = upload_and_ask(client, "What notice period applies to termination for convenience?")["run_id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert isinstance(finding["valueChoices"], list)
    quoted = " ".join(s["quote"] for s in finding["spans"] if s["verified"])
    for choice in finding["valueChoices"]:
        assert all(value in quoted for value in choice["values"]), "every value listed is in a verified quote"
