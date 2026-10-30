"""Reader v16: a line in capitals is a heading only when it stands alone as a title; a wrapped line stays in its sentence.

Found by the adversarial stress test (2026-10-30) on CUAD's eGain hosting agreement (the holdout's H03), read as PDF:
"7. Limitation of liability. EXCLUDING LIABILITY FOR INFRINGEMENT CLAIMS AS DISCUSSED IN" / "SECTION 9 OF THIS
AGREEMENT, IN NO EVENT SHALL eGAIN BE LIABLE TO CUSTOMER FOR" / "CONSEQUENTIAL, EXEMPLARY, …". The second line became
section §9, the third an unnumbered heading, and the exclusion of consequential damages sat in headings only, so no
quote of it could be verified, and its lines were labelled by a clause number the clause is not.

Every test the reader used to tell a sentence from a title read letter case (a title's words open with capitals, an
operative verb is lower case), and a line in capitals has none; and a line was judged alone, whatever came before it.
The invariants: a line in capitals is judged on its words, so one that states an operative word ("shall", "in no
event", "hereby"), ends in a comma, a semicolon or a function word, or opens with one ("OF THIS AGREEMENT") is a
sentence; and a line opens a heading only at a paragraph boundary (a blank line, a heading before it, or a line that
ends a passage), so lines 2 to n of a wrapped paragraph stay in it. Controls: a standalone capitals title, a numbered
title running straight into its body, "ARTICLE II" / "PURCHASE AND SALE", a schedule's heading.
"""

from __future__ import annotations

import textwrap

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ingest import ingest
from app.ingest.sections import looks_like_heading
from app.verify.spans import locate
from tests.support import FUZZ_SCALE
from tests.test_running_lines import text_pdf


def read(text: str, kind: str = "txt") -> list[tuple[str, str, str]]:
    data = text.encode() if kind == "txt" else text_pdf([text.splitlines()])
    return [(s.number, s.heading, s.text) for s in ingest(f"contract.{kind}", data).sections]


H03 = """HOSTING AGREEMENT

6. Warranties

eGain warrants that the Services will be performed in a professional manner.

7. Limitation of liability. EXCLUDING LIABILITY FOR INFRINGEMENT CLAIMS AS DISCUSSED IN
SECTION 9 OF THIS AGREEMENT, IN NO EVENT SHALL eGAIN BE LIABLE TO CUSTOMER FOR
CONSEQUENTIAL, EXEMPLARY, INDIRECT, SPECIAL OR INCIDENTAL DAMAGES (INCLUDING,
WITHOUT LIMITATION, LOST PROFITS), HOWEVER CAUSED.

8. Term

This Agreement lasts one year.
"""


@pytest.mark.parametrize("kind", ["txt", "pdf"])
def test_the_hosting_agreements_exclusion_is_quotable_text_of_section_7(kind: str) -> None:
    sections = read(H03, kind)
    numbers = [number for number, _, _ in sections]
    assert "9" not in numbers, "no section is made of a cross-reference that opens a line"
    seven = next(text for number, _, text in sections if number == "7")
    for quote in ("IN NO EVENT SHALL eGAIN BE LIABLE TO CUSTOMER FOR CONSEQUENTIAL, EXEMPLARY, INDIRECT, SPECIAL OR INCIDENTAL DAMAGES", "HOWEVER CAUSED"):
        assert locate(quote, seven) is not None, quote
    assert numbers[-1] == "8"


@pytest.mark.parametrize(
    "line",
    [
        "IN NO EVENT SHALL EITHER PARTY BE LIABLE",
        "ALL OTHER WARRANTIES ARE HEREBY DISCLAIMED.",
        "MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND AGAINST INFRINGEMENT,",
        "TO THE MAXIMUM EXTENT POSSIBLE BY LAW",
        "CUSTOMER MAY TERMINATE THIS AGREEMENT",
        "THE HILLMAN GROUP CANADA ULC,",
        "9 OF THIS AGREEMENT, IN NO EVENT",
        "SECTION 19 OF THE FACILITY LEASE, OR MODIFY",
        "12 OF THE MASTER AGREEMENT",
    ],
)
def test_a_capitals_line_that_reads_as_a_sentence_is_not_a_heading(line: str) -> None:
    assert not looks_like_heading(line)


@pytest.mark.parametrize(
    "line",
    [
        "LIMITATION OF LIABILITY",
        "TERM AND TERMINATION.",
        "DISCLAIMER OF WARRANTIES",
        "ARTICLE II",
        "PURCHASE AND SALE",
        "7. LIMITATION OF LIABILITY",
        "12. MISCELLANEOUS.",
        "SCHEDULE A",
        "EXHIBIT B",
        "IN WITNESS WHEREOF",
        "MAY 2026 AMENDMENT",
        "NOTICES",
    ],
)
def test_control_capitals_titles_are_headings(line: str) -> None:
    assert looks_like_heading(line)


def test_a_numbered_capitals_sentence_keeps_every_word_as_body() -> None:
    sections = read("AGREEMENT\n\n8. Indemnity\n\n8.1 SELLER SHALL INDEMNIFY BUYER AGAINST ALL LOSSES.\n\n9. Term\n\nOne year.\n")
    text = " ".join(text for _, _, text in sections)
    assert locate("SELLER SHALL INDEMNIFY BUYER AGAINST ALL LOSSES", text) is not None


def test_a_standalone_capitals_sentence_is_quotable() -> None:
    sections = read("AGREEMENT\n\n6. Warranties\n\nThe Services are provided as is.\n\nALL OTHER WARRANTIES ARE HEREBY DISCLAIMED.\n\n7. Term\n\nOne year.\n")
    six = next(text for number, _, text in sections if number == "6")
    assert locate("ALL OTHER WARRANTIES ARE HEREBY DISCLAIMED.", six) is not None


def test_control_titles_running_into_their_body_and_part_lines_stay_headings() -> None:
    sections = read(
        "PURCHASE AGREEMENT\n\nARTICLE II\nPURCHASE AND SALE\n\n2.1 Purchase\nThe Seller shall sell the Shares.\n\n"
        "LIMITATION OF LIABILITY\nNeither party is liable for indirect loss.\n\n4.13 No Indebtedness\nThe Borrower has no debt.\n"
    )
    headings = [heading for _, heading, _ in sections]
    assert "ARTICLE II PURCHASE AND SALE" in headings and "Purchase" in headings and "LIMITATION OF LIABILITY" in headings and "No Indebtedness" in headings


def test_a_capitals_title_that_wraps_is_one_heading() -> None:
    sections = read("AGREEMENT\n\nARTICLE IV\nREPRESENTATIONS AND\nWARRANTIES OF THE BORROWER\n\n4.1 Organization\n\nThe Borrower is a company.\n")
    assert "ARTICLE IV REPRESENTATIONS AND WARRANTIES OF THE BORROWER" in [heading for _, heading, _ in sections]


@pytest.mark.parametrize(
    ("before", "line"),
    [
        ("The accounts are prepared in accordance with", "GAAP."),
        ("This Agreement is made by and between", "THE HILLMAN GROUP CANADA ULC"),
        ("THE SERVICES ARE PROVIDED BY THE SUPPLIER", "AS IS."),
    ],
)
def test_a_title_like_line_inside_a_paragraph_is_the_paragraphs(before: str, line: str) -> None:
    sections = read(f"AGREEMENT\n\n1. Accounts\n\n{before}\n{line}\n\n2. Term\n\nOne year.\n")
    one = next(text for number, _, text in sections if number == "1")
    assert locate(f"{before} {line}", one) is not None


def test_control_a_title_after_a_line_that_ends_without_a_stop_is_still_a_heading() -> None:
    sections = read('AGREEMENT\n\nThis Agreement is dated 1 March 2026 (the "Agreement")\nRECITALS\n\nThe parties wish to agree.\n')
    assert "RECITALS" in [heading for _, heading, _ in sections]


CLAUSE = (
    "CUSTOMER MAY TERMINATE THIS AGREEMENT FOR CONVENIENCE UPON THIRTY (30) DAYS' PRIOR WRITTEN NOTICE TO PROVIDER, "
    "UNLESS CUSTOMER IS THEN IN BREACH OF ITS PAYMENT OBLIGATIONS."
)
EXCLUSION = (
    "EXCEPT FOR A BREACH OF SECTION 9, IN NO EVENT WILL EITHER PARTY BE LIABLE TO THE OTHER FOR ANY INDIRECT, "
    "INCIDENTAL, CONSEQUENTIAL OR SPECIAL DAMAGES, HOWEVER CAUSED AND UNDER ANY THEORY OF LIABILITY."
)


@settings(max_examples=60 * FUZZ_SCALE, deadline=None)
@given(st.sampled_from([CLAUSE, EXCLUSION]), st.integers(min_value=30, max_value=100), st.sampled_from(["txt", "pdf"]))
def test_a_capitals_paragraph_wrapped_at_any_width_is_one_quotable_passage_of_its_clause(clause: str, width: int, kind: str) -> None:
    wrapped = "\n".join(textwrap.wrap(clause, width))
    sections = read(f"SERVICES AGREEMENT\n\n4. Termination\n\n{wrapped}\n\n5. Fees\n\nFees are due monthly.\n", kind)
    four = [text for number, _, text in sections if number == "4"]
    assert len(four) == 1 and locate(clause, four[0]) is not None, (width, sections)
    assert [n for n, _, _ in sections if n] == ["4", "5"]
