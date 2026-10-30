"""Reader v17: a section the reader split for size says so as data, not in its heading's words (stress test, 2026-10-30,
second wave; the interface corner's finding 6).

A long section is stored as parts headed "X (part 1)", "X (part 2)" …, and the only record of the split was that suffix:
clause_label_in parsed it back from the heading, and so did the interface. A document that writes such headings itself
("Definitions (part 1)", "Recitals" then "Recitals (part 2)") was read as the reader's own split: the paper dropped its
words and showed a heading as a continuation, and a passage in "Recitals (part 2)" was labelled by a clause opened under
"Recitals" ("§1.1 Governing Law" for "The Licensee shall pay the fees"), through a branch that accepted a bare heading as
part 1, which no reading has ever written. The invariant: the split is data (ParsedSection.part, stored on the section;
0 for a section not split), every heading is the document's own words or the reader's suffix on a part it made, and a
passage is read with earlier parts only when the reader made them. A reading stored before parts were recorded (part
NULL) is read by the strict suffix rule alone: an explicit "(part 1)", the same number, indices running on by one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ingest import ingest
from app.ingest.sections import MAX_SECTION_CHARS, clause_label_in, part_heading

LONG = " ".join(f"The Supplier shall provide service {i} to the Customer under this Agreement." for i in range(240))


def test_a_section_split_for_size_records_each_part_and_one_not_split_records_none() -> None:
    sections = ingest("long.txt", f"AGREEMENT\n\n1. Services\n\n{LONG}\n\n2. Fees\n\nFees are due monthly.\n".encode()).sections
    services = [s for s in sections if s.number == "1"]
    assert len(services) >= 3 and all(len(s.text) <= MAX_SECTION_CHARS for s in services)
    assert [s.part for s in services] == list(range(1, len(services) + 1))
    assert [s.heading for s in services] == [part_heading("Services", n) for n in range(1, len(services) + 1)]
    assert next(s for s in sections if s.number == "2").part == 0


def test_a_documents_own_part_headings_are_its_words_and_no_split() -> None:
    text = "AGREEMENT\n\n1. Definitions (part 1)\n\nAffiliate means a company.\n\n2. Definitions (part 2)\n\nFee means the fee.\n"
    sections = ingest("parts.txt", text.encode()).sections
    assert [(s.number, s.heading, s.part) for s in sections if s.number] == [("1", "Definitions (part 1)", 0), ("2", "Definitions (part 2)", 0)]


GOVERNING = "1.1 Governing Law. This Agreement is governed by the laws of England."
PAYING = "The Licensee shall pay the fees within thirty days."


@pytest.mark.parametrize("recorded", [True, False])
def test_a_documents_bare_heading_and_its_part_2_are_never_read_as_one(recorded: bool) -> None:
    rows: list[tuple[str, ...]] = [("", "Recitals", GOVERNING), ("", "Recitals (part 2)", PAYING)]
    if recorded:
        rows = [(*row, 0) for row in rows]
    assert clause_label_in(rows, 1, 0) is None


@pytest.mark.parametrize("recorded", [True, False])
def test_a_documents_part_chain_is_not_joined_when_the_reading_recorded_no_split(recorded: bool) -> None:
    rows = [("5", "Fees (part 1)", "5.1 Price. The price is fixed."), ("5", "Fees (part 2)", PAYING)]
    if recorded:
        assert clause_label_in([(*row, 0) for row in rows], 1, 0) is None, "parts recorded as 0: the document wrote them"
    else:
        # Stored before parts were recorded: an explicit part 1 and part 2 of one number are the reader's own split.
        assert clause_label_in(rows, 1, 0) == "§5.1 Price"


@pytest.mark.parametrize("recorded", [True, False])
def test_control_a_clause_opened_in_part_2_labels_a_passage_at_the_top_of_part_3(recorded: bool) -> None:
    rows: list[tuple[str, ...]] = [
        ("5", part_heading("Intellectual Property", 1), "5.1 Ownership. The Licensor owns the software."),
        ("5", part_heading("Intellectual Property", 2), "13.2 Governing Law. This Agreement and"),
        ("5", part_heading("Intellectual Property", 3), "shall be governed by English law."),
    ]
    if recorded:
        rows = [(*row, n) for n, row in enumerate(rows, start=1)]
    assert clause_label_in(rows, 2, 0) == "§13.2 Governing Law"


def test_the_store_keeps_each_sections_part(client: TestClient) -> None:
    from app.db import SessionLocal
    from app.models import Section

    body = f"AGREEMENT\n\n1. Services\n\n{LONG}\n\n2. Fees\n\nFees are due monthly.\n"
    uploaded = client.post("/api/documents", files={"file": ("parts.txt", body.encode(), "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    with SessionLocal() as session:
        stored = session.scalars(select(Section).where(Section.document_id == uploaded.json()["id"]).order_by(Section.ordinal)).all()
        parts = [(s.number, s.heading, s.part) for s in stored]
    assert parts == [(s.number, s.heading, s.part) for s in ingest("parts.txt", body.encode()).sections]
    assert ("2", "Fees", 0) in parts and max(part or 0 for _, _, part in parts) >= 3
