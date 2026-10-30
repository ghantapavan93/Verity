"""Every way a contract opens a condition is read as one (policy-v17, the stress test of 2026-10-30, policy finding 6).

`policy.proof.CARVE_OUT` matched whole words from a short list, so a quote trimmed after "Provided Customer has paid all
undisputed Fees," or "With the exception of any Order Form then in effect," left out a condition that no check saw: the
pass carried code's "consistent" sentence, check_conditions never lowered it, and docs/STATUS.md says code reads "no
condition or exception in its sentence". Measured over the local CUAD copy (510 contracts, 5,666 sentences that state a
period): about 50 sentences in 40 contracts open their condition with a word the list lacked, a third as often as a
bare "except".

The class, from the skeptic's table: bare "provided" opening a clause, the inflections of "except", "with the exception
of", "conditional(ly) (up)on", "conditioned (up)on", "on (the) condition that", "save where/if/when/to the extent",
"absent", "barring", "only after/when/where/upon", "solely if/where/to the extent". Controls: "provided" as a verb
("provided by", "as provided in", "the services provided to") opens nothing.
"""

from __future__ import annotations

import pytest

from app.policy.proof import CARVE_OUT
from app.runs.status import Decision, check_conditions, decide, left_out_condition

QUOTE = "Customer may terminate this Agreement for convenience on thirty (30) days' written notice."
GUIDANCE = "Termination for convenience requires at least 30 days' notice."
LEADS = [
    "Provided Customer has paid all undisputed Fees,",
    "Provided that Customer has paid all undisputed Fees,",
    "With the exception of any Order Form then in effect,",
    "Excepting any Order Form then in effect,",
    "Save where an Order Form is then in effect,",
    "Save to the extent an Order Form is then in effect,",
    "Conditional upon payment of all undisputed Fees,",
    "Conditionally on payment of all undisputed Fees,",
    "Conditioned upon payment of all undisputed Fees,",
    "On condition that all undisputed Fees are paid,",
    "Absent a continuing payment default,",
    "Barring a continuing payment default,",
    "Only after the first Contract Year,",
    "Only upon payment of all undisputed Fees,",
    "Solely where all undisputed Fees are paid,",
    "Solely to the extent all undisputed Fees are paid,",
]


@pytest.mark.parametrize("lead", LEADS)
def test_a_condition_opened_by_any_of_these_words_is_read_and_left_out(lead: str) -> None:
    section = f"{lead} {QUOTE}"
    start = section.index(QUOTE)
    condition = left_out_condition(section, start, start + len(QUOTE))
    assert condition is not None and condition == lead.rstrip(",")
    lowered = check_conditions(Decision("pass", "model_hint"), [condition])
    assert (lowered.status, lowered.source) == ("needs_review", "position_check")
    passed = decide("pass", None, None, True, True, quotes=[QUOTE], guidance=GUIDANCE, topic="Termination for convenience", passages=[section])
    assert "a condition or an exception" in passed.reason and "consistent" not in passed.reason


@pytest.mark.parametrize(
    "sentence",
    [
        "The Services provided by Provider under this Agreement may be terminated on thirty (30) days' written notice.",
        "As provided in Section 4, Customer may terminate on thirty (30) days' written notice.",
        "Customer may terminate the Services provided to it on thirty (30) days' written notice.",
        "Notice is provided under Section 12 and may be given on thirty (30) days' written notice.",
    ],
)
def test_controls_provided_as_a_verb_opens_no_condition(sentence: str) -> None:
    assert CARVE_OUT.search(sentence) is None


def test_the_words_the_old_list_read_are_still_read() -> None:
    for word in ("unless", "except", "excluding", "provided that", "provided, however", "notwithstanding", "subject to", "save as", "other than", "only if"):
        assert CARVE_OUT.search(f"Customer may terminate, {word} the Fees are paid.") is not None, word
