"""The number that names an instrument by its mark is not a value the answer states (policy-v15).

Found on the live amendment challenge (2026-10-16, three recorded runs on the amended sample, no model call needed to
repeat it): the answer "… ninety (90) days before the end of the then-current Term. This is found in §7.2 of the
Agreement, which was amended by Amendment No. 1 to specify the notice period." was set to needs review with the reason
"the evidence shown does not establish 1: no verified quote or guidance states it". The 1 is the amendment's number.

The invariant: the number of an instrument or a document named with a mark, "No." or "#" ("Amendment No. 1", "Change
Order #7", "Contract No. 98-1234"), is not an answer value. Added to an answer, such a name changes none of the values
code reads in it: in the check that lowers a pass and the "Numbers" row (`unquoted_values`), the choices disclosed
(`value_choices`), and the values runs.relations compares with a replaced clause and its replacement
(`stated_values(answer=True)`). The guidance and the question are read the same way, so an answer stating a
number they name only as a marked name's can newly be lowered (a test below). Section pointers are read as v14 read them.

The controls: every number of a name carries its own mark, so a count after one, however joined, stays the answer's
("Under Amendment No. 1, 2 renewals"), and so does a value after the mark (a quantity with a unit or a magnitude, a
date, money, a grouped number). Five broader designs were rejected by fresh reviews for hiding values v14 read; this
one is checked against v14 by a differential fuzz (DECISIONS.md). Not set aside, as before: an unmarked number
("Amendment 2"), one after "Number", a "Nos." list, a grouped number ("Patent No. 7,123,456").
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.runs.values import stated_values, uniform_party_choices, unquoted_values, value_choices
from tests.test_relations_oracle import OracleModel
from tests.test_unquoted_values import assert_linear, read_time

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "public" / "samples" / "linen-services-agreement-amended.pdf"


def _ask(client: TestClient, monkeypatch: pytest.MonkeyPatch, file: tuple[str, bytes, str], question: str, finding: dict[str, Any]) -> dict[str, Any]:
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = OracleModel(finding)  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": file}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": question})
    assert started.status_code == 202, started.text
    recorded: dict[str, Any] = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    return recorded


# The recorded answer and its two verified quotes, as the three live runs of 2026-10-16 showed them.
CHALLENGE = "What is the deadline now for giving notice that we do not want the agreement to renew?"
CHALLENGE_ANSWER = (
    "The deadline for giving notice that the agreement does not wish to renew is ninety (90) days before the end of the "
    "then-current Term. This is found in §7.2 of the Agreement, which was amended by Amendment No. 1 to specify the notice period."
)
CHALLENGE_QUOTES = [
    "unless either party gives the other written notice of non-renewal not less than ninety (90) days before the end of the then-current Term.",
    'Section 7.2 of the Agreement is deleted in its entirety and replaced with the following: "7.2 This Agreement renews automatically at '
    'the end of the Initial Term and at the end of each Renewal Term for a further term of twelve (12) months (each a "Renewal Term") '
    "unless either party gives the other written notice of non-renewal not less than one hundred fifty (150) days, and not more than two "
    "hundred ten (210) days, before the end of the then-current Term.",
]


@pytest.mark.parametrize("observed", [None, "ninety (90) days"])
def test_the_amendment_challenge_answer_is_not_told_it_states_the_amendments_number(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, observed: str | None
) -> None:
    finding = _ask(
        client,
        monkeypatch,
        (SAMPLE.name, SAMPLE.read_bytes(), "application/pdf"),
        CHALLENGE,
        {"topic": "Renewal Notice Deadline", "conclusion": CHALLENGE_ANSWER, "observed": observed, "quotes": CHALLENGE_QUOTES},
    )
    assert all(span["verified"] for span in finding["spans"])
    assert finding["unquotedValues"] == []
    assert not [c for c in [finding["statusReason"] or "", *finding["concerns"]] if "establish 1" in c or "states 1," in c]
    # What code does see: the answer quotes the replacement and gives only the replaced wording's value. Since policy-v16
    # (the owner's decision, 2026-10-17) that is needs review set by code, with code's sentence as the reason.
    (note,) = finding["relations"]
    assert note["effect"] == "old_value"
    assert (finding["status"], finding["statusSource"], finding["statusReason"]) == ("needs_review", "position_check", note["sentence"])


def _supply(replaced: str, replacement: str) -> bytes:
    return "\n\n".join(
        [
            "SUPPLY AGREEMENT",
            "1. TERM",
            "1.1 This Agreement runs for three (3) years from 1 March 2025.",
            f"1.2 {replaced}",
            "AMENDMENT NO. 1",
            'This Amendment No. 1 is dated September 18, 2025 (the "Amendment Date").',
            "1. With effect from the Amendment Date, clause 1.2 of the Agreement is deleted in its entirety and replaced with the following: "
            f'"1.2 {replacement}"',
        ]
    ).encode("utf-8")


def test_an_answer_naming_the_amendment_by_number_does_not_state_the_replacements_value(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """runs.relations read "Amendment No. 1" as the 1 of a replacement's "one (1) month", so an answer quoting only the
    replaced clause was told it states a value only the replacement states, and kept its pass instead of the
    replaced-clause review."""
    old = "Either party may terminate this Agreement on ninety (90) days' written notice."
    finding = _ask(
        client,
        monkeypatch,
        ("supply.txt", _supply(old, "Either party may terminate this Agreement on one (1) month's written notice."), "text/plain"),
        "How much notice must a party give to terminate?",
        {
            "topic": "Termination notice",
            "conclusion": "A party must give ninety (90) days' written notice under clause 1.2, which Amendment No. 1 did not change.",
            "observed": None,
            "quotes": [old],
        },
    )
    (note,) = finding["relations"]
    assert note["effect"] == "replaced", note["sentence"]
    assert (finding["status"], finding["statusSource"], finding["statusReason"]) == ("needs_review", "position_check", note["sentence"])


def test_control_a_count_after_the_amendments_number_is_still_the_replacements_value(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The 3 after "Amendment No. 1," is the answer's, and only the replacement states it (review of policy-v15)."""
    old = "Supplier shall keep two (2) delivery trucks available."
    finding = _ask(
        client,
        monkeypatch,
        ("trucks.txt", _supply(old, "Supplier shall keep three (3) delivery trucks available."), "text/plain"),
        "How many delivery trucks must the Supplier keep available?",
        {
            "topic": "Delivery trucks",
            "conclusion": "Under Amendment No. 1, 3 delivery trucks must be kept available.",
            "observed": None,
            "quotes": [old],
        },
    )
    (note,) = finding["relations"]
    assert note["effect"] == "context" and "states a value only the replacement states" in note["sentence"], note["sentence"]


# ------------------------------------------------------------------------------------------------- the property

NAMES = [
    "Amendment", "Supplement", "Modification", "Restatement", "Side Letter", "Statement of Work", "SOW", "Change Order",
    "Work Order", "Purchase Order", "Order Form", "Order", "Contract", "Agreement", "Invoice", "Patent", "Policy", "Lease",
]  # fmt: skip
MARKS = ["No. ", "No.", "no. ", "NO. ", "#", "# "]
NUMBERS = st.one_of(
    st.integers(1, 999).map(str),
    st.tuples(st.integers(1, 40), st.integers(1, 20)).map(lambda p: f"{p[0]}.{p[1]}"),
    st.sampled_from(["A", "IV", "4500012345", "98-1234", "2024-17", "P00003", "10-1", "8.1(a)"]),
)


@st.composite
def names(draw: st.DrawFn) -> str:
    name = draw(st.sampled_from(NAMES))
    name = draw(st.sampled_from([name, name.upper(), name.lower()]))
    first = f"{name} {draw(st.sampled_from(MARKS))}{draw(NUMBERS)}"
    more = draw(st.lists(st.tuples(st.sampled_from([" and ", ", ", " or ", " & ", ", and ", " to "]), st.sampled_from(MARKS), NUMBERS), max_size=2))
    return first + "".join(f"{joint}{mark}{number}" for joint, mark, number in more)


# Answers whose values code reads, against quotes that state some of them and not others; some open with their value.
ANSWERS = [
    ("Notice of non-renewal is due ninety (90) days before the end of the Term.", ["not less than ninety (90) days"]),
    ("Notice is due 150 to 210 days before expiry; late notice has no effect.", ["one hundred fifty (150) days"]),
    ("The Customer may claim within 30 days, and credits are 20% of the charge.", ["within thirty (30) days"]),
    ("The cap is $3,000,000 per occurrence, renewed for 12 months.", ["US$3,000,000 per occurrence"]),
    ("The Initial Term ends on 31 March 2029.", ["ends on 31 March 2029"]),
    ("Payment is due within one (1) business day.", ["payment of the charges"]),
    ("2 renewals are allowed after the Initial Term.", ["renews for twelve (12) months"]),
    ("500,000 is the cap on liability.", ["the cap is set out in Schedule B"]),
    ("3 delivery trucks must be kept available.", ["two (2) delivery trucks"]),
    ("1 March 2026 is when the change takes effect.", ["takes effect on 21 September 2026"]),
    ("USD 10,000 is invoiced each month.", ["invoiced monthly"]),
]
PLACINGS = [
    "{answer} See {identifier}.",
    "Under {identifier}, {answer}",
    "Under {identifier} and {answer}",
    "{answer} This is found in {identifier}, as amended.",
    "{identifier} – {answer}",
    "{identifier}—{answer}",
    "{identifier}: {answer}",
]


@settings(max_examples=500, deadline=None)
@given(names(), st.sampled_from(ANSWERS), st.sampled_from(PLACINGS))
def test_a_marked_name_in_an_answer_changes_no_value_code_reads(identifier: str, case: tuple[str, list[str]], placing: str) -> None:
    answer, quotes = case
    with_it = placing.format(answer=answer, identifier=identifier)
    assert unquoted_values(with_it, quotes) == unquoted_values(answer, quotes), with_it
    assert stated_values(with_it, answer=True) == stated_values(answer, answer=True), with_it
    assert [c.answer for c in value_choices(with_it, quotes)] == [c.answer for c in value_choices(answer, quotes)], with_it


@pytest.mark.parametrize(
    "answer",
    [
        "Under Change Order No. 2024-17 the licence is exclusive.",  # dashed, never cut to "17"
        "Under amendment no. 1 the licence is exclusive.",
        "AMENDMENT NO. 1 makes the licence exclusive.",
        "Amendment No. 1 and No. 2 make the licence exclusive.",
        "Under Contract #98-1234 the licence is exclusive.",
    ],
)
def test_a_marked_name_is_read_whole(answer: str) -> None:
    assert unquoted_values(answer, ["the licence is exclusive"]) == [], answer
    assert stated_values(answer, answer=True) == set(), answer


# --------------------------------------------------------------------------------------------------- the controls


@pytest.mark.parametrize(
    ("answer", "unquoted"),
    [
        ("Under Amendment No. 1, notice is 1 day.", ["1 day"]),
        ("Amendment No. 1 sets one (1) business day.", ["one (1) business day"]),
        ("Under Change Order #7 the fee is $1.", ["$1"]),
        ("Under Amendment No. 1 the credit is 1%.", ["1%"]),
        ("Under Amendment No. 1, 2 renewals are allowed.", ["2"]),  # each number of a name carries its mark
        ("Under Amendment No. 1 and 2 renewals are allowed.", ["2"]),
        ("Under Change Orders No. 4 and No. 5, 2 additional engineers are billed.", ["2"]),
        ("Amendment No. 1—2 renewal terms are allowed.", ["2"]),
        ("Amendment No. 30 days later notice was due.", ["30 days"]),  # a quantity is never a name
        ("Is renewal automatic? Answer No. 2 renewals require notice.", ["2"]),  # "No." after a word that names nothing
        ("The amendment no 2 renewals change.", ["2"]),  # "no" without its full stop is a word
        ("Under Amendment 2 renewals apply.", ["2"]),  # an unmarked number stays a value, as before
        ("Under Purchase Order USD 10,000 is invoiced.", ["USD 10,000"]),  # money keeps its kind
        # Fifth review of policy-v15: what a marked name took that v14 read as a value.
        ("The Customer's licences number 250.", ["250"]),  # "number" is no mark: after a plural it is the verb
        ("Purchase orders number 3 per month at most.", ["3"]),
        ("Amendment No. 30 (thirty) days later notice was due.", ["30"]),  # a unit after a bracketed restatement
        ("Amendment No. 2 million is the cap.", ["2 million"]),
        ("Notice is in the Agreement\n\n# 2 renewals are allowed.", ["2"]),  # a mark on the next line is a heading
        ("Under Amendment No. 1,500 additional units are added.", ["1,500"]),  # a grouped number is a value
        ("Under U.S. Patent No. 7,123,456 the licence is exclusive.", ["7,123,456"]),  # so, as under v14, read whole
        ("Under Amendment No. 1 March 2026 applies.", ["1 March 2026"]),  # a date is a value
        ("Under Amendment No. 2024-01-15 applies.", ["2024-01-15"]),
        ("Under Amendment No. USD 10,000 applies.", ["USD 10,000"]),
    ],
)
def test_a_value_beside_a_marked_name_is_still_a_value(answer: str, unquoted: list[str]) -> None:
    assert unquoted_values(answer, ["notice of ninety (90) days"]) == unquoted, answer


PARTY_QUOTE = "Customer must give forty-five (45) days' notice; Provider must give sixty (60) days' notice."


def test_the_uniform_party_check_splits_statements_as_v14_did() -> None:
    """Final review of policy-v15: splitting after marked names were set aside joined "… Amendment No. 1 (60 days for the
    Provider)" into one statement giving both values, which chose nothing, so a pass v14 lowered stood. Statements are
    split as v14 split them; a marked name is set aside only within each."""
    answer = "Each party must give 45 days' notice, as set out in Amendment No. 1 (60 days for the Provider)."
    assert [u.choice.answer for u in uniform_party_choices(answer, ["This Amendment No. 1 amends clause 9.", PARTY_QUOTE])] == ["45 days"]


def test_not_fixed_a_party_statement_split_at_a_marked_names_full_stop_keeps_its_pass() -> None:
    """Not fixed, and pinned: v14 splits statements at "No.", so "Each party, under Amendment No. 1, must give 45 days'
    notice" keeps its subject apart from its value and the uniform-party check sees neither together. v14 lowered such an
    answer only for the false "does not establish 1"; now nothing lowers it. Joining the statement would keep "… Amendment
    No. 1 (60 days for the Provider)" from being lowered instead (the test above), so the gap is v14's and stays."""
    answer = "Each party, under Amendment No. 1, must give 45 days' notice."
    assert uniform_party_choices(answer, [PARTY_QUOTE]) == []
    assert unquoted_values(answer, [PARTY_QUOTE]) == []


def test_the_readers_text_no_longer_supplies_a_marked_names_number() -> None:
    """New in policy-v15, and disclosed: the guidance and the question are read like the answer, so an instrument's
    marked number in them is not a value they state, and an answer stating that number can newly be lowered."""
    assert unquoted_values("2 renewals remain after the Initial Term.", ["the term renews"], ["Our standard: Amendment No. 2 must not be signed."]) == ["2"]
    found = uniform_party_choices(
        "Each party must give 1 month's notice.",
        ["Customer must give one (1) month's notice; Provider must give two (2) months' notice."],
        ["Under Amendment No. 1, how much notice must each party give?"],
    )
    assert [u.choice.answer for u in found] == ["1 month"]


def test_a_quote_is_still_read_whole() -> None:
    """Only the answer and the reader's own text set a name aside: a quote's every number counts as stated, so a quote
    that names "Amendment No. 1" still states 1 (a value it may be cited for is never missed)."""
    assert stated_values("This Amendment No. 1 changes Section 7.2.") == {"n:1", "n:7.2"}
    assert stated_values("This Amendment No. 1 changes Section 7.2.", answer=True) == set()  # runs.relations, since v16


HOSTILE = [("Amendment No. 1 and ", 1_000), ("Order #1-", 1_500), ("Contract No. 1-1-1-1 ", 600), ("Patent No. 1,000,", 900)]


@pytest.mark.parametrize(("unit", "repeats"), HOSTILE, ids=[f"hostile-{i}" for i in range(len(HOSTILE))])
def test_hostile_names_are_read_in_linear_time(unit: str, repeats: int) -> None:
    assert_linear(lambda text: (unquoted_values(text, [text], [text]), stated_values(text, answer=True)), unit, repeats)


@pytest.mark.parametrize("pointer", ["Amendment No. 1,", "Section 1,", "Sections 1,", "§§ 1,", "Contract No. 1"])
def test_a_long_run_of_spaces_after_a_pointer_is_read_in_linear_time(pointer: str) -> None:
    """Review of policy-v15: two whitespace runs that could share one split it quadratically, 7 s under v14 for one read
    of 20,000 spaces of guidance after "Section 1,"; those runs are now taken possessively."""

    def read(spaces: int) -> float:
        text = f"{pointer}{' ' * spaces}x"
        return read_time(lambda t: (unquoted_values("a", ["b"], [t]), unquoted_values(t, ["b"])), text)

    assert read(20_000) < 8 * read(5_000) + 0.02
