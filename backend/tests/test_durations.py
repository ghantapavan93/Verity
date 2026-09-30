"""Durations parsed by code from contract and guidance text: their unit, their doubts, and the one comparison the
workbench makes. The nasty cases are the point: words against digits, business days against calendar days, months."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.policy.durations import Duration, DurationUnit, GuidanceRule, Operator, evaluate, observed_fact, parse_durations, parse_rule, words_to_number

D = Decimal


@pytest.mark.parametrize(
    ("text", "value", "unit"),
    [
        ("30 days", 30, DurationUnit.CALENDAR_DAY),
        ("thirty (30) days", 30, DurationUnit.CALENDAR_DAY),
        ("30 (thirty) days", 30, DurationUnit.CALENDAR_DAY),
        ("twenty-one (21) days", 21, DurationUnit.CALENDAR_DAY),
        ("forty-five (45) days' written notice", 45, DurationUnit.CALENDAR_DAY),
        ("ninety days", 90, DurationUnit.CALENDAR_DAY),
        ("one hundred twenty (120) days", 120, DurationUnit.CALENDAR_DAY),
        ("30 calendar days", 30, DurationUnit.CALENDAR_DAY),
        ("20 Working Days", 20, DurationUnit.BUSINESS_DAY),
        ("ten (10) business days", 10, DurationUnit.BUSINESS_DAY),
        ("four weeks", 4, DurationUnit.WEEK),
        ("one month", 1, DurationUnit.MONTH),
        ("a month", 1, DurationUnit.MONTH),
        ("two (2) years", 2, DurationUnit.YEAR),
        ("1.5 days", D("1.5"), DurationUnit.CALENDAR_DAY),
    ],
)
def test_the_ways_contracts_write_a_duration_parse_with_their_unit(text: str, value: int | Decimal, unit: DurationUnit) -> None:
    mentions = parse_durations(f"notice of {text} to the other party")
    assert len(mentions) == 1 and mentions[0].duration == Duration(D(value), unit), mentions
    assert mentions[0].ambiguity is None


def test_words_and_digits_that_disagree_are_ambiguous_not_a_choice() -> None:
    (mention,) = parse_durations("upon twenty-one (30) days' notice")
    assert mention.duration is None and mention.ambiguity == "the words say 21 and the digits say 30"
    (mention,) = parse_durations("upon 30 (twenty) days' notice")
    assert mention.duration is None and "20" in (mention.ambiguity or "")


def test_text_without_a_duration_yields_nothing() -> None:
    assert parse_durations("promptly, and in any event with reasonable notice") == []
    assert parse_durations("several days later") == []
    assert parse_durations(None) == [] and parse_durations("") == []


def test_every_mention_is_returned_in_order_with_its_offsets() -> None:
    text = "within thirty (30) days, and in any event 10 business days before the renewal; a month later"
    mentions = parse_durations(text)
    assert [m.duration for m in mentions] == [
        Duration(D(30), DurationUnit.CALENDAR_DAY),
        Duration(D(10), DurationUnit.BUSINESS_DAY),
        Duration(D(1), DurationUnit.MONTH),
    ]
    assert [text[m.start : m.end] for m in mentions] == ["thirty (30) days", "10 business days", "a month"]


def test_word_numbers() -> None:
    assert words_to_number("forty-five") == 45 and words_to_number("forty five") == 45
    assert words_to_number("one hundred and twenty") == 120 and words_to_number("two thousand") == 2000
    assert words_to_number("a") == 1 and words_to_number("several") is None and words_to_number("") is None


@pytest.mark.parametrize(
    ("guidance", "operator", "value"),
    [
        ("We accept termination on 30 days' notice or more.", Operator.MINIMUM, 30),
        ("Notice must be at least thirty (30) days.", Operator.MINIMUM, 30),
        ("The cure period may be no longer than 15 days.", Operator.MAXIMUM, 15),
        ("Payment terms of up to 60 days are acceptable.", Operator.MAXIMUM, 60),
        ("Cure within 10 business days.", Operator.MAXIMUM, 10),
        ("Exactly 90 days of notice.", Operator.EXACT, 90),
        ("Notice period: 30 days.", Operator.MINIMUM, 30),  # a bare notice requirement is a floor, stated once here
    ],
)
def test_the_guidance_rule_carries_the_comparison_the_guidance_states(guidance: str, operator: Operator, value: int) -> None:
    rule = parse_rule(guidance)
    assert rule is not None and rule.operator is operator and rule.duration.value == value


def test_guidance_without_a_duration_has_no_rule() -> None:
    assert parse_rule("Anything unusual needs review.") is None and parse_rule(None) is None


def test_the_observed_fact_comes_from_the_quote_and_the_model_may_only_choose_among_the_quotes_durations() -> None:
    quote = "Customer may terminate upon thirty (30) days' notice, and Provider upon ten (10) days' notice."
    fact = observed_fact(quote)
    assert fact is not None and fact.duration == Duration(D(30), DurationUnit.CALENDAR_DAY) and quote[fact.start : fact.end] == "thirty (30) days"
    chosen = observed_fact(quote, stated="10 days' notice")
    assert chosen is not None and chosen.duration == Duration(D(10), DurationUnit.CALENDAR_DAY)
    invented = observed_fact(quote, stated="90 days' notice")
    assert invented is not None and invented.duration == Duration(D(30), DurationUnit.CALENDAR_DAY), "a stated figure absent from the quote selects nothing"
    assert observed_fact("Either party may terminate for convenience.") is None


def test_evaluation_compares_only_what_is_comparable() -> None:
    rule30 = GuidanceRule(Operator.MINIMUM, Duration(D(30), DurationUnit.CALENDAR_DAY), "at least 30 days")
    assert evaluate(observed_fact("fifteen (15) days' notice"), rule30).outcome == "needs_review"
    assert evaluate(observed_fact("forty-five (45) days' notice"), rule30).outcome == "pass"
    assert evaluate(observed_fact("five (5) weeks' notice"), rule30).outcome == "pass", "weeks convert to days exactly"
    assert evaluate(observed_fact("one month's notice"), rule30).outcome == "incomparable", "a month is not thirty days"
    assert evaluate(observed_fact("thirty (30) business days' notice"), rule30).outcome == "incomparable", "business days are not calendar days"
    assert evaluate(observed_fact("twenty-one (30) days' notice"), rule30).outcome == "ambiguous"
    assert evaluate(observed_fact("upon notice"), rule30).outcome == "incomparable"
    assert evaluate(observed_fact("30 days"), None).outcome == "incomparable"
    ceiling = GuidanceRule(Operator.MAXIMUM, Duration(D(30), DurationUnit.CALENDAR_DAY), "no longer than 30 days")
    assert evaluate(observed_fact("45 days"), ceiling).outcome == "needs_review"
    assert evaluate(observed_fact("15 days"), ceiling).outcome == "pass"
    exact = GuidanceRule(Operator.EXACT, Duration(D(30), DurationUnit.CALENDAR_DAY), "exactly 30 days")
    assert evaluate(observed_fact("30 days"), exact).outcome == "pass" and evaluate(observed_fact("31 days"), exact).outcome == "needs_review"
    reason = evaluate(observed_fact("fifteen (15) days' notice"), rule30).reason
    assert reason == "the contract provides 15 calendar days; the guidance requires at least 30 calendar days"
