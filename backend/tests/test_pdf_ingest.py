"""PDFs are read as text. Headings come from numbering or capitals; without them the file is flat,
and the interface says so. Quotes still verify against the text either way."""

from __future__ import annotations

from pathlib import Path

from app.ingest import ingest
from app.ingest.sections import looks_like_heading

FIXTURES = Path(__file__).with_name("fixtures")


def test_pdf_with_only_visual_headings_is_read_flat_but_complete() -> None:
    parsed = ingest("services-agreement.pdf", (FIXTURES / "services-agreement.pdf").read_bytes())
    assert parsed.pages == 1
    joined = " ".join(s.text for s in parsed.sections)
    assert "fifteen (15) days" in joined and "State of Delaware" in joined
    assert sum(1 for s in parsed.sections if s.number) == 0, "no numbering in the text, so no numbered sections"
    assert "  " not in joined, "layout-mode padding is collapsed"


def test_cross_references_are_not_mistaken_for_headings() -> None:
    assert not looks_like_heading("5.5 (Effect of Termination), Section 5.6 (Survival),")
    assert not looks_like_heading("2.1 See Section 4 for fees")
    assert looks_like_heading("5.5 Effect of Termination")
    assert looks_like_heading("12.9 Notices")
