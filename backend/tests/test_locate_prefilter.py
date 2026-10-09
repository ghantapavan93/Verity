"""The prefilters in front of the ladder only skip work: they never reject what the full ladder would accept.

`_cannot_hold` (each word of the quote must stand in the text) and `_may_carry_label` (the heading must stand in the
quote) are necessary conditions. Here the filtered paths are compared with the unfiltered ones on generated pairs:
quotes cut from the text and then perturbed the ways a model's quote differs (case, curly quotes, dashes, spacing,
zero-width characters, a copied label), and unrelated quotes.
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.verify import spans
from app.verify.spans import Located, strip_label

ALPHABET = [*"abcXYZ019 .,;-'\"", "’", "“", "”", "—", " ", "​", "ß", "İ", "\n"]
text_strategy = st.text(alphabet=st.sampled_from(ALPHABET), min_size=1, max_size=120)


def perturb(quote: str, how: int) -> str:
    return [
        quote,
        quote.upper(),
        quote.replace("'", "’").replace('"', "“"),
        quote.replace(" ", "  "),
        quote.replace("-", "—"),
        "​".join(quote.split(" ")),
        f"7.2 Payment Terms {quote}",
    ][how % 7]


def unfiltered_locate(quote: str, text: str, label: str | None = None) -> Located | None:
    if not quote or not quote.strip():
        return None
    found = spans._tiers(quote, text)
    if found is None and label:
        stripped = strip_label(quote, label)
        if stripped is not None:
            found = spans._tiers(stripped, text)
            if found is not None:
                found = Located(found.start, found.end, f"unprefixed:{found.method}", found.count)
    return found


@settings(max_examples=400)
@given(text_strategy, st.integers(0, 119), st.integers(1, 60), st.integers(0, 6))
def test_a_quote_cut_from_the_text_is_located_the_same_with_and_without_the_prefilter(text: str, at: int, length: int, how: int) -> None:
    quote = perturb(text[at : at + length], how)
    assume(quote.strip())  # locate's contract: an empty quote is refused before any tier (spans.locate)
    assert spans._ladder(quote, text) == spans._tiers(quote, text), (quote, text)
    assert spans.locate(quote, text, "7.2 Payment Terms") == unfiltered_locate(quote, text, "7.2 Payment Terms"), (quote, text)


@settings(max_examples=200)
@given(text_strategy, text_strategy)
def test_an_unrelated_quote_is_refused_the_same_with_and_without_the_prefilter(quote: str, text: str) -> None:
    assume(quote.strip())
    assert spans._ladder(quote, text) == spans._tiers(quote, text)
    assert spans.locate(quote, text, "Payment") == unfiltered_locate(quote, text, "Payment")


def test_the_prefilter_skips_a_section_that_cannot_hold_the_quote() -> None:
    assert spans._cannot_hold("termination for convenience", "The fees are payable monthly.")
    assert not spans._cannot_hold("Termination for CONVENIENCE", "termination for con​venience applies")
