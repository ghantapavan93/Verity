"""Typed tokens: the representation under which a quote and its source are compared once exact text has failed.

The letters-and-digits tier compared two texts by their letters and digits alone, which made "$1,500" and
"$15.00" the same six characters and "15%" the same as "1.5%". Under typed tokens a number is a number:
"1,500" and "1500" are one value (Decimal, never float), "15.00" and "1,500" are two, "15%" and "1.5%" are
two, and a run of letters is a word, compared whole. Punctuation, quotation marks, dashes and whitespace carry
no meaning and are dropped, so "days’ written" still meets "days written" and "non- exclusive" still meets
"non-exclusive", while a changed digit or a moved decimal point can never be forgiven, and neither can a space
moved inside the letters: "the rapist" is not "therapist" (verifier v6).

Every token keeps the offsets of its surface in the original text, so a match is reported as exact
character offsets and the interface highlights what was found.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class Kind(StrEnum):
    WORD = "word"
    NUMBER = "number"
    CURRENCY = "currency"
    PERCENT = "percent"
    SECTION = "section"  # "8.1.2", "12.4(a)": an identifier made of numbers, never a quantity
    PUNCT = "punct"


@dataclass(frozen=True)
class Token:
    kind: Kind
    canonical: str
    start: int
    end: int

    @property
    def significant(self) -> bool:
        return self.kind is not Kind.PUNCT


_CURRENCY = r"[$€£¥]|USD|EUR|GBP|CHF|CAD|AUD"
_TOKEN = re.compile(
    rf"""
    (?<![^\W_])                                                                           # no token starts inside a run of letters and digits
    (?:(?P<section>\d+(?:\.\d+){{2,}}(?:\([a-z0-9]+\))*|\d+(?:\.\d+)?(?:\([a-z0-9]+\))+)   # 8.1.2, 12.4(a), 3(b)
    |(?P<currency>(?:{_CURRENCY})\s?\d[\d,]*(?:\.\d+)?)                                 # $1,500  USD 10.00
    |(?P<percent>\d[\d,]*(?:\.\d+)?\s?(?:%|percent\b|per\s+cent\b))                     # 15%  1.5 percent
    |(?P<number>\d[\d,]*(?:\.\d+)?(?![^\W\d_]))                                        # 30  1,500  15.00; not "0A"
    |(?P<word>[^\W_]+)                                                                  # letters, any script; "A1" is one word
    |(?P<punct>[^\w\s]|_))
    """,
    re.IGNORECASE | re.VERBOSE,
)


def canonical_number(text: str) -> str:
    """ "1,500" → "1500": thousands separators and spaces carry nothing. The digits themselves are kept as written,
    so "15.00" is not "15" and "1.50" is not "1.5": a verifier forgives spelling, never precision."""
    cleaned = text.replace(",", "").replace(" ", "")
    try:
        Decimal(cleaned)
    except InvalidOperation:
        return text
    return cleaned


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    for match in _TOKEN.finditer(text):
        kind = Kind(match.lastgroup or "punct")
        surface = match.group(0)
        if kind is Kind.WORD:
            canonical = surface.casefold()
        elif kind is Kind.NUMBER:
            canonical = canonical_number(surface)
        elif kind is Kind.CURRENCY:
            symbol = re.match(rf"(?:{_CURRENCY})", surface, re.IGNORECASE)
            assert symbol is not None
            canonical = symbol.group(0).upper() + canonical_number(surface[symbol.end() :])
        elif kind is Kind.PERCENT:
            digits = re.match(r"[\d,]*(?:\.\d+)?", surface)
            assert digits is not None
            canonical = canonical_number(digits.group(0)) + "%"
        elif kind is Kind.SECTION:
            canonical = surface.lower()
        else:
            canonical = surface
        tokens.append(Token(kind, canonical, match.start(), match.end()))
    return tokens


def significant(tokens: list[Token]) -> list[Token]:
    return [t for t in tokens if t.significant]


@dataclass(frozen=True)
class TokenMatch:
    start: int  # offsets into the original text
    end: int
    count: int  # how many places in the text the token sequence occurs; 1 means the location is unambiguous


def locate_tokens(quote: str, text: str) -> TokenMatch | None:
    """The first place the quote's tokens occur, in order and next to each other, among the text's, with the number of
    such places. Every token must be identical: a number its value, an amount its currency, a percentage its sign, a
    section identifier its dots, a word its letters. A match therefore never starts or ends inside a word or a number,
    never forgives a changed digit, and never forgives a space moved inside the letters.

    Until v6 a run of consecutive words was compared as its joined letters, so that a space the reader lost or added
    ("advisedof", "speci fying") was forgiven. The same rule made "the rapist" equal to "therapist" and "un able" to
    "unable": two different texts called the same. Replayed over the record on 2026-10-02, 7 of 1,475 verified spans
    (5 runs, none a golden) had needed the forgiveness; from v6 such a quote is withheld instead."""
    needle = [(t.kind, t.canonical) for t in significant(tokenize(quote))]
    hay = significant(tokenize(text))
    if not needle or len(needle) > len(hay):
        return None
    keys = [(t.kind, t.canonical) for t in hay]
    first: tuple[int, int] | None = None
    count = 0
    for i in range(len(hay) - len(needle) + 1):
        if keys[i : i + len(needle)] == needle:
            count += 1
            if first is None:
                first = (hay[i].start, hay[i + len(needle) - 1].end)
    return None if first is None else TokenMatch(first[0], first[1], count)
