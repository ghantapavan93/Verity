"""A value only the guidance states supports an answer that compares, never one that gives it as the contract's (policy-v17).

The stress test of 2026-10-30 (policy finding 5): `check_values` counted every value the guidance states as stated, so
that "90 days meets the 45-day minimum" keeps its pass. It never checked that the answer compares anything. Over a quote
with no period, "on 90 days' written notice, which meets the guidance" (the guidance's own 90 days) kept its pass while
the same answer with 120 or 60 days was lowered; "capped at $1,000,000" over a quoted "$500,000" kept its pass beside
guidance of "at least $1,000,000". The one figure the guard could not see is the one a model shown the guidance is most
likely to echo.

The rule: a value only the guidance states supports the answer when the answer also states, of the same kind (a
percentage, money, a duration of any unit, a date), a value a verified quote states: the answer is comparing. Otherwise
it is a premise taken from the guidance, named as one. The account's Numbers row reads the same function.

Also here (tools finding 1): reading a finding's values parses the run's guidance once per process, not about sixteen
times per finding per request, so a long playbook does not make every read of every finding slow.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.runs import values
from app.runs.status import Decision, check_values
from app.runs.values import unquoted_values, value_choices
from app.verify.tokens import Token

PASS = Decision("pass", "model_hint")

# (kind, a value of it as the guidance and the answer write it, another value of the same kind, a quote with none)
KINDS = [
    ("duration", "90 days", "45 days", "Either party may terminate this Agreement for convenience upon written notice to the other party."),
    ("money", "$1,000,000", "$2,000,000", "Provider's liability shall not exceed the fees paid in the preceding months."),
    ("percent", "10%", "15%", "Provider shall credit Customer as set out in the service level schedule."),
]


@settings(max_examples=120, deadline=None)
@given(st.sampled_from(KINDS), st.booleans(), st.sampled_from(["{v}, which meets the guidance.", "The contract provides {v}.", "It is {v}."]))
def test_a_value_only_the_guidance_states_is_a_premise_when_no_quoted_value_of_its_kind_is_compared(
    kind: tuple[str, str, str, str], other_value_quoted: bool, template: str
) -> None:
    name, echoed, other, quote = kind
    quotes = [quote + (f" The figure is {other}." if other_value_quoted else "")]
    guidance = f"We require at least {echoed}."
    decision = check_values(PASS, template.format(v=echoed), quotes, "What does the contract provide?", guidance)
    assert (decision.status, decision.source) == ("needs_review", "position_check"), (name, decision)
    assert f"{echoed} comes from the guidance, and no verified quote states it" in decision.reason


@pytest.mark.parametrize(
    ("answer", "quote", "guidance"),
    [
        ("90 days meets the 45-day minimum.", "Customer may terminate on ninety (90) days' notice.", "At least 45 days' notice."),
        ("The $2,000,000 cap meets the $1,000,000 minimum.", "Liability is capped at $2,000,000.", "We require a cap of at least $1,000,000."),
        ("A credit of 15% exceeds the 10% the guidance asks for.", "Provider shall credit 15% of the monthly fee.", "Service credits of at least 10%."),
        ("Three months exceeds the 90-day minimum.", "Either party may terminate on three (3) months' notice.", "At least 90 days' notice."),
    ],
)
def test_controls_an_answer_comparing_a_quoted_value_with_the_guidances_keeps_the_pass(answer: str, quote: str, guidance: str) -> None:
    assert check_values(PASS, answer, [quote], "Is it acceptable?", guidance) == PASS


def test_the_stress_tests_cases() -> None:
    notice = "Either party may terminate this Agreement for convenience upon written notice to the other party."
    guidance = "Termination for convenience requires at least 90 days' prior written notice."
    for figure in ("90", "120", "60"):
        decision = check_values(PASS, f"Either party may terminate on {figure} days' written notice, which meets the guidance.", [notice], None, guidance)
        assert decision.status == "needs_review", figure
    capped = check_values(
        PASS, "Liability is capped at $1,000,000, which meets the guidance.", ["Liability shall not exceed $500,000."], None, "At least $1,000,000."
    )
    assert capped.status == "needs_review" and "$1,000,000 comes from the guidance" in capped.reason


def test_the_guidance_is_read_once_however_many_findings_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic: count the characters the value reader tokenizes. Ten findings' reads over a 20,000-character
    guidance tokenize it once, not once per finding (tools finding 1: 16 parses per finding per request)."""
    read: list[int] = []
    tokenize = values.tokenize

    def counted(text: str) -> list[Token]:
        read.append(len(text))
        return tokenize(text)

    monkeypatch.setattr(values, "tokenize", counted)
    guidance = ("Notice must be at least 30 days; credits of 5% apply; the cap is $1,000. " * 300)[:20000]
    question = "What notice does the agreement require?"
    for n in range(10):
        answer = f"Finding {n}: either party may terminate on {n + 31} days' notice."
        quote = f"Either party may terminate on {n + 31} days' notice."
        unquoted_values(answer, [quote], [], standards=[guidance])
        value_choices(answer, [quote], [question], [guidance])
    assert sum(read) < 2 * len(guidance), sum(read)


@pytest.mark.parametrize("mark", ["\u200b", "\u200e", "\u061c", "\ufeff", "\u200d"])
def test_a_character_a_reader_does_not_see_changes_no_value(mark: str) -> None:
    character = mark
    quote = f"Either party may terminate on 9{character}0 days' notice; the cap is $1{character},500."
    assert unquoted_values("Either party may terminate on 90 days' notice; the cap is $1,500.", [quote]) == []
    assert unquoted_values(f"Either party may terminate on 9{character}0 days' notice.", ["Either party may terminate on 90 days' notice."]) == []
