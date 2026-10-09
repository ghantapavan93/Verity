"""A guidance bound is read the way it is written, or not read at all.

Found by the holdout audit (2026-10-09, run 4af95ce6c1dd4bb3): "The cure period for a material breach must not exceed
60 days" parsed as a floor; the reason told the reader "the guidance requires at least 60 calendar days", and a
contract's 120 days stood as within guidance. "Must not exceed" was missing from the ceiling words, and a period with
no comparison word is a floor by rule, so every ceiling phrasing not on the list became a floor.

The invariant: a ceiling phrasing never parses as a floor, nor a floor as a ceiling; and where a negation code does
not read stands beside the period ("more than 60 days are not acceptable"), or a bare comparative whose side only
the predicate settles ("less than 60 days" is a ceiling after "must be", a floor before "requires review"), code
states no rule and the comparison stays the model's.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.policy.durations import Operator, parse_rule, stated_rules
from app.runs.status import decide

CEILINGS = [
    "The cure period must not exceed 60 days.",
    "The cure period shall not exceed sixty (60) days.",
    "The cure period may not exceed 60 days.",
    "A cure period not exceeding 60 days is acceptable.",
    "The cure period is not to exceed 60 days.",
    "The cure period must be no more than 60 days.",
    "The cure period shall not be more than 60 days.",
    "The cure period should be no longer than 60 days.",
    "The cure period may be no greater than 60 days.",
    "The cure period is capped at 60 days.",
    "The cure period must be at most 60 days.",
    "The cure period must be 60 days or less.",
    "A maximum of 60 days for cure.",
]
FLOORS = [
    "Notice must be at least 60 days.",
    "Notice shall be not less than sixty (60) days.",
    "Notice must be no fewer than 60 days.",
    "Notice of not fewer than 60 days is required.",
    "Notice shall not be less than 60 days.",
    "Notice must be no shorter than 60 days.",
    "Notice of 60 days or more.",
    "A minimum of 60 days' notice.",
    "Termination requires 60 days' notice.",
]
UNREAD = [
    "More than 60 days are not acceptable for cure.",
    "A cure period longer than 60 days is not permitted.",
    "Notice of 60 days will not do.",
    "Notice must not be at least 60 days.",
    # A bare comparative names the side the sentence is about, not the side it allows; the predicate decides.
    "The cure period must be less than 60 days.",
    "Anything below 60 days requires review.",
    "Anything longer than 60 days requires approval.",
    "A cure period in excess of 60 days needs sign-off.",
]


@pytest.mark.parametrize("guidance", CEILINGS)
def test_a_ceiling_phrasing_is_a_maximum(guidance: str) -> None:
    rule = parse_rule(guidance)
    assert rule is not None and rule.operator is Operator.MAXIMUM and rule.duration.value == Decimal(60), (guidance, rule)
    assert [r.operator for r in stated_rules(guidance)] == [Operator.MAXIMUM]


@pytest.mark.parametrize("guidance", FLOORS)
def test_a_floor_phrasing_is_a_minimum(guidance: str) -> None:
    rule = parse_rule(guidance)
    assert rule is not None and rule.operator is Operator.MINIMUM and rule.duration.value == Decimal(60), (guidance, rule)


@pytest.mark.parametrize("guidance", UNREAD)
def test_a_negation_code_does_not_read_states_no_rule(guidance: str) -> None:
    assert parse_rule(guidance) is None, guidance
    assert stated_rules(guidance) == []


def test_negating_a_floor_never_leaves_a_floor() -> None:
    """Property over the floor phrasings: the same sentence with its requirement negated is never read as that floor."""
    for floor in FLOORS:
        negated = floor.replace(" must be ", " must not be ").replace(" shall be ", " shall never be ").replace("requires", "does not require")
        if negated == floor:
            continue
        rule = parse_rule(negated)
        assert rule is None or rule.operator is not Operator.MINIMUM, (negated, rule)


def test_the_audits_cure_period_is_lowered_with_a_true_reason() -> None:
    guidance = "The cure period for a material breach must not exceed 60 days."
    quote = "within one hundred twenty (120) days after notice thereof"
    decision = decide("pass", "120 days", "60 days", True, True, quotes=[quote], guidance=guidance, topic="Cure period for material breach")
    assert decision.status != "pass", decision
    assert "at least" not in (decision.reason or ""), decision.reason


def test_a_ceiling_met_by_the_contract_is_not_lowered_for_its_polarity() -> None:
    """Control: 30 days against "must not exceed 60 days" is not called wrong because of the ceiling."""
    guidance = "The cure period for a material breach must not exceed 60 days."
    rule = parse_rule(guidance)
    assert rule is not None and rule.operator is Operator.MAXIMUM
    decision = decide(
        "pass",
        "30 days",
        "60 days",
        True,
        True,
        quotes=["within thirty (30) days after notice of a material breach"],
        guidance=guidance,
        topic="Cure period for material breach",
    )
    assert decision.status == "pass", decision
