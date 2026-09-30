"""Typed tokens: the representation under which a quote and its source are compared once exact text has failed.

The letters-and-digits tier compared two texts by their letters and digits alone, which made "$1,500" and
"$15.00" the same six characters and "15%" the same as "1.5%". Under typed tokens a number is a number:
"1,500" and "1500" are one value (Decimal, never float), "15.00" and "1,500" are two, "15%" and "1.5%" are
two, and a run of letters is a word. Punctuation, quotation marks, dashes and whitespace carry no meaning
and are dropped, so "days’ written" still meets "days written" and "non- exclusive" still meets
"non-exclusive", while a changed digit or a moved decimal point can never be forgiven.

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


@dataclass(frozen=True)
class Item:
    """A rigid token (number, currency, percent, section) or a run of consecutive words. Words in a run are joined,
    because the reader's own text carries joins and splits ("advisedof", "speci fying": four spans in the record on
    2026-09-29) that a reader forgives; the run remembers where its words began so a match still starts and ends
    at a word boundary. Numbers are never joined: "1 5" is not "15"."""

    kind: Kind
    canonical: str
    start: int
    end: int
    boundaries: tuple[int, ...]  # for a word run: the offset into `canonical` where each word begins, and its length at the end
    starts: tuple[int, ...]  # the original offset of each word in the run
    ends: tuple[int, ...]


def items(tokens: list[Token]) -> list[Item]:
    result: list[Item] = []
    run: list[Token] = []

    def flush() -> None:
        if run:
            joined = "".join(t.canonical for t in run)
            bounds = [0]
            for t in run:
                bounds.append(bounds[-1] + len(t.canonical))
            result.append(Item(Kind.WORD, joined, run[0].start, run[-1].end, tuple(bounds), tuple(t.start for t in run), tuple(t.end for t in run)))
            run.clear()

    for token in tokens:
        if not token.significant:
            continue
        if token.kind is Kind.WORD:
            run.append(token)
        else:
            flush()
            result.append(Item(token.kind, token.canonical, token.start, token.end, (0, len(token.canonical)), (token.start,), (token.end,)))
    flush()
    return result


def _suffix_start(hay: Item, needle: str) -> int | None:
    """The original offset where ``needle`` begins as a word-boundary-aligned suffix of the run, else None."""
    if not hay.canonical.endswith(needle):
        return None
    at = len(hay.canonical) - len(needle)
    return hay.starts[hay.boundaries.index(at)] if at in hay.boundaries else None


def _prefix_end(hay: Item, needle: str) -> int | None:
    """The original offset where ``needle`` ends as a word-boundary-aligned prefix of the run, else None."""
    if not hay.canonical.startswith(needle):
        return None
    at = len(needle)
    return hay.ends[hay.boundaries.index(at) - 1] if at in hay.boundaries else None


def _spans_within(hay: Item, needle: str) -> list[tuple[int, int]]:
    """``needle`` as a word-boundary-aligned substring of one run: every such place, in order."""
    found: list[tuple[int, int]] = []
    for i, at in enumerate(hay.boundaries[:-1]):
        if hay.canonical.startswith(needle, at) and (at + len(needle)) in hay.boundaries:
            found.append((hay.starts[i], hay.ends[hay.boundaries.index(at + len(needle)) - 1]))
    return found


def _matches_at(hay: list[Item], i: int, needle: list[Item]) -> list[tuple[int, int]]:
    """The original offsets of every match of ``needle`` starting at haystack item ``i`` (several only when a one-run
    quote occurs more than once inside one run of words)."""
    first, last = needle[0], needle[-1]
    if len(needle) == 1:
        if first.kind is not Kind.WORD:
            return [(hay[i].start, hay[i].end)] if (hay[i].kind, hay[i].canonical) == (first.kind, first.canonical) else []
        return _spans_within(hay[i], first.canonical) if hay[i].kind is Kind.WORD else []
    if i + len(needle) > len(hay):
        return []
    if first.kind is Kind.WORD:
        if hay[i].kind is not Kind.WORD:
            return []
        start = _suffix_start(hay[i], first.canonical)
    else:
        start = hay[i].start if (hay[i].kind, hay[i].canonical) == (first.kind, first.canonical) else None
    if start is None:
        return []
    for offset in range(1, len(needle) - 1):
        if (hay[i + offset].kind, hay[i + offset].canonical) != (needle[offset].kind, needle[offset].canonical):
            return []
    tail = hay[i + len(needle) - 1]
    if last.kind is Kind.WORD:
        end = _prefix_end(tail, last.canonical) if tail.kind is Kind.WORD else None
    else:
        end = tail.end if (tail.kind, tail.canonical) == (last.kind, last.canonical) else None
    return [] if end is None else [(start, end)]


def locate_tokens(quote: str, text: str) -> TokenMatch | None:
    """The first occurrence of the quote's tokens, in order, among the text's, with the number of occurrences. Rigid
    tokens (numbers, amounts, percentages, section identifiers) must be identical; words must be identical letters at
    word boundaries, joins and splits between them forgiven. A match therefore never starts or ends inside a word or a
    number, and never forgives a changed digit."""
    needle = items(tokenize(quote))
    haystack = items(tokenize(text))
    if not needle or not haystack:
        return None
    first: tuple[int, int] | None = None
    count = 0
    for i in range(len(haystack)):
        for found in _matches_at(haystack, i, needle):
            count += 1
            if first is None:
                first = found
    if first is None:
        return None
    return TokenMatch(first[0], first[1], count)
