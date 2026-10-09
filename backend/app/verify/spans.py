"""Locate a quoted passage in a section's text and return exact offsets into the original.

The model proposes quotes; this module decides whether they exist. It is the one component that
must never say "found" when the text is not there. The ladder is fixed and disclosed; the tier
that matched is stored on the span and shown in the interface:

1. exact       the quote is a substring of the text;
2. normalized  typographic quotes and dashes unified and whitespace runs collapsed, on both sides;
3. casefold    the same, case-insensitively;
4. typed       (verifier v5, in place of the letters-and-digits tier) the quote and the text as typed tokens:
               a number is a value ("1,500" is "1500", "15.00" is not), an amount keeps its currency, a
               percentage its sign, a section identifier its dots; a run of letters is a word, compared whole
               (v6: a space moved inside the letters is no longer forgiven, so "the rapist" is not "therapist");
               punctuation and quotation marks carry nothing (verify/tokens.py).

A quote that begins with the section's own label ("13.1 Defining Variables Variables have …") or
its heading alone is retried without it, and the tier is reported as ``unprefixed:<tier>``. The
number is recognised only as written and followed by its heading, never on its own (verifier v4):
before, "15 days' notice" under §1.5 lost its digits and verified against "45 days' notice".

There is no similarity-ratio tier. A census of every withheld quote (DECISIONS.md, 2026-09-28)
found a 0.994 ratio hiding a changed digit, and in a contract the digit is the point. The alnum
tier forgives what a person would not notice and nothing a person would.

At every tier a match may not split a run of letters and digits at either edge (verifier v3, after the
independent review of 2026-09-29): "5 days" is not inside "fifteen (15) days" and "$1,500" is not
inside "$11,500". A verbatim quote that drops a neighbouring word ("less than 30 days" for "not less
than 30 days") is still found, and the highlight shows the word it dropped.

Offsets always index the ORIGINAL text, so the interface highlights the characters that matched.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass

from .tokens import Kind, locate_tokens, tokenize

VERIFIER_VERSION = "v7"

# A section number as the reader writes it: "12", "8.1.2". Anything else in front of a label is heading text.
_SECTION_NUMBER = re.compile(r"\d+(?:\.\d+)*")

_QUOTE_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "–": "-",
        "—": "-",
        "−": "-",
        " ": " ",
        "​": "",
        "‎": "",
        "‏": "",
        "﻿": "",
    }
)


@dataclass(frozen=True)
class Located:
    start: int
    end: int
    method: str
    # How many places in the text the quote occurs under the tier that matched; 1 means the location is unambiguous,
    # more means the first bounded occurrence is shown and the record says so (verifier v5).
    count: int = 1


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Return the normalised text and, for each normalised character, its index in the original."""
    out: list[str] = []
    index_map: list[int] = []
    pending_space = False
    for i, ch in enumerate(text):
        mapped = ch.translate(_QUOTE_MAP)
        if mapped == "":
            continue
        if mapped.isspace():
            pending_space = True
            continue
        if pending_space and out:
            out.append(" ")
            index_map.append(index_map[-1] + 1 if index_map else i)
        pending_space = False
        out.append(mapped)
        index_map.append(i)
    return "".join(out), index_map


def fold_with_map(text: str, index_map: list[int]) -> tuple[str, list[int]]:
    """Casefold without losing the map: a character that folds to several ("ß" → "ss") keeps its index for each."""
    out: list[str] = []
    folded_map: list[int] = []
    for ch, source in zip(text, index_map, strict=True):
        folded = ch.casefold()
        out.append(folded)
        folded_map.extend([source] * len(folded))
    return "".join(out), folded_map


def alnum_with_map(text: str) -> tuple[str, list[int]]:
    """Letters and digits only, casefolded, each mapped to its index in the original. A full stop between
    two digits is a decimal point and is kept (verifier v4): "$15.00" is not "$1,500", "1.5%" is not "15%";
    a thousands separator is dropped, because "1500" and "1,500" are the same number to a reader."""
    out: list[str] = []
    index_map: list[int] = []
    last = len(text) - 1
    for i, ch in enumerate(text):
        if ch.isalnum():
            folded = ch.casefold()
            out.append(folded)
            index_map.extend([i] * len(folded))
        elif ch == "." and 0 < i < last and text[i - 1].isdigit() and text[i + 1].isdigit():
            out.append(ch)
            index_map.append(i)
    return "".join(out), index_map


def _normalize_quote(quote: str) -> str:
    normalized, _ = normalize_with_map(quote)
    return normalized.strip()


def bounded(text: str, start: int, end: int) -> bool:
    """A span is bounded when neither of its edges splits a run of letters and digits: "5 days" is not
    found inside "fifteen (15) days", "$1,500" is not found inside "$11,500", "able to terminate" is not
    found inside "unable to terminate". An edge that sits on punctuation or a space is a boundary on
    its own, so a verbatim quote ending in "(" stays exact when a letter follows; the start and the end
    of the text are boundaries."""
    if start > 0 and text[start - 1].isalnum() and text[start].isalnum():
        return False
    return not (end < len(text) and text[end - 1].isalnum() and text[end].isalnum())


def _find_bounded(haystack: str, needle: str, index_map: list[int] | None, text: str) -> tuple[int, int, int] | None:
    """The first occurrence of ``needle`` in ``haystack`` whose span, mapped back onto ``text``, is bounded, with the
    number of bounded occurrences."""
    first: tuple[int, int] | None = None
    count = 0
    at = haystack.find(needle)
    while at >= 0:
        if index_map is None:
            start, end = at, at + len(needle)
        else:
            start, end = index_map[at], index_map[at + len(needle) - 1] + 1
        if bounded(text, start, end):
            count += 1
            if first is None:
                first = (start, end)
        at = haystack.find(needle, at + 1)
    return None if first is None else (first[0], first[1], count)


# Characters normalisation deletes, derived from the one map so the prefilter and the tiers never drift.
_DELETED = {code: None for code, mapped in _QUOTE_MAP.items() if mapped in (None, "")}


@functools.lru_cache(maxsize=1024)
def _quote_words(quote: str) -> tuple[str, ...]:
    """The quote's words, casefolded, longest first (the likeliest to be absent)."""
    return tuple(sorted({t.canonical for t in tokenize(quote) if t.kind is Kind.WORD}, key=len, reverse=True))


def _cannot_hold(quote: str, text: str) -> bool:
    """A condition every tier needs, checked at C speed: each word of the quote stands in the text, casefolded, once
    the characters normalisation deletes are deleted. No tier changes a letter (exact, normalized and casefold keep
    words whole; typed compares words whole, casefolded), so a text without one of the words cannot hold the quote.
    Counting a quote's places across a 1.25M-character document ran every tier on every section: 1.9 s a quote; with
    this, 0.11 s, and outcomes identical on 212,248 pairs (2026-10-09)."""
    words = _quote_words(quote)
    if not words:
        return False
    folded = text.translate(_DELETED).casefold()
    return not all(word in folded for word in words)


def _ladder(quote: str, text: str) -> Located | None:
    return None if _cannot_hold(quote, text) else _tiers(quote, text)


def _tiers(quote: str, text: str) -> Located | None:
    found = _find_bounded(text, quote, None, text)
    if found is not None:
        return Located(found[0], found[1], "exact", found[2])

    norm_text, norm_map = normalize_with_map(text)
    norm_quote = _normalize_quote(quote)
    if not norm_quote:
        return None
    found = _find_bounded(norm_text, norm_quote, norm_map, text)
    if found is not None:
        return Located(found[0], found[1], "normalized", found[2])

    folded_text, folded_map = fold_with_map(norm_text, norm_map)
    found = _find_bounded(folded_text, norm_quote.casefold(), folded_map, text)
    if found is not None:
        return Located(found[0], found[1], "casefold", found[2])

    typed = locate_tokens(quote, text)
    if typed is not None and bounded(text, typed.start, typed.end):
        return Located(typed.start, typed.end, "typed", typed.count)
    return None


def strip_label(quote: str, label: str) -> str | None:
    """The quote without the section label the model copied in front of it, or None when it does not
    start with it. The label may have been copied whole ("12.11 No Third-Party Beneficiary") or as the
    heading alone; the number is recognised only as written, with its dots, followed by a separator,
    and never on its own (verifier v4): "15 days" does not carry the label of §1.5, and a number that
    is not a label is a number the ladder must find."""
    first, _, rest = label.partition(" ")
    number, heading = (first, rest) if _SECTION_NUMBER.fullmatch(first) else ("", label)
    norm_quote, norm_map = normalize_with_map(quote)
    start = 0
    if number:
        written = re.match(rf"{re.escape(number)}[.):\]]?(?:\s|$)", norm_quote)
        if written is not None:
            if written.end() >= len(norm_quote):
                return None  # the quote is the number and nothing else
            start = norm_map[written.end()]
    heading_alnum, _ = alnum_with_map(heading)
    if len(heading_alnum) < 2:
        return None
    body = quote[start:]
    body_alnum, body_map = alnum_with_map(body)
    if not body_alnum.startswith(heading_alnum) or len(body_alnum) == len(heading_alnum):
        return None
    # The first character of the quote that belongs to the text proper.
    remainder = body[body_map[len(heading_alnum)] :].lstrip()
    return remainder or None


@functools.lru_cache(maxsize=1024)
def _alnum(text: str) -> str:
    return alnum_with_map(text)[0]


def _may_carry_label(quote: str, label: str) -> bool:
    """strip_label can succeed only when the heading's letters and digits stand in the quote's: checked first, once per
    quote and label, instead of normalising the quote again for every section it is tried against."""
    first, _, rest = label.partition(" ")
    heading = rest if _SECTION_NUMBER.fullmatch(first) else label
    heading_alnum = _alnum(heading)
    return len(heading_alnum) >= 2 and heading_alnum in _alnum(quote)


def locate(quote: str, text: str, label: str | None = None) -> Located | None:
    """Find ``quote`` in ``text``; None when it is not there under the rules above."""
    if not quote or not quote.strip():
        return None
    found = _ladder(quote, text)
    if found is None and label and _may_carry_label(quote, label):
        stripped = strip_label(quote, label)
        if stripped is not None:
            found = _ladder(stripped, text)
            if found is not None:
                found = Located(found.start, found.end, f"unprefixed:{found.method}", found.count)
    return found
