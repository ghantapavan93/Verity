"""Code reads a period as the text writes it, or not at all (policy-v17, the stress test of 2026-10-30).

Six findings, one primitive (`policy.durations.parse_durations` and the readings built on it):

- A range or a list written with its unit once was read as its last number alone, and each end of a range as a floor of
  its own: "between 30 and 90 days" was "at least 90", so 60 days was code's shortfall, and "at least 30 but no more than
  90 days" kept only "at most 90", so 10 days carried code's "consistent". Number words were summed across "and":
  "between thirty and sixty days" was ninety.
- A range whose floor and ceiling are in different units was compared in two units at once (6 weeks against "at least 14
  days and no more than 8 weeks" was a shortfall).
- A period beside a negation ("Customer is not required to give thirty (30) days' notice") was code's "the contract
  provides 30 calendar days".
- A period whose words and digits disagree ("sixty (20) days") counted only when it came first, so the model's
  `observed` and its quote order decided the status; "56 days" was not the quote's "eight (8) weeks".
- A character a reader does not see ("9\\u200b0 days", "15\\u200e days") or a typeset dash ("forty\\u2011five") changed
  the number code read.
- A pass whose stated position names a period no verified quote states stood when the quotes state none.

The invariants: a computed shortfall and code's "consistent" sentence hold only against what the guidance states; the
same evidence and guidance give one status whatever the model's wording; code lowers a status, never raises one.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.policy.durations import (
    Duration,
    DurationUnit,
    GuidanceRule,
    Operator,
    evaluate,
    observed_fact,
    parse_durations,
    parse_rule,
    stated_periods,
    words_to_number,
)
from app.runs.status import decide

DAYS = DurationUnit.CALENDAR_DAY
TOPIC = "Termination for convenience"
_WORDS = {
    5: "five", 10: "ten", 14: "fourteen", 15: "fifteen", 20: "twenty", 21: "twenty-one", 30: "thirty", 45: "forty-five",
    60: "sixty", 75: "seventy-five", 90: "ninety", 120: "one hundred twenty",
}  # fmt: skip


def _written(value: int, form: str) -> str:
    return {"digits": str(value), "words": _WORDS[value], "both": f"{_WORDS[value]} ({value})"}[form]


def _days(value: int) -> Duration:
    return Duration(Decimal(value), DAYS)


def _quote(value: int) -> str:
    return f"Either party may terminate this Agreement for convenience on {value} days' written notice to the other party."


# ----------------------------------------------------------------------------- ranges and lists in the guidance

# How a guidance writes a range: the joining words before and between its two numbers.
RANGES = [
    ("between {lo} and {hi}", "range"),
    ("from {lo} to {hi}", "range"),
    ("{lo} to {hi}", "range"),
    ("{lo} through {hi}", "range"),
    ("{lo}-{hi}", "range"),
    ("{lo}–{hi}", "range"),
    ("at least {lo} and no more than {hi}", "bounds"),
    ("at least {lo} but no more than {hi}", "bounds"),
    ("at least {lo} and at most {hi}", "bounds"),
    ("no less than {lo} and no more than {hi}", "bounds"),
    ("not less than {lo} nor more than {hi}", "bounds"),
    ("a minimum of {lo} and a maximum of {hi}", "bounds"),
]
PAIRS = [(10, 20), (14, 21), (30, 60), (30, 90), (45, 75), (60, 120)]


@settings(max_examples=300, deadline=None)
@given(
    st.sampled_from(RANGES),
    st.sampled_from(PAIRS),
    st.sampled_from(["digits", "words", "both"]),
    st.booleans(),
    st.sampled_from([5, 10, 14, 15, 20, 21, 30, 45, 60, 75, 90, 120]),
)
def test_a_range_in_the_guidance_is_read_whole_or_not_at_all(
    phrasing: tuple[str, str], pair: tuple[int, int], form: str, repeat_unit: bool, contract: int
) -> None:
    """Over every way of writing a range: the rule is the range or no rule, never one end of it, and the status code
    computes for any contract period is a shortfall only outside the range and "consistent" only inside it."""
    lo, hi = pair
    template, _ = phrasing
    if "{lo}-" in template or "{lo}–" in template:
        form = "digits"  # "thirty-sixty days" is no way to write a range; "sixty-one hundred" is a number
    low = _written(lo, form) + (" days" if repeat_unit else "")
    guidance = f"Termination for convenience notice must be {template.format(lo=low, hi=_written(hi, form))} days."
    rule = parse_rule(guidance, TOPIC)
    assert rule is None or (rule.operator, rule.duration, rule.maximum, rule.alternatives) == (Operator.MINIMUM, _days(lo), _days(hi), ()), guidance
    decision = decide("pass", None, None, True, True, quotes=[_quote(contract)], guidance=guidance, topic=TOPIC)
    if decision.source == "computed_days":
        assert not lo <= contract <= hi, (guidance, contract, decision)
        assert f"between {lo} and {hi} calendar days" in decision.reason
    if "code found the day counts consistent" in decision.reason:
        assert lo <= contract <= hi, (guidance, contract, decision)


def test_the_ranges_the_stress_test_found_are_read_as_ranges() -> None:
    for guidance in (
        "Termination for convenience notice must be between 30 and 90 days.",
        "Termination for convenience notice must be between thirty (30) and ninety (90) days.",
        "Termination for convenience notice must be 30 through 90 days.",
        "Termination for convenience notice must be from 30 to 90 days.",
        "Termination for convenience notice must be at least 30 but no more than 90 days.",
        "Termination for convenience notice must be at least 30 and at most 90 days.",
        "Termination for convenience notice must be 30-90 days.",
        "Termination for convenience notice must be between 30 days and 90 days.",
        "Termination for convenience notice must be 30 days to 90 days.",
    ):
        rule = parse_rule(guidance, TOPIC)
        assert rule is not None and (rule.duration, rule.maximum) == (_days(30), _days(90)), guidance
        assert decide("pass", None, None, True, True, quotes=[_quote(60)], guidance=guidance, topic=TOPIC).source == "model_hint"
        for outside in (10, 100):
            assert decide("pass", None, None, True, True, quotes=[_quote(outside)], guidance=guidance, topic=TOPIC).source == "computed_days"
    words = parse_rule("Notice must be between one and three months.")
    assert words is not None and (words.duration, words.maximum) == (Duration(Decimal(1), DurationUnit.MONTH), Duration(Decimal(3), DurationUnit.MONTH))


@pytest.mark.parametrize(
    "guidance",
    [
        "Termination for convenience notice must be 30, 60 or 90 days.",  # alternatives, none of them stated as a bound
        "Termination for convenience notice must be 30 or 90 days.",
        "Termination for convenience requires 90 days' notice, or 30 days for small accounts.",  # two bare periods
        "Termination for convenience notice must be 30 or more but under 60 days.",  # a bare comparative code does not read
        "Termination for convenience requires at least thirty (60) days' notice. Invoices are payable within 30 days.",  # ambiguous
        "Termination for convenience must be on at least 90 days' notice, but no more than 30 days.",  # bounds that do not pair
    ],
)
def test_a_sentence_code_cannot_read_whole_is_no_rule_never_part_of_one(guidance: str) -> None:
    assert parse_rule(guidance, TOPIC) is None
    for contract in (10, 45, 100):
        decision = decide("pass", None, None, True, True, quotes=[_quote(contract)], guidance=guidance, topic=TOPIC)
        assert decision.source != "computed_days" and "consistent" not in decision.reason


def test_a_shortfall_is_codes_only_against_every_period_the_rules_sentence_states() -> None:
    guidance = "Termination for convenience requires at least 90 days' notice, or 30 days for small accounts."
    rule = parse_rule(guidance, TOPIC)
    assert rule is not None and rule.duration == _days(90) and [r.duration for r in rule.alternatives] == [_days(30)]
    split = decide("pass", None, None, True, True, quotes=[_quote(60)], guidance=guidance, topic=TOPIC)
    assert (split.status, split.source) == ("pass", "model_hint") and "does not fall short of them all" in split.reason
    assert decide("needs_review", None, None, True, True, quotes=[_quote(60)], guidance=guidance, topic=TOPIC).source == "model_hint"
    # Short of both: code's, as before.
    assert decide("pass", None, None, True, True, quotes=[_quote(10)], guidance=guidance, topic=TOPIC).source == "computed_days"
    # Control: the enterprise case keeps its reading, a floor of 30 and a floor of 90 (test_policy_rules).
    enterprise = parse_rule("Termination requires at least 30 days' notice, or 90 days for enterprise agreements.")
    assert enterprise is not None and enterprise.duration == _days(30) and [r.duration for r in enterprise.alternatives] == [_days(90)]


def test_controls_a_period_alone_is_read_as_before() -> None:
    assert (r := parse_rule("Notice period: 30 days.")) is not None and (r.operator, r.duration, r.maximum) == (Operator.MINIMUM, _days(30), None)
    assert (r := parse_rule("Cure within 10 business days.")) is not None and r.operator is Operator.MAXIMUM
    assert (r := parse_rule("The cure period may be no longer than 15 days.")) is not None and r.operator is Operator.MAXIMUM
    assert (r := parse_rule("Notice must be not less than 30 nor more than 60 days.")) is not None and (r.duration, r.maximum) == (_days(30), _days(60))
    assert parse_rule("Termination without cause requires at least 30 days' notice.") is None  # policy-v4: a negation code does not read


# ----------------------------------------------------------------------------- number words and digits


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(sorted(_WORDS)), st.sampled_from(sorted(_WORDS)), st.sampled_from([" and ", " or ", " to "]))
def test_number_words_are_never_summed_across_a_joining_word(a: int, b: int, joiner: str) -> None:
    """ "thirty and sixty days" states thirty and sixty, never ninety: every number written is read, and no other."""
    text = f"between {_WORDS[a]}{joiner}{_WORDS[b]} days"
    assert {d.value for m in parse_durations(text) for d in m.readings} == {Decimal(a), Decimal(b)}
    assert words_to_number(f"{_WORDS[a]}{joiner}{_WORDS[b]}") is None


def test_number_words_still_read_as_numbers() -> None:
    assert words_to_number("one hundred and twenty") == 120 and words_to_number("forty-five") == 45 and words_to_number("two thousand") == 2000
    assert words_to_number("twenty one") == 21 and words_to_number("seventeen") == 17 and words_to_number("a") == 1


def test_digits_grouped_in_thousands_are_one_number() -> None:
    assert [m.duration for m in parse_durations("within 1,095 days")] == [_days(1095)]
    assert [m.duration for m in parse_durations("1,000 days")] == [_days(1000)]
    assert parse_durations("1,5 days") == []  # a European decimal is not read as 5 or 15


# ----------------------------------------------------------------------------- the quote side

QUOTE_RANGES = ["{a} or {b} days' notice", "between {a} and {b} days' notice", "{a} to {b} days' notice", "{a}, {b} or 120 days' notice"]


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(QUOTE_RANGES), st.sampled_from([(10, 90), (15, 60), (30, 45)]), st.sampled_from(["digits", "words", "both"]))
def test_every_period_a_quote_writes_together_is_a_period_it_states(template: str, pair: tuple[int, int], form: str) -> None:
    a, b = pair
    quote = "Either party may terminate on " + template.format(a=_written(a, form), b=_written(b, form))
    assert {_days(a), _days(b)} <= stated_periods(quote), quote
    # The several-periods rule then decides: 10 or 90 days against a floor of 50 is no pass and no shortfall of code's.
    periods = {a, b, *([120] if "120" in template else [])}
    decision = decide("pass", None, None, True, True, quotes=[quote], guidance="We require at least 50 days' notice.")
    meets = {p >= 50 for p in periods}
    expected = "ambiguous_fact" if len(meets) > 1 else ("model_hint" if meets == {True} else "computed_days")
    assert decision.source == expected, (quote, decision)


# ----------------------------------------------------------------------------- units of a range


EXACT_UNITS = [(DurationUnit.CALENDAR_DAY, 1), (DurationUnit.WEEK, 7)]


@settings(max_examples=400, deadline=None)
@given(
    st.sampled_from(EXACT_UNITS),
    st.integers(0, 12),
    st.sampled_from(EXACT_UNITS),
    st.integers(0, 12),
    st.sampled_from(EXACT_UNITS),
    st.integers(0, 12),
)
def test_a_range_compares_in_one_unit(
    left: tuple[DurationUnit, int], n: int, low: tuple[DurationUnit, int], lo: int, high: tuple[DurationUnit, int], hi: int
) -> None:
    """A range's outcome is its floor's and its ceiling's together, whatever unit each is written in, and writing a
    period in an equal unit never changes it (6 weeks against "at least 14 days and no more than 8 weeks" was code's
    shortfall, stress test 2026-10-30)."""
    fact = observed_fact(f"{n} {'days' if left[0] is DAYS else 'weeks'}")
    floor, ceiling = Duration(Decimal(lo), low[0]), Duration(Decimal(hi), high[0])
    ranged = evaluate(fact, GuidanceRule(Operator.MINIMUM, floor, "", maximum=ceiling)).outcome
    alone = {evaluate(fact, GuidanceRule(Operator.MINIMUM, floor, "")).outcome, evaluate(fact, GuidanceRule(Operator.MAXIMUM, ceiling, "")).outcome}
    assert ranged == ("pass" if alone == {"pass"} else "needs_review")
    in_days = observed_fact(f"{n * left[1]} days")
    as_days = GuidanceRule(Operator.MINIMUM, _days(lo * low[1]), "", maximum=_days(hi * high[1]))
    assert evaluate(in_days, as_days).outcome == ranged


def test_a_mixed_unit_range_names_each_bound_in_its_own_unit() -> None:
    guidance = "Termination notice must be at least 14 days and no more than 8 weeks."
    weeks = "Either party may terminate this Agreement for convenience on six (6) weeks' written notice to the other party."
    decision = decide("pass", None, None, True, True, quotes=[weeks], guidance=guidance, topic="Termination notice")
    assert decision.source == "model_hint" and "between 14 calendar days and 8 weeks" in decision.reason
    reverse = decide("pass", None, None, True, True, quotes=[weeks], guidance="Termination notice must be at least 2 weeks and no more than 30 days.")
    assert (reverse.status, reverse.source) == ("needs_review", "computed_days") and "between 2 weeks and 30 calendar days" in reverse.reason


# ----------------------------------------------------------------------------- one status whatever the model's wording

AMBIGUOUS = "Either party may terminate this Agreement for convenience on sixty (20) days' written notice."
CLEAN_45 = "Either party may terminate this Agreement for convenience on 45 days' written notice following a Change of Control."
GUIDANCE_30 = "Termination for convenience requires at least 30 days' written notice."


@settings(max_examples=60, deadline=None)
@given(
    st.permutations([AMBIGUOUS, CLEAN_45]),
    st.sampled_from([None, "45 days", "60 days", "20 days", "sixty (20) days"]),
    st.sampled_from([GUIDANCE_30, "Termination for convenience requires at least 50 days' notice."]),
)
def test_an_ambiguous_period_anywhere_in_the_quotes_decides_whatever_the_model_points_at(quotes: list[str], observed: str | None, guidance: str) -> None:
    decision = decide("pass", observed, None, True, True, quotes=quotes, guidance=guidance, topic=TOPIC)
    assert (decision.status, decision.source) == ("needs_review", "ambiguous_fact")
    assert "the words say 60 and the digits say 20" in decision.reason
    # In one quote, in either order the contract writes them.
    for clause in (
        f"{AMBIGUOUS[:-1]}, or on 45 days' notice following a Change of Control.",
        f"{CLEAN_45[:-1]}, or otherwise on sixty (20) days' written notice.",
    ):
        assert decide("pass", observed, None, True, True, quotes=[clause], guidance=guidance, topic=TOPIC).source == "ambiguous_fact"


def test_an_ambiguous_period_beside_the_quote_or_in_the_guidance_is_never_dropped() -> None:
    sub_quote = "on 45 days' written notice following a Change of Control"
    passage = f"Either party may terminate on sixty (20) days' written notice, or {sub_quote}."
    beside = decide("pass", None, None, True, True, quotes=[sub_quote], guidance=GUIDANCE_30, topic=TOPIC, passages=[passage])
    assert "another period" in beside.reason and "consistent" not in beside.reason
    two_rules = "Termination for convenience requires at least 30 days' written notice. Enterprise agreements require ninety (60) days."
    decision = decide("pass", None, None, True, True, quotes=[CLEAN_45], guidance=two_rules, topic=TOPIC)
    assert decision.source == "model_hint" and "does not read" in decision.reason and "consistent" not in decision.reason


@pytest.mark.parametrize("observed", ["8 weeks", "56 days", "eight (8) weeks'", None])
def test_a_period_stated_in_an_equal_unit_is_the_same_period(observed: str | None) -> None:
    quote = "Either party may terminate this Agreement for convenience on eight (8) weeks' written notice."
    decision = decide("pass", observed, None, True, True, quotes=[quote], guidance=GUIDANCE_30, topic=TOPIC)
    assert (decision.status, decision.source) == ("pass", "model_hint") and "consistent" in decision.reason


def test_a_pass_stating_a_period_no_quote_states_is_lowered_when_the_quotes_state_none() -> None:
    quote = "Either party may terminate this Agreement for convenience upon written notice to the other party."
    for observed in ("120 days' written notice", "90 days' written notice"):
        lowered = decide("pass", observed, None, True, True, quotes=[quote], guidance=GUIDANCE_30, topic=TOPIC)
        assert (lowered.status, lowered.source) == ("needs_review", "position_check")
    assert decide("pass", "written notice", None, True, True, quotes=[quote], guidance=GUIDANCE_30, topic=TOPIC).status == "pass"


# ----------------------------------------------------------------------------- a negation beside the period

NEGATED = [
    "Customer is not required to give thirty (30) days' notice of termination for convenience and may terminate at any time.",
    "Provider waives the thirty (30) days' notice period for termination for convenience.",
    "Thirty (30) days' notice of termination for convenience is not required.",
    "Provider may not terminate this Agreement for convenience without prior notice.",
    "Neither party shall terminate this Agreement for convenience immediately.",
]


@pytest.mark.parametrize("quote", NEGATED)
@pytest.mark.parametrize("hint", ["pass", "needs_review"])
@pytest.mark.parametrize(
    "guidance", ["Termination for convenience requires at least 60 days' notice.", "Termination for convenience notice must not exceed 35 days."]
)
def test_a_period_beside_a_negation_is_never_what_code_says_the_contract_provides(quote: str, hint: str, guidance: str) -> None:
    decision = decide(hint, None, None, True, True, quotes=[quote], guidance=guidance, topic=TOPIC)  # type: ignore[arg-type]
    assert decision.source != "computed_days" and "consistent" not in decision.reason
    if decision.source == "ambiguous_fact":
        assert decision.reason.startswith("a negation (")
    else:  # a pass, or the model's doubt, is the model's, with the arithmetic said and the negation beside it
        assert decision.source == "model_hint" and decision.status == hint and "a negation stands beside the period" in decision.reason


@pytest.mark.parametrize(
    "quote",
    [
        "Either party may terminate this Agreement without cause upon ten (10) days' notice.",
        "Either party may terminate this Agreement, without liability, by giving thirty (30) days' written notice.",
    ],
)
def test_without_before_another_word_denies_that_word_and_the_shortfall_stays_codes(quote: str) -> None:
    decision = decide("pass", None, None, True, True, quotes=[quote], guidance="Termination requires at least 60 days' notice.")
    assert (decision.status, decision.source) == ("needs_review", "computed_days")


def test_a_cure_period_not_met_is_still_sent_to_review() -> None:
    quote = "Either party may terminate if a material breach is not cured within thirty (30) days of notice."
    decision = decide("pass", None, None, True, True, quotes=[quote], guidance="A material breach must allow at least 45 days to cure.")
    assert decision.status == "needs_review"


# ----------------------------------------------------------------------------- what a reader does not see

# Characters a reader does not see (format characters and other default-ignorable code points) and typeset dashes.
UNSEEN = ["\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\u061c", "\u2060", "\ufeff", "\u034f", "\ufe0f", "\u00ad"]
DASHES = ["‐", "‑", "‒", "–", "—", "−"]


@settings(max_examples=400, deadline=None)
@given(
    st.sampled_from(["upon 90 days' written notice", "upon fifteen (15) days' written notice", "within 1,095 days", "on thirty (30) days' notice"]), st.data()
)
def test_a_character_a_reader_does_not_see_never_changes_a_period(text: str, data: st.DataObject) -> None:
    mark = data.draw(st.sampled_from(UNSEEN))
    at = data.draw(st.integers(0, len(text)))
    marked = text[:at] + mark + text[at:]
    assert [m.readings for m in parse_durations(marked)] == [m.readings for m in parse_durations(text)], ascii(marked)
    assert stated_periods(marked) == stated_periods(text)


@pytest.mark.parametrize("dash", DASHES)
def test_a_typeset_dash_in_a_number_word_is_a_hyphen(dash: str) -> None:
    assert [m.duration for m in parse_durations(f"forty{dash}five (45) days")] == [_days(45)]
    assert [(m.duration, m.in_range) for m in parse_durations(f"10{dash}60 days")] == [(_days(10), "low"), (_days(60), "high")]
