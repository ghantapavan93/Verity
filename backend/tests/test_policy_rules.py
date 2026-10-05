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
    assert _decided("Either party may terminate for convenience upon 90 days' notice, or upon 120 days' notice in the second year.") == (
        "pass",
        "model_hint",
    )
    assert _decided("Customer pays within 30 days; either party may terminate upon 60 days' notice.") == ("needs_review", "computed_days")
    # One period: unchanged.
    assert _decided("Either party may terminate upon sixty (60) days' written notice.") == ("needs_review", "computed_days")
    assert _decided("Either party may terminate for convenience upon ninety (90) days' written notice.") == ("pass", "model_hint")


def test_a_point_the_model_reported_as_not_found_is_never_decided_by_code() -> None:
    # Run 5ff255e1c3154792, 2026-09-29: asked for a most favoured nation clause under guidance about termination, the
    # model answered "missing" and cited the cure period as the closest provision; code computed a pass from its 30 days.
    guidance = "We can accept termination for convenience at 30 days' notice or more. Anything below 30 days requires review."
    cure = "if the other party fails to cure a material breach of the Framework Terms or an Order Form following 30 days notice;"
    decision = decide("missing", None, None, True, True, quotes=[cure], guidance=guidance, topic="Most Favored Nation Clause")
    assert (decision.status, decision.source) == ("missing", "model_hint")
    assert "closest provision" in decision.reason
    # Nor a shortfall, nor an ambiguity: the quote is not the contract's position, whatever periods it carries.
    assert decide("missing", None, None, True, True, quotes=[cure], guidance=GUIDANCE_90, topic=TOPIC).source == "model_hint"
    two = "The term is three years and renews unless notice is given 90 days before its end; a breach may be cured within 30 days."
    assert decide("missing", None, None, True, True, quotes=[two], guidance=GUIDANCE_90, topic=TOPIC).status == "missing"
    # A point the model did find is still code's to lower: 30 days against a floor of 90.
    assert decide("needs_review", None, None, True, True, quotes=[cure], guidance=GUIDANCE_90, topic=TOPIC).source == "computed_days"
    # Without a comparable period nothing changes, and no reason is invented.
    assert decide("missing", None, None, True, True, quotes=["Provider will make the Product available."], guidance=guidance, topic=TOPIC).reason == ""


def test_a_carve_out_with_no_number_is_a_period_too() -> None:
    # Returned by the live model on 2026-10-02 with a hint of pass, and a computed pass against a 90-day minimum.
    carve_out = (
        "Either party may terminate this Agreement for convenience upon ninety (90) days' prior written notice, "
        "except that Provider may terminate immediately upon written notice."
    )
    decision = decide("pass", "ninety (90) days' prior written notice", "at least 90 days", True, True, quotes=[carve_out], guidance=GUIDANCE_90, topic=TOPIC)
    assert (decision.status, decision.source) == ("needs_review", "ambiguous_fact")
    assert "0 calendar days" in decision.reason and "90 calendar days" in decision.reason
    # The same when the carve-out is in a second quote of the same finding.
    assert _decided_many(["Either party may terminate upon 90 days' notice.", "Provider may terminate without notice."]) == ("needs_review", "ambiguous_fact")
    # No notice at all, on its own, is still one period and still decided.
    assert _decided("Either party may terminate this Agreement immediately upon written notice.") == ("needs_review", "computed_days")


def _decided_many(quotes: list[str]) -> tuple[str, str]:
    decision = decide("pass", None, None, True, True, quotes=quotes, guidance=GUIDANCE_90, topic=TOPIC)
    return decision.status, decision.source


def test_code_does_not_pass_a_quote_against_one_of_several_periods_in_the_guidance() -> None:
    quote_45 = "Either party may terminate upon 45 days' written notice."
    for guidance in (
        "Termination requires at least 30 days' notice. Enterprise agreements require 90 days.",
        "Termination requires at least 30 days' notice, or 90 days for enterprise agreements.",
    ):
        decision = decide("pass", "45 days", None, True, True, quotes=[quote_45], guidance=guidance, topic=TOPIC)
        assert (decision.status, decision.source) == ("pass", "model_hint"), guidance  # shown as the model's view, never as code's
        assert "30 calendar days" in decision.reason and "90 calendar days" in decision.reason
        # A quote that meets both periods still does not name the enterprise rule's subject: not code's pass either.
        assert _rule_of_several(guidance, "Either party may terminate upon 120 days' written notice.") == ("pass", "model_hint")
        # A shortfall against the rule about the topic is still code's to report: that direction sends it to a person.
        assert _rule_of_several(guidance, "Either party may terminate upon 10 days' written notice.") == ("needs_review", "computed_days")
    convenience_45 = "Either party may terminate for convenience upon 45 days' written notice."
    # A floor and a ceiling are one rule, not two.
    ranged = "Notice of termination for convenience must be at least 30 days but no more than 90 days."
    assert _rule_of_several(ranged, convenience_45) == ("pass", "model_hint")
    # The same period said twice is one period, and a sentence that only restates it ("Anything below …") names no subject of its own.
    twice = "We can accept termination for convenience at 30 days' notice or more. Anything below 30 days requires review."
    assert _rule_of_several(twice, convenience_45) == ("pass", "model_hint")
    # The same guidance and a quote that never says "convenience": the model's view.
    assert _rule_of_several(twice, quote_45) == ("pass", "model_hint")


def _rule_of_several(guidance: str, quote: str) -> tuple[str, str]:
    decision = decide("pass", None, None, True, True, quotes=[quote], guidance=guidance, topic=TOPIC)
    return decision.status, decision.source
