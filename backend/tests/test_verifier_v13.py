"""Verifier v13: a word read whole through its marks takes every token it reaches whole (release review, 2026-11-02).

The invariant is the verifier's own: it never says "found" when the text is not there, and the typed tier never forgives
a changed digit. Since v11 a word runs on through a combining mark and the letters and digits after it (`whole_words`),
so a decomposed "caf\u00e9" is one word. It then skipped every token that began inside that run, though a token could begin
there and end past it: in "cafe\u0301USD 900" the run is "cafe\u0301USD", and the token "USD 900" began at "U". The word took
"USD" and the token was dropped, so "900" was never compared, and the quote "fee is cafe\u0301USD 500" was found in "The
fee is cafe\u0301USD 900 per month." The same dropped the rest of "1,500", "15%", "1.2.3" and "US$500" after a mark.

From v13 a word that reaches into a token takes that token whole, so every character the tokens held is compared. The
evidence pack reads a v13 run the same way and keeps v12's reading for a v12 run.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.verify.spans import _INVISIBLE as INVISIBLE
from app.verify.spans import VERIFIER_VERSION, locate
from app.verify.tokens import compared, locate_tokens, signed, significant, tokenize, whole_words
from tests.support import FUZZ_SCALE
from tests.test_pack_parity import _checker, _pack, _verdict

CIRCUMFLEX, TILDE = "\u0302", "\u0303"
ACUTE, DIAERESIS = "\u0301", "\u0308"


def test_this_is_verifier_v13() -> None:
    assert VERIFIER_VERSION == "v13"


# A quote whose number differs from the text's, after a word with a decomposed accent glued to the number's first
# characters; and the text v12's typed tier matched.
SWALLOWED = [
    ("fee is cafe\u0301USD 500", "The fee is cafe\u0301USD 900 per month.", "fee is cafe\u0301USD"),  # the review's case
    ("cafe\u03011,900 units", "The cafe\u03011,500 units ship.", "cafe\u03011,500 units"),  # the rest of a grouped number
    ("A cafe\u030115 fee", "A cafe\u030115% fee applies.", "A cafe\u030115% fee"),  # a percent sign
    ("see e\u03011.9.9 below", "see e\u03011.2.3 below", "see e\u03011.2.3 below"),  # a section identifier
    ("fee is cafe\u0301US$500 now", "fee is cafe\u0301US$900 now", "fee is cafe\u0301US$900 now"),  # a currency in letters
    ("pays nai\u0308USD 5,000 now", "pays nai\u0308USD 5,900 now", "pays nai\u0308USD 5,900 now"),  # another mark
]


# The token a word takes is compared as that token compares it, never more loosely (release review of 4a77d1b): a
# section identifier keeps its clause letter's case, which the word's caseless reading dropped.
LOOSENED = [
    ("see e\u03012.1\u03012.1(a) now", "Then see e\u03012.1\u03012.1(A) now.", "see e\u03012.1\u03012.1(A) now"),  # the review's case
    ("see e\u03011.2.3(b) now", "see e\u03011.2.3(B) now", "see e\u03011.2.3(B) now"),  # the first token taken (v11 to v13)
]


@pytest.mark.parametrize(("quote", "text", "matched"), SWALLOWED + LOOSENED)
def test_a_word_read_through_a_mark_drops_no_part_of_a_token(quote: str, text: str, matched: str) -> None:
    assert matched in text
    assert locate(quote, text) is None
    assert locate_tokens(quote, text, INVISIBLE) is None


@pytest.mark.parametrize(
    ("quote", "text", "matched"),
    [
        # The same texts, quoted as they stand, are found and highlighted whole.
        ("fee is cafe\u0301USD 900", "The fee is cafe\u0301USD 900 per month.", "fee is cafe\u0301USD 900"),
        ("cafe\u03011,500 units", "The cafe\u03011,500 units ship.", "cafe\u03011,500 units"),
        ("A cafe\u030115% fee", "A cafe\u030115% fee applies.", "A cafe\u030115% fee"),
        # v11's rule stands: a decomposed word is one word, and is the composed one.
        ("the caf\u00e9 menu", "See the cafe\u0301 menu.", "the cafe\u0301 menu"),
        ("pays the na\u00efve fee", "It pays the nai\u0308ve fee.", "pays the nai\u0308ve fee"),
        # A number the word takes is compared by its value, as the typed tier compares numbers: "1500" is "1,500".
        ("fee is cafe\u03011500 now", "The fee is cafe\u03011,500 now.", "fee is cafe\u03011,500 now"),
        ("see e\u03011.2.3(B) now", "see e\u03011.2.3(B) now", "see e\u03011.2.3(B) now"),
        # An amount word the word takes is compared as the typed tier compares it, written apart or not (the second
        # review of v13: the prefilter looked for "USD10K" as written and refused it).
        ("The cafe\u0301USD10K fee", "The cafe\u0301USD 10K fee.", "The cafe\u0301USD 10K fee"),
    ],
)
def test_control_what_the_text_says_is_still_found(quote: str, text: str, matched: str) -> None:
    found = locate(quote, text)
    assert found is not None
    assert text[found.start : found.end] == matched


FRAGMENTS = st.sampled_from(["cafe", ACUTE, DIAERESIS, "USD", "US$", " ", "500", "1,500", "15%", "1.2.3", "(", ")", "-", "e", "s", "7", ".", ","])


def _covered(tokens: list) -> set[int]:
    return {at for t in tokens for at in range(t.start, t.end)}


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(parts=st.lists(FRAGMENTS, min_size=1, max_size=10))
def test_reading_words_whole_drops_no_character_the_tokens_held(parts: list[str]) -> None:
    text = "".join(parts)
    held = significant(signed(text, tokenize(text)))
    assert _covered(held) <= _covered(whole_words(text, held)), ascii(text)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(parts=st.lists(FRAGMENTS, min_size=1, max_size=10), data=st.data())
def test_a_changed_digit_is_never_found(parts: list[str], data: st.DataObject) -> None:
    text = "".join(parts)
    digits = [at for at, ch in enumerate(text) if ch in "0123456789"]
    if not digits:
        return
    at = data.draw(st.sampled_from(digits))
    changed = text[:at] + data.draw(st.sampled_from([d for d in "0123456789" if d != text[at]])) + text[at + 1 :]
    assert locate_tokens(text, changed, INVISIBLE) is None, (ascii(text), ascii(changed))
    assert locate(text, changed) is None, (ascii(text), ascii(changed))


CLAUSES = st.sampled_from(["e", ACUTE, DIAERESIS, "2.1", "1.2.3(b)", "2.1(a)", "4(c)", " ", "(d)", "7", "USD"])


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(parts=st.lists(CLAUSES, min_size=1, max_size=10), data=st.data())
def test_a_clause_letter_of_another_case_is_never_found(parts: list[str], data: st.DataObject) -> None:
    text = "".join(parts)
    letters = [at for at in range(1, len(text) - 1) if text[at - 1] == "(" and text[at + 1] == ")" and text[at].isalpha()]
    if not letters:
        return
    at = data.draw(st.sampled_from(letters))
    changed = text[:at] + text[at].swapcase() + text[at + 1 :]
    assert locate_tokens(text, changed, INVISIBLE) is None, (ascii(text), ascii(changed))
    assert locate(text, changed) is None, (ascii(text), ascii(changed))


def test_a_v12_run_compares_as_v12_did() -> None:
    text = "The fee is cafe\u0301USD 900 per month."
    assert [t.canonical for t in compared(text, 12)][3] == "caf\u00e9usd"  # 900 dropped, as recorded
    assert "USD900" in [t.canonical for t in compared(text, 13)][3]  # the amount, compared as the amount


@pytest.mark.parametrize(("quote", "text", "matched"), SWALLOWED)
def test_a_v13_pack_refuses_what_v13_refuses_and_a_v12_pack_keeps_v12_s_verdict(tmp_path: Path, quote: str, text: str, matched: str) -> None:
    start = text.index(matched)
    end = start + len(matched)
    assert not _verdict(_pack(tmp_path / "v13", text, start, end, quote, "typed", "v13"))
    assert _verdict(_pack(tmp_path / "v12", text, start, end, quote, "typed", "v12")), "a v12 run's pack reads as v12 did"


def test_control_a_v13_pack_passes_what_v13_finds(tmp_path: Path) -> None:
    text = "The fee is cafe\u0301USD 900 per month. The cafe\u03011,500 units ship."
    for quote in ("fee is cafe\u0301USD 900", "cafe\u03011,500 units"):
        located = locate(quote, text)
        assert located is not None, ascii(quote)
        folder = tmp_path / str(located.start)
        assert _verdict(_pack(folder, text, located.start, located.end, quote, located.method, "v13")), ascii(quote)


# Stacked marks, as a decomposed Vietnamese name is written: the pack read the second mark as punctuation and kept it as
# a value of the word (the second review of v13), so a span the workbench verified failed in the pack.
STACKED = "Payment to Nguye\u0302\u0303n Van A is due."


def test_control_a_v13_pack_passes_a_word_with_stacked_marks(tmp_path: Path) -> None:
    quote = unicodedata.normalize("NFC", "Nguye\u0302\u0303n Van A")
    located = locate(quote, STACKED)
    assert located is not None
    assert _verdict(_pack(tmp_path / "v13", STACKED, located.start, located.end, quote, located.method, "v13"))


V13_PARTS = [
    "e",
    "a",
    "A",
    "\u00e9",
    "\u00ea",
    "\u1ec5",
    ACUTE,
    DIAERESIS,
    CIRCUMFLEX,
    TILDE,
    "USD",
    "10K",
    "1,500",
    "2.1(a)",
    "(B)",
    " ",
    "-",
    "(",
    ")",
    "%",
    "7",
    "/",
]
V13_TEXT = st.lists(st.sampled_from(V13_PARTS), min_size=1, max_size=10).map("".join)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(a=V13_TEXT, other=V13_TEXT, form=st.sampled_from(["NFC", "NFD", "other"]))
def test_the_pack_compares_typed_tokens_as_the_workbench_does_under_v13(tmp_path_factory: pytest.TempPathFactory, a: str, other: str, form: str) -> None:
    """Both ways, and against the same text in the other normal form, as a model's quote is often written."""
    checker = _checker(tmp_path_factory.mktemp("typed-v13"))
    b = other if form == "other" else unicodedata.normalize(form, a)

    def runtime(text: str) -> list[tuple[str, str]]:
        return [(str(t.kind), t.canonical) for t in compared(text, 13, INVISIBLE)]

    expected = any(ch.isalnum() for ch in b) and bool(runtime(a)) and runtime(a) == runtime(b)
    assert checker.same(a, b, "typed", 13) == expected, (ascii(a), ascii(b))
