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
        ("approval of 23 of the Lenders", "approval of 2/3 of the Lenders"),  # the joint is part of the value
        ("a rate of 11/2% per month", "a rate of 1 1/2% per month"),
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


@pytest.mark.parametrize("quote", [".", "\u2026", " - ", "“”"])
def test_a_quote_with_no_letter_or_digit_is_never_found(quote: str) -> None:
    assert locate(quote, "The term is one year. - “Agreement” \u2026") is None


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
NNBSP = "\u202f"


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


# The headline invariant, held by two implementations: whatever the workbench locates, at whatever tier, the evidence
# pack's own checker accepts at the same offsets under the same version. Quotes are cut from the text, then put in
# capitals, stripped of punctuation or given doubled spaces, so every tier is reached.
CONTRACTISH = st.text(alphabet="0123456789,.%$()-−+±>/: aAbBeT\u0301\u200c;!\u202f", min_size=1, max_size=40)
VARIANTS = [str, str.upper, lambda q: "".join(c for c in q if c.isalnum() or c.isspace()), lambda q: q.replace(" ", "  ")]


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(text=CONTRACTISH, data=st.data())
def test_whatever_the_workbench_locates_its_pack_accepts(tmp_path_factory: pytest.TempPathFactory, text: str, data: st.DataObject) -> None:
    checker = _checker(tmp_path_factory.mktemp("located-v11"))
    start = data.draw(st.integers(0, len(text) - 1))
    end = data.draw(st.integers(start + 1, len(text)))
    quote = data.draw(st.sampled_from(VARIANTS))(text[start:end])
    # Some quotes copy the section's label in front, as models do, and reach the unprefixed tiers.
    label = data.draw(st.sampled_from(["", "4 Fees", "12.1 Term and Renewal", "Fees"]))
    if label and data.draw(st.booleans()):
        quote = f"{label} {quote}"
    found = locate(quote, text, label or None)
    if found is None:
        return
    span = text[found.start : found.end]
    assert checker.same(span, quote, found.method, 11, (text, found.start, found.end), label), (text, quote, label, found)
    assert checker.edges_hold(text, found.start, found.end, 11), (text, quote, found)


# ------------------------------------------------------------------ the fresh review of v11 (2026-10-30)
# Each was found against the v11 candidate and also held on v10: the same classes v11 closed, reached another way.
GRAVE = "\u0300"


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("ou le bailleur", f"le locataire ou{GRAVE} le bailleur"),  # "où" (where) written decomposed, quoted as "ou" (or)
        ("paye ment", f"le pay{NFD_E}ment est dû"),  # a mark inside a word does not part it in two
        ("$.50", "a fee of -$.50 per unit"),
        ("$.50", "a fee of ($.50) per unit"),
        ("par value $.01 per share", "par value ($.01) per share"),
        ("a fee of €.50 per unit", "a fee of $.50 per unit"),
        ("5%", "Margin>5% applies"),
        ("Leverage Ratio 3.50:1.00", "Leverage Ratio≤3.50:1.00"),
        ("5%", "a fee ≠5% applies"),
        ("5%", "a rate ⩾5% applies"),
        ("may terminate without cause", "The Customer may terminate.Without cause, the Supplier may suspend."),
        ("may terminate without cause", "The Customer may terminate.\u200bWithout cause, the Supplier may suspend."),
        ("may terminate without cause", "The Customer may terminate\u2026 Without cause, the Supplier may suspend."),
        ("clause (A) above", "as in clause (a) above"),
        ("Article IV(A) applies", "Article IV(a) applies"),
        ("Sections 2(a)/2(B)/2(c) apply", "Sections 2(a)/2(b)/2(c) apply"),
    ],
)
def test_the_review_s_cases_are_not_found(quote: str, text: str) -> None:
    assert locate(quote, text) is None


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("où le bailleur", f"le locataire ou{GRAVE} le bailleur"),  # composed in the quote, decomposed in the text
        ("$.50 per unit", "a fee of $.50 per unit"),
        ("Margin>5% applies", "Margin>5% applies"),
        ("i.e. the Customer", "that is, i.e. the Customer, pays"),  # an abbreviation is no sentence end
        ("clause (a) above", "as in Clause (a) above"),
        ("U.S. Dollars", "payable in U.S. Dollars only"),
    ],
)
def test_control_the_review_s_cases_as_written_are_found(quote: str, text: str) -> None:
    assert locate(quote, text) is not None


def test_a_pack_checks_an_unprefixed_span_as_the_workbench_located_it(tmp_path: Path) -> None:
    """The pack checked an unprefixed:* span by a letters-and-digits suffix alone, so it passed "-5%" for the quote
    "Fees 5%" (label "4 Fees") that the workbench refuses. From v11 it strips the label as the workbench does and
    compares the rest under the span's own tier."""
    text = "Late payment carries -5% interest."
    start = text.index("-5%")
    assert locate("Fees 5%", text, "4 Fees") is None
    refused = _pack(tmp_path / "refused", text, start, start + 3, "Fees 5%", "unprefixed:exact", "v11")
    assert not _verdict(refused)
    found = locate("Fees -5% interest", text, "4 Fees")
    assert found is not None and found.method == "unprefixed:exact", found
    kept = _pack(tmp_path / "kept", text, found.start, found.end, "Fees -5% interest", found.method, "v11")
    assert _verdict(kept), "control: a span the workbench located unprefixed passes its pack"


# ------------------------------------------------------------------ the stress test of v11 (2026-10-30)
# Seventeen adversarial finders, each finding reproduced by an independent skeptic. These are the verifier's.


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        # What a reader does not see is not read: every default-ignorable code point, not four of them.
        ("upon 9", "Provider may terminate upon 9\u061c0 days' notice."),
        ("$1", "a fee of $1\u061c,500 per year"),
        ("$1\u200d", "a fee of $1\u200d,500 per year"),
        ("1.5\u200d", "a rate of 1.5\u200d% per month"),
        # A typeset joint is a joint: fraction slashes, ratio colons, middle dots, fullwidth marks.
        ("2% per month", "Overdue amounts bear interest at 1\u20442% per month."),
        ("2% per month", "Overdue amounts bear interest at 1\u22152% per month."),
        ("2% per month", "Overdue amounts bear interest at 1\uff0f2% per month."),
        ("1 debt to equity", "a ratio of 3\u22361 debt to equity"),
        ("1 debt to equity", "a ratio of 3\uff1a1 debt to equity"),
        ("5% per month", "interest of 1\u00b75% per month"),
        ("5% per month", "interest of 1\uff0e5% per month"),
        ("500 per month", "a fee of $1\uff0c500 per month"),
        # A whole number and its fraction are one number: the US late-fee idiom.
        ("1/2% per month", "interest at the rate of 1 1/2% per month."),
        ("1/2%) per month", "one and one-half percent (1 1/2%) per month."),
        ("-1/2%) per month", "one and one-half percent (1-1/2%) per month."),
        ("\u00bd times the fees paid", "liability is capped at 2 \u00bd times the fees paid."),
        # A unit sign written against a number belongs to it.
        ("interest of 5 per month", "Overdue sums bear interest of 5\u2030 per month."),
        ("interest of 5 per month", "Overdue sums bear interest of 5\uff05 per month."),
        ("interest of 5 per month", "Overdue sums bear interest of 5\u066a per month."),
        ("rated at least A-1", "notes rated at least A-1+ by S&P"),
        ("at least 5 years", "at least 5+ years of experience"),
        # A casefold match never starts or ends inside one character's fold ("\ufb00" folds to "ff").
        ("Customer may not set of", "Customer may not set o\ufb00 any amount."),
        ("IVE DAY CURE PERIOD APPLIES", "A \ufb01ve day cure period applies."),
        ("paid in full DAS", "the sum is paid in full da\u00df it is due"),
    ],
)
def test_the_stress_test_s_cases_are_not_found(quote: str, text: str) -> None:
    assert locate(quote, text) is None


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("upon 90 days", "Provider may terminate upon 9\u061c0 days' notice."),  # the mark is invisible, so forgiven
        ("1 1/2% per month", "interest at the rate of 1 1/2% per month."),
        ("2 \u00bd times the fees paid", "liability is capped at 2 \u00bd times the fees paid."),
        ("interest of 5\u2030 per month", "Overdue sums bear interest of 5\u2030 per month."),
        ("USD 500 per month", "a fee of USD 500 per month"),
        ("500 per month", "a fee of USD 500 per month"),  # a currency's code may still be left out, as since v9
        ("SET OFF ANY AMOUNT", "Customer may not set o\ufb00 any amount."),
        ("five day cure period", "A \ufb01ve day cure period applies."),
        ("PAID IN FULL DASS", "the sum is paid in full da\u00df it is due"),
    ],
)
def test_control_the_stress_test_s_cases_as_written_are_found(quote: str, text: str) -> None:
    assert locate(quote, text) is not None


def test_a_window_cut_is_never_a_boundary() -> None:
    """The model is shown the first 6,000 characters of a section, and the search was made in that cut-out, whose end
    was read as the text's end: "a licence fee of $1,500" verified exact where the section says "$1,500,000"."""
    text = "x" * 5977 + " a licence fee of $1,500,000 per year."
    cut = text.index(",000 per")
    assert locate("a licence fee of $1,500", text, window=cut) is None
    assert locate("a licence fee of $1,500", text[:cut]) is not None, "control: the old reading of the cut-out"
    assert locate("a licence fee of", text, window=cut) is not None  # control: a quote that ends before the cut


@pytest.mark.parametrize(
    ("quote", "text", "label"),
    [
        (
            "Supplier's liability under this Agreement is unlimited.",
            "Except as stated, the Customer's liability under this Agreement is unlimited.",
            "8 Supplier",
        ),
        ("Schedule 1,500 units per month", "The Customer may order up to 500 units per month.", "Schedule 1"),
        ("Annex 10% discount", "Customers get a 0% discount.", "Annex 1"),
    ],
)
def test_a_label_is_stripped_only_whole(quote: str, text: str, label: str) -> None:
    """strip_label ended the heading inside a word or a number of the quote, and the rest verified at another party's
    text: "Supplier's liability" under the label "8 Supplier" became "'s liability", found in "the Customer's liability"."""
    assert locate(quote, text, label) is None


def test_control_a_label_copied_whole_is_still_stripped() -> None:
    found = locate("4 Fees: The Customer pays the Fees monthly.", "The Customer pays the Fees monthly.", "4 Fees")
    assert found is not None and found.method == "unprefixed:exact", found


def test_a_pack_reads_its_files_as_bytes(tmp_path: Path) -> None:
    """verify.py read the model input in text mode, so a carriage return in a question or the guidance made a genuine
    pack fail its input hash. It now decodes every file it reads from bytes, and its hash is of exactly those bytes."""
    checker = _checker(tmp_path)
    target = tmp_path / "user.txt"
    target.write_bytes(b"line one\r\nline two\rthree")
    assert checker.text_of(target) == "line one\r\nline two\rthree"


@pytest.mark.parametrize(("recorded", "passes"), [("99.0.0", False), (None, True)])
def test_a_pack_refuses_to_judge_what_its_unicode_cannot_read(tmp_path: Path, recorded: str | None, passes: bool) -> None:
    """verify.py's verdict hung on the checker's Unicode database: a character assigned after it read as unassigned and
    a genuine span failed, unexplained (stress test, 2026-10-30). The pack now records its Unicode version, and a span
    holding a character the checker does not know is failed by name when the versions differ."""
    import json
    import unicodedata

    unknown = chr(0x0378)  # unassigned in every Unicode so far: what a newer character looks like to an older database
    text = f"The Lessor is {unknown} Holdings Limited."
    quote = f"{unknown} Holdings Limited"
    start = text.index(quote)
    folder = _pack(tmp_path / "pack", text, start, start + len(quote), quote, "exact", "v11")
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    run["verifier"]["unicode"] = recorded or unicodedata.unidata_version
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    assert _verdict(folder) is passes


@pytest.mark.parametrize("sign", sorted(tokens._CURRENCY_SYMBOLS))
def test_every_currency_sign_belongs_to_its_number(sign: str) -> None:
    """The rule that a currency sign belongs to its number was pinned for four of the signs the verifier knows; with it
    narrowed, "500 per seat" verified inside a rupee amount (mutation run of the stress test, 2026-10-30)."""
    text = f"The fee is {sign}500 per seat per year."
    assert locate("500 per seat", text) is None
    assert locate(f"{sign}500 per seat", text) is not None  # control: the amount with its sign
