"""Verifier v14: a clause's letter is read as a reader sees it (release review of b5dffaf, 2026-11-02).

Since v11 case is forgiven everywhere but in a clause's letter: "(A)" and "(a)" name two clauses. The casefold tier and
the typed tier both asked whether a letter alone in parentheses stood in the quote, on the characters as they are
stored, so an invisible character inside the parentheses ("4(C" + U+200E + ")"), or a letter written with a combining
mark ("(a" + U+0301 + ")"), was no clause letter to them, and its case was forgiven: "x 4(C\u200e) y" was found in
"x 4(c\u200e) y". From v14 both tiers, and the evidence pack, read clause letters with the characters normalisation
deletes left out and the marks composed (`tokens.clause_letters`). A v13 run is still read as v13 read it.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.verify.spans import _INVISIBLE as INVISIBLE
from app.verify.spans import VERIFIER_VERSION, _cannot_hold, _tiers, locate
from app.verify.tokens import clause_letters, compared, locate_tokens
from tests.support import FUZZ_SCALE
from tests.test_pack_parity import _checker, _pack, _verdict


def test_this_is_verifier_v14() -> None:
    assert VERIFIER_VERSION == "v14"


# A clause letter of another case, hidden from the check by a character the reader does not see or by a mark.
HIDDEN = [
    ("x 4(C\u200e) y", "x 4(c\u200e) y"),  # the review's case
    ("see 2(\u200ba) now", "see 2(\u200bA) now"),
    ("see (i\u00adv) now", "see (I\u00adV) now"),
    ("see (\ufeffb) now", "see (\ufeffB) now"),
    ("x (a\u0301) y", "x (A\u0301) y"),  # a decomposed letter
    # The review of 9eb23b5: spaces inside the parentheses, a mark before the letter, a roman numeral with a mark,
    # full-width and parenthesised forms.
    ("see ( a ) now", "see ( A ) now"),
    ("see (\u0301a) now", "see (\u0301A) now"),
    ("see (i\u0301v) now", "see (I\u0301V) now"),
    ("see \uff08a\uff09 now", "see \uff08A\uff09 now"),
    ("see \u24d0 now", "see \u24b6 now"),  # a circled letter and its capital
]


@pytest.mark.parametrize(("quote", "text"), HIDDEN)
def test_a_hidden_clause_letter_of_another_case_is_never_found(quote: str, text: str) -> None:
    assert locate(quote, text) is None
    assert locate_tokens(quote, text, INVISIBLE) is None


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("x 4(C\u200e) y", "x 4(C) y"),  # the same letter, an invisible character apart
        ("x (a\u0301) y", "x (\u00e1) y"),  # the same letter, decomposed and composed
        ("SECTION 4(c) applies", "Section 4(c) applies"),  # case outside the letter is still forgiven
    ],
)
def test_control_the_same_clause_letter_is_found(quote: str, text: str) -> None:
    assert locate(quote, text) is not None


def test_clause_letters_are_read_as_a_reader_sees_them() -> None:
    assert clause_letters("4(C\u200e) and (a\u0301)", INVISIBLE) == ["(C)", "(\u00e1)"]


HIDE = st.sampled_from(["\u200e", "\u200b", "\u00ad", "\ufeff", ""])


@settings(max_examples=300 * FUZZ_SCALE, deadline=None)
@given(letter=st.sampled_from(list("abcdivxAB")), before=HIDE, after=HIDE, data=st.data())
def test_a_clause_letter_of_another_case_is_never_found_however_it_is_hidden(letter: str, before: str, after: str, data: st.DataObject) -> None:
    other = letter.swapcase()
    hidden = data.draw(st.sampled_from(["", "\u0301"]))
    quote = f"see 4({before}{letter}{hidden}{after}) now"
    text = f"see 4({before}{other}{hidden}{after}) now"
    assert locate(quote, text) is None, (ascii(quote), ascii(text))


@pytest.mark.parametrize(("quote", "text"), [(q, t) for q, t in HIDDEN if any(ch.isalnum() for ch in q.split(" ", 1)[1].rsplit(" ", 1)[0])])
def test_a_v14_pack_refuses_what_v14_refuses_and_a_v13_pack_keeps_v13_s_verdict(tmp_path: Path, quote: str, text: str) -> None:
    checker = _checker(tmp_path)
    assert not checker.same(text.split(" ", 1)[1].rsplit(" ", 1)[0], quote.split(" ", 1)[1].rsplit(" ", 1)[0], "casefold", 14)
    assert checker.same(text.split(" ", 1)[1].rsplit(" ", 1)[0], quote.split(" ", 1)[1].rsplit(" ", 1)[0], "casefold", 13)


def test_control_a_v14_pack_passes_what_v14_finds(tmp_path: Path) -> None:
    text = "Under Section 4(c\u200e) the fee applies."
    quote = "SECTION 4(c\u200e) the fee"
    located = locate(quote, text)
    assert located is not None
    assert _verdict(_pack(tmp_path / "v14", text, located.start, located.end, quote, located.method, "v14"))


# The typed tier dropped a symbol that reads as a letter or digit as punctuation, so a circled or parenthesised letter
# was found where the text has another letter (found while reviewing 9eb23b5). From v14 it is compared as it reads.
ENCLOSED = [
    ("see \u24d0 now", "see \u24d1 now"),  # circled a, circled b
    ("see \u249c now", "see \u249d now"),  # parenthesised a, parenthesised b
    ("item \u24b6 applies", "item \u24b7 applies"),
]


@pytest.mark.parametrize(("quote", "text"), ENCLOSED)
def test_a_symbol_that_reads_as_a_letter_is_compared(quote: str, text: str, tmp_path: Path) -> None:
    assert locate(quote, text) is None
    assert locate_tokens(quote, text, INVISIBLE) is None
    checker = _checker(tmp_path)
    assert not checker.same(text, quote, "typed", 14)
    assert checker.same(text, quote, "typed", 13), "a v13 run's pack reads as v13 did"


def test_control_the_same_enclosed_letter_is_found() -> None:
    assert locate("see \u24d0 now", "We see \u24d0 now.") is not None


V14_PARTS = ["(", ")", " ", "a", "A", "b", "i", "v", "I", "V", "x", "4", chr(0x301), chr(0x308), chr(0x200E), chr(0xAD)]
V14_PARTS += [chr(0x24D0), chr(0x24B6), chr(0x249C), chr(0xFF08), chr(0xFF09), chr(0xE1)]
V14_TEXT = st.lists(st.sampled_from(V14_PARTS), min_size=1, max_size=10).map("".join)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(a=V14_TEXT, other=V14_TEXT, form=st.sampled_from(["NFC", "NFD", "swap", "other"]))
def test_the_pack_reads_clause_letters_as_the_workbench_does_under_v14(tmp_path_factory: pytest.TempPathFactory, a: str, other: str, form: str) -> None:
    """At the typed and casefold tiers, against the same text in the other normal form or case, and against another."""
    checker = _checker(tmp_path_factory.mktemp("clauses-v14"))
    b = {"swap": a.swapcase(), "other": other}.get(form) or unicodedata.normalize(form, a)
    runtime = [(str(t.kind), t.canonical) for t in compared(a, 14, INVISIBLE)]
    expected = any(ch.isalnum() for ch in b) and bool(runtime) and runtime == [(str(t.kind), t.canonical) for t in compared(b, 14, INVISIBLE)]
    assert checker.same(a, b, "typed", 14) == expected, (ascii(a), ascii(b))
    assert clause_letters(a, INVISIBLE) == checker.clause_letters(a, 14), ascii(a)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(quote=V14_TEXT, text=V14_TEXT)
def test_the_prefilter_never_refuses_a_clause_the_tiers_find(quote: str, text: str) -> None:
    if _tiers(quote, text) is not None:
        assert not _cannot_hold(quote, text), (ascii(quote), ascii(text))


# The review of the second v14 (8e12f4d, not released): a letter that the compatibility form makes two letters lost its
# clause; and symbols the first rule missed (a squared unit, a negative circled or squared capital) were still dropped.
@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("see (" + chr(0x1C4) + ") now", "see (" + chr(0x1C6) + ") now"),
        ("see (" + chr(0x132) + ") now", "see (" + chr(0x133) + ") now"),
        ("see (FF) now", "see (" + chr(0xFB00) + ") now"),
        ("5 " + chr(0x338E) + " daily", "5 " + chr(0x338F) + " daily"),
        ("see " + chr(0x1F151) + " now", "see " + chr(0x1F150) + " now"),
        ("see " + chr(0x1F171) + " now", "see " + chr(0x1F170) + " now"),
        # The review of 7b38f5a: a Unicode roman numeral is a number, not a letter, and still a clause's numeral.
        ("see (" + chr(0x2163) + ") now", "see (" + chr(0x2173) + ") now"),
        ("see (" + chr(0x2160) + ") now", "see (" + chr(0x2170) + ") now"),
        ("see " + chr(0xFF08) + chr(0x2163) + chr(0xFF09) + " now", "see " + chr(0xFF08) + chr(0x2173) + chr(0xFF09) + " now"),
    ],
)
def test_a_letter_is_tested_as_stored_and_every_enclosed_form_is_compared(quote: str, text: str) -> None:
    assert locate(quote, text) is None


def test_control_a_trade_mark_sign_is_still_no_part_of_what_a_quote_says() -> None:
    assert locate("Acme Widget", "The Acme" + chr(0x2122) + " Widget ships.") is not None
