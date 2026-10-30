"""A "days" convention limited to one part of the contract is not applied to every quote (policy-v17).

The stress test of 2026-10-30 (policy finding 3, the scope half): §5 said 'In this Clause 5 only, "days" means Business
Days.', and §2's "thirty (30) days' written notice" was read as thirty Business Days. Against "must not exceed 35 days"
that was code's shortfall; against "at least 40 days" a pass carrying code's "consistent", where the same contract
without §5 is code's shortfall. day_convention read the whole document with no scope.

The rule: a convention whose sentence limits it to a part ("In this Clause 5 only", "For the purposes of this
Schedule", "except in clause 7") is not applied to a quote code cannot place in that part: the quote's bare "days" are
read both ways, and where the two readings do not meet the guidance alike the finding is an ambiguous fact; where they
do, it is read as written. Controls: an unscoped convention ("In this Agreement, unless the context otherwise
requires, ...") applies as before.
"""

from __future__ import annotations

import pytest

from app.policy.durations import business_week, day_convention
from app.runs.status import decide

BUSINESS_DAY = '"Business Day" means a day other than a Saturday, a Sunday or a public holiday in England.'
QUOTE = "Either party may terminate this Agreement for convenience on thirty (30) days' written notice."
TOPIC = "Termination for convenience"


def _decided(convention: str, guidance: str) -> tuple[str, str, str]:
    sections = [("§2", QUOTE), ("§4", BUSINESS_DAY), ("§5", convention)]
    decision = decide(
        "pass", None, None, True, True, quotes=[QUOTE], guidance=guidance, topic=TOPIC, week=business_week(sections), days=day_convention(sections)
    )
    return decision.status, decision.source, decision.reason


SCOPED = [
    'In this Clause 5 only, "days" means Business Days.',
    'For the purposes of this Schedule, "days" means Business Days.',
    'Except in clause 7, "days" means Business Days.',
]


@pytest.mark.parametrize("convention", SCOPED)
@pytest.mark.parametrize(
    "guidance", ["Termination for convenience notice must not exceed 35 days.", "Termination for convenience requires at least 40 days' notice."]
)
def test_a_scoped_convention_reads_the_quote_both_ways(convention: str, guidance: str) -> None:
    status, source, reason = _decided(convention, guidance)
    assert (status, source) == ("needs_review", "ambiguous_fact") and "only where that sentence says" in reason
    assert "consistent" not in reason


@pytest.mark.parametrize("convention", SCOPED)
def test_a_scoped_convention_where_both_readings_agree_reads_the_quote_as_written(convention: str) -> None:
    status, source, reason = _decided(convention, "Termination for convenience requires at least 20 days' notice.")
    assert (status, source) == ("pass", "model_hint") and "Business Days in this contract" not in reason


def test_control_an_unscoped_convention_applies_to_every_quote() -> None:
    convention = 'In this Agreement, unless the context otherwise requires, a reference to "days" is to Business Days.'
    status, source, reason = _decided(convention, "Termination for convenience notice must not exceed 35 days.")
    assert (status, source) == ("needs_review", "computed_days") and "Business Days in this contract" in reason
