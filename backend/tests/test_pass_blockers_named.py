"""Code writes "code found the day counts consistent" exactly when no reason against the pass holds (stress test, 2026-10-30).

Mutation finding 5: four conditions in policy.proof could each be broken with every test still passing (the
every-sentence rule of `same_point`, its guard for guidance with no subject word, a floor or ceiling in the quote against
a range, and a deadline counted back on the guidance's side only), because each was pinned by one quote shape. Each
break wrote code's "consistent" where the pass has a reason against it. The skeptic found a defect in the same primitive:
`concept_stems` took a spelled-out number for a subject word, so "ninety (90) days" in the guidance and the quote was
the shared subject of a cure-for-cause quote and a termination-for-convenience rule.

The property: over a table where each condition is on alone, from either side, the reasons named are exactly the
conditions switched on, read at `runs.status.decide`, where the sentence is written; and writing a number in words or
in digits changes no reason but the number.
"""

from __future__ import annotations

import pytest

from app.runs.status import decide

CONSISTENT = "code found the day counts consistent"
FEW_WORDS = "share too few words"
STATED_AS = "the quote states its period as a"
COUNTED_BACK = "counted back from an event"
BLOCKERS = (FEW_WORDS, STATED_AS, COUNTED_BACK)

QUOTE = "Either party may terminate this Agreement for convenience on ninety (90) days' written notice."
RULE = "Termination for convenience requires at least 30 days' notice."
RANGE = "Termination for convenience requires not less than 30 nor more than 120 days' notice."

CASES = [
    # Controls: nothing is on.
    (QUOTE, RULE, set()),
    (QUOTE, RANGE, set()),
    (
        "Either party may terminate this Agreement for convenience by written notice given at least ninety (90) days before the end of the term.",
        "Termination for convenience notice must be given at least 30 days before the end of the term.",
        set(),
    ),
    # Every period sentence of the guidance must share words with the quotes, the off-subject one first or last.
    (QUOTE, f"{RULE} Renewal notices need at least 60 days.", {FEW_WORDS}),
    (QUOTE, f"Renewal notices need at least 60 days. {RULE}", {FEW_WORDS}),
    # Guidance with no word of its own about a subject is about nothing code can check.
    (QUOTE, "At least 30 days' notice is required.", {FEW_WORDS}),
    (QUOTE, "Thirty (30) days or more is required.", {FEW_WORDS}),
    # A floor, a ceiling or a fixed period in the quote does not meet a range.
    (QUOTE.replace("on ninety", "on at least ninety"), RANGE, {STATED_AS}),
    (QUOTE.replace("on ninety", "on no more than ninety"), RANGE, {STATED_AS}),
    (QUOTE.replace("on ninety", "on exactly ninety"), RANGE, {STATED_AS}),
    # A deadline is not a length of notice, from either side.
    (
        "Either party may terminate this Agreement for convenience by written notice given ninety (90) days before the end of the term.",
        RULE,
        {COUNTED_BACK},
    ),
    (QUOTE, "Termination for convenience notice must be given at least 30 days before the end of the term.", {COUNTED_BACK}),
]


def _named(reason: str) -> set[str]:
    return {blocker for blocker in BLOCKERS if blocker in reason}


@pytest.mark.parametrize(("quote", "guidance", "on"), CASES)
def test_the_reasons_named_are_the_conditions_that_hold(quote: str, guidance: str, on: set[str]) -> None:
    decision = decide("pass", None, None, True, True, quotes=[quote], guidance=guidance, topic="Termination for convenience")
    assert (decision.status, decision.source) == ("pass", "model_hint"), decision
    assert _named(decision.reason) == on, decision.reason
    assert (CONSISTENT in decision.reason) is (not on), decision.reason


@pytest.mark.parametrize(
    ("quote", "guidance"),
    [
        (
            "Customer may terminate for cause on ninety (90) days' notice.",
            "Termination for convenience requires at least ninety (90) days' notice.",
        ),
        ("Either party may terminate for breach upon sixty (60) days' notice.", "Termination for convenience requires at least sixty (60) days' notice."),
        (QUOTE, RULE),
    ],
)
def test_a_number_written_in_words_is_no_subject_word(quote: str, guidance: str) -> None:
    """Writing a number as "ninety (90)" or "90" changes no reason but the number."""
    as_digits = (quote.replace("ninety (90)", "90").replace("sixty (60)", "60"), guidance.replace("ninety (90)", "90").replace("sixty (60)", "60"))
    worded = decide("pass", None, None, True, True, quotes=[quote], guidance=guidance)
    digits = decide("pass", None, None, True, True, quotes=[as_digits[0]], guidance=as_digits[1])
    assert _named(worded.reason) == _named(digits.reason) and (CONSISTENT in worded.reason) is (CONSISTENT in digits.reason)
