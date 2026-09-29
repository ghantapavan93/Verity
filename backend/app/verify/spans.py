"""Locate a quoted passage in a section's text and return exact offsets into the original.

The model proposes quotes; this module decides whether they exist. It is the one component that
must never say "found" when the text is not there. The ladder is fixed and disclosed; the tier
that matched is stored on the span and shown in the interface:

1. exact       the quote is a substring of the text;
2. normalized  typographic quotes and dashes unified and whitespace runs collapsed, on both sides;
3. casefold    the same, case-insensitively;
4. alnum       letters and digits only, casefolded: punctuation, quotation marks and spacing are
               ignored, but every letter and every digit must match, in order.

A quote that begins with the section's own label ("13.1 Defining Variables Variables have …") is
retried without it, and the tier is reported as ``unprefixed:<tier>``.

There is no similarity-ratio tier. A census of every withheld quote (DECISIONS.md, 2026-09-28)
found a 0.994 ratio hiding a changed digit, and in a contract the digit is the point. The alnum
tier forgives what a person would not notice and nothing a person would.

Offsets always index the ORIGINAL text, so the interface highlights the characters that matched.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    """Letters and digits only, casefolded, each mapped to its index in the original."""
    out: list[str] = []
    index_map: list[int] = []
    for i, ch in enumerate(text):
        if ch.isalnum():
            folded = ch.casefold()
            out.append(folded)
            index_map.extend([i] * len(folded))
    return "".join(out), index_map


def _normalize_quote(quote: str) -> str:
    normalized, _ = normalize_with_map(quote)
    return normalized.strip()


def _ladder(quote: str, text: str) -> Located | None:
    exact = text.find(quote)
    if exact >= 0:
        return Located(exact, exact + len(quote), "exact")

    norm_text, norm_map = normalize_with_map(text)
    norm_quote = _normalize_quote(quote)
    if not norm_quote:
        return None
    at = norm_text.find(norm_quote)
    if at >= 0:
        return Located(norm_map[at], norm_map[at + len(norm_quote) - 1] + 1, "normalized")

    folded_text, folded_map = fold_with_map(norm_text, norm_map)
    folded_quote = norm_quote.casefold()
    at = folded_text.find(folded_quote)
    if at >= 0:
        return Located(folded_map[at], folded_map[at + len(folded_quote) - 1] + 1, "casefold")

    alnum_text, alnum_map = alnum_with_map(text)
    alnum_quote, _ = alnum_with_map(quote)
    if not alnum_quote:
        return None
    at = alnum_text.find(alnum_quote)
    if at >= 0:
        return Located(alnum_map[at], alnum_map[at + len(alnum_quote) - 1] + 1, "alnum")
    return None


def strip_label(quote: str, label: str) -> str | None:
    """The quote without the section label the model copied in front of it, or None when it does not
    start with it. The label may have been copied whole ("12.11 No Third-Party Beneficiary"), as the
    heading alone, or as the number alone; the longest match is removed."""
    quote_alnum, quote_map = alnum_with_map(quote)
    number, _, heading = label.partition(" ")
    candidates = [label, heading, number] if heading else [label]
    for candidate in candidates:
        candidate_alnum, _ = alnum_with_map(candidate)
        if len(candidate_alnum) < 2 or not quote_alnum.startswith(candidate_alnum) or len(quote_alnum) == len(candidate_alnum):
            continue
        # The first character of the quote that belongs to the text proper.
        cut = quote_map[len(candidate_alnum)]
        remainder = quote[cut:].lstrip()
        if remainder:
            return remainder
    return None


def locate(quote: str, text: str, label: str | None = None) -> Located | None:
    """Find ``quote`` in ``text``; None when it is not there under the rules above."""
    if not quote or not quote.strip():
        return None
    found = _ladder(quote, text)
    if found is None and label:
        stripped = strip_label(quote, label)
        if stripped is not None:
            found = _ladder(stripped, text)
            if found is not None:
                found = Located(found.start, found.end, f"unprefixed:{found.method}")
    return found
