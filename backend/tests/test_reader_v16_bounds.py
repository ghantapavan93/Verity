"""Reader v16: what a reading hands on is bounded, a long paragraph is cut only where a passage ends, and an invisible
mark cannot part a number. Found by the adversarial stress test (2026-10-30).

(1) The reader put no limit on the sections it made. One 5.9 MB text of 100,000 short capitals headings read inside
the child's bounds, and then every cost that grows with sections fell on the API process: the insert held the store's
write lock for 16.5 s, the API took 416 MB, the upload's answer was 11.6 MB. The invariant: what one upload costs past
its reading is bounded, so a reading with more sections or more text than any contract has is refused in the child
(TooLargeToRead, a 413), counted after a long paragraph is split.

(2) A paragraph longer than a section was cut at the 6,000th character when no sentence end was in reach, inside a word
or a number: a credit agreement's "(part 3)" ended "the greater of $350," and "(part 4)" began "000,000 and 7.5%", and
"not to exceed the greater of $350" was verified, since a part's end is the end of the text the verifier searches.
The invariant: a part's edge is never inside a word, inside a number as it is written (verify.tokens.written_numbers),
or inside a sentence when a sentence end is within reach; a CJK stop ends a passage too.

(3) An LRM, RLM or ALM between two digits was kept: "upon 9؜0 days" displays "upon 90 days", and whatever reads
numbers read 9 and 0. The invariant: inside a number written in ASCII digits no invisible character is kept.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app import ingest as ingest_module
from app.ingest import TooLargeToRead, ingest
from app.ingest.invisible import remove_format_characters
from app.ingest.sections import MAX_SECTION_CHARS, split_paragraph
from app.verify.spans import bounded, locate
from tests.support import FUZZ_SCALE

# ---------------------------------------------------------------- (1) a reading's size is bounded


def test_a_reading_with_more_sections_than_any_contract_is_refused_in_the_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_module, "MAX_SECTIONS", 50)
    headings = "".join(f"TERM {chr(65 + i // 26)}{chr(65 + i % 26)}\n\nThe term runs.\n\n" for i in range(60))
    with pytest.raises(TooLargeToRead, match="sections"):
        ingest("many.txt", headings.encode())
    ingest("few.txt", headings[: headings.index("TERM BX")].encode())  # under the limit: read as before


def test_the_section_limit_counts_the_parts_a_long_paragraph_is_split_into(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_module, "MAX_SECTIONS", 10)
    wall = "The Provider shall deliver the services under this Agreement. " * 2_000  # one paragraph, about 21 parts
    with pytest.raises(TooLargeToRead):
        ingest("wall.txt", wall.encode())


def test_a_reading_with_more_text_than_any_contract_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_module, "MAX_TEXT_CHARS", 10_000)
    with pytest.raises(TooLargeToRead, match="characters"):
        ingest("long.txt", ("1. Term\n\n" + "The term runs for one year. " * 400).encode())


def test_the_limits_hold_three_times_the_largest_real_contract() -> None:
    assert ingest_module.MAX_SECTIONS >= 3 * 7_174 and ingest_module.MAX_TEXT_CHARS >= 3 * 4_400_000


def test_an_upload_past_the_section_limit_is_a_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_module, "MAX_SECTIONS", 50)
    headings = "".join(f"TERM {chr(65 + i // 26)}{chr(65 + i % 26)}\n\nThe term runs.\n\n" for i in range(60))
    response = client.post("/api/documents", files={"file": ("many.txt", headings.encode(), "text/plain")})
    assert response.status_code == 413, response.text
    assert "sections" in response.text


# ---------------------------------------------------------------- (2) a part's edge is a passage end


def _cuts(paragraph: str, pieces: list[str]) -> list[int]:
    """Where in ``paragraph`` each piece after the first begins."""
    offsets, at = [], 0
    for piece in pieces:
        at = paragraph.index(piece, at)
        offsets.append(at)
        at += len(piece)
    return offsets[1:]


AMOUNTS = ["$1,500,000", "$350,000,000", "7.5%", "-Rs. 5M", "USD 1,250.50", "15", "(30)", "2/3", "1.25x", "£12,000"]
WORDS = ["licence", "fee", "of", "the", "greater", "and", "Consolidated", "Net", "Tangible", "Assets", "per", "year", "or", "Lender"]


@st.composite
def long_paragraphs(draw: st.DrawFn) -> str:
    """A paragraph of words and written numbers, with semicolons, sentence ends or none, as a covenant runs."""
    tokens = draw(st.lists(st.one_of(st.sampled_from(WORDS), st.sampled_from(AMOUNTS)), min_size=150, max_size=400))
    stops = draw(st.sampled_from(["", ";", ".", "。"]))
    every = draw(st.integers(min_value=7, max_value=200))
    words = [f"{t}{stops}" if stops and i % every == every - 1 else t for i, t in enumerate(tokens)]
    return " ".join(words)


@settings(max_examples=150 * FUZZ_SCALE, deadline=None)
@given(long_paragraphs(), st.integers(min_value=120, max_value=600))
def test_no_part_of_a_long_paragraph_ends_inside_a_word_or_a_number(paragraph: str, cap: int) -> None:
    pieces = split_paragraph(paragraph, cap)
    assert " ".join(pieces).split() == paragraph.split(), "nothing is lost or moved"
    for cut in _cuts(paragraph, pieces):
        assert bounded(paragraph, cut, cut), f"a cut splits {paragraph[cut - 12 : cut]!r}|{paragraph[cut : cut + 12]!r}"


def test_the_credit_agreements_amount_is_never_cut() -> None:
    """The real case's shape: a covenant paragraph of semicolons only, the cap falling inside "$350,000,000"."""
    head = "Indebtedness in an aggregate principal amount not to exceed the greater of "
    paragraph = ("the Borrower may incur Indebtedness under this clause subject to the conditions below; " * 70)[: MAX_SECTION_CHARS - len(head) - 4]
    paragraph += head + "$350,000,000 and 7.5% of Consolidated Net Tangible Assets; and the Liens securing it"
    pieces = split_paragraph(paragraph, MAX_SECTION_CHARS)
    assert len(pieces) == 2 and all("$350" not in p or "$350,000,000" in p for p in pieces)
    assert locate("not to exceed the greater of $350", pieces[0]) is None and locate("not to exceed the greater of $350", pieces[1]) is None
    assert pieces[0].endswith(";"), "cut where the list's item ends"


def test_a_paragraph_without_any_stop_is_cut_at_a_space_that_splits_no_number() -> None:
    paragraph = " ".join(["a licence fee of $1,500,000 per year"] * 400)
    for cut in _cuts(paragraph, pieces := split_paragraph(paragraph, MAX_SECTION_CHARS)):
        assert bounded(paragraph, cut, cut)
    assert all(len(p) <= MAX_SECTION_CHARS for p in pieces)


def test_a_cjk_paragraph_is_cut_at_its_own_stops() -> None:
    paragraph = "许可费为人民币1,500,000元，每年支付。" * 600
    pieces = split_paragraph(paragraph, MAX_SECTION_CHARS)
    assert len(pieces) > 1 and all(p.endswith("。") for p in pieces[:-1]) and "".join(pieces) == paragraph


def test_a_paragraph_with_no_place_to_cut_stays_whole() -> None:
    paragraph = "许可费为人民币" * 2_000
    assert split_paragraph(paragraph, MAX_SECTION_CHARS) == [paragraph]


def test_a_sentence_end_past_the_cap_is_preferred_to_a_cut_inside_a_sentence() -> None:
    sentence = "x" * 5 + " " + "word " * 1_300 + "end. "
    paragraph = (sentence + "More text follows here. ") * 2
    pieces = split_paragraph(paragraph, MAX_SECTION_CHARS)
    assert pieces[0].endswith("end."), "the part runs on to the sentence's end"


def test_control_sentence_ends_inside_the_cap_are_cut_as_before() -> None:
    sentence = "The Supplier shall provide the Services in accordance with the Specification and the Service Levels. "
    paragraph = (sentence * 200).strip()
    pieces = split_paragraph(paragraph, MAX_SECTION_CHARS)
    assert all(len(p) <= MAX_SECTION_CHARS and p.endswith(".") for p in pieces) and " ".join(pieces) == paragraph


def test_a_quote_of_a_truncated_amount_is_not_found_in_any_part_of_the_reading() -> None:
    """Through ingest: the part the verifier searches no longer ends inside the amount."""
    filler = ("the Borrower may incur Indebtedness under this clause subject to the conditions below; " * 80)[: MAX_SECTION_CHARS - 40]
    text = f"CREDIT AGREEMENT\n\n1. Fees\n\n{filler} a licence fee of $1,500,000 per year; and other terms apply\n"
    sections = ingest("credit.txt", text.encode()).sections
    for section in sections:
        assert locate("a licence fee of $1,500", section.text) is None
    assert any(locate("a licence fee of $1,500,000 per year", s.text) is not None for s in sections)


# ---------------------------------------------------------------- (3) no invisible character inside an ASCII number


@pytest.mark.parametrize("mark", ["‎", "‏", "؜", "‌", "‍", "️"])
@pytest.mark.parametrize(("hidden", "shown"), [("upon 9{m}0 days", "upon 90 days"), ("$1{m},500", "$1,500"), ("$1,{m}500", "$1,500"), ("2.{m}5%", "2.5%")])
def test_an_invisible_mark_inside_a_number_is_removed_and_counted(mark: str, hidden: str, shown: str) -> None:
    assert remove_format_characters(hidden.format(m=mark)) == (shown, 1)


def test_control_marks_between_letters_and_beside_scripts_stay() -> None:
    for text in ("a‎b‏c", "שלום‏ 90", "9‏ שלום", "مرحبا؜ 12"):
        assert remove_format_characters(text) == (text, 0)


def test_an_alm_between_digits_reads_as_the_number_displayed() -> None:
    parsed = ingest("notice.txt", "1. Notice\n\nEither party may terminate upon 9؜0 days' notice.\n".encode())
    assert "upon 90 days" in parsed.sections[-1].text
    assert next(c for c in parsed.coverage if c.part == "format_characters").count == 1
