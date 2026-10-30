"""A line that opens with a reference to a clause does not open that clause (stress test, 2026-10-30, second wave).

clause_openings read a line starting "Section 5.4 of the Lease is deleted and replaced …" as opening clause 5.4, so the
sentence of an amendment that names the Lease's clause was taken for the document's own 5.4: labels of passages after it
named it, and every reference to 5.4 was linked to the amendment (the retrieval team worked around it in runs/links.py).
The invariant: a clause number opens a clause only where the words after it begin the clause, not where they go on
naming it ("of the Lease", "and 5.5", "hereof"). Controls: a clause that opens with its title, or with a sentence
("12.3 Notwithstanding …", "5.4 To the extent …"), still opens it.
"""

from __future__ import annotations

import pytest

from app.ingest.sections import clause_label, clause_openings, stated_clause_numbers


@pytest.mark.parametrize(
    "text",
    [
        "Section 5.4 of the Lease is deleted and replaced with the following.",
        "Section 5.4 of this Agreement shall not apply.",
        "SECTION 5.4 OF THE AGREEMENT IS HEREBY AMENDED.",
        "5.4 of the Agreement is amended by deleting the words.",
        "Clause 12 of the Framework Agreement applies.",
        "Article 7 and Article 8 survive.",
        "Section 5.4 and 5.5 survive termination.",
        "Sections 5.4 or 5.5 apply.",
        "Section 9 hereof governs.",
        "Fees are due. Section 4.2 of the Lease applies to them.",
    ],
)
def test_a_line_that_names_a_clause_does_not_open_it(text: str) -> None:
    assert clause_openings(text) == [], clause_openings(text)


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("Section 5.4 Fees. The fees are due monthly.", "5.4"),
        ("12.3 Notwithstanding Section 9, the Supplier may terminate.", "12.3"),
        ("5.4 To the extent permitted by law, neither party is liable.", "5.4"),
        ("Article 7 Term. The term is one year.", "7"),
        ("6. Termination. Either party may terminate.", "6"),
        ("Fees are due. 4.1 Late Fees. Interest accrues.", "4.1"),
        ("SECTION 5.4 OFFSET. THE CUSTOMER MAY SET OFF.", "5.4"),
    ],
)
def test_control_a_line_that_opens_a_clause_still_opens_it(text: str, number: str) -> None:
    assert number in [found for found, _ in clause_openings(text)]


def test_an_amendment_naming_a_clause_neither_labels_nor_states_it() -> None:
    text = "1. Amendment. The parties amend the Lease as follows.\n\nSection 5.4 of the Lease is deleted and replaced with: the rent is due quarterly."
    assert stated_clause_numbers([text]) == {"1"}
    assert clause_label(text, text.index("the rent is due")) == "§1 Amendment"
