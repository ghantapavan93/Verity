"""A reference is unknown only when the document has no such clause, by its reader's numbering or by its own text.

Found by the holdout audit and the journey audit (2026-10-09; runs acdcf704a1ac45e1, 3e9181397312438f): code lowered
correct answers with "the conclusion names a section this document does not have" for §6, §12.3, §5(i) and §4.1, all
printed in the document. The check knew only the reader's section numbers: a clause written as a numbered paragraph
inside a stored section ("12.3 Notwithstanding Section 4.1, …" inside §12), or a document read without numbering, had
no number it could see. A reference to a clause whose sub-clauses are the stored sections ("Section 6" over 6.1 and
6.2) was unknown for the same reason.

The invariant: every number the document's text opens a clause with, and every number its sections carry or sit
under, is known; a number the document states nowhere as a clause stays reported.
"""

from __future__ import annotations

from app.ingest.sections import stated_clause_numbers
from app.runs.status import Decision, check_references, unknown_references

C32_SECTION = (
    "12. General\n\n12.1 Assignment. Neither party may assign this Agreement without consent.\n\n"
    "12.3 Notwithstanding Section 4.1, neither party may terminate this Agreement for convenience on less than ninety "
    "(90) days' prior written notice."
)
NUMBERLESS = (
    "EXHIBIT A\n\n6. TERMINATION. (a) Either party may terminate on thirty days' notice. (b) Company may terminate for "
    "cause. (c) In the event of termination under either section 6(a) or 6(b), Contractor shall be paid all fees."
)
RUN_TOGETHER = "Fees are due monthly. 5. Payment Terms. (i) Invoices are payable in thirty days. 4.1 Late fees accrue."


def test_a_clause_the_text_opens_inside_a_stored_section_is_known() -> None:
    stated = stated_clause_numbers([C32_SECTION])
    assert {"12.1", "12.3"} <= stated
    assert unknown_references("The notice period is ninety days, as §12.3 states.", ["12"], ["sec_11"], stated) == []


def test_a_clause_in_a_reading_without_numbering_is_known() -> None:
    stated = stated_clause_numbers([NUMBERLESS])
    assert "6" in stated
    assert unknown_references("Section 6(c) says Contractor is paid all fees.", ["", ""], ["sec_0", "sec_1"], stated) == []


def test_a_clause_opened_after_a_sentence_end_is_known() -> None:
    stated = stated_clause_numbers([RUN_TOGETHER])
    assert {"5", "4.1"} <= stated
    assert unknown_references("Under §5(i) invoices are due in thirty days; §4.1 sets late fees.", [""], [], stated) == []


def test_a_clause_whose_sub_clauses_are_the_sections_is_known() -> None:
    assert unknown_references("Section 6 governs termination.", ["6.1", "6.2", "7"], [], set()) == []


def test_a_number_the_document_never_opens_a_clause_with_stays_reported() -> None:
    """Controls: an amount, a cross-reference and a period in the text are not clause openings."""
    text = "Payment is due 30 days after invoice. Subject to Section 9, fees are fixed. 2.5 million units ship yearly"
    stated = stated_clause_numbers([text, C32_SECTION])
    assert "30" not in stated and "9" not in stated
    assert unknown_references("Section 30 sets the payment term; §9 fixes fees; §14.2 grants pricing.", ["12"], [], stated) == ["30", "9", "14.2"]
    assert unknown_references("Section 12.2 covers assignment.", ["12"], [], stated) == ["12.2"], "a sibling the text never opens"


def test_the_check_lowers_a_pass_only_for_a_reference_the_document_lacks() -> None:
    passing = Decision("pass", "model_hint")
    stated = stated_clause_numbers([C32_SECTION])
    assert check_references(passing, "Ninety days, per §12.3.", ["12"], [], stated) is passing
    lowered = check_references(passing, "Ninety days, per §14.2.", ["12"], [], stated)
    assert (lowered.status, lowered.source) == ("needs_review", "reference_check")


def test_a_numbered_list_does_not_make_a_section_known() -> None:
    """Triage, 2026-10-09: a list item opens no clause. "1. deliver goods;" is not clause 1, so "§2" stays reported in a
    contract whose only "2." is a list item; a whole number counts only when it opens a titled clause."""
    listed = "The Supplier shall:\n\n1. deliver the goods;\n\n2. invoice monthly; and\n\n3. keep records."
    stated = stated_clause_numbers([listed, "Fees are due. 4 days later the goods ship."])
    assert stated.isdisjoint({"1", "2", "3", "4"}), stated
    assert unknown_references("Section 2 grants exclusivity; §3 caps liability.", ["7"], [], stated) == ["2", "3"]


def test_a_titled_whole_number_clause_is_known() -> None:
    stated = stated_clause_numbers(["Recitals here.\n\n6. WRF Patents. Washington shall file the applications."])
    assert "6" in stated
    assert unknown_references("Under Section 6 the patents are filed.", ["1"], [], stated) == []


def test_a_hostile_line_is_read_in_linear_time() -> None:
    """Security audit, 2026-10-09: one long line of whole-number openings cost seconds per run."""
    import time

    for hostile in ("1. A " * 20_000, "Fees are due. 1. Title. " * 8_000, "1." * 30_000):
        started = time.perf_counter()
        stated_clause_numbers([hostile])
        assert time.perf_counter() - started < 0.5, hostile[:20]
