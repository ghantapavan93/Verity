"""A page's running header or footer is never a heading.

Found by the holdout audit (2026-10-09, run 6b8da75cfe744eeb): a lease printed "1 – LEASE AGREEMENT" at the foot of
every page, and the reader made each a section, §1 to §37. The page break inside clause 11 cut "Base Rent shall equal
$285,585.50 per month" off from its heading, so retrieval never handed it over and the answer could not give the rent.

The invariant: a heading line that repeats, page number aside, at least three times with that number rising (a run that
restarts, as an exhibit's pages do, counts on its own), and whose words are "Page" or a heading the document also prints
unnumbered, is the page's running line: text where it stands, never a heading. Measured over 510 CUAD and 800 EDGAR
texts and the lease: 87 of 54,901 heading lines in 7 documents, every one a page footer or a contents line with its page
number. Controls: numbered exhibits, articles, schedules and clauses with repeated titles stay headings.

A line with no page number escaped that rule (war room F-04, 2026-10-13): a PDF printing "ACME SERVICES AGREEMENT" at
the top of every page made each a section, so §7 ended "shall not exceed the fees paid in the" and its exception, "except
for breach of Section 9", sat in a section of its own that retrieval never handed over. The invariant, for a format with
pages: a line printed the same on most pages (three at least) is the page's furniture, not a part of the document. It is
text where it stands, never a heading, and never splits a clause. Header or footer, with digits or without, a stamp
("CONFIDENTIAL", "DRAFT") or a company name. Controls: the document's own heading printed once at its head, a structural
line (an exhibit's pages), a numbered clause heading, a line on a minority of pages, and a format with no pages.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.ingest import ingest
from app.ingest.sections import Block, build_sections
from app.retrieval.aliases import expand_query
from app.retrieval.lexical import LexicalIndex
from tests.support import FUZZ_SCALE


def _lease() -> list[Block]:
    blocks = [Block("heading", "LEASE AGREEMENT", 1, implicit_number=False)]
    for page in range(1, 7):
        blocks.append(Block("text", f"Clause text on page {page}."))
        if page == 3:
            blocks.append(Block("heading", "11. Base Rent", 1, implicit_number=False))
            blocks.append(Block("text", "Base Rent shall be paid monthly. Except as provided below, Base Rent shall equal"))
        blocks.append(Block("heading", f"{page} – LEASE AGREEMENT", 1, implicit_number=False))
        if page == 3:
            blocks.append(Block("text", "$285,585.50 per month."))
    return blocks


def test_a_running_footer_is_text_where_it_stands_and_the_clause_stays_whole() -> None:
    sections = build_sections(_lease())
    headings = [s.heading for s in sections]
    assert not any("– LEASE AGREEMENT" in h for h in headings), headings
    rent = next(s for s in sections if s.heading == "Base Rent")
    assert "$285,585.50 per month" in rent.text, "the page break no longer cuts the amount off its clause"
    assert "3 – LEASE AGREEMENT" in rent.text, "the footer stays as printed text; nothing is deleted"


def test_page_footers_and_restarting_runs_are_running_lines() -> None:
    blocks = [Block("heading", "SERVICES AGREEMENT", 1, implicit_number=False)]
    for page in [1, 2, 3, 4, 1, 2, 3]:  # the agreement, then an exhibit numbered from 1
        blocks += [Block("text", "Body."), Block("heading", f"Page {page}", 1, implicit_number=False)]
    assert [s.heading for s in build_sections(blocks)] == ["SERVICES AGREEMENT"]


def test_numbered_headings_that_repeat_are_still_headings() -> None:
    """Controls: rising numbers alone, or a structural word, never make a running line."""
    exhibits = [Block("heading", "EXHIBIT B", 1, implicit_number=False)] + [
        b for n in (1, 2, 3) for b in (Block("heading", f"EXHIBIT B-{n}", 1, implicit_number=False), Block("text", "Form."))
    ]
    assert [s.heading for s in build_sections(exhibits)][-3:] == ["EXHIBIT B-1", "EXHIBIT B-2", "EXHIBIT B-3"]

    reserved = [b for n in (4, 5, 6) for b in (Block("heading", f"{n}. [Reserved]", 1, implicit_number=False), Block("text", "None."))]
    assert [s.number for s in build_sections(reserved)] == ["4", "5", "6"], "a repeated title with no unnumbered twin"

    twice = [Block("heading", "Definitions", 1, implicit_number=False)] + [
        b for n in (1, 2) for b in (Block("heading", f"{n} Definitions", 1, implicit_number=False), Block("text", "Terms."))
    ]
    assert len([s for s in build_sections(twice) if s.number]) == 2, "two occurrences are not a running line"

    falling = [Block("heading", "LEASE", 1, implicit_number=False)] + [
        b for n in (3, 2, 1) for b in (Block("heading", f"{n} LEASE", 1, implicit_number=False), Block("text", "Body."))
    ]
    assert len([s for s in build_sections(falling) if s.number]) == 3, "numbers that fall are not pages"


def test_a_heading_of_thousands_of_digits_is_read_not_refused() -> None:
    """Security audit, 2026-10-09: a heading holding a 4,300-digit number made int() refuse it and the upload a 500."""
    huge = "9" * 5_000
    blocks = [Block("heading", "LEASE", 1, implicit_number=False)] + [
        b for _ in range(3) for b in (Block("heading", f"{huge} LEASE", 1, implicit_number=False), Block("text", "Body."))
    ]
    assert build_sections(blocks)


# ---------------------------------------------------------------- page furniture: a line printed on most pages


def text_pdf(pages: Sequence[Sequence[str]]) -> bytes:
    """A PDF that prints each page's lines top to bottom, one per row ("" is an empty row), in Helvetica: the smallest
    file whose text layer the reader takes apart page by page, as it would a printed contract."""
    objects: list[bytes] = [b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    page_ids: list[int] = []
    pages_id = 2 + 2 * len(pages)
    for lines in pages:
        rows = b" ".join(b"(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1") + b") '" for line in lines)
        stream = b"BT /F1 11 Tf 72 760 Td 14 TL " + rows + b" ET"
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        objects.append(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Contents %d 0 R /Resources << /Font << /F1 1 0 R >> >> >>" % (pages_id, len(objects))
        )
        page_ids.append(len(objects))
    objects.append(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % i for i in page_ids), len(page_ids)))
    objects.append(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer << /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, len(objects), xref)
    return bytes(out)


# The war room's four pages (W2-AI F-04): an unnumbered header on every page, §7 broken across the page break.
ACME = [
    ["ACME SERVICES AGREEMENT", "", "6. Fees", "", "Customer shall pay the fees set out in the Order Form.", "", "Confidential - Page 1 of 4"],
    [
        "ACME SERVICES AGREEMENT",
        "",
        "7. Limitation of Liability",
        "",
        "Each party's aggregate liability shall not exceed the fees paid in the",
        "",
        "Confidential - Page 2 of 4",
    ],
    [
        "ACME SERVICES AGREEMENT",
        "",
        "twelve (12) months preceding the claim, except for breach of Section 9.",
        "",
        "8. Term",
        "",
        "This Agreement lasts one year.",
        "",
        "Confidential - Page 3 of 4",
    ],
    ["ACME SERVICES AGREEMENT", "", "9. Confidentiality", "", "Each party keeps the other's information confidential.", "", "Confidential - Page 4 of 4"],
]


def test_the_war_room_pdf_keeps_the_exception_in_its_clause_and_retrieval_hands_it_over() -> None:
    sections = ingest("acme.pdf", text_pdf(ACME)).sections
    assert [s.number for s in sections if s.number] == ["6", "7", "8", "9"]
    assert [s.heading for s in sections].count("ACME SERVICES AGREEMENT") == 1, "only the title block carries the line as its name"
    liability = next(s for s in sections if s.number == "7")
    assert "shall not exceed the fees paid in the" in liability.text and "except for breach of Section 9" in liability.text
    assert sum(s.text.count("ACME SERVICES AGREEMENT") for s in sections) == 4, "printed four times, kept four times as text: nothing is deleted"
    # Retrieval is unchanged; the clause it ranks first now carries its exception.
    question = expand_query("What is the cap on each party's liability, and are there exceptions?")
    top = LexicalIndex([(s.heading, s.text) for s in sections]).search(question, 8)[0]
    assert "except for breach of Section 9" in sections[top.index].text


FURNITURE = [
    "ACME SERVICES AGREEMENT",  # the document's name, with no page number
    "CONFIDENTIAL",  # a stamp
    "DRAFT",
    "EXECUTION VERSION",
    "NORTHWIND TRADING CORP.",  # a company name
    "CONFIDENTIAL TREATMENT REQUESTED",
    "US-DOCS\\123456789.3",  # a document number: digits that are not a page number
]
SUBJECTS = ["fees", "notice", "term", "audit", "renewal", "records", "insurance", "publicity"]


@settings(max_examples=40 * FUZZ_SCALE, deadline=None)
@given(
    clauses=st.integers(min_value=3, max_value=7),
    cuts=st.sets(st.integers(min_value=1, max_value=400), min_size=2, max_size=6),
    furniture=st.sampled_from(FURNITURE),
    where=st.sampled_from(["top", "bottom", "both"]),
)
def test_a_line_printed_on_every_page_never_splits_a_clause(clauses: int, cuts: set[int], furniture: str, where: str) -> None:
    """Property: whatever the line, wherever it is printed and wherever the page breaks fall (between clauses, between a
    heading and its body, or inside a sentence), every clause keeps its heading and its whole body in one section, and
    every printing of the line is still in the text."""
    rows = ["MASTER AGREEMENT", ""]
    for k in range(1, clauses + 1):
        subject, other = SUBJECTS[k], SUBJECTS[k - 1]
        rows += [f"{k}. {subject.title()}", "", f"Clause {k} opens with the {subject} and runs on", f"until it ends with the {other} it names.", ""]
    breaks = sorted({c % (len(rows) - 1) + 1 for c in cuts})
    assume(len(breaks) >= 2)  # three pages at least: two printings are not a running line
    body = [rows[a:b] for a, b in zip([0, *breaks], [*breaks, len(rows)], strict=True)]
    top, bottom = where in ("top", "both"), where in ("bottom", "both")
    pages = [[*([furniture, ""] if top else []), *lines, *(["", furniture] if bottom else [])] for lines in body]

    sections = ingest("paged.pdf", text_pdf(pages)).sections

    numbered = [s for s in sections if s.number]
    assert [s.number for s in numbered] == [str(k) for k in range(1, clauses + 1)], [(s.number, s.heading) for s in sections]
    for k, section in enumerate(numbered, start=1):
        words = " ".join(section.text.replace(furniture, " ").split())
        assert words == f"Clause {k} opens with the {SUBJECTS[k]} and runs on until it ends with the {SUBJECTS[k - 1]} it names.", (k, section.text)
    # Before the first clause the line may stand once as the document's own heading (a cover page whose only other
    # line is the title): that splits no clause. From the first clause on, it never names a section.
    first = sections.index(numbered[0])
    name = furniture.rstrip(".")
    assert not any(name in s.heading for s in sections[first:]), [s.heading for s in sections]
    kept = sum(1 for s in sections[1:first] if s.heading == name)
    assert kept <= 1 and sum(s.text.count(furniture) for s in sections) + kept == sum(page.count(furniture) for page in pages), "nothing printed is deleted"


def paged(pages: Sequence[Sequence[Block]]) -> list[Block]:
    return [Block(b.kind, b.text, b.level, b.implicit_number, page=number) for number, page in enumerate(pages) for b in page]


def heading(line: str) -> Block:
    return Block("heading", line, 1, implicit_number=False)


def body(line: str) -> Block:
    return Block("text", line)


def test_the_documents_own_heading_printed_once_at_its_head_stays_a_heading() -> None:
    """Control, from a holdout PDF (H03, CUAD's eGain hosting agreement): the agreement's name is its heading on the first
    page and its running header on the next two, where a page break falls inside a sentence. The first printing stays the
    heading; the others are text in the clause they interrupt."""
    pages = [
        [body("Exhibit 10.8"), heading("HOSTING AGREEMENT"), heading("1. Hosting Agreement"), body("This Agreement is entered into.")],
        [heading("6.1 Downtime"), body("Downtime begins upon Customer notification, either"), heading("HOSTING AGREEMENT"), body("by speaking with eGain.")],
        [body("to the Customer."), heading("HOSTING AGREEMENT"), heading("7. Limitation of liability"), body("No liability.")],
        [body("Signatures."), body("Exhibit A.")],
    ]
    sections = build_sections(paged(pages), title="Exhibit 10.8")
    assert [s.heading for s in sections] == ["Exhibit 10.8", "HOSTING AGREEMENT", "Hosting Agreement", "Downtime", "Limitation of liability"]
    downtime = next(s for s in sections if s.number == "6.1")
    assert "either\n\nHOSTING AGREEMENT\n\nby speaking with eGain." in downtime.text


@pytest.mark.parametrize(
    ("pages", "why"),
    [
        ([[heading(f"EXHIBIT B-{n}"), body("Form.")] for n in (1, 2, 3)], "an exhibit per page: the lines differ"),
        ([[heading("EXHIBIT B"), body(f"Form, page {n}.")] for n in (1, 2, 3)], "an exhibit's own pages: a structural line names a part"),
        ([[heading("1. Definitions"), body(f"Terms of schedule {n}.")] for n in (1, 2, 3)], "a numbered clause heading is the document's numbering"),
        (
            [[heading("INTENTIONALLY OMITTED") if n in (1, 3, 5) else heading(f"{n}. Clause"), body("Body.")] for n in range(1, 8)],
            "a line on three of seven pages is not on most pages",
        ),
        ([[heading("CONFIDENTIAL"), body("Body.")], [heading("CONFIDENTIAL"), body("Body.")]], "two pages are not a running line"),
    ],
)
def test_lines_that_are_not_page_furniture_stay_headings(pages: list[list[Block]], why: str) -> None:
    blocks = paged(pages)
    expected = [b.text for b in blocks if b.kind == "heading"]
    assert [f"{s.number}. {s.heading}" if s.number else s.heading for s in build_sections(blocks) if s.heading] == expected, why


def test_a_format_without_pages_is_read_as_before() -> None:
    """Scope: only a format that says where a page begins (PDF) has page furniture. A plain-text or Word heading printed
    five times stays five headings; the rising-number rule above is the only one that reads those formats."""
    blocks = [b for n in range(5) for b in (heading("CONFIDENTIAL"), body(f"Body {n}."))]
    assert [s.heading for s in build_sections(blocks)] == ["CONFIDENTIAL"] * 5
