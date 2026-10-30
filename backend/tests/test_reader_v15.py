"""Reader v15: a schedule's heading is a heading in every format, and a PDF's page furniture is left out and counted.

Both found by the blind contract stress test (2026-10-16) on one synthetic agreement read as DOCX and as PDF.

(1) "Schedule A. Service Level and Credits" and "Schedule B. Exclusions and Administrative Notes" were headings in the
DOCX (styled Heading 1) and body text in the PDF (an unnumbered line in mixed case), so both schedules were read into
§13 Miscellaneous, and the SLA credit the model quoted from Schedule A was cited as "§13.3 No Penalty for Non-Renewal"
(run bb38458cafc4409c). The invariant: in plain text and PDF, a line that names a part of the agreement by its kind, its
mark and, after a full stop, a colon or a dash, a title ("Schedule A. Service Level and Credits", "Annex 2 – Fees",
"Appendix B: Data Processing Terms") is a heading, as the same line styled in Word is. Not a heading (controls): a
sentence that opens with the words ("Schedule A sets out the fees"), a list of references, a contents line ("Schedule 1
The Mandated Lead Arrangers and the Lenders7", "Schedule 2.5Fees"), and the mark alone ("Exhibit 10.1"): the first
replay of this rule over the corpus made the "Exhibit 10.1" that many EDGAR texts print on every page a heading each
time, which split their clauses at the page breaks, the war room's F-04 by another route (test below).

(2) The PDF printed "SYNTHETIC LEGAL BENCHMARK / LARKSPUR-2026" and "FICTIONAL TEST DOCUMENT | Not a real agreement | No
confidential data" at the top of every page. Since v12 such lines were text where they stand, so they sat inside §3,
§11 and §13, on the document pane between clauses, and in the model's input; a sentence broken by a page break carried
them in its middle, so a quote of that sentence as the contract prints it was not found. A DOCX's headers and footers
are left out of the reading and counted in its coverage. The invariant, for PDF, now the same: a line printed the same
(digits read as one) at the top or the foot of at least three pages, and of most pages that carry text, is the page's
furniture, left out of the sections and counted in the coverage, which names what was left out. Kept as before
(controls): the document's own heading printed once at its head, a numbered clause heading, a structural line ("EXHIBIT
B" on each page of the exhibit), a line on a minority of pages, a line in the body of the page, and plain text, which
has no pages. This replaces v12's "nothing printed is deleted" for PDFs: the bytes are kept and the coverage says what
the reading left out, as it does for Word.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.ingest import PARSER_VERSION, ingest
from app.ingest.sections import looks_like_heading
from tests.support import FUZZ_SCALE
from tests.test_running_lines import FURNITURE, SUBJECTS, text_pdf

# ---------------------------------------------------------------- (1) a schedule's heading


@pytest.mark.parametrize(
    "line",
    [
        "Schedule A. Service Level and Credits",
        "Schedule B. Exclusions and Administrative Notes",
        "Exhibit C. Signed Amendment Number One",
        "Annex 2 – Fees",
        "Appendix B: Data Processing Terms",
        "Attachment 1 - Form of Order",
        "Addendum 3. Pricing",
        "Exhibit 10.1. Form of Note",
    ],
)
def test_a_line_naming_a_part_of_the_agreement_is_a_heading(line: str) -> None:
    assert looks_like_heading(line)


@pytest.mark.parametrize(
    "line",
    [
        "Schedule A sets out the fees payable by Customer.",
        "Exhibit A (Form of Assignment), Exhibit B (Notices) and Exhibit C (Escrow).",
        "Schedule A ........................................ 14",
        "Schedule A to this Agreement shall govern the fees and the credits payable under it in every case.",
        "Scheduled maintenance is excluded from availability.",
        "Exhibit 10.1",
        "Schedule A.",
        "Exhibit 10.1 Form of Note",
        "Schedule 1 The Mandated Lead Arrangers and the Lenders7",
        "Schedule 2.5Fees",
        "Schedule 1.01(A) Lenders and Lenders’ Term Loan Commitments",
        "Schedule 3. Conditions Precedent 14",
    ],
)
def test_controls_sentences_lists_and_contents_lines_are_not_headings(line: str) -> None:
    assert not looks_like_heading(line)


def test_a_mark_printed_on_every_page_of_a_text_does_not_split_its_clauses() -> None:
    """The first v15 replay's regression, kept: an EDGAR exhibit prints "Exhibit 10.1" at the top of each page."""
    lines = [
        "Exhibit 10.1",
        "",
        "1. Grant",
        "",
        "The Company grants the units",
        "Exhibit 10.1",
        "described in this Agreement.",
        "",
        "2. Vesting",
        "",
        "Units vest.",
    ]
    text = "\n".join(lines).encode("utf-8")
    sections = ingest("ex101.txt", text).sections
    grant = next(s for s in sections if s.number == "1")
    assert "described in this Agreement." in grant.text, [(s.number, s.heading) for s in sections]
    assert [s.number for s in sections if s.number] == ["1", "2"]


SCHEDULED = [
    [
        "SERVICES AGREEMENT",
        "",
        "13. Miscellaneous",
        "",
        "13.3 No Penalty for Non-Renewal. There is no early renewal penalty or separate non-renewal fee.",
        "",
        "Schedule A. Service Level and Credits",
        "",
        "Worked example: monthly availability of 98.7% qualifies for a 10% credit.",
        "",
        "Schedule B. Exclusions and Administrative Notes",
        "",
        "B.1 Excluded Materials. SOW notes have no independent contractual force.",
    ]
]


def test_the_blind_tests_schedules_are_sections_of_their_own_in_a_pdf() -> None:
    sections = ingest("scheduled.pdf", text_pdf(SCHEDULED)).sections
    # Labelled as the DOCX labels them: "Schedule A", its title the first line of its text.
    headings = [s.heading for s in sections]
    assert "Schedule A" in headings and "Schedule B" in headings, headings
    miscellaneous = next(s for s in sections if s.number == "13")
    assert "98.7%" not in miscellaneous.text, "the SLA example is Schedule A's, not §13's"
    schedule_a = next(s for s in sections if s.heading.startswith("Schedule A"))
    assert "98.7% qualifies for a 10% credit" in schedule_a.text


def test_the_same_schedules_in_plain_text_read_the_same() -> None:
    text = "\n".join(SCHEDULED[0]).encode("utf-8")
    sections = ingest("scheduled.txt", text).sections
    assert [s.heading for s in sections if s.heading.startswith("Schedule")] == ["Schedule A", "Schedule B"]
    assert next(s for s in sections if s.heading == "Schedule A").text.startswith("Service Level and Credits")


# ---------------------------------------------------------------- (2) page furniture left out and counted


HEADER = "SYNTHETIC LEGAL BENCHMARK / LARKSPUR-2026"
BANNER = "FICTIONAL TEST DOCUMENT | Not a real agreement | No confidential data"
LARKSPUR = [
    [
        HEADER,
        BANNER,
        "Larkspur Cloud Platform Services Agreement",
        "",
        "7. Security and Incident Notices",
        "",
        "7.1 Confirmed Incident. Provider must notify Customer without undue delay and in any event within",
    ],
    [
        HEADER,
        BANNER,
        "forty-eight (48) hours after Provider confirms a Confirmed Security Incident affecting Customer Data.",
        "",
        "8. Limits on Liability",
        "",
        "8.1 General Cap. Each party's aggregate liability is limited to the fees paid.",
    ],
    [
        HEADER,
        BANNER,
        "9. Intellectual Property and Indemnity",
        "",
        "9.1 Provider IP Indemnification. Provider will defend Customer against a third-party claim.",
    ],
    [HEADER, BANNER, "10. Confidentiality", "", "10.1 Confidential Information. Each party shall protect the other party's information."],
]


def test_the_blind_tests_running_header_is_left_out_of_every_section_and_counted() -> None:
    parsed = ingest("larkspur.pdf", text_pdf(LARKSPUR))
    after_title = parsed.sections[1:]
    assert not any(HEADER in s.text or BANNER in s.text for s in after_title), [s.text for s in after_title]
    headers = next(part for part in parsed.coverage if part.part == "headers")
    assert headers.status == "omitted" and headers.count == 6, headers  # pages 2 to 4, two lines each; page 1's opens the document
    assert HEADER in headers.note and BANNER in headers.note, "the coverage names what the reading left out"


def test_a_sentence_broken_by_a_page_break_reads_whole_so_its_quote_is_found() -> None:
    incident = next(s for s in ingest("larkspur.pdf", text_pdf(LARKSPUR)).sections if s.number == "7")
    assert "and in any event within forty-eight (48) hours after Provider confirms" in " ".join(incident.text.split())


def test_page_numbers_at_the_foot_are_furniture_too() -> None:
    pages = [[f"{k}. Clause {k}", "", f"Clause {k} text runs here and ends.", "", f"Page {k} of 4"] for k in range(1, 5)]
    parsed = ingest("numbered.pdf", text_pdf(pages))
    assert not any("Page " in s.text for s in parsed.sections)
    footers = next(part for part in parsed.coverage if part.part == "footers")
    assert footers.status == "omitted" and footers.count == 4


@pytest.mark.parametrize(
    ("pages", "kept"),
    [
        # A structural line on each page of an exhibit names the part.
        ([["EXHIBIT B", "", f"{k}. Item", "", f"The {SUBJECTS[k]} item reads so."] for k in range(1, 5)], "EXHIBIT B"),
        # On a minority of pages.
        ([["NOTICE", "", "1. A", "", "a."], ["2. B", "", "b."], ["3. C", "", "c."], ["4. D", "", "d."], ["NOTICE", "", "5. E", "", "e."]], "NOTICE"),
        # In the body of each page, not at its edge.
        (
            [
                [
                    f"{k}. {SUBJECTS[k].title()}",
                    "",
                    f"The {SUBJECTS[k]} clause opens.",
                    f"It covers {SUBJECTS[k]}.",
                    "The same sentence on every page.",
                    f"It names {SUBJECTS[k - 1]}.",
                    f"The {SUBJECTS[k]} clause ends.",
                ]
                for k in range(1, 5)
            ],
            "The same sentence on every page.",
        ),
    ],
)
def test_controls_lines_that_are_not_page_furniture_stay_in_the_text(pages: list[list[str]], kept: str) -> None:
    parsed = ingest("controls.pdf", text_pdf(pages))
    printed = sum(page.count(kept) for page in pages)
    assert sum(s.text.count(kept) + (s.heading == kept) for s in parsed.sections) >= printed, "every printing is read, as text or as a heading"
    assert all(part.status != "omitted" for part in parsed.coverage if part.part in ("headers", "footers"))


def test_plain_text_has_no_pages_and_keeps_every_line() -> None:
    text = "\n".join(line for page in LARKSPUR for line in [*page, ""]).encode("utf-8")
    sections = ingest("larkspur.txt", text).sections
    assert sum(s.text.count(HEADER) + (HEADER in s.heading) for s in sections) >= 4, "an all-caps line in plain text is read, as a heading"


@settings(max_examples=30 * FUZZ_SCALE, deadline=None)
@given(
    clauses=st.integers(min_value=3, max_value=7),
    cuts=st.sets(st.integers(min_value=1, max_value=400), min_size=2, max_size=6),
    furniture=st.sampled_from(FURNITURE),
    where=st.sampled_from(["top", "bottom", "both"]),
)
def test_property_furniture_at_the_page_edge_is_left_out_and_every_clause_reads_whole(clauses: int, cuts: set[int], furniture: str, where: str) -> None:
    """Whatever the line, at the top or the foot, wherever the page breaks fall (inside a sentence included): every
    clause keeps its heading and its whole body, the line is in no section after the first page's opening, and the
    coverage counts every printing it left out."""
    rows = ["MASTER AGREEMENT", ""]
    for k in range(1, clauses + 1):
        subject, other = SUBJECTS[k], SUBJECTS[k - 1]
        rows += [f"{k}. {subject.title()}", "", f"Clause {k} opens with the {subject} and runs on", f"until it ends with the {other} it names.", ""]
    breaks = sorted({c % (len(rows) - 1) + 1 for c in cuts})
    assume(len(breaks) >= 2)
    body = [rows[a:b] for a, b in zip([0, *breaks], [*breaks, len(rows)], strict=True)]
    top, bottom = where in ("top", "both"), where in ("bottom", "both")
    pages = [[*([furniture, ""] if top else []), *lines, *(["", furniture] if bottom else [])] for lines in body]

    parsed = ingest("paged.pdf", text_pdf(pages))

    numbered = [s for s in parsed.sections if s.number]
    assert [s.number for s in numbered] == [str(k) for k in range(1, clauses + 1)]
    for k, section in enumerate(numbered, start=1):
        # A page break is a paragraph break, as before; the words run on in order with nothing between them.
        words = " ".join(section.text.split())
        assert words == f"Clause {k} opens with the {SUBJECTS[k]} and runs on until it ends with the {SUBJECTS[k - 1]} it names.", (k, section.text)
    first = parsed.sections.index(numbered[0])
    name = furniture.rstrip(".")
    assert not any(name in s.heading or furniture in s.text for s in parsed.sections[first:]), "after the opening the line is in no section"
    left = sum(part.count for part in parsed.coverage if part.part in ("headers", "footers"))
    kept = sum(1 for s in parsed.sections[1:first] if s.heading == name)
    still = sum(s.text.count(furniture) for s in parsed.sections) + kept
    assert left + still == sum(page.count(furniture) for page in pages), "every printing is either read or counted as left out"


def test_the_reader_keeps_v15s_rules() -> None:
    assert PARSER_VERSION in ("v15", "v16")  # v16 (test_reader_v16_*.py) keeps every rule tested here
