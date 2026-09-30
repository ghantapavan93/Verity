"""Properties of the verifier that must hold for every text and every quote, not only the ones we
thought of. Hypothesis generates the inputs; the invariant under test is the one the product rests
on: a located span never highlights text whose letters and digits differ from the quote.
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.verify.spans import alnum_with_map, bounded, locate, strip_label
from tests.support import FUZZ_SCALE

TEXT_ALPHABET = st.characters(
    whitelist_categories=("Lu", "Ll", "Lo", "Nd", "Pc", "Pd", "Ps", "Pe", "Po", "Zs"),
    whitelist_characters="‘’“” \n",
)
texts = st.text(alphabet=TEXT_ALPHABET, min_size=1, max_size=240)
words = st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")), min_size=1, max_size=12)


def has_bounded_occurrence(text: str, needle: str) -> bool:
    at = text.find(needle)
    while at >= 0:
        if bounded(text, at, at + len(needle)):
            return True
        at = text.find(needle, at + 1)
    return False


def letters_and_digits(value: str) -> str:
    return alnum_with_map(value)[0]


@st.composite
def text_and_substring(draw: st.DrawFn) -> tuple[str, str]:
    text = draw(texts)
    start = draw(st.integers(min_value=0, max_value=len(text) - 1))
    end = draw(st.integers(min_value=start + 1, max_value=len(text)))
    return text, text[start:end]


@st.composite
def text_with_spaced_quote(draw: st.DrawFn) -> tuple[str, str]:
    """A text that contains a quote of at least two words separated by single spaces."""
    quote = " ".join(draw(st.lists(words, min_size=2, max_size=6)))
    return f"{draw(texts)} {quote} {draw(texts)}", quote


@st.composite
def text_with_numbered_quote(draw: st.DrawFn) -> tuple[str, str, int]:
    """A text that contains a quote with a number in it, and the index of one of that number's digits."""
    number = str(draw(st.integers(min_value=0, max_value=99999)))
    before = draw(st.lists(words, min_size=1, max_size=3))
    after = draw(st.lists(words, min_size=0, max_size=3))
    quote = " ".join([*before, number, *after])
    position = quote.index(number) + draw(st.integers(min_value=0, max_value=len(number) - 1))
    return f"{draw(texts)} {quote} {draw(texts)}", quote, position


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(text_and_substring())
def test_a_verbatim_substring_is_found_exactly_and_the_offsets_return_it(pair: tuple[str, str]) -> None:
    text, quote = pair
    assume(quote.strip())
    start = text.index(quote)
    assume(bounded(text, start, start + len(quote)))  # a substring cut inside a word or a number is refused on purpose
    found = locate(quote, text)
    assert found is not None
    assert 0 <= found.start < found.end <= len(text)
    assert text[found.start : found.end] == quote
    assert found.method == "exact"


@settings(max_examples=300 * FUZZ_SCALE, deadline=None)
@given(text_and_substring())
def test_whatever_is_located_is_bounded_by_non_letters_and_non_digits(pair: tuple[str, str]) -> None:
    text, quote = pair
    found = locate(quote, text)
    if found is not None:
        assert bounded(text, found.start, found.end)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(texts, texts)
def test_whatever_is_located_has_the_quote_s_letters_and_digits(text: str, quote: str) -> None:
    found = locate(quote, text)
    if found is None:
        return
    assert 0 <= found.start < found.end <= len(text)
    assert letters_and_digits(text[found.start : found.end]) == letters_and_digits(quote)
    assert found.method in {"exact", "normalized", "casefold", "typed"}


@settings(max_examples=300 * FUZZ_SCALE, deadline=None)
@given(text_with_spaced_quote(), st.sampled_from(["  ", "\n", " ", " \n "]))
def test_extra_whitespace_inside_a_quote_is_forgiven_without_moving_the_span_off_the_text(pair: tuple[str, str], filler: str) -> None:
    text, quote = pair
    loosened = quote.replace(" ", filler, 1)
    found = locate(loosened, text)
    assert found is not None
    assert letters_and_digits(text[found.start : found.end]) == letters_and_digits(loosened)


@settings(max_examples=300 * FUZZ_SCALE, deadline=None)
@given(text_with_numbered_quote(), st.integers(min_value=1, max_value=9))
def test_a_changed_digit_is_never_matched_to_the_original_digit(triple: tuple[str, str, int], offset: int) -> None:
    text, quote, position = triple
    changed = str((int(quote[position]) + offset) % 10)
    altered = quote[:position] + changed + quote[position + 1 :]
    assert locate(quote, text) is not None, "the unaltered quote is in the text by construction"
    found = locate(altered, text)
    if found is not None:
        # Only a passage that really carries the new digit may be highlighted.
        assert letters_and_digits(text[found.start : found.end]) == letters_and_digits(altered)


@settings(max_examples=200 * FUZZ_SCALE, deadline=None)
@given(st.text(alphabet=" \t\n ", max_size=8), texts)
def test_an_empty_or_blank_quote_is_never_located(blank: str, text: str) -> None:
    assert locate(blank, text) is None


@settings(max_examples=200 * FUZZ_SCALE, deadline=None)
@given(
    st.integers(min_value=1, max_value=99), st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll")), min_size=3, max_size=20), text_and_substring()
)
def test_a_section_label_copied_in_front_of_a_real_quote_is_stripped_and_the_body_located(number: int, heading: str, pair: tuple[str, str]) -> None:
    text, body = pair
    assume(body.strip() and letters_and_digits(body))
    assume(has_bounded_occurrence(text, body.strip()))  # a body cut inside a word or a number is refused on purpose
    label = f"{number} {heading}"
    quote = f"{label} {body.strip()}"
    assume(letters_and_digits(quote) not in letters_and_digits(text))
    assert strip_label(quote, label) is not None
    found = locate(quote, text, label)
    assert found is not None
    assert found.method.startswith("unprefixed:")
    assert letters_and_digits(text[found.start : found.end]) == letters_and_digits(body.strip())
