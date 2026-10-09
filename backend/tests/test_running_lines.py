"""A page's running header or footer is never a heading.

Found by the holdout audit (2026-10-09, run 6b8da75cfe744eeb): a lease printed "1 – LEASE AGREEMENT" at the foot of
every page, and the reader made each a section, §1 to §37. The page break inside clause 11 cut "Base Rent shall equal
$285,585.50 per month" off from its heading, so retrieval never handed it over and the answer could not give the rent.

The invariant: a heading line that repeats, page number aside, at least three times with that number rising (a run that
restarts, as an exhibit's pages do, counts on its own), and whose words are "Page" or a heading the document also prints
unnumbered, is the page's running line: text where it stands, never a heading. Measured over 510 CUAD and 800 EDGAR
texts and the lease: 87 of 54,901 heading lines in 7 documents, every one a page footer or a contents line with its page
number. Controls: numbered exhibits, articles, schedules and clauses with repeated titles stay headings.
"""

from __future__ import annotations

from app.ingest.sections import Block, build_sections


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
