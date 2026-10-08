"""A section number shown for a plain-text or PDF reading is a number the document states at the start of that heading.

Found by the QA campaign of 2026-10-08 on a real contract PDF from CUAD: the notice addresses "15285 Minnetonka Blvd."
and "15407 McGinty Road West" became sections §15285 and §15407, the clauses after them (term, governing law) were cited
under "§15407 McGinty Road West Suite 2000", and the signature block, milestones and exhibits after it were numbered
§15408 to §15415, numbers that appear nowhere in the document. Over the 510 CUAD texts, 14 readings had such numbers
(91 sections), and 339 had headings numbered by computation from levels, which a plain-text or PDF file never shows.
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from app.ingest import ingest
from app.ingest.sections import MAX_NUMBER_GAP, Block, build_sections, continues_numbering


def reading(text: str) -> list[tuple[str, str]]:
    return [(s.number, s.heading) for s in ingest("contract.txt", text.encode()).sections]


NOTICES = """DEVELOPMENT AGREEMENT

1. Scope of Work Plan

The parties will carry out the work plan described in Exhibit A.

2. Fees and Milestones

Fees are payable within thirty (30) days of invoice.

9. Notices. All notices must be in writing and delivered to the addresses below.

If to the Supplier:
15285 Minnetonka Blvd.  Suite 4110
Minnetonka, Minnesota 55345

If to the Customer:
15407 McGinty Road West Suite 2000
Wayzata, Minnesota 55391

13.2 Governing Law

This Agreement is governed by the laws of the State of Minnesota.

SIGNATURES

MILESTONE 1

EXHIBIT D
"""


def test_the_original_an_address_is_not_a_section_and_no_heading_gets_an_invented_number() -> None:
    sections = reading(NOTICES)
    numbers = [n for n, _ in sections if n]
    assert numbers == ["1", "2", "13.2"], sections
    assert ("", "MILESTONE 1") in sections and ("", "EXHIBIT D") in sections and ("", "SIGNATURES") in sections
    notices = next(s for s in ingest("contract.txt", NOTICES.encode()).sections if "15285 Minnetonka" in s.text)
    assert "15407 McGinty Road West" in notices.text, "the address stays text, beside the clause it belongs to"


def test_siblings_a_year_a_registration_number_and_a_short_address_are_not_clause_numbers() -> None:
    assert reading("2024 PRICING SCHEDULE\n\nPrices are fixed for the year.\n")[0][0] == ""
    assert all(n != "4552374" for n, _ in reading("1. Marks\n\nThe marks are listed below.\n\n4552374 TRADEMARK REGISTRATION\n\nfor apparel\n"))
    assert reading("621 North Avenue NE Suite C-30\n\nAtlanta, Georgia\n\n1. Services\n\nThe services are described below.\n")[-1][0] == "1"


def test_controls_real_numbering_with_skips_and_restarts_keeps_its_numbers() -> None:
    text = "\n\n".join(
        [
            "1. Definitions",
            "Terms are defined here.",
            "2. Services",
            "The services are listed in Exhibit A.",
            "14. Miscellaneous",  # a skip of twelve: clauses 3 to 13 were written inline
            "Entire agreement.",
            "EXHIBIT A",
            "1. Service Levels",  # a restart in the exhibit
            "Availability is 99.9 percent.",
            "2.1 Credits",
            "Credits are ten percent.",
        ]
    )
    assert [n for n, _ in reading(text) if n] == ["1", "2", "14", "1", "2.1"]
    assert ("", "EXHIBIT A") in reading(text)


def test_control_a_word_document_still_computes_its_automatic_numbering() -> None:
    """DOCX headings are numbered by Word without the number in the text; that numbering is still computed."""
    blocks = [Block("heading", "Definitions", 1), Block("text", "Terms."), Block("heading", "Payment", 1), Block("text", "Fees.")]
    assert [(s.number, s.heading) for s in build_sections(blocks)] == [("1", "Definitions"), ("2", "Payment")]
    plain = [Block("heading", "DEFINITIONS", 1, implicit_number=False), Block("text", "Terms.")]
    assert [(s.number, s.heading) for s in build_sections(plain)] == [("", "DEFINITIONS")]


def test_the_bound_is_relative_to_the_last_clause_number() -> None:
    assert continues_numbering("1", 0) and continues_numbering(str(MAX_NUMBER_GAP), 0)
    assert not continues_numbering(str(MAX_NUMBER_GAP + 1), 0)
    assert continues_numbering("101", 100) and continues_numbering("3.2", 40)  # table rows count on; restarts go back
    assert not continues_numbering("15285", 9)


LINE = st.one_of(
    st.builds(lambda n, w: f"{n}. {w}", st.integers(1, 99999), st.sampled_from(["Term", "Fees", "Notices", "Main Street Suite 100"])),
    st.builds(lambda n, m, w: f"{n}.{m} {w}", st.integers(1, 40), st.integers(1, 9), st.sampled_from(["Payment", "Audit"])),
    st.sampled_from(["EXHIBIT A", "SCHEDULE OF FEES", "IN WITNESS WHEREOF", "MILESTONE 2"]),
    st.sampled_from(["The parties agree to the terms below.", "Fees are due within thirty (30) days.", "Wayzata, Minnesota 55391"]),
)


@settings(max_examples=200, deadline=None)
@given(st.lists(LINE, min_size=1, max_size=25))
def test_every_number_shown_is_stated_by_the_document(lines: list[str]) -> None:
    """The invariant: a reading's section number is empty or begins a line of the source."""
    text = "\n\n".join(lines)
    starts = {re.match(r"\s*(\d+(?:\.\d+)*)", line).group(1) for line in lines if re.match(r"\s*\d", line)}  # type: ignore[union-attr]
    try:
        sections = ingest("contract.txt", text.encode()).sections
    except ValueError:
        return  # no readable text: refused, nothing shown
    for section in sections:
        assert section.number == "" or section.number in starts, (section.number, section.heading)


def test_a_numbered_line_whose_words_open_in_lower_case_is_not_a_heading() -> None:
    """Reader v8. A clause title opens with a capital; a numbered line that does not is a wrapped sentence, a figure or a
    list item inside a clause. Measured 2026-10-08 over the CUAD texts and 300 EDGAR filings: 460 of 11,646 numbered
    heading lines, none of 60 sampled a clause title."""
    from app.ingest.sections import looks_like_heading

    for line in ("6.09 shall be paid into the Net Cash Proceeds Account", "3.00 to 1.00", "3.1.14 make available for", "15 years", "2 of 6"):
        assert not looks_like_heading(line), line
    for line in ("5.5 Effect of Termination", "12. Notices", "Section 7 Governing Law", "ARTICLE 3 REPRESENTATIONS"):
        assert looks_like_heading(line), line
    # Recorded trade-off: a title that opens with a lower-case brand ("eBay") is read as body, under the clause before it.
    assert not looks_like_heading("10. eBay Listings")


def test_a_lower_case_list_item_stays_in_its_clause() -> None:
    text = "1. Services\n\nThe Supplier will:\n\n1.1 deliver the goods\n\n1.2 install them\n\n2. Payment\n\nFees are due monthly.\n"
    assert [n for n, _ in reading(text) if n] == ["1", "2"]
    services = next(s for s in ingest("contract.txt", text.encode()).sections if s.number == "1")
    assert "1.1 deliver the goods" in services.text and "1.2 install them" in services.text
