"""Verifier v14: a clause's letter is read as a reader sees it (release review of b5dffaf, 2026-11-02).

Since v11 case is forgiven everywhere but in a clause's letter: "(A)" and "(a)" name two clauses. The casefold tier and
the typed tier both asked whether a letter alone in parentheses stood in the quote, on the characters as they are
stored, so an invisible character inside the parentheses ("4(C" + U+200E + ")"), or a letter written with a combining
mark ("(a" + U+0301 + ")"), was no clause letter to them, and its case was forgiven: "x 4(C\u200e) y" was found in
"x 4(c\u200e) y". From v14 both tiers, and the evidence pack, read clause letters with the characters normalisation
deletes left out and the marks composed (`tokens.clause_letters`). A v13 run is still read as v13 read it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.verify.spans import _INVISIBLE as INVISIBLE
from app.verify.spans import VERIFIER_VERSION, locate
from app.verify.tokens import clause_letters, locate_tokens
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


@pytest.mark.parametrize(("quote", "text"), HIDDEN)
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
