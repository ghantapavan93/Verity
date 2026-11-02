"""Verifier v12: an invisible character is absent to the typed tier too (release gate, 2026-11-01).

The invariant is the verifier's own: it never says "found" when the text is not there. Since v11 every default-ignorable
code point is read as absent, as a reader sees the text, and the exact, normalized and casefold tiers did so. The typed
tier did not: it read the contract and the quote as typed tokens where they stand, so a zero-width space, a word joiner or
a soft hyphen inside a word ended the word there. "the​rapist" displays as "therapist", and the quote "the rapist"
was found in it, by the typed tier, though v6 refuses a space moved inside the letters. The other direction (an invisible
character in the quote, a space in the text) was refused only because the prefilter reads the quote as a reader does; the
property test of the prefilter found the disagreement (`test_locate_prefilter.py`).

From v12 the typed tier reads both texts as a reader sees them: v11's tokens over the visible text, their offsets mapped
back into the original, so the highlight still covers the characters that matched. The evidence pack reads a v12 run the
same way and keeps v11's reading for a v11 run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.verify.spans import _INVISIBLE as INVISIBLE
from app.verify.spans import VERIFIER_VERSION, locate
from app.verify.tokens import locate_tokens
from tests.support import FUZZ_SCALE
from tests.test_pack_parity import _pack, _verdict

ZWSP, WORD_JOINER, SOFT_HYPHEN, BOM = "​", "⁠", "­", "﻿"


def test_this_is_verifier_v12() -> None:
    assert VERIFIER_VERSION == "v12"


# A word the reader sees whole, and a quote that splits it with a space.
# A word the reader sees whole, a quote that splits it with a space, and the text v11's typed tier matched.
JOINED_IN_THE_TEXT = [
    ("the rapist", f"The patient was seen by a the{ZWSP}rapist on Monday.", f"the{ZWSP}rapist"),
    ("is un able to pay", f"The Customer is un{WORD_JOINER}able to pay the fees.", f"is un{WORD_JOINER}able to pay"),
    ("a non refundable deposit", f"The Customer pays a non{SOFT_HYPHEN}refundable deposit.", f"a non{SOFT_HYPHEN}refundable deposit"),
    ("within 30 days", f"The Supplier pays within 30{BOM}days of the invoice.", f"within 30{BOM}days"),
]


@pytest.mark.parametrize(("quote", "text", "matched"), JOINED_IN_THE_TEXT)
def test_an_invisible_character_does_not_part_a_word_of_the_text(quote: str, text: str, matched: str) -> None:
    assert locate(quote, text) is None
    assert locate_tokens(quote, text, INVISIBLE) is None


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        (f"the{ZWSP}rapist", "The patient was seen by the rapist on Monday."),
        (f"0{ZWSP}X", "0 X"),  # the prefilter property's counterexample
        (f"un{SOFT_HYPHEN}able to pay", "The Customer is un able to pay the fees."),
    ],
)
def test_an_invisible_character_does_not_part_a_word_of_the_quote(quote: str, text: str) -> None:
    assert locate(quote, text) is None
    assert locate_tokens(quote, text, INVISIBLE) is None


@pytest.mark.parametrize(
    ("quote", "text", "matched"),
    [
        ("unable to pay", f"The Customer is un{ZWSP}able to pay.", f"un{ZWSP}able to pay"),
        ("seen by the rapist", f"The patient was seen by the {ZWSP}rapist.", f"seen by the {ZWSP}rapist"),
        # The typed tier itself: "1500" is "1,500", and the invisible character inside the number stays in the highlight.
        ("fees of 1500 dollars", f"It pays fees of 1,5{WORD_JOINER}00 dollars.", f"fees of 1,5{WORD_JOINER}00 dollars"),
    ],
)
def test_control_what_the_reader_sees_is_still_found_and_highlighted_in_the_original(quote: str, text: str, matched: str) -> None:
    found = locate(quote, text)
    assert found is not None
    assert text[found.start : found.end] == matched


WORDS = st.lists(st.sampled_from(["the", "rapist", "therapist", "un", "able", "30", "days", "1,500", "$5", "fee."]), min_size=1, max_size=8)


@settings(max_examples=300 * FUZZ_SCALE, deadline=None)
@given(words=WORDS, cut=st.integers(0, 7), length=st.integers(1, 4), places=st.lists(st.integers(0, 80), max_size=4), data=st.data())
def test_invisible_characters_change_nothing_the_typed_tier_decides(words: list[str], cut: int, length: int, places: list[int], data: st.DataObject) -> None:
    text = " ".join(words)
    quote = " ".join(words[cut : cut + length]) or text
    hidden = text
    for at in sorted(places, reverse=True):
        at = min(at, len(hidden))
        hidden = hidden[:at] + data.draw(st.sampled_from(sorted(INVISIBLE))) + hidden[at:]
    plain, invisible = locate_tokens(quote, text, INVISIBLE), locate_tokens(quote, hidden, INVISIBLE)
    assert (plain is None) == (invisible is None), (quote, hidden)
    if plain is not None and invisible is not None:
        assert plain.count == invisible.count
        assert hidden[invisible.start : invisible.end].translate({ord(ch): None for ch in INVISIBLE}) == text[plain.start : plain.end]


@pytest.mark.parametrize(("quote", "text", "matched"), JOINED_IN_THE_TEXT)
def test_a_v12_pack_refuses_what_v12_refuses_and_a_v11_pack_keeps_v11_s_verdict(tmp_path: Path, quote: str, text: str, matched: str) -> None:
    start = text.index(matched)
    end = start + len(matched)
    assert not _verdict(_pack(tmp_path / "v12", text, start, end, quote, "typed", "v12"))
    assert _verdict(_pack(tmp_path / "v11", text, start, end, quote, "typed", "v11")), "a v11 run's pack reads as v11 did"


def test_control_a_v12_pack_passes_what_v12_finds(tmp_path: Path) -> None:
    text = f"It pays fees of 1,5{WORD_JOINER}00 dollars. The Customer is un{ZWSP}able to pay."
    for quote in ("fees of 1500 dollars", "unable to pay"):
        located = locate(quote, text)
        assert located is not None, quote
        folder = tmp_path / str(located.start)
        assert _verdict(_pack(folder, text, located.start, located.end, quote, located.method, "v12")), quote
