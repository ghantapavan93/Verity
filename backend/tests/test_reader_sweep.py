"""Reader defects found by the document sweep of 2026-10-01, each held by a test on the file that exposed it: text inside
nested tables and block-level content controls was dropped while coverage called those parts read; a UTF-16 or
Windows-1252 text file became replacement characters; a 100,000-character first paragraph became a 100,000-character title;
an image-only PDF page was "unknown" when it was known; a known file under a .docm name was "reused" past the type check."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.ingest import ingest
from app.ingest.readers import MAX_TITLE_CHARS, decode_text, shorten_title
from app.ingest.sections import MAX_HEADING_CHARS

FIXTURES = Path(__file__).parent / "fixtures" / "reader"


def _text(name: str) -> str:
    parsed = ingest(name, (FIXTURES / name).read_bytes())
    return "\n".join(f"{s.heading}\n{s.text}" for s in parsed.sections)


def _coverage(name: str) -> dict[str, tuple[str, int]]:
    parsed = ingest(name, (FIXTURES / name).read_bytes())
    return {c.part: (str(c.status), c.count) for c in parsed.coverage}


def test_a_table_nested_in_a_cell_is_read_inside_that_cell() -> None:
    text = _text("nested-tables.docx")
    assert "Inner 2: termination fee 5,000 EUR" in text
    assert _coverage("nested-tables.docx")["tables"] == ("read", 2)


def test_a_block_level_content_control_is_entered_heading_and_clause_alike() -> None:
    text = _text("content-controls.docx")
    assert "liability is capped at 100,000 USD" in text
    status, count = _coverage("content-controls.docx")["content_controls"]
    assert status == "read" and count >= 2


def test_a_table_wrapped_in_a_content_control_is_read() -> None:
    assert "fee 9,999 USD" in _text("degenerate-tables.docx")


def test_a_vertically_merged_cell_is_read_once_not_once_per_row() -> None:
    text = _text("merged-cells.docx")
    assert text.count("Vertical: Fees") == 1 and text.count("Spanning header: Payment terms") == 1


def test_a_utf16_text_file_is_decoded_not_read_as_nul_interleaved_garbage() -> None:
    text = _text("utf16.txt")
    assert "Either party may terminate on 30 days notice." in text and "\x00" not in text and "�" not in text
    assert _coverage("utf16.txt")["main_body"] == ("read", 0)
    parsed = ingest("utf16.txt", (FIXTURES / "utf16.txt").read_bytes())
    assert "UTF-16" in parsed.coverage[0].note


def test_a_windows_1252_text_file_keeps_its_euro_sign_and_accents() -> None:
    text = _text("windows-1252.txt")
    assert "€1,500" in text and "Société Générale" in text and "�" not in text


def test_decode_text_names_what_it_did() -> None:
    assert decode_text(b"plain") == ("plain", "UTF-8")
    assert decode_text(b"\xef\xbb\xbfbom") == ("bom", "UTF-8")
    assert decode_text("wide".encode("utf-16")) == ("wide", "UTF-16")
    assert decode_text("wide".encode("utf-16-le")) == ("wide", "UTF-16")
    assert decode_text("caf\xe9 €".encode("cp1252")) == ("café €", "Windows-1252")


def test_a_wall_of_text_is_named_by_its_first_words_and_kept_whole_as_body() -> None:
    wall = ("The Supplier shall deliver the Services to the Customer in accordance with this Agreement. " * 1200).strip()
    parsed = ingest("wall.txt", wall.encode())
    names = [re.sub(r" \(part \d+\)$", "", s.heading) for s in parsed.sections]
    assert names[0].endswith("…") and len(names[0]) <= MAX_TITLE_CHARS + 1, names[0]
    assert all(len(name) <= max(MAX_TITLE_CHARS, MAX_HEADING_CHARS) + 1 for name in names), [len(n) for n in names]
    assert " ".join(s.text for s in parsed.sections) == wall
    assert shorten_title("short") == "short"
    assert len(shorten_title("word " * 100)) <= MAX_TITLE_CHARS + 1


def test_an_image_only_page_is_counted_as_omitted_not_unknown() -> None:
    parsed = ingest("image-only-middle-page.pdf", (FIXTURES / "image-only-middle-page.pdf").read_bytes())
    assert parsed.pages == 3
    scanned = next(c for c in parsed.coverage if c.part == "scanned_pages")
    assert str(scanned.status) == "omitted" and scanned.count == 1
    text_only = ingest("services-agreement.pdf", (FIXTURES.parent / "services-agreement.pdf").read_bytes())
    assert str(next(c for c in text_only.coverage if c.part == "scanned_pages").status) == "absent"


def test_a_known_file_under_an_unsupported_name_is_refused_not_reused(client: TestClient) -> None:
    data = b"1. Term\n\nThe term is twelve months.\n"
    first = client.post("/api/documents", files={"file": ("terms.txt", data, "text/plain")})
    assert first.status_code == 201, first.text
    for name in ("terms.docm", "terms", "terms.exe"):
        again = client.post("/api/documents", files={"file": (name, data, "application/octet-stream")})
        assert again.status_code == 422 and "unsupported file type" in again.text, (name, again.status_code, again.text)
