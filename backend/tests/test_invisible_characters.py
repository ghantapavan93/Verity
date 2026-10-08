"""The text a person reads is the text that is checked. Invisible format characters (Unicode Cf) are removed wherever text
enters, and the reading counts them. Found by the adversarial review of 2026-10-08: "terminate on \\u202e09\\u202c days"
displayed as "90 days" on the paper and in the evidence sheet, "Found word for word … exact", while the model, the
verifier and the day parser read "09"; "9\\u200b0 days" displayed "90" and parsed as 0 days.
"""

from __future__ import annotations

import io
import unicodedata

import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ingest import base_name, ingest, readers
from app.ingest.invisible import remove_format_characters
from app.ingest.sections import Block
from app.policy.durations import parse_durations
from tests.support import GUIDANCE

KEPT = {"\u200c", "\u200d", "\u200e", "\u200f", "\u061c"}


def body(name: str, data: bytes) -> str:
    return " ".join(s.text for s in ingest(name, data).sections)


@pytest.mark.parametrize(
    ("hidden", "shown"),
    [
        ("terminate on \u202e09\u202c days", "terminate on 09 days"),  # the original: a direction override
        ("terminate on 9\u200b0 days", "terminate on 90 days"),  # zero-width space
        ("terminate on 9\u00ad0 days", "terminate on 90 days"),  # soft hyphen
        ("terminate on 9\ufeff0 days", "terminate on 90 days"),  # zero-width no-break space
        ("terminate on 9\u20600 days", "terminate on 90 days"),  # word joiner
        ("terminate on \u2068\u202e09\u202c\u2069 days", "terminate on 09 days"),  # an isolate around the override
    ],
)
def test_the_stored_text_is_the_text_a_person_sees_and_the_day_parser_reads_it(hidden: str, shown: str) -> None:
    text = body("notice.txt", f"1. Termination\n\nEither party may {hidden} written notice.\n".encode())
    assert shown in text
    assert not any(unicodedata.category(ch) == "Cf" for ch in text)
    mentions = parse_durations(shown)
    duration = mentions[0].duration if mentions else None
    assert duration is not None and str(duration.value) == shown.split(" ")[2].lstrip("0")


def test_the_reading_counts_what_it_removed() -> None:
    parsed = ingest("notice.txt", "1. Term\n\nIt ends after \u202e09\u202c days.\n".encode())
    part = next(p for p in parsed.coverage if p.part == "format_characters")
    assert part.count == 2 and part.status.value == "excluded"
    clean = next(p for p in ingest("plain.txt", b"1. Term\n\nIt ends after 90 days.\n").coverage if p.part == "format_characters")
    assert clean.count == 0 and clean.status.value == "absent"


def test_a_heading_with_an_invisible_character_is_still_found() -> None:
    sections = ingest("contract.txt", "1.\u200b Term\n\nThe term is two years.\n\n2. Fees\n\nFees are monthly.\n".encode()).sections
    assert [(s.number, s.heading) for s in sections if s.number] == [("1", "Term"), ("2", "Fees")]


def test_a_word_document_is_cleaned_the_same_way() -> None:
    document = DocxDocument()
    document.add_paragraph("Either party may terminate on 9\u200b0 days written notice.")
    data = io.BytesIO()
    document.save(data)
    assert "terminate on 90 days" in body("notice.docx", data.getvalue())


def test_the_read_boundary_cleans_whatever_a_reader_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guarantee holds for any reader: a block carrying a format character leaves `read` without it."""

    def leaky(_data: bytes) -> readers.ReadResult:
        return readers.ReadResult(blocks=[Block("text", "pay within 9\u200b0 days")], pages=1, title="T\u2060itle")

    monkeypatch.setattr(readers, "read_pdf", leaky)
    result = readers.read("x.pdf", b"%PDF-1.4 minimal")
    # the title is a label derived from the text: cleaned, not counted twice
    assert result.blocks[0].text == "pay within 90 days" and result.title == "Title" and result.format_characters == 1


@pytest.mark.parametrize(
    "hidden",
    ["\u034f", "\ufe00", "\ufe0f", "\U000e0100", "\u17b4", "\u180b", "\u3164", "\u115f"],
    ids=[
        "combining-grapheme-joiner",
        "variation-selector-1",
        "variation-selector-16",
        "variation-selector-17",
        "khmer-vowel-inherent",
        "mongolian-fvs1",
        "hangul-filler",
        "hangul-choseong-filler",
    ],
)
def test_an_invisible_character_that_is_not_a_format_character_is_removed_between_digits(hidden: str) -> None:
    """Triage review, 2026-10-08: reader v9 removed only Cf, and "9<U+FE0F>0 days" still displayed 90 and parsed as 0."""
    text = body("notice.txt", f"1. Termination\n\nEither party may terminate on 9{hidden}0 days written notice.\n".encode())
    assert "terminate on 90 days" in text
    mentions = parse_durations(text)
    duration = mentions[0].duration if mentions else None
    assert duration is not None and str(duration.value) == "90"


def test_controls_a_keycap_an_emoji_form_and_a_cjk_variant_keep_their_selectors() -> None:
    for text in ("9\ufe0f\u20e3", "\u2764\ufe0f", "\u6f22\ufe00", "a\ufe0f b"):
        assert remove_format_characters(text) == (text, 0)


def test_the_unicode_database_is_the_one_the_reader_was_versioned_under() -> None:
    """The Cf set is read from Python's Unicode database. A Python whose database differs may remove other characters
    from the same bytes, which is a new reading: change the reader version with it, then this pin."""
    assert unicodedata.unidata_version == "15.1.0"


def test_controls_scripts_emoji_and_direction_marks_are_text() -> None:
    for text in ("שלום مرحبا", "\U0001f468\u200d\U0001f469\u200d\U0001f467", "a\u200eb\u200fc", "م\u200cن"):
        assert remove_format_characters(text) == (text, 0)
    assert remove_format_characters("x\u200dy") == ("xy", 1)  # a joiner between two ASCII letters shapes nothing


def test_a_file_name_cannot_disguise_its_extension() -> None:
    assert base_name("Invoice-\u202efdp.exe.txt") == "Invoice-fdp.exe.txt"
    assert base_name("family-\U0001f468\u200d\U0001f469.txt") == "family-\U0001f468\u200d\U0001f469.txt"


def test_guidance_a_question_and_a_review_are_stored_as_they_are_seen(client: TestClient) -> None:
    document = client.post(
        "/api/documents",
        files={
            "file": (
                "c.txt",
                b"1. Term\n\nThe term is two years.\n\n2. Termination for Convenience\n\n"
                b"Customer may terminate this Agreement for convenience upon fifteen (15) days\xe2\x80\x99 written notice to Provider.\n",
                "text/plain",
            )
        },
    ).json()
    guidance = client.post("/api/guidance", json={"text": GUIDANCE.replace("30 days", "3\u200b0 days")}).json()
    assert "\u200b" not in guidance["text"] and "30 days" in guidance["text"]
    run = client.post(
        "/api/runs", json={"documentId": document["id"], "guidanceId": guidance["id"], "question": "Can the customer \u202eterminate\u202c?"}
    ).json()
    assert run["question"] == "Can the customer terminate?"
    finding = client.get(f"/api/runs/{run['id']}").json()["findings"][0]
    review = client.post(f"/api/findings/{finding['id']}/review", json={"verdict": "confirmed", "reviewer": "A\u200b. Reviewer", "note": "ok\u2060"}).json()
    assert review["review"]["reviewer"] == "A. Reviewer" and review["review"]["note"] == "ok"


VISIBLE = st.text(alphabet=st.sampled_from(list("0123456789 abcdefxyz.,")), min_size=1, max_size=40)
INVISIBLE = st.sampled_from(
    ["\u200b", "\u00ad", "\ufeff", "\u2060", "\u202e", "\u202c", "\u2066", "\u2069", "\U000e0041", "\u200d", "\ufe0f", "\u034f", "\U000e0100"]
)
# Kept beside anything that is not an ASCII letter or digit: they shape or vary the character they follow.
SHAPING = "\u200c\u200d\ufe0f\u034f\U000e0100"


@settings(max_examples=300, deadline=None)
@given(st.lists(st.tuples(VISIBLE, INVISIBLE), min_size=1, max_size=8))
def test_removing_invisible_characters_leaves_exactly_the_visible_text(pieces: list[tuple[str, str]]) -> None:
    hidden = "".join(text + mark for text, mark in pieces)
    visible = "".join(text for text, _ in pieces)
    cleaned, count = remove_format_characters(hidden)
    # A joiner or selector is kept only beside a character that is not an ASCII letter or digit (a space, a stop).
    assert all(unicodedata.category(ch) != "Cf" or ch in KEPT for ch in cleaned)
    assert "".join(ch for ch in cleaned if ch not in SHAPING) == visible and count == len(hidden) - len(cleaned)
