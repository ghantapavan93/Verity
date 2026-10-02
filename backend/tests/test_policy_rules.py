"""Policy rules found wrong by the hostile review of 2026-10-01 and fixed: the rule is the duration about the finding's
topic, not the first duration in the guidance; the comparison word nearest the duration decides, a floor and a ceiling
in one sentence are a range; hyphenated and zero-notice forms parse; the number-word pattern cannot be made to crawl."""

from __future__ import annotations

import time
from decimal import Decimal

from app.policy.durations import Duration, DurationUnit, Operator, evaluate, observed_fact, parse_durations, parse_rule
from app.runs.status import decide

QUOTE_60 = "Either party may terminate this Agreement for convenience on sixty (60) days' written notice."


def test_the_rule_is_the_duration_about_the_topic_not_the_first_one() -> None:
    guidance = "Payment terms are 30 days. Termination for convenience must be on at least 90 days' notice."
    rule = parse_rule(guidance, topic="Termination for convenience")
    assert rule is not None and rule.duration == Duration(Decimal(90), DurationUnit.CALENDAR_DAY) and rule.operator is Operator.MINIMUM
    decision = decide(
        "pass", "60 days' written notice", "at least 90 days", True, True, quotes=[QUOTE_60], guidance=guidance, topic="Termination for convenience"
    )
    assert decision.status == "needs_review" and decision.source == "computed_days"
    assert "60 calendar days" in (decision.reason or "") and "90" in (decision.reason or "")


def test_without_a_topic_a_notice_sentence_wins_over_an_unrelated_one() -> None:
    guidance = "Payment terms are 30 days. Notice of termination must be at least 90 days."
    rule = parse_rule(guidance)
    assert rule is not None and rule.duration.value == Decimal(90)


def test_the_comparison_word_nearest_the_duration_decides() -> None:
    rule = parse_rule("Notice must be at least 30 days but no more than 90 days.")
    assert rule is not None and rule.operator is Operator.MINIMUM and rule.duration.value == Decimal(30)
    assert rule.maximum is not None and rule.maximum.value == Decimal(90)
    fact_45 = observed_fact("terminate on 45 days' notice")
    fact_10 = observed_fact("terminate on 10 days' notice")
    fact_120 = observed_fact("terminate on 120 days' notice")
    assert evaluate(fact_45, rule).outcome == "pass"
    assert evaluate(fact_10, rule).outcome == "needs_review"
    assert evaluate(fact_120, rule).outcome == "needs_review"


def test_not_less_than_x_nor_more_than_y_is_a_range() -> None:
    rule = parse_rule("Notice must be not less than 30 nor more than 60 days.")
    assert rule is not None and rule.operator is Operator.MINIMUM and rule.duration.value == Decimal(30)
    assert rule.maximum is not None and rule.maximum.value == Decimal(60)


def test_no_later_than_before_an_event_is_a_floor() -> None:
    rule = parse_rule("Notice must be given no later than 30 days before the end of the term.")
    assert rule is not None and rule.operator is Operator.MINIMUM


def test_hyphenated_and_zero_notice_forms_parse() -> None:
    assert [m.duration for m in parse_durations("a 30-day notice period")] == [Duration(Decimal(30), DurationUnit.CALENDAR_DAY)]
    assert [m.duration for m in parse_durations("a thirty-day period")] == [Duration(Decimal(30), DurationUnit.CALENDAR_DAY)]
    assert [m.duration for m in parse_durations("within a fortnight")] == [Duration(Decimal(2), DurationUnit.WEEK)]
    fact = observed_fact("once a year on 30 days' notice", stated="30-day")
    assert fact is not None and fact.duration == Duration(Decimal(30), DurationUnit.CALENDAR_DAY)
    immediate = observed_fact("Either party may terminate this Agreement immediately upon written notice.")
    assert immediate is not None and immediate.duration == Duration(Decimal(0), DurationUnit.CALENDAR_DAY)
    rule = parse_rule("at least 30 days' notice")
    assert rule is not None and evaluate(immediate, rule).outcome == "needs_review"


def test_the_number_word_pattern_is_linear_on_hostile_guidance() -> None:
    hostile = ("one and " * 2500)[:20000]
    started = time.perf_counter()
    parse_rule(hostile)
    parse_durations(("twenty-one-" * 1800)[:20000])
    assert time.perf_counter() - started < 0.5


GUIDANCE_90 = "We require at least 90 days' notice for termination for convenience."
TOPIC = "Termination for convenience"


def _decided(quote: str, observed: str | None = None) -> tuple[str, str]:
    decision = decide("pass", observed, None, True, True, quotes=[quote], guidance=GUIDANCE_90, topic=TOPIC)
    return decision.status, decision.source


def test_a_quote_with_several_periods_is_decided_by_code_only_when_they_all_agree() -> None:
    # Hostile cases, 2026-10-02: the first period used to decide alone, and both of these were computed passes.
    unless = "Either party may terminate upon 90 days' notice, unless the other party is in breach, in which case 10 days."
    excepted = "Either party may terminate upon 120 days' notice except that Customer may terminate on 5 days' notice."
    assert _decided(unless) == ("needs_review", "ambiguous_fact")
    assert _decided(excepted) == ("needs_review", "ambiguous_fact")
    # The model pointing at the period it prefers does not settle which one governs.
    assert _decided(unless, observed="90 days' notice") == ("needs_review", "ambiguous_fact")
    reason = decide("pass", None, None, True, True, quotes=[unless], guidance=GUIDANCE_90, topic=TOPIC).reason
    assert "10 calendar days" in reason and "90 calendar days" in reason
    # Periods that all lead to the same result are still decided by code, either way.
    assert _decided("Either party may terminate upon 90 days' notice, or upon 120 days' notice after the first year.") == ("pass", "computed_days")
    assert _decided("Customer pays within 30 days; either party may terminate upon 60 days' notice.") == ("needs_review", "computed_days")
    # One period: unchanged.
    assert _decided("Either party may terminate upon sixty (60) days' written notice.") == ("needs_review", "computed_days")
    assert _decided("Either party may terminate upon ninety (90) days' written notice.") == ("pass", "computed_days")
