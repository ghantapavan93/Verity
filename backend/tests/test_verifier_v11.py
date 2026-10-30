"""Verifier v11: four ways a quote was found that the text does not say (break audit, 2026-10-30).

The invariant is the verifier's own: it never says "found" when the text is not there. Each case below was reproduced
against v10, and the first ones through the API: a late fee of ".5%" quoted as "5%" ended as a pass.

1. A number may open with more than a minus sign or a parenthesis: a leading decimal point (".5%" is not "5%"), a
   comparator or a plus-minus (">$1,000,000", "≥99.9%", "±5%", "+/-5%"), and digits joined by "/" or ":" are one
   number ("2/3" is not "2-3").
2. The typed tier forgives punctuation, and so it joined two sentences: "The Customer may terminate. Without cause,
   the Supplier may suspend" held the quote "The Customer may terminate without cause". A sentence break inside the
   matched text must be in the quote too.
3. A combining mark or a joiner is part of the word it is written in: in decomposed "payé" (e + U+0301) the quote
   "paye" stopped before the accent, and in Persian "غیر\u200cقابل" ("non-") the quote "قابل" stopped at the joiner.
4. A quote with no letter or digit in it ("." from an empty answer) is never found.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.verify import tokens
from app.verify.spans import _INVISIBLE as INVISIBLE
from app.verify.spans import VERIFIER_VERSION, bounded, locate
from tests.support import FUZZ_SCALE
from tests.test_pack_parity import _checker, _pack, _verdict

NFD_E = "e\u0301"
ZWNJ = "\u200c"


def test_this_is_verifier_v11() -> None:
    assert VERIFIER_VERSION == "v11"


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("5%", "a late fee of .5% per month"),
        ("a late fee of 5% per month", "a late fee of .5% per month"),
        ("a tolerance of 5%", "a tolerance of ±5%"),
        ("an adjustment of -5%", "an adjustment of +/-5%"),
        ("fees of $1,000,000", "fees of >$1,000,000"),
        ("uptime of 99.9%", "uptime of ≥99.9%"),
        ("approval of 2-3 of the Lenders", "approval of 2/3 of the Lenders"),
        ("a ratio of 3 1", "a ratio of 3:1"),
    ],
)
def test_a_number_is_read_with_what_it_opens_with_and_what_joins_its_digits(quote: str, text: str) -> None:
    assert locate(quote, text) is None


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        (".5%", "a late fee of .5% per month"),
        ("0.5%", "a late fee of 0.5% per month"),
        ("±5%", "a tolerance of ±5%"),
        ("≥99.9%", "uptime of ≥99.9% each month"),
        ("2/3 of the Lenders", "approval of 2/3 of the Lenders"),
        ("Customer pays within 30 days", "Customer pays within 30 days of the invoice."),
    ],
)
def test_control_a_number_quoted_as_written_is_found(quote: str, text: str) -> None:
    assert locate(quote, text) is not None


def test_two_sentences_are_not_one_quote() -> None:
    text = "The Customer may terminate. Without cause, the Supplier may suspend the Services."
    assert locate("The Customer may terminate without cause", text) is None


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("The Customer may terminate", "The Customer may terminate. Without cause, the Supplier may suspend the Services."),
        ("Acme Inc shall pay the Fees", "Acme Inc. shall pay the Fees."),  # an abbreviation's full stop is no sentence end
        ("the Agreement may be renewed", "the “Agreement” may be renewed"),  # punctuation still carries nothing
    ],
)
def test_control_punctuation_inside_one_sentence_is_still_forgiven(quote: str, text: str) -> None:
    assert locate(quote, text) is not None


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("paye", f"Customer will pay{NFD_E} the fee."),
        ("قابل استرداد", f"این مبلغ غیر{ZWNJ}قابل استرداد است"),
    ],
)
def test_a_mark_or_a_joiner_belongs_to_its_word(quote: str, text: str) -> None:
    assert locate(quote, text) is None


def test_control_a_composed_accented_word_is_found() -> None:
    assert locate("payé", "Customer will payé the fee.") is not None


@pytest.mark.parametrize("quote", [".", "…", " - ", "“”"])
def test_a_quote_with_no_letter_or_digit_is_never_found(quote: str) -> None:
    assert locate(quote, "The term is one year. - “Agreement” …") is None


# ------------------------------------------------------------------------------------------------- as properties
OPENERS = ["", "-", "+", "±", "+/-", ">", ">=", "<", "≥", "≤", "~", "."]
BODIES = ["5%", "250", "1,500", "2.5", "99.9%", "$1,000,000", "USD 10"]


def _written(opener: str, body: str) -> str:
    return opener + body


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(body=st.sampled_from(BODIES), quote_opener=st.sampled_from(OPENERS), text_opener=st.sampled_from(OPENERS))
def test_a_number_is_found_exactly_when_what_it_opens_with_agrees(body: str, quote_opener: str, text_opener: str) -> None:
    assume(body[0].isdigit() or "." not in (quote_opener, text_opener))  # a decimal point opens digits, not "$"
    quote = f"a fee of {quote_opener}{body}"
    text = f"The parties agree a fee of {text_opener}{body} applies."
    found = locate(quote, text)
    assert (found is not None) == (quote_opener == text_opener), (quote, text, found)


FIRST = ["the", "customer", "may", "terminate", "pay"]
SECOND = ["without", "cause", "notice", "fees", "thereafter"]


@settings(max_examples=300 * FUZZ_SCALE, deadline=None)
@given(
    first=st.lists(st.sampled_from(FIRST), min_size=1, max_size=4),
    second=st.lists(st.sampled_from(SECOND), min_size=1, max_size=4),
    mark=st.sampled_from([".", "!", "?", ";"]),
)
def test_a_quote_never_runs_one_sentence_into_the_next(first: list[str], second: list[str], mark: str) -> None:
    opening = " ".join(second)
    text = f"Recitals aside, {' '.join(first)}{mark} {opening.capitalize()} applies."
    assert locate(" ".join(first + second), text) is None, text
    assert locate(f"{' '.join(first)}{mark} {opening.capitalize()}", text) is not None, text  # control: as written


# ------------------------------------------------------------------------------------------------- the pack agrees
V11_TEXT = st.text(alphabet="0123456789,.%$()-−+±<>≥/: aAeT\u0301\u200c;!", min_size=1, max_size=24)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(text=V11_TEXT, data=st.data())
def test_the_pack_reads_every_edge_as_the_workbench_does_under_v11(tmp_path_factory: pytest.TempPathFactory, text: str, data: st.DataObject) -> None:
    checker = _checker(tmp_path_factory.mktemp("edges-v11"))
    start = data.draw(st.integers(0, len(text)))
    end = data.draw(st.integers(start, len(text)))
    assert checker.edges_hold(text, start, end, 11) == bounded(text, start, end), (text, start, end)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(a=V11_TEXT, b=V11_TEXT)
def test_the_pack_compares_typed_tokens_as_the_workbench_does_under_v11(tmp_path_factory: pytest.TempPathFactory, a: str, b: str) -> None:
    checker = _checker(tmp_path_factory.mktemp("typed-v11"))

    def runtime(text: str) -> list[tuple[str, str]]:
        return [(str(t.kind), t.canonical) for t in tokens.compared(text, 11, INVISIBLE)]

    expected = any(ch.isalnum() for ch in b) and bool(runtime(a)) and runtime(a) == runtime(b)
    assert checker.same(a, b, "typed", 11) == expected, (a, b)


CASES_FOR_PACKS = [
    # (text, span the run recorded, quote, method)
    ("A late fee of .5% per month applies.", "5%", "5%", "exact"),
    ("Approval of 2/3 of the Lenders is needed.", "2/3 of the Lenders", "2-3 of the Lenders", "typed"),
    ("The Customer may terminate. Without cause, the Supplier may suspend.", "may terminate. Without cause", "may terminate without cause", "typed"),
    ("The term is one year.", ".", ".", "exact"),
    ("Section 2(a) applies.", "Section 2(a) applies", "section 2(A) applies", "casefold"),
    ("Section 2(a) applies.", "Section 2(a) applies", "Section 2(A), applies", "typed"),
]


@pytest.mark.parametrize(("text", "found", "quote", "method"), CASES_FOR_PACKS)
def test_a_v11_pack_refuses_what_v11_refuses_and_a_v10_pack_keeps_v10_s_verdict(tmp_path: Path, text: str, found: str, quote: str, method: str) -> None:
    assert locate(quote, text) is None
    start = text.index(found)
    assert not _verdict(_pack(tmp_path / "v11", text, start, start + len(found), quote, method, "v11"))
    assert _verdict(_pack(tmp_path / "v10", text, start, start + len(found), quote, method, "v10")), "a v10 run's pack reads as v10 did"


def test_control_a_v11_pack_passes_what_v11_finds(tmp_path: Path) -> None:
    text = "A late fee of .5% per month applies; approval of 2/3 of the Lenders is needed."
    for quote in (".5% per month", "approval of 2/3 of the Lenders", "applies; approval"):
        located = locate(quote, text)
        assert located is not None, quote
        folder = tmp_path / str(located.start)
        assert _verdict(_pack(folder, text, located.start, located.end, quote, located.method, "v11")), quote


# ------------------------------------------------------- a clause's letter, and a later place the first one hides
# Found by the same audit, after the four above. Contracts number sub-clauses (a) and (A) at different levels, and the
# casefold and typed tiers found "Section 2(A)" at "Section 2(a)": another clause. And the typed tier tried only the
# first place its tokens occur, so a quote whose first place lay inside a number ("1 500" with a narrow space) was
# withheld though the text says it, word for word, further on (a false negative, the safe way round).
NNBSP = " "


@pytest.mark.parametrize(
    "quote",
    ["Section 2(A) applies", "section 2(A) applies", "Section 2(A), applies"],
)
def test_a_clause_s_letter_keeps_its_case(quote: str) -> None:
    assert locate(quote, "Section 2(a) applies. Section 2(A)(i) differs.") is None


@pytest.mark.parametrize(
    ("quote", "method"),
    [("SECTION 2(a) APPLIES", "casefold"), ("Section 2(a), applies", "typed"), ("section 12.4(b) applies", "casefold")],
)
def test_control_a_clause_quoted_with_its_own_letter_is_found(quote: str, method: str) -> None:
    found = locate(quote, "Section 2(a) applies. Section 12.4(b) applies.")
    assert found is not None and found.method == method, found


def test_a_later_place_is_found_when_the_first_lies_inside_a_number() -> None:
    text = f"1{NNBSP}500 shares; later, 500 shares"
    found = locate("500, shares", text)
    assert found is not None and found.method == "typed" and text[found.start : found.end] == "500 shares", found
    assert found.start == text.rindex("500") and found.count == 1
