"""runs.relations beyond the oracle (test_relations_oracle.py): what the stored corpus taught, and the properties.

A read of every stored document (457 unique, 2026-10-14; outside
the repository) found 75 replacement statements, every sampled one genuine. Some replace only part of a clause: one
definition among many ("The definition of 'Applicable Margin' in Section 1.01 … is amended and restated"), one sentence,
some words. Read as whole-clause replacements, a quote of another definition in 1.01 would have been flagged. They are
limits, as written.
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.runs.relations import CONCERNS, Recorded, asked_time, assess, dump, load, locate_relations, parts_of, perspective
from tests.support import FUZZ_SCALE

AS_OF = date(2026, 10, 14)


def section(text: str, number: str = "", heading: str = "AMENDMENT NO. 1", id: str = "a") -> SimpleNamespace:
    return SimpleNamespace(id=id, number=number, heading=heading, text=text)


@pytest.mark.parametrize(
    ("statement", "scope"),
    [
        (
            "The definition of “Applicable Margin” in Section 1.01 (Defined Terms) of the Existing Credit Agreement is hereby amended and restated "
            "in its entirety as follows:",
            "The definition of “Applicable Margin” in Section 1.01",
        ),
        (
            'The first sentence of Section 1 of the Note is deleted and replaced with the following: "1. The Note bears interest at 7%."',
            "The first sentence of Section 1",
        ),
        ('In Section 4.1, the words "thirty (30) days" are replaced with "ten (10) days".', 'Section 4.1, the words "thirty (30) days"'),
        (
            'Paragraph (b) of clause 6.1 of the Agreement is deleted and replaced with the following: "(b) to the mill within 30 hours."',
            "Paragraph (b) of clause 6.1",
        ),
        ("Clause 8.7(i) of Module 1 is replaced with: the new text.", "Clause 8.7(i)"),
        (
            "For Linen collected from the Annex during 2027 only, Section 4.3 of the Agreement applies as if the words "
            '"forty-eight (48) hours" read "seventy-two (72) hours".',
            'For Linen collected from the Annex during 2027 only; applies as if the words "forty-eight (48) hours" read "seventy-two (72) hours"',
        ),
    ],
)
def test_a_replacement_of_part_of_a_clause_is_a_limit_as_written(statement: str, scope: str) -> None:
    (relation,) = locate_relations([section(statement)], AS_OF)
    assert relation.kind == "replaces" and relation.scope == scope


def test_control_a_whole_clause_replacement_with_a_start_already_reached_is_unqualified() -> None:
    sections = [
        section('This Amendment is dated September 18, 2025 (the "Amendment Date").', heading="AMENDMENT NO. 1", id="p"),
        section(
            "With effect from the Amendment Date, clause 3.2 of the Agreement is deleted in its entirety and replaced with the following: "
            '"3.2 Notice of renewal is given 120 to 45 days before expiry."',
            heading="RECITALS",
            id="r",
        ),
        section("3.1 The term is three years. 3.2 Notice of renewal is given 210 to 150 days before expiry.", number="3", heading="TERM", id="t"),
    ]
    replaces = next(r for r in locate_relations(sections, AS_OF) if r.kind == "replaces")
    assert replaces.scope is None and replaces.effective == "2025-09-18, the Amendment Date"
    assert replaces.replaced is not None and replaces.replaced.section_id == "t" and "210 to 150" in replaces.replaced.text
    assert replaces.replacement is not None and replaces.replacement.text.startswith("3.2 Notice") and replaces.replacement.text.endswith("expiry.")


def test_a_start_not_yet_reached_or_unreadable_is_a_limit() -> None:
    later = locate_relations([section('With effect from 1 July 2027, clause 3.2 is replaced with the following: "3.2 New."')], AS_OF)[0]
    assert later.scope is not None and "not reached on 2026-10-14" in later.scope
    unknown = locate_relations([section('With effect from the Closing, clause 3.2 is replaced with the following: "3.2 New."')], AS_OF)[0]
    assert unknown.scope == "With effect from the Closing"


@pytest.mark.parametrize(
    ("when", "effective", "limit"),
    [
        ("September 18, 2025", "2025-09-18, September 18, 2025", None),  # cut at its comma until 2026-10-14, and never read
        ("March 2026", "2026-03-01, March 2026", None),  # a month is read from its 1st (this raised ValueError until 2026-10-14)
        ("March 2027", None, "With effect from March 2027 (2027-03-01, not reached on 2026-10-14)"),
        ("February 30, 2026", None, "With effect from February 30, 2026"),  # no calendar has it: unread, so a limit
        ("2026-13-01", None, "With effect from 2026-13-01"),
    ],
)
def test_a_start_written_as_a_month_or_an_impossible_day_is_read_or_kept_as_a_limit(when: str, effective: str | None, limit: str | None) -> None:
    (relation,) = locate_relations([section(f'With effect from {when}, clause 3.2 is replaced with the following: "3.2 New."')], AS_OF)
    assert (relation.effective, relation.scope) == (effective, limit)


@settings(max_examples=120 * FUZZ_SCALE, deadline=None)
@given(
    month=st.sampled_from(["January", "Feb", "March", "Sept", "December", "Smarch"]),
    day=st.integers(0, 99),
    year=st.integers(1000, 9999),
    form=st.sampled_from(["{m} {d}, {y}", "{d} {m} {y}", "{m} {y}", "{y}-{d:02d}-{d:02d}", "the {d}th day of {m}, {y}"]),
    defined=st.booleans(),
)
def test_no_written_start_breaks_reading_the_document(month: str, day: int, year: int, form: str, defined: bool) -> None:
    """Whatever date a start or a defined term writes, the statement is located: read as a start, or kept as a limit."""
    written = form.format(m=month, d=day, y=year)
    sections = [
        section(f'This Amendment is dated {written} (the "Amendment Date").', id="p"),
        section(
            f"With effect from {'the Amendment Date' if defined else written}, clause 3.2 is deleted in its entirety and replaced with the "
            'following: "3.2 New."',
            id="r",
        ),
    ]
    (relation,) = locate_relations(sections, AS_OF)
    assert (relation.effective is None) != (relation.scope is None)


DATED = [
    ("What was the renewal notice deadline in June 2025?", "June 2025"),
    ("What notice applied on 3 June 2028?", "3 June 2028"),
    ("What was the notice period as at 2025-03-01?", "2025-03-01"),
    ("What was the notice period on September 18, 2025?", "September 18, 2025"),
    ("How much notice was needed during 2024?", "during 2024"),
    ("What did renewal require before 2025?", "before 2025"),
    ("What was the deadline as of the financial year 2024?", "as of the financial year 2024"),
    ("What was the payment period last year?", "last year"),
    ("What will the price be next year?", "next year"),
    ("What did the price clause say two years ago?", "two years ago"),
    ("What was the notice period previously?", "previously"),
    ("What is the Minimum Annual Volume in the first Contract Year?", "in the first Contract Year"),
    ("What is the rate for Contract Year 3?", "for Contract Year 3"),
    ("What could Customer do during the Initial Term?", "during the Initial Term"),
    ("Can Northgate Logistics terminate this Agreement for convenience during the first year?", "during the first year"),  # stored
]
UNDATED = [
    "When can the agreement be renewed?",
    "What is the renewal deadline now?",
    "What is the non-renewal notice period as of today?",
    "How many bottles must Pindlebury buy each year?",
    "What is the price for each Contract Year?",
    "Is a fee due after 2000 hours of use?",
    "How much is payable within thirty (30) days of a 12-month term?",
    "Under the amendment dated 18 September 2025, what is the notice period now?",
    "What does Section 2024 say?",
    # Stored questions (2026-10-14) where a period or a date is what the question is about, or names a document.
    "Confirm that the Initial Term of this Agreement is five years.",
    "Who has the right to extend the Initial Term, and is that right subject to any conditions?",
    "When does the initial term of the data services agreement end, and what is the last day to stop it renewing?",
    "Under the January 2025 addendum, what is her new annual pay?",
]


@pytest.mark.parametrize(("question", "when"), DATED)
def test_a_question_that_names_a_time_is_dated_and_says_which(question: str, when: str) -> None:
    assert perspective(question) == "dated" and asked_time(question) == when


@pytest.mark.parametrize("question", UNDATED)
def test_control_a_question_that_names_no_time_is_read_as_it_stands(question: str) -> None:
    assert asked_time(question) is None and perspective(question) in ("current", "unstated")


def test_an_explicitly_historical_question_stays_historical_whatever_time_it_names() -> None:
    assert perspective("What did the agreement originally require in 2024?") == "historical"


MENTIONS = ["subject to clause {n}", "notwithstanding clause {n}", "as amended from time to time", "clause {n} remains unchanged", "as set out in Section {n}"]


@settings(max_examples=60 * FUZZ_SCALE, deadline=None)
@given(
    mention=st.sampled_from(MENTIONS),
    n=st.sampled_from(["2.1", "3.2", "7", "11.4"]),
    lead=st.sampled_from(["The Supplier shall deliver the goods", "Payment is due", "Either party may terminate"]),
)
def test_a_mention_is_never_a_replacement(mention: str, n: str, lead: str) -> None:
    text = f"{lead}, {mention.format(n=n)}, within thirty (30) days. Except as amended by this Amendment, the Agreement remains in full force and effect."
    assert [r for r in locate_relations([section(text, number="4", heading="DELIVERY")], AS_OF) if r.kind == "replaces"] == []


@settings(max_examples=40 * FUZZ_SCALE, deadline=None)
@given(prefix=st.text(alphabet="abc .,;\n", max_size=60), n=st.sampled_from(["3.2", "4.1", "6"]))
def test_every_located_passage_is_the_text_at_its_offsets(prefix: str, n: str) -> None:
    sections = [
        section(
            f'{prefix}Clause {n} of the Agreement is deleted in its entirety and replaced with the following: "{n} New wording within ten (10) days."', id="a"
        ),
        section(f"{n} Old wording within thirty (30) days. 9.9 Unrelated.", number=n.split(".")[0], heading="BODY", id="b"),
        section("In the event of any conflict, the clauses prevail over the Schedules.", number="1", heading="INTERPRETATION", id="c"),
    ]
    texts = {s.id: s.text for s in sections}
    for relation in locate_relations(sections, AS_OF):
        for passage in (relation.statement, relation.replaced, relation.replacement):
            if passage is not None:
                assert texts[passage.section_id][passage.start : passage.end] == passage.text


# A replacement with a reached start, and its replaced clause: the setting of every case below.
REPLACED = [
    section('This Amendment is dated September 18, 2025 (the "Amendment Date").', id="p"),
    section(
        "With effect from the Amendment Date, clause 3.2 of the Agreement is deleted in its entirety and replaced with the following: "
        '"3.2 Notice of renewal is given 120 to 45 days before expiry."',
        id="r",
    ),
    section("3.1 The term is three years. 3.2 Notice of renewal is given 210 to 150 days before expiry.", number="3", heading="TERM", id="t"),
]
OLD_ANSWER, NEW_ANSWER, SHARED_ANSWER = "Notice is due 210 to 150 days before expiry.", "Notice is due 120 to 45 days before expiry.", "Renewal is by notice."


def _quoted(old: bool, new: bool) -> list[tuple[str, int, int]]:
    (relation,) = [r for r in locate_relations(REPLACED, AS_OF) if r.kind == "replaces"]
    assert relation.replaced is not None and relation.replacement is not None
    return [(p.section_id, p.start, p.end) for p, used in ((relation.replaced, old), (relation.replacement, new)) if used]


def _effects(question: str, answer: str, old: bool = True, new: bool = False) -> list[str]:
    relations = locate_relations(REPLACED, AS_OF)
    return [n.effect for n in assess(relations, _quoted(old, new), answer, question, parts_of(REPLACED))]


@pytest.mark.parametrize(("question", "when"), DATED)
def test_code_never_sets_the_status_for_a_question_that_names_a_time(question: str, when: str) -> None:
    """The run's date is not the time a question names: the replaced clause quoted for a dated question is a concern that
    names the time as written, never needs review set by code, and quoting the replacement instead raises it too."""
    relations = locate_relations(REPLACED, AS_OF)
    for old, new in ((True, False), (False, True), (True, True)):
        (note,) = assess(relations, _quoted(old, new), OLD_ANSWER, question, parts_of(REPLACED))
        assert note.effect == "dated" and f"the question names a time (“{when}”)" in note.sentence
        assert "in effect from 2025-09-18, the Amendment Date" in note.sentence  # the start, for the reader to compare


@pytest.mark.parametrize("question", UNDATED)
def test_control_the_same_quote_for_a_question_naming_no_time_is_codes_needs_review(question: str) -> None:
    assert _effects(question, OLD_ANSWER) == ["replaced"]


@pytest.mark.parametrize(
    ("answer", "old", "new", "effect"),
    [
        (OLD_ANSWER, True, True, "old_value"),  # quotes both, states only what the replaced clause states
        (OLD_ANSWER, False, True, "old_value"),  # quotes only the replacement, still states the replaced periods
        (NEW_ANSWER, True, True, "context"),  # control: states the replacement's periods
        (SHARED_ANSWER, True, True, "context"),  # control: states no value either side alone states
        (NEW_ANSWER, True, False, "context"),  # control: quotes the old clause, states only the replacement's periods
        (OLD_ANSWER, True, False, "replaced"),  # control: quotes and states only the replaced clause: code's status
    ],
)
def test_quoting_the_replacement_is_not_taken_for_following_it(answer: str, old: bool, new: bool, effect: str) -> None:
    assert _effects("When must notice of renewal be given?", answer, old, new) == [effect]


def test_control_a_limited_replacement_never_raises_old_value_or_dated() -> None:
    """Outside a limit the replaced values still stand ("for the second Contract Year only"), and code does not apply a
    limit: a limited replacement stays a scoped concern or context, whatever the answer states or the question names."""
    sections = [
        section('For the second Contract Year only, clause 4.1 is amended and restated to read as follows: "4.1 The volume is 905 tonnes."', id="a"),
        section("4.1 The volume is 1,340 tonnes.", number="4", heading="VOLUME", id="b"),
    ]
    (relation,) = locate_relations(sections, AS_OF)
    assert relation.replaced is not None and relation.replacement is not None
    old = (relation.replaced.section_id, relation.replaced.start, relation.replaced.end)
    new = (relation.replacement.section_id, relation.replacement.start, relation.replacement.end)
    for question in ("What is the volume?", "What is the volume in the third Contract Year?"):
        for quoted in ([old], [new], [old, new]):
            effects = {n.effect for n in assess([relation], quoted, "The volume is 1,340 tonnes.", question, parts_of(sections))}
            assert effects in ({"scoped"}, {"context"})


@settings(max_examples=150 * FUZZ_SCALE, deadline=None)
@given(
    base=st.sampled_from(["What notice is required", "When must notice be given", "What was the notice period", "How much notice applied"]),
    when=st.sampled_from([w for _, w in DATED] + ["", "", "now", "today"]),
    answer=st.sampled_from([OLD_ANSWER, NEW_ANSWER, SHARED_ANSWER]),
    old=st.booleans(),
    new=st.booleans(),
)
def test_every_note_says_only_what_code_saw(base: str, when: str, answer: str, old: bool, new: bool) -> None:
    """The invariant behind both repairs (external review of the owner note, 2026-10-14): code's status is only for a
    question naming no time, and no note says the answer uses, relies on or follows a wording: code sees quotes and values."""
    question = f"{base} {when}?" if when else f"{base}?"
    notes = assess(locate_relations(REPLACED, AS_OF), _quoted(old, new), answer, question, parts_of(REPLACED))
    assert len(notes) == (1 if old or new else 0)
    for note in notes:
        assert note.effect != "replaced" or asked_time(question) is None
        assert note.effect != "dated" or asked_time(question) is not None
        assert not re.search(r"\b(?:uses?|using|relies|relying|rests?|follows?|applies)\b", note.sentence), note.sentence
        assert note.effect in CONCERNS | {"replaced", "context"}


def test_the_question_says_whether_it_asks_about_the_original_agreement() -> None:
    assert perspective("What notice did the agreement originally require?") == "historical"
    assert perspective("What did clause 3.2 say before the amendment?") == "historical"
    assert perspective("What is the renewal deadline now?") == "current"
    assert perspective("When can the agreement be renewed?") == "unstated"


def test_an_unverified_quote_grounds_nothing_and_the_record_round_trips() -> None:
    sections = [
        section('Clause 3.2 of the Agreement is deleted in its entirety and replaced with the following: "3.2 Notice is 45 days."', id="a"),
        section("3.1 Term. 3.2 Notice is 150 days.", number="3", heading="TERM", id="b"),
    ]
    relations = locate_relations(sections, AS_OF)
    assert assess(relations, [], "Notice is 150 days.", "What notice is required?", parts_of(sections)) == []
    old = relations[0].replaced
    assert old is not None
    notes = assess(relations, [("b", old.start, old.end)], "Notice is 150 days.", "What notice is required?", parts_of(sections))
    assert [n.effect for n in notes] == ["replaced"]
    recorded = load(dump(Recorded(tuple(relations), {0: tuple(notes)})))
    assert recorded.relations == tuple(relations) and recorded.notes == {0: tuple(notes)}
    assert load(None) == Recorded()


# The 30/60-day full replacement: an answer can quote both clauses and state both values whatever it concludes, so the
# quotes and the prose's values cannot tell a wrong answer from a right one. The model's own stated value (`observed`)
# can, when it names one of the values the two texts differ in. No phrase of the prose is read.
COMPETING = [
    section("9.1 Supplier shall give thirty (30) days' notice of a price increase.", number="9", heading="PRICES", id="s9"),
    section(
        "Clause 9.1 of the Agreement is deleted in its entirety and replaced with the following: "
        '"9.1 Supplier shall give sixty (60) days\' notice of a price increase."',
        id="am",
    ),
]
BOTH = "Supplier must give 30 days' notice; the amendment mentions 60 days."


def _competing(
    answer: str, observed: str | None, old: bool, new: bool, question: str = "How much notice must Supplier give before raising prices?"
) -> list[str]:
    relations = locate_relations(COMPETING, AS_OF)
    (relation,) = relations
    assert relation.replaced is not None and relation.replacement is not None
    spans = [(p.section_id, p.start, p.end) for p, used in ((relation.replaced, old), (relation.replacement, new)) if used]
    return [n.effect for n in assess(relations, spans, f"{answer} {observed or ''}".strip(), question, parts_of(COMPETING), observed)]


@pytest.mark.parametrize(
    ("answer", "observed", "old", "new", "effect"),
    [
        (BOTH, "30 days", True, True, "old_value"),  # quotes both; its stated value is the replaced one: a concern
        (BOTH, "60 days", True, True, "context"),  # control: its stated value is the replacement's
        (BOTH, "30 or 60 days", True, True, "context"),  # control: it does not decide; nothing for code to say
        (BOTH, None, True, True, "context"),  # control: no stated value; the prose states both (as before)
        (BOTH, "30 days", True, False, "replaced"),  # quotes only the old clause, states the old value: code's status
        ("Supplier must give 60 days' notice.", "60 days", True, False, "context"),  # control: the replacement's value
    ],
)
def test_the_models_stated_value_is_its_stance_between_two_quoted_clauses(answer: str, observed: str | None, old: bool, new: bool, effect: str) -> None:
    assert _competing(answer, observed, old, new) == [effect]


def test_control_a_historical_question_keeps_the_original_as_context_whatever_the_stated_value() -> None:
    assert _competing(BOTH, "30 days", True, True, question="What notice did the agreement originally require?") == ["context"]


def _competing_sentence(answer: str, observed: str | None, old: bool, new: bool) -> str:
    relations = locate_relations(COMPETING, AS_OF)
    (relation,) = relations
    assert relation.replaced is not None and relation.replacement is not None
    spans = [(p.section_id, p.start, p.end) for p, used in ((relation.replaced, old), (relation.replacement, new)) if used]
    question = "How much notice must Supplier give before raising prices?"
    (note,) = assess(relations, spans, f"{answer} {observed or ''}".strip(), question, parts_of(COMPETING), observed)
    return note.sentence


@pytest.mark.parametrize(("old", "new"), [(True, True), (True, False)])
def test_a_sentence_decided_by_the_stated_value_speaks_of_that_value_not_of_everything_the_answer_states(old: bool, new: bool) -> None:
    # The prose names both values; only the stated value is the replaced one. "States none only the new wording states"
    # would be false of this answer (skeptic, 2026-10-15).
    sentence = _competing_sentence(BOTH, "30 days", old, new)
    assert "the value it gives as the contract's includes one only the replaced wording states" in sentence
    assert "states a value only the replaced wording states" not in sentence and "nor states a value only it states" not in sentence


def test_control_with_no_stated_value_the_sentence_still_speaks_of_what_the_answer_states() -> None:
    sentence = _competing_sentence("Supplier must give 30 days' notice.", None, True, True)
    assert "states a value only the replaced wording states and none only the new wording states" in sentence
