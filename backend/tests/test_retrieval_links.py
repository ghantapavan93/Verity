"""retrieval-v2 (runs.links): after the ranking, the sections the top ranked ones depend on, where the contract says which.

The cases are the failure classes the retrieval study found on unfamiliar agreements (outside the repository): a defined
term whose definition shares no word with the question; an amendment that replaces a clause, read in a format that cut
it from the clause; a clause "subject to" another. Each has a control: a section the question already ranks is not added
twice, nothing is followed from the opening fallback, and the added text stays within what the ranked sections may
already carry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.runs.links import MAX_LINKS, _definitions, because, linked, links_of
from app.runs.service import FrozenOptions, _retrieve
from tests.test_policy_v10_calendar import DisputeProvider


@dataclass
class S:
    number: str
    heading: str
    text: str
    id: str = ""


FILLER = [S(str(n), f"Miscellaneous {n}", f"This clause {n} concerns unrelated administrative matter number {n}.") for n in range(20, 34)]
FROZEN = FrozenOptions(retrieval_k=6, retriever="bm25", aliases=True, embed_model="", window=6000, decoding={})


def _sections() -> list[S]:
    return [
        S("1", "Definitions", '"Business Day" means any day other than a Saturday or Sunday. "Initial Term" means the first twelve months.'),
        S("4", "Fees", "Customer shall pay the Fees within thirty days of invoice."),
        S("8", "Termination", "Either party may terminate for convenience after the Initial Term, subject to Section 9 and on ten Business Days' notice."),
        S("9", "Early Termination Fee", "A party terminating under Section 8 shall pay an early termination fee of $5,000."),
        S("", "Amendment No. 1", "Section 4 of the Agreement is replaced: Customer shall pay the Fees within forty-five days of invoice."),
        *FILLER,
    ]


def test_a_clause_brings_its_definitions_the_clause_it_is_subject_to_and_its_amendments() -> None:
    sections = _sections()
    found = {(link.kind, link.index) for link in links_of(sections, 2)}  # §8
    assert ("definition", 0) in found and ("reference", 3) in found
    assert ("amendment", 4) in {(link.kind, link.index) for link in links_of(sections, 1)}  # §4, replaced by the amendment


def test_links_are_added_after_the_ranked_sections_amendments_first_and_at_most_two() -> None:
    sections = _sections()
    added = linked(sections, [1, 5, 6, 7, 8, 9], window=6000)  # §4 ranked first: its amendment comes before anything else
    assert [link.kind for link in added][:1] == ["amendment"] and added[0].index == 4 and len(added) <= MAX_LINKS
    assert because(added[0], sections) == "it amends or overrides §4, handed as §4"


def test_control_a_section_already_ranked_is_not_added_again() -> None:
    sections = _sections()
    assert all(link.index not in (2, 0, 3) for link in linked(sections, [2, 0, 3, 5, 6, 7], window=6000))


def test_control_the_added_text_stays_within_what_the_ranked_sections_may_carry() -> None:
    sections = _sections()
    sections[0] = S("1", "Definitions", '"Initial Term" means the first twelve months. ' + "x" * 5900)
    ranked = [2]  # one ranked section of ~120 characters may carry one window: a 5,900-character definition fits, two do not
    added = linked(sections, ranked, window=6000)
    assert sum(min(len(sections[i].text), 6000) for i in [*ranked, *(link.index for link in added)]) <= 6000


def test_control_nothing_is_followed_from_the_opening_fallback() -> None:
    sections = _sections()
    frozen = FrozenOptions(retrieval_k=6, retriever="bm25", aliases=True, embed_model="", window=6000, decoding={})
    chosen, mode, why = _retrieve(sections, "zzzz qqqq", None, frozen)  # type: ignore[arg-type]
    assert mode == "opening_fallback" and why == {} and chosen == sections[:6]


def test_a_run_records_why_a_linked_section_was_handed(client: TestClient) -> None:
    """The pilot's H4-Q5 clause, in an agreement long enough that the definitions are not handed by rank: the
    definition of the Closing Statement is linked from §7, and the run says why. (Guidance joins the retrieval query,
    and this guidance names the defined terms, so the question is asked without it.)"""
    from tests.test_policy_v10_calendar import CONTRACT_WITH_DEFINITION

    contract = CONTRACT_WITH_DEFINITION + "".join(f"\n{n}. Miscellaneous {n}\nUnrelated administrative matter number {n}.\n" for n in range(10, 30))
    client.app.state.provider = DisputeProvider()  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("apa.txt", contract.encode("utf-8"), "text/plain")}).json()
    question = "How long does the Seller have to object after receiving it?"  # no defined term in the question's words
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": question})
    assert started.status_code == 202, started.text
    from app.db import SessionLocal
    from app.models import Run

    with SessionLocal() as session:
        run = session.get(Run, started.json()["id"])
        assert run is not None
        handed = json.loads(run.candidates_json or "[]")
    assert any(c.get("linked", "").startswith('the definition of "') for c in handed), handed


# retrieval-v3 (stress test 2026-10-30, retrieval corner, finding 6): one reading of a defined term, whatever the drafting.
# A definition in single quotes or guillemets was never linked (UK, Commonwealth and EU drafting); an interpretation
# clause ('"including" means "including without limitation"') made a word of construction a term matched in every
# section, so its definition took a link place from what the clause cites; a term in a clause printed in capitals, or in
# its "-ies" plural, was not seen as used.


def _uk(opening: str, closing: str) -> list[S]:
    return [
        S("1", "Definitions", f"{opening}Business Day{closing} means a day other than a Saturday, Sunday or public holiday in England.", "s1"),
        S("3", "Payment", "The Customer shall pay each undisputed invoice within ten Business Days of receipt.", "s3"),
        *FILLER,
    ]


@pytest.mark.parametrize(
    ("opening", "closing"),
    [("\u201c", "\u201d"), ('"', '"'), ("\u2018", "\u2019"), ("'", "'"), ("\u00ab", "\u00bb"), ("\u00ab ", " \u00bb"), ("\u201e", "\u201c")],
)
def test_a_definition_is_linked_whatever_its_quotation_marks(opening: str, closing: str) -> None:
    sections = _uk(opening, closing)
    assert ("definition", 0, "Business Day") in {(link.kind, link.index, link.by) for link in links_of(sections, 1)}
    chosen, _, why = _retrieve(sections, "How long does the customer have to pay an invoice?", None, FROZEN)  # type: ignore[arg-type]
    assert sections[0] in chosen and why[sections[0].id] == 'the definition of "Business Day", used in §3'


def test_an_apostrophe_never_opens_or_closes_a_term() -> None:
    assert _definitions([S("1", "x", "Each of the Parties' and the Members' interest includes all rights in the Fund.")]) == {}
    assert list(_definitions([S("1", "x", '"Customer\'s Control Panel" shall mean the portal.')])) == ["Customer's Control Panel"]
    assert list(_definitions([S("1", "x", "\u2018Customer\u2019s Data\u2019 means the data the Customer uploads.")])) == ["Customer\u2019s Data"]
    assert list(_definitions([S("1", "x", "The Supplier's 'Personal Data' means data about a person.")])) == ["Personal Data"]


def test_an_interpretation_clause_defines_no_term_and_takes_no_link_place() -> None:
    sections = [
        S(
            "1",
            "Definitions",
            '"Business Day" means a weekday. "including" means "including without limitation"; "to" means "to but excluding";'
            ' "to the extent" means the degree to which; "$" means United States dollars.',
        ),
        S("4", "Payment", "Subject to Clause 9, the Customer shall pay all charges, including expenses, within ten Business Days of invoice."),
        S("9", "Set-off", "The Customer may set off any amount the Supplier owes it."),
        *FILLER,
    ]
    assert set(_definitions(sections)) == {"Business Day"}
    added = linked(sections, [1, *range(3, 8)], window=6000)
    assert {(link.kind, link.index) for link in added} == {("definition", 0), ("reference", 2)}, [because(link, sections) for link in added]


def test_control_a_lower_case_content_term_still_links() -> None:
    sections = [
        S("1", "Definitions", '"days" means Business Days, unless stated otherwise.'),
        S("5", "Notice", "Notice takes effect five days after it is sent."),
        *FILLER,
    ]
    assert ("definition", 0, "days") in {(link.kind, link.index, link.by) for link in links_of(sections, 1)}
    assert all(link.by != "days" for link in links_of([sections[0], S("6", "Days", "Days of rest are agreed."), *FILLER], 1)), "matched as written"


def test_a_term_is_used_in_capitals_and_in_its_plural() -> None:
    sections = [
        S("1", "Definitions", '"Fees" means the charges in Schedule 1. "Party" means the Supplier or the Customer. "Act" means the Data Act.'),
        S("12", "Limitation", "IN NO EVENT SHALL EITHER PARTY'S AGGREGATE LIABILITY EXCEED THE FEES PAID IN THE TWELVE MONTHS BEFORE THE CLAIM."),
        S("13", "Cooperation", "The Parties shall cooperate; the Supplier meets the ACT standard for accessible design in every release it makes."),
        *FILLER,
    ]
    assert {link.by for link in links_of(sections, 1) if link.kind == "definition"} == {"Fees", "Party"}
    assert {link.by for link in links_of(sections, 2) if link.kind == "definition"} == {"Party"}, "an acronym in mixed text is not the term"


# retrieval-v3 (stress test 2026-10-30, retrieval corner, finding 2): an amendment that changes what is handed is handed
# with it. Links were followed one hop from the top three ranked sections, and an amendment matched only the clause
# numbers its target opened, so a definition or a cited clause reached the model as a link in its superseded wording and
# the amendment never did: a pass with both quotes verified on a maturity date the contract had moved two years.

RENEWAL = """RENEWAL SERVICES AGREEMENT

1. Definitions
1.1 "Effective Date" means the date both parties sign this Agreement.
1.2 "Initial Term" means three years from the Effective Date.
1.3 "Cut-Off Date" means the date sixty (60) days before the end of the then-current term.

2. Fees
2.1 Fees are payable monthly in arrears.

3. Renewal
3.1 This Agreement renews for successive periods of one year after the Initial Term.
3.2 The Customer may prevent a renewal by written notice to the Supplier given on or before the Cut-Off Date.

4. Termination for Cause
4.1 Either party may terminate this Agreement for a material breach not cured within thirty (30) days, subject to Section 22.
{filler}
22. Remedies
22.1 On an uncured material breach, liquidated damages of five thousand dollars ($5,000) are payable.

AMENDMENT NO. 1
The parties agree as follows. {amendment}
All other terms remain in full force and effect.
"""
_MISCELLANEOUS = "".join(
    f"""
{n}. Miscellaneous {n}
This clause {n} concerns unrelated administrative matter number {n}.
"""
    for n in range(5, 22)
)
NEW_DEFINITION = '"Cut-Off Date" means the date one hundred twenty (120) days before the end of the then-current term.'
DEFINITION_AMENDED = {
    "amended by amending and restating": (
        'Section 1.3 of the Agreement is hereby amended by amending and restating the definition of "Cut-Off Date" in its entirety as follows: '
    ),
    "definition in a section, restated": 'The definition of "Cut-Off Date" in Section 1.3 of the Agreement is amended and restated to read as follows: ',
    "section deleted and replaced": "Section 1.3 of the Agreement is hereby deleted in its entirety and replaced with the following: ",
    "no section named": 'The definition of "Cut-Off Date" is hereby amended to read as follows: ',
    "the parent clause named": "Section 1 of the Agreement is amended by replacing the definition of Cut-Off Date with the following: ",
}


def _read(amendment: str) -> list[S]:
    from app.ingest import ingest

    text = RENEWAL.format(filler=_MISCELLANEOUS, amendment=amendment)
    return [S(s.number, s.heading, s.text, f"s{i}") for i, s in enumerate(ingest("agreement.txt", text.encode("utf-8")).sections)]


def _amendment_of(sections: list[S]) -> S:
    return next(s for s in sections if s.heading.startswith("AMENDMENT"))


@pytest.mark.parametrize("wording", sorted(DEFINITION_AMENDED))
def test_a_linked_definition_brings_the_amendment_that_restates_it(wording: str) -> None:
    sections = _read(DEFINITION_AMENDED[wording] + NEW_DEFINITION)
    chosen, mode, why = _retrieve(sections, "How late can the Customer give notice to prevent a renewal?", None, FROZEN)  # type: ignore[arg-type]
    amendment = _amendment_of(sections)
    assert mode == "lexical_match" and amendment in chosen, [(s.number, s.heading, why.get(s.id)) for s in chosen]
    assert "amend" in why[amendment.id], "handed as a link: it shares no word with the question"


def test_a_cited_clause_brings_its_amendment() -> None:
    sections = _read("Section 22.1 of the Agreement is amended to read as follows: the other party may claim liquidated damages of $9,000.")
    chosen, _, why = _retrieve(sections, "When is termination for cause allowed?", None, FROZEN)  # type: ignore[arg-type]
    remedies = next(s for s in sections if s.number == "22")
    assert remedies in chosen and why[remedies.id] == "§4 refers to §22"
    assert _amendment_of(sections) in chosen and why[_amendment_of(sections).id] == "it amends or overrides §22.1, handed as §22"


def test_an_amendment_naming_a_sub_clause_the_reader_left_inside_its_section_is_found() -> None:
    sections = [
        S("1", "Definitions", '1.1 "Fees" means the charges. 1.3 "Cut-Off Date" means sixty days before renewal.'),
        S("", "Amendment No. 1", "Section 1.3 of the Agreement is deleted and replaced: the Cut-Off Date is ninety days before renewal."),
        *FILLER,
    ]
    assert ("amendment", 1) in {(link.kind, link.index) for link in links_of(sections, 0)}


def test_a_ranked_section_beyond_the_top_three_brings_its_amendment() -> None:
    sections = _sections()  # the Amendment No. 1 section (index 4) replaces §4 (index 1)
    added = linked(sections, [5, 6, 7, 1, 8, 9], window=6000)  # §4 ranked fourth
    assert [(link.kind, link.index) for link in added][:1] == [("amendment", 4)]


def test_control_an_unamended_definition_is_linked_as_before() -> None:
    sections = _read(DEFINITION_AMENDED["no section named"] + NEW_DEFINITION)
    _, _, why = _retrieve(sections, "How long is each renewal?", None, FROZEN)  # type: ignore[arg-type]
    assert 'the definition of "Initial Term", used in §3' in why.values(), why


def test_control_citing_a_clause_is_not_amending_it() -> None:
    sections = [S("1", "Definitions", '"Fees" means the charges.'), S("7", "Invoices", "Invoices are issued as set out in Section 1."), *FILLER]
    assert ("amendment", 1) not in {(link.kind, link.index) for link in links_of(sections, 0)}


# A generated agreement: a definitions clause (each definition after the first opened mid-line, as TXT and PDF readings
# leave them), clauses that use the terms, and amending instruments that change some of them by clause number, by
# sub-clause, or by the name of a definition. Whatever is ranked, each handed section's amendments are handed, unless the
# two places are full or an amendment would take the text past what the ranked sections may carry.
_TERMS = ["Fees", "Term", "Territory", "Products", "Notice Period", "Cap"]


@st.composite
def _agreements(draw: st.DrawFn) -> tuple[list[S], list[int], dict[int, set[int]]]:
    clauses = draw(st.integers(min_value=3, max_value=9))
    definitions = " ".join(f'1.{i + 1} "{term}" means the {term.lower()} of the parties.' for i, term in enumerate(_TERMS))
    sections = [S("1", "Definitions", definitions, "d")]
    for n in range(2, clauses + 2):
        used = draw(st.lists(st.sampled_from(_TERMS), max_size=3, unique=True))
        sections.append(S(str(n), f"Clause {n}", f"{n}.1 The supplier delivers under clause {n}. " + " ".join(f"The {t} applies." for t in used), f"c{n}"))
    amends: dict[int, set[int]] = {}
    for a in range(draw(st.integers(min_value=1, max_value=3))):
        kind = draw(st.sampled_from(["clause", "sub-clause", "definition"]))
        if kind == "definition":
            term = draw(st.sampled_from(_TERMS))
            sentence, target = f'The definition of "{term}" is hereby amended and restated in its entirety.', 0
        else:
            target = draw(st.integers(min_value=1, max_value=clauses))
            named = sections[target].number + (".4" if kind == "sub-clause" else "")
            sentence = f"Section {named} of the Agreement is hereby deleted and replaced with new text."
        sections.append(S("", f"Amendment No. {a + 1}", sentence, f"a{a}"))
        amends.setdefault(target, set()).add(len(sections) - 1)
    sections += FILLER
    ranked = draw(st.lists(st.integers(min_value=0, max_value=len(sections) - 1), min_size=1, max_size=6, unique=True))
    return sections, ranked, amends


@settings(max_examples=300, deadline=None)
@given(_agreements())
def test_every_handed_section_brings_its_amendments_while_places_remain(agreement: tuple[list[S], list[int], dict[int, set[int]]]) -> None:
    sections, ranked, amends = agreement
    added = linked(sections, ranked, window=6000)
    handed = set(ranked) | {link.index for link in added}
    assert len(added) <= MAX_LINKS
    for target in sorted(handed):
        for amendment in sorted(amends.get(target, set()) - handed):
            assert len(added) == MAX_LINKS, (target, amendment, [because(link, sections) for link in added])
