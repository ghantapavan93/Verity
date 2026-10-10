"""When the cited passages state several values of the kind the answer gives, code says so beside them.

Found by the evaluation workstream (2026-10-09): a service-credit table quoted word for word holds 5%, 10% and 25%, and
the answer chose 5% where the band gives 10% (AD7). Band answers were right in 2 of 6 on record, and each wrong one read
as a plain pass over a quote "found word for word"; the unquoted-value check names none of them, because the wrong value
is in the quote. Which value applies is a reading of the passage; code does not make it. What code can say, truly, is
that the passage offered several values of that kind and which one the answer used.

The invariant: for each kind the answer gives (a percentage, money, or a duration within one unit family), when the
finding's verified passages together state two or more distinct values of that kind and the answer uses some but not all
of them, code lists those values (in order, at most 8, then a count) and the ones the answer used. A value the question
names is the condition asked about and set aside; a guidance's value stays among the passages. It changes no status.
The predicate was pre-registered per quote, amended openly to pooled passages, and revised after triage; the counts and
their post-hoc labels are in docs/FAILURE-ENVELOPE.md.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.runs.values import ValueChoice, unquoted_values, value_choices
from tests.support import upload_and_ask
from tests.test_unquoted_values import HOSTILE, assert_linear

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
    choices = value_choices("Notice is 30 days' prior written notice.", quotes, ["Does the notice meet our guidance?"], guidance=["At least 60 days."])
    assert [(c.answer, c.values) for c in choices] == [("30 days", ["thirty (30) days", "ninety (90) days"])]


def test_one_provision_is_one_value_however_it_spells_it() -> None:
    """Triage, revision: "thirty (60) days" is one provision; the bracket rule that listed it twice is gone."""
    assert value_choices("The notice period is 60 days.", ["upon thirty (60) days' written notice to Provider"], []) == []


def test_the_readers_own_values_stay_among_the_passages() -> None:
    """Triage, revision: set aside only on the answer's side. Guidance "at least 90 days", passages stating 30 and 90, an
    answer of 30: the passages offered a choice, and hiding the 90 hid the conflict."""
    quotes = ["terminate on thirty (30) days' notice", "notwithstanding the above, not on less than ninety (90) days' notice"]
    choices = value_choices("Notice is 30 days.", quotes, ["What notice applies?"], guidance=["At least 90 days' notice."])
    assert [(c.answer, c.values) for c in choices] == [("30 days", ["thirty (30) days", "ninety (90) days"])]


def test_a_value_the_passages_do_not_state_is_not_a_choice() -> None:
    """Triage, revision: an answer computed from the passages ($71,100 + $7,500 = $78,600) chose nothing among them;
    unquoted_values already names it. Only answer values that are among the passages' values are reported as used."""
    quotes = ["Total | $71,100.00", "a one-time onboarding fee of $7,500.00"]
    assert value_choices("The total payable is $78,600.00.", quotes, []) == []
    mixed = value_choices("The total is USD 64,000: USD 4,000 and USD 60,000.", ["Implementation USD 4,000; licence USD 2,500 a month"], [])
    assert [(c.answer, c.values) for c in mixed] == [("USD 4,000", ["USD 4,000", "USD 2,500"])]


def test_durations_compare_within_one_unit_family_and_equivalents_merge() -> None:
    """Triage, revision: a term (12 months) and a notice (30 days) are not a choice; one year and twelve months are one value."""
    term_and_notice = ["The Initial Term is twelve (12) months.", "Either party may terminate on thirty (30) days' notice."]
    assert value_choices("Notice is 30 days.", term_and_notice, []) == []
    assert value_choices("The term is one year.", ["The term is one (1) year, being twelve (12) months."], []) == []
    weeks = value_choices("Notice is 2 weeks.", ["notice of two weeks, or 30 days for cause"], [])
    assert [(c.answer, c.values) for c in weeks] == [("2 weeks", ["two weeks", "30 days"])]


@pytest.mark.parametrize(("unit", "repeats"), HOSTILE, ids=[f"hostile-{i}" for i in range(len(HOSTILE))])
def test_hostile_text_is_read_in_linear_time(unit: str, repeats: int) -> None:
    assert_linear(lambda text: value_choices(text, [text], [text]), unit, repeats)


def test_the_run_detail_carries_them(client: TestClient) -> None:
    run_id = upload_and_ask(client, "What notice period applies to termination for convenience?")["run_id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert isinstance(finding["valueChoices"], list)
    quoted = " ".join(s["quote"] for s in finding["spans"] if s["verified"])
    for choice in finding["valueChoices"]:
        assert all(value in quoted for value in choice["values"]), "every value listed is in a verified quote"


def test_the_readers_value_is_recognised_in_any_unit() -> None:
    """C09: the question names "sixty minutes"; an answer repeating it chose nothing, though code compares in seconds."""
    quote = "For the first sixty (60) minutes of Downtime during Normal Business Hours or the first four (4) hours outside"
    question = "What service credit does the customer receive for the first sixty minutes of downtime?"
    assert value_choices("One (1) day of credit for the first sixty (60) minutes.", [quote], [question]) == []


def test_an_answer_that_gives_every_value_made_no_choice() -> None:
    """A conditional answer that states both periods (U1: 30 days, or 90 days after the first year) left nothing out:
    "which one applies" would be untrue. A choice is some of the passages' values used and others left out."""
    quotes = ["terminate on thirty (30) days' notice", "after the first year, on ninety (90) days' notice"]
    assert value_choices("Thirty (30) days, or ninety (90) days after the first year.", quotes, []) == []
    assert [c.answer for c in value_choices("Thirty (30) days.", quotes, [])] == ["Thirty (30) days"]


def test_the_condition_the_question_names_is_not_an_alternative() -> None:
    """Fresh evaluation C1 (2026-10-09), a control: one clause, "7% … for each month in which availability falls below
    99.5%", asked about "below 99.5%". The question's own value is the condition asked about, set aside on both sides; a
    guidance's value stays among the passages, as a competing standard (test above)."""
    quote = "Supplier shall pay a service credit of 7% of the monthly fee for each month in which availability falls below 99.5%."
    question = "What service credit does the Supplier pay for a month in which availability falls below 99.5%?"
    assert value_choices("A service credit of 7% for a month below 99.5%.", [quote], [question]) == []


# ------------------------------------------------------------------------------------------- no text can make them raise
# Bug hunt, 2026-10-09: "ſep 2024" (a long s) matched the month pattern under IGNORECASE, which folds Unicode case, while
# the lookup lowered it, which does not: StopIteration, and every read of the run a 500. "thouſand" did the same to the
# magnitude table (KeyError). These read model output and contract text on every finding read; no input may raise.
_PIECES = [*"0123456789 ,.-/%$€£()§:;'\n\u00a0\u2013\u2014\u017f\u212akı\u0130", "thousand", "million", "Sep", "January"]
_PIECES += [
    "days",
    "months",
    "percent",
    "Section ",
    "sec_",
    "thirty ",
    "one ",
    "USD ",
    "EUR ",
    "thou\u017fand",
    "\u017fep",
    "\u212aelvin",
    " \u017fep 2024 ",
    " 2 thou\u017fand ",
]
_PIECES += ["9" * 45, "1" * 31, "1e999 ", "inf "]  # review, 2026-10-09: an oversized digit run must be set aside, not raise
_CONTRACT_TEXT = st.lists(st.sampled_from(_PIECES), max_size=40).map("".join)


@settings(max_examples=400, deadline=None)
@given(answer=_CONTRACT_TEXT, quote=_CONTRACT_TEXT, question=_CONTRACT_TEXT)
def test_no_text_makes_the_value_checks_raise(answer: str, quote: str, question: str) -> None:
    unquoted_values(answer, [quote], [question])
    value_choices(answer, [quote], [question], [question])


def test_unicode_case_folds_are_read_not_raised() -> None:
    assert value_choices("The fee is 5%.", ["5% or 10%"], ["ſep 2024"]) == [ValueChoice("percent", "5%", ["5%", "10%"], 0)]
    assert unquoted_values("$2 thouſand", ["$2,000"], []) == []


def test_a_digit_run_longer_than_any_contract_value_is_set_aside_not_raised() -> None:
    """Review, 2026-10-09: a run of a million digits overflowed Decimal's exponent on normalising (a 500 on the read)."""
    huge = "9" * 1_000_001
    assert unquoted_values("The total is 5 days.", [huge], []) == ["5 days"]
    assert value_choices(f"{huge}%", ["5% or 10%"], []) == []
