"""Verifier v8: no located span begins or ends inside a number, and no sign is dropped (war room F-03, R3, 2026-10-13).

Until v8 an edge on a comma or a point between two digits was an edge, and the exact tier runs first, so "$1,500" was
found word for word in "$1,500,000", "$15" in "$15.50", "within 30" in "within 30.5" and "Section 5" in "Section 5.2";
the memo printed "$1,500" under "every quoted passage was found in the document text". The typed tier dropped a minus
sign and the parentheses of an accounting negative, so "an adjustment of 5%" verified against "-5%" and "a credit of
$500" against "($500)".

The invariant: a located span never begins or ends inside a number, and a number's sign is part of its value at every
tier. A number is its digits, the marks that join them (a decimal point or a thousands separator, in any form it is
typeset), and what is written against it: its sign, its currency or percent sign, a section label's parts, and the
parentheses around it. A character normalisation deletes (a zero-width space) makes no edge; a space is still one.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.verify.spans import locate
from app.verify.tokens import significant, tokenize
from tests.support import FUZZ_SCALE

# (quote, text, label). Each was found under v7, at the tier its id names; each is withheld from v8.
NUMBER_CUT = [
    pytest.param("$1,500", "The fee is $1,500,000 per year.", None, id="exact-thousands-right-edge-AI01"),
    pytest.param("an annual fee of $1,500", "Customer shall pay an annual fee of $1,500,000, payable in advance.", None, id="exact-AI01-memo"),
    pytest.param("a fee of $15", "Customer shall pay a fee of $15.50 per user per month.", None, id="exact-decimal"),
    pytest.param("capped at $1", "Liability is capped at $1,000,000 in aggregate.", None, id="exact-currency-thousands"),
    pytest.param("within 30", "Invoices are payable within 30.5 days.", None, id="exact-decimal-days"),
    pytest.param("as set out in Section 5", "as set out in Section 5.2 below", None, id="exact-section-number"),
    pytest.param("under Section 12", "under Section 12.3(a) of this Agreement", None, id="exact-section-before-subsection"),
    pytest.param("under Section 12.3", "under Section 12.3(a) of this Agreement", None, id="exact-section-label"),
    pytest.param("500,000 per year", "The fee is $1,500,000 per year.", None, id="exact-thousands-left-edge"),
    pytest.param("5 days", "Invoices are payable within 30.5 days.", None, id="exact-decimal-left-edge"),
    pytest.param("a discount of 10", "a discount of 10% applies", None, id="exact-percent-sign"),
    pytest.param("10.5", "a discount of 10.5% applies", None, id="exact-percent-sign-after-decimal"),
    pytest.param("500 per year", "a fee of $500 per year", None, id="exact-currency-sign"),
    pytest.param("5% each year", "Prices are subject to an adjustment of -5% each year.", None, id="exact-minus-sign"),
    pytest.param("$500", "The invoice shows a credit of ($500) to Customer.", None, id="exact-accounting-parentheses"),
    pytest.param("a fee of  $1,500", "a fee of $1,500,000 per year", None, id="normalized-thousands"),
    pytest.param("a “fee” of $15", 'a "fee" of $15.50 per user', None, id="normalized-decimal"),
    pytest.param("A FEE OF $1,500", "a fee of $1,500,000 per year", None, id="casefold-thousands"),
    pytest.param("AS SET OUT IN SECTION 5", "as set out in Section 5.2 below", None, id="casefold-section-number"),
    pytest.param("an adjustment of 5%", "Prices are subject to an adjustment of -5% each year.", None, id="typed-minus-dropped"),
    pytest.param("an adjustment of 5%", "Prices are subject to an adjustment of \u22125% each year.", None, id="typed-typeset-minus-dropped"),
    pytest.param("a credit of $500", "The invoice shows a credit of ($500) to Customer.", None, id="typed-accounting-dropped"),
    pytest.param("a credit of 1 500", "The invoice shows a credit of (1\u202f500) to Customer.", None, id="typed-accounting-around-typeset-grouping"),
    pytest.param("a fee of: EUR 1", "a fee of EUR 1\u202f500 per year", None, id="typed-narrow-space-grouping"),
    pytest.param("$1,500", "The fee is $1,500\u200b,000 per year.", None, id="exact-zero-width-space-inside-the-number"),
    pytest.param("€1", "a fee of €1\u00a0500 per year", None, id="exact-no-break-space-grouping"),
    pytest.param("CHF 1’500", "a fee of CHF 1’500’000 per year", None, id="exact-apostrophe-grouping"),
    pytest.param("4 Fees a fee of $1,500", "a fee of $1,500,000 per year", "4 Fees", id="unprefixed-exact-thousands"),
    pytest.param("4 Fees: an adjustment of 5%", "Prices: an adjustment of -5% each year.", "4 Fees", id="unprefixed-typed-minus-dropped"),
]


@pytest.mark.parametrize(("quote", "text", "label"), NUMBER_CUT)
def test_a_quote_cut_inside_a_number_or_off_its_sign_is_withheld_at_every_tier(quote: str, text: str, label: str | None) -> None:
    assert locate(quote, text, label) is None


def test_a_sign_the_text_does_not_have_is_not_found_either() -> None:
    assert locate("an adjustment of -5%", "Prices are subject to an adjustment of 5% each year.") is None
    assert locate("a credit of ($500)", "The invoice shows a credit of $500 to Customer.") is None


# (quote, text, method, the characters highlighted). None of these moves under v8.
UNCHANGED = [
    pytest.param("The fee is $1,500.", "The fee is $1,500. Payment is due on receipt.", "exact", "The fee is $1,500.", id="number-then-sentence-end"),
    pytest.param("The fee is $1,500", "The fee is $1,500. Payment is due on receipt.", "exact", "The fee is $1,500", id="number-before-sentence-end"),
    pytest.param("within 30", "payable within 30, and in any case", "exact", "within 30", id="number-comma-space"),
    pytest.param("within 30 days", "within 30, 60 or 90 days, or within 30 days, as", "exact", "within 30 days", id="number-comma-space-list"),
    pytest.param("thirty (30) days' notice", "upon thirty (30) days’ notice", "normalized", "thirty (30) days’ notice", id="typographic-quotes"),
    pytest.param("“GDPR” means", '"GDPR" means the Regulation', "normalized", '"GDPR" means', id="typographic-double-quotes"),
    pytest.param("(15) days", "Customer may cure within fifteen (15) days of notice.", "exact", "(15) days", id="parentheses-kept"),
    pytest.param("a credit of ($500)", "The invoice shows a credit of ($500) to Customer.", "exact", "a credit of ($500)", id="accounting-kept"),
    pytest.param("an adjustment of -5%", "an adjustment of \u22125% each year", "normalized", "an adjustment of \u22125%", id="typeset-minus-kept"),
    pytest.param("6 business days", "within 4-6 business days", "exact", "6 business days", id="a-range-dash-is-not-a-sign"),
    pytest.param("19 pandemic", "during the COVID-19 pandemic", "exact", "19 pandemic", id="a-hyphen-in-a-word-is-not-a-sign"),
    pytest.param("15 days", "within 1\u200b5 days", "normalized", "1\u200b5 days", id="zero-width-space-in-the-source"),
    pytest.param("Sections 4-6", "Sections\u00a04\u20136", "normalized", "Sections\u00a04\u20136", id="no-break-space-and-en-dash"),
    pytest.param("500 per year", "a fee of USD 500 per year", "exact", "500 per year", id="a-space-is-still-an-edge"),
    pytest.param("or (c) if neither (", "or (c) if neither (a) nor (b) are available", "exact", "or (c) if neither (", id="parenthesis-before-a-letter"),
    pytest.param("fee of $1500 per user", "The fee of “$1,500” per user is payable.", "typed", "fee of “$1,500” per user", id="typed-thousands-spelling"),
    pytest.param("less than 30 days", "Notice of not less than 30 days is required.", "exact", "less than 30 days", id="dropped-neighbouring-word"),
]


@pytest.mark.parametrize(("quote", "text", "method", "shown"), UNCHANGED)
def test_controls_a_whole_number_is_still_found_as_before(quote: str, text: str, method: str, shown: str) -> None:
    found = locate(quote, text)
    assert found is not None and found.method == method
    assert text[found.start : found.end] == shown


@pytest.mark.parametrize(
    ("quote", "text", "shown"),
    [
        pytest.param("4 Fees: -5% each year", "Prices change by -5% each year.", "-5% each year", id="minus"),
        pytest.param("4 Fees $500 per year", "a fee of $500 per year", "$500 per year", id="currency"),
        pytest.param("4 Fees (30) days", "within thirty (30) days", "(30) days", id="parentheses"),
    ],
)
def test_a_copied_label_is_stripped_without_the_sign_of_the_number_after_it(quote: str, text: str, shown: str) -> None:
    """Found by the label property under v8: the label was cut at the body's first letter or digit, so "Fees: -5%" left
    "5%", which v7 highlighted without its sign and v8 would refuse. The body keeps what is written against its number."""
    found = locate(quote, text, "4 Fees")
    assert found is not None and found.method == "unprefixed:exact"
    assert text[found.start : found.end] == shown


def test_controls_a_longer_number_on_the_left_was_and_is_refused() -> None:
    assert locate("$1,500", "The fee is $11,500 per year.") is None


def test_the_tokens_values_are_read_from_are_unchanged() -> None:
    """runs.values (policy) and trust.facts read values from `tokenize`; v8 joins signs only where the verifier compares
    (tokens.signed), so what those modules read does not move and the policy version stays."""
    text = "a credit of ($500), an adjustment of -5% and (30) days"
    assert [(t.kind.value, t.canonical) for t in significant(tokenize(text))] == [
        ("word", "a"),
        ("word", "credit"),
        ("word", "of"),
        ("currency", "$500"),
        ("word", "an"),
        ("word", "adjustment"),
        ("word", "of"),
        ("percent", "5%"),
        ("word", "and"),
        ("number", "30"),
        ("word", "days"),
    ]


# ---- properties over generated numbers ---------------------------------------------------------------------------

DIGITS = "0123456789"
GROUP_MARKS = [",", ".", "\u00a0", "\u202f", "\u2009", "'", "’", "\u066c"]  # comma, point, no-break, narrow, thin, apostrophes, Arabic
DECIMAL_MARKS = [".", ",", "\u066b"]
CURRENCY_SIGNS = ["$", "€", "£", "¥"]
# Every dash a typesetter writes for minus: hyphen-minus, hyphens, figure, en and em dash, minus, small and full width.
MINUS = "-\u2010\u2011\u2012\u2013\u2014\u2212\ufe63\uff0d"
ZERO_WIDTH = chr(0x200B)
words = st.text(alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABC"), min_size=1, max_size=8)


@st.composite
def written_number(draw: st.DrawFn, signed: bool | None = None) -> str:
    """A number as a contract writes it, without a space inside: a section identifier ("12.3(a)(ii)"), or an amount with
    thousands groups and decimals in any typeset form, a currency or percent sign, a minus sign, and parentheses."""
    if signed is None and draw(st.integers(0, 3)) == 0:
        parts = draw(st.lists(st.integers(0, 40), min_size=1, max_size=3))
        labels = draw(st.lists(st.sampled_from(["a", "b", "ii", "iv", "1"]), max_size=2))
        number = ".".join(map(str, parts)) + "".join(f"({label})" for label in labels)
        return f"({number})" if draw(st.booleans()) else number
    groups = [draw(st.text(DIGITS, min_size=1, max_size=3)), *draw(st.lists(st.text(DIGITS, min_size=3, max_size=3), max_size=3))]
    number = draw(st.sampled_from(GROUP_MARKS)).join(groups)
    if draw(st.booleans()):
        number += draw(st.sampled_from(DECIMAL_MARKS)) + draw(st.text(DIGITS, min_size=1, max_size=2))
    unit = draw(st.sampled_from(["", "%", "currency"]))
    if unit == "%":
        number += "%"
    elif unit == "currency":
        number = draw(st.sampled_from(CURRENCY_SIGNS)) + number
    minus, parentheses = draw(st.booleans()), draw(st.booleans())
    if signed and not (minus or parentheses):
        minus = True
    if signed is not None and not signed:
        minus = parentheses = False
    number = (draw(st.sampled_from(MINUS)) if minus else "") + number
    return f"({number})" if parentheses else number


@st.composite
def text_with_numbers(draw: st.DrawFn) -> tuple[str, list[tuple[int, int]]]:
    """Words and numbers, each number followed by nothing or by sentence punctuation, with where each number lies."""
    text, extents = draw(words), []
    for _ in range(draw(st.integers(1, 3))):
        number = draw(written_number())
        if len(number) > 1 and draw(st.integers(0, 4)) == 0:  # a zero-width space typed inside it makes no edge
            at = draw(st.integers(1, len(number) - 1))
            number = number[:at] + ZERO_WIDTH + number[at:]
        text += " "
        extents.append((len(text), len(text) + len(number)))
        text += number + draw(st.sampled_from(["", ".", ",", ";", ":"])) + " " + draw(words)
    return text, extents


def perturbed(quote: str, how: int) -> tuple[str, str | None]:
    """The quote as a model may differ from the text, so that every tier is reached, and the label it may carry."""
    return [
        (quote, None),
        (quote.replace(" ", "  "), None),  # normalized
        (quote.upper(), None),  # casefold
        ("".join("-" if ch in MINUS else ch for ch in quote), None),  # normalized: a typeset minus written plainly
        (quote.replace(" ", ' " '), None),  # typed: quotation marks carry nothing
        (f"4.1 Fees {quote}", "4.1 Fees"),  # unprefixed
    ][how]


@settings(max_examples=600 * FUZZ_SCALE, deadline=None)
@given(text_with_numbers(), st.data(), st.integers(0, 5))
def test_a_located_span_never_begins_or_ends_inside_a_number(case: tuple[str, list[tuple[int, int]]], data: st.DataObject, how: int) -> None:
    text, extents = case
    start = data.draw(st.integers(0, len(text) - 1))
    end = data.draw(st.integers(start + 1, len(text)))
    quote, label = perturbed(text[start:end], how)
    assume(quote.strip())
    found = locate(quote, text, label)
    if found is None:
        return
    for low, high in extents:
        assert not low < found.start < high, (found, text[found.start : found.end], text[low:high])
        assert not low < found.end < high, (found, text[found.start : found.end], text[low:high])


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(written_number(signed=True), words, words, st.integers(0, 4))
def test_a_number_s_sign_is_never_dropped_or_added(number: str, before: str, after: str, how: int) -> None:
    bare = number.removeprefix("(").removesuffix(")") if number.startswith("(") and number.endswith(")") else number
    bare = bare[1:] if bare[:1] and bare[0] in MINUS else bare
    assume(bare != number)
    with_sign, without = f"{before} {number} {after}", f"{before} {bare} {after}"
    assert locate(perturbed(without, how)[0], with_sign) is None, "a sign the quote drops"
    assert locate(perturbed(with_sign, how)[0], without) is None, "a sign the quote adds"
    found = locate(perturbed(with_sign, how)[0], with_sign)
    assert found is not None and with_sign[found.start : found.end] == with_sign, "control: the signed quote is found"


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(text_with_numbers(), st.data())
def test_a_quote_that_keeps_every_number_whole_is_found_word_for_word(case: tuple[str, list[tuple[int, int]]], data: st.DataObject) -> None:
    text, _ = case
    starts = [0, *(i + 1 for i, ch in enumerate(text) if ch == " ")]
    start = data.draw(st.sampled_from(starts))
    ends = [i for i, ch in enumerate(text) if ch == " " and i > start] + [len(text)]
    end = data.draw(st.sampled_from(ends))
    found = locate(text[start:end], text)
    assert found is not None and found.method == "exact"
    assert text[found.start : found.end] == text[start:end]
