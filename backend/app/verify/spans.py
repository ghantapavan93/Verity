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

Nor may it begin or end inside a number (verifier v8, after the war-room review of 2026-10-13, F-03): until
then a comma or a point between digits was an edge, so "$1,500" was found exact in "$1,500,000", "$15" in
"$15.50" and "Section 5" in "Section 5.2", and a sign, a currency or percent sign and the parentheses of an
accounting negative could be cut off. What belongs to a number is read once, in verify/tokens.py.

Nor may a sign be lost from an amount written with a magnitude letter (verifier v9, the legal evaluation's blocker B1,
2026-10-14): "$5M" was read as a word, so "Adjustment Amount $5M" verified against "Adjustment Amount -$5M" and "$5M"
was found word for word inside "-$5M". From v9 such an amount is a number like any other, and inside a number written
with a sign or parentheses every edge splits it, a space included: "10K" is not found inside "-USD 10K".

Nor may it split a word at a combining mark or a joiner, or say anything without a letter or a digit (verifier v11, the
break audit, 2026-10-30). A mark written after its letter (a decomposed "é" is "e" and U+0301) and a zero-width joiner or
non-joiner inside a word (Persian writes "non-" as "غیر" and U+200C before the word it negates) belong to that word, as
Unicode's word boundaries read them: "paye" was found inside a decomposed "payé", and "قابل" ("refundable") inside
"non-refundable", written so. A quote of punctuation alone, "." from an empty answer, was found exact in any text with a
full stop.
From v11 a number also keeps a comparator, a plus sign or a leading decimal point, and "/" or ":" joins its digits
(verify/tokens.py), and inside a number opened by any of them every edge splits it: "5%" is not inside ".5%".

Offsets always index the ORIGINAL text, so the interface highlights the characters that matched.

What is worked out about a text along the way (where its numbers are, a quote's words, letters and digits) is
remembered for one verification pass only (`verification_pass`): a run's verification, a trust manifest, a trust diff,
or a single `locate`. These were process-wide caches keyed by the texts themselves, so a visitor's contract and the
quotes from it stayed in memory after the workspace holding them was deleted (release integration, 2026-10-13).
Within a pass a text is still read once: without it, a quote that occurs thousands of times in a long section had its
numbers found again at every occurrence.
"""

from __future__ import annotations

import bisect
import re
from array import array
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import cast

from .tokens import (
    _CLAUSE_LETTER,
    SIGN_OPENERS_V11,
    VERSION,
    Kind,
    attaches,
    caseless,
    is_amount,
    joins_digits,
    locate_tokens,
    marked,
    tokenize,
    whole_words,
    written_numbers,
)

VERIFIER_VERSION = f"v{VERSION}"

# A section number as the reader writes it: "12", "8.1.2". Anything else in front of a label is heading text.
_SECTION_NUMBER = re.compile(r"\d+(?:\.\d+)*")
# What may follow a heading the model copied in front of its quote, besides a space (v11).
_LABEL_ENDS = ".:;)]-–—"

_QUOTE_MAP_V10 = str.maketrans(
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
# Verifier v11 reads every default-ignorable code point (Unicode's Default_Ignorable_Code_Point, written out so every
# Python and every pack reads the same set) as absent, as a reader sees the text. v10 deleted four of them, so an Arabic
# letter mark between two digits ("9", U+061C, "0" displays as 90) parted a number, and "upon 9" was found exact in it,
# and a joiner or a variation selector after a digit hid the number's end (stress test, 2026-10-30). `_QUOTE_MAP_V10`
# is v10's, kept for the evidence packs of runs verified under v10 and before.
IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
# And every apostrophe a keyboard or a font writes is one: the modifier letter, the fullwidth form, the grave and the acute
# accent typed for it (the retrieval team's report, 2026-10-30).
QUOTE_FOLDS_V11 = {"\u02bc": "'", "\uff07": "'", "`": "'", "\u00b4": "'"}
_QUOTE_MAP: dict[int, str] = {
    **_QUOTE_MAP_V10,
    **{code: "" for low, high in IGNORABLE_RANGES for code in range(low, high + 1)},
    **str.maketrans(QUOTE_FOLDS_V11),
}


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
    found inside "unable to terminate"; nor a number with what is written against it (v8): "$1,500" is not
    found inside "$1,500,000", "Section 5" inside "Section 5.2", "5%" inside "-5%", "$500" inside "($500)".
    Any other edge that sits on punctuation or a space is a boundary on its own, so a verbatim quote ending
    in "(" stays exact when a letter follows; the start and the end of the text are boundaries."""
    return not (_splits(text, start) or _splits(text, end))


def _splits(text: str, at: int) -> bool:
    """Whether the edge before ``text[at]`` falls inside what a reader reads as one run: letters and digits, or a
    number as it is written (verify/tokens.written_numbers). The characters are the ones the reader sees: those
    normalisation deletes are skipped, so a zero-width space inside "1,500,000" or "unable" makes no edge (v8)."""
    before, after = _seen(text, at, -1), _seen(text, at, 1)
    if not before or not after:
        return False  # the start and the end of the text
    if (_in_run(before[-1]) and _in_run(after[0])) or joins_digits(before, after):
        return True
    attached = attaches(before[-1], after[0])
    starts, ends = _numbers(text)
    last = bisect.bisect_left(starts, at) - 1  # the last number that starts before the edge
    if last < 0 or ends[last] <= at:
        return False
    # Inside a number: at what is written against it, always (v8); anywhere else (a space, the full stop of "Rs."), only
    # in a number written with a sign or parentheses, so a quote cannot drop "-USD " from "-USD 10K" (v9) while "500"
    # still stands alone in "USD 500"; from v11 also a comparator, a plus sign or a leading decimal point, and anywhere
    # after a number's first digit, so "1/2%" is not found inside "1 1/2%" (stress test, 2026-10-30).
    return attached or text[starts[last]] in SIGN_OPENERS_V11 or any(ch.isdigit() for ch in text[starts[last] : at])


def _in_run(ch: str) -> bool:
    """Whether ``ch`` belongs to a run of letters and digits: a letter or a digit, or (v11) a combining mark or a joiner,
    which belong to the letters they are written between or after (tokens.marked)."""
    return ch.isalnum() or marked(ch)


def _seen(text: str, at: int, step: int) -> str:
    """The two characters a reader sees before (step -1) or after (step 1) the edge before ``text[at]``, nearest at the
    edge; fewer at the start or the end of the text."""
    near = text[max(0, at - 2) : at] if step < 0 else text[at : at + 2]
    if _INVISIBLE.isdisjoint(near):
        return near
    seen: list[str] = []
    i = at - 1 if step < 0 else at
    while 0 <= i < len(text) and len(seen) < 2:
        if ord(text[i]) not in _DELETED:
            seen.append(text[i])
        i += step
    return "".join(reversed(seen)) if step < 0 else "".join(seen)


_pass: ContextVar[dict[tuple[str, str], object] | None] = ContextVar("verification_pass", default=None)


@contextmanager
def verification_pass() -> Iterator[None]:
    """Remember what is worked out about each text until the pass ends, then let all of it go. A pass already open is
    joined, so a run's verification remembers across its quotes and a single locate across its occurrences."""
    if _pass.get() is not None:
        yield
        return
    opened = _pass.set({})
    try:
        yield
    finally:
        _pass.reset(opened)


def _remembered[T](kind: str, key: str, work: Callable[[str], T]) -> T:
    memo = _pass.get()
    if memo is None:
        return work(key)
    if (kind, key) not in memo:
        memo[(kind, key)] = work(key)
    return cast(T, memo[(kind, key)])


def _numbers(text: str) -> tuple[array[int], array[int]]:
    """Where each number of ``text`` starts and ends, in order, as the reader sees it: read once per text and pass, on the
    first edge that needs it, with the characters normalisation deletes left out and the offsets mapped back."""
    return _remembered("numbers", text, _read_numbers)


def _read_numbers(text: str) -> tuple[array[int], array[int]]:
    visible = text.translate(_DELETED)
    starts, ends = array("q"), array("q")
    if len(visible) == len(text):
        for low, high in written_numbers(text):
            starts.append(low)
            ends.append(high)
        return starts, ends
    # A visible index v is the original v + the number of deleted characters before it: for the j-th deleted
    # character, at original index d, every visible index from d - j on lies after it.
    after_deleted = array("q", (i - j for j, i in enumerate(i for i, ch in enumerate(text) if ord(ch) in _DELETED)))
    for low, high in written_numbers(visible):
        starts.append(low + bisect.bisect_right(after_deleted, low))
        ends.append(high - 1 + bisect.bisect_right(after_deleted, high - 1) + 1)
    return starts, ends


def _find_bounded(
    haystack: str, needle: str, index_map: list[int] | None, text: str, keep: Callable[[int, int], bool] | None = None
) -> tuple[int, int, int] | None:
    """The first occurrence of ``needle`` in ``haystack`` whose span, mapped back onto ``text``, is bounded (and kept by
    ``keep``, when given), with the number of such occurrences. A mapped occurrence that begins or ends inside what one
    character of ``text`` became ("ﬀ" folds to "ff") is no occurrence: "set of" is not found at "set oﬀ" (v11)."""
    first: tuple[int, int] | None = None
    count = 0
    n = len(needle)
    at = haystack.find(needle)
    while at >= 0:
        if index_map is None:
            start, end = at, at + n
        else:
            start, end = index_map[at], index_map[at + n - 1] + 1
        inside_a_fold = index_map is not None and (
            (at > 0 and index_map[at - 1] == index_map[at]) or (at + n < len(index_map) and index_map[at + n] == index_map[at + n - 1])
        )
        if not inside_a_fold and bounded(text, start, end) and (keep is None or keep(start, end)):
            count += 1
            if first is None:
                first = (start, end)
        at = haystack.find(needle, at + 1)
    return None if first is None else (first[0], first[1], count)


# Characters normalisation deletes, derived from the one map so the prefilter and the tiers never drift.
_DELETED = {code: None for code, mapped in _QUOTE_MAP.items() if mapped in (None, "")}
_INVISIBLE = frozenset(map(chr, _DELETED))


def _quote_words(quote: str) -> tuple[str, ...]:
    """The quote's words, casefolded, longest first (the likeliest to be absent)."""
    return _remembered("words", quote, _read_quote_words)


def _read_quote_words(quote: str) -> tuple[str, ...]:
    # An amount word ("usd10k") is a number to the typed tier (v9), which may find it written apart ("USD 10K"). A word
    # is read whole and compared caseless as the typed tier reads it (v11): "ou" with U+0300 is the word "où". Both sides
    # are first read through the quote table, as the normalized tier reads them: it folds U+02BC, a letter, to an
    # apostrophe, so a word holding one is two words to the tiers that find it (v11).
    folded = quote.translate(_QUOTE_MAP)
    words = whole_words(folded, tokenize(folded))
    return tuple(sorted({caseless(folded[t.start : t.end]) for t in words if t.kind is Kind.WORD and not is_amount(folded, t)}, key=len, reverse=True))


def _cannot_hold(quote: str, text: str) -> bool:
    """A condition every tier needs, checked at C speed: each word of the quote stands in the text, both in their
    canonical caseless form (tokens.caseless), once the characters normalisation deletes are deleted. No tier changes a
    letter (exact, normalized and casefold keep words whole; typed compares words whole, caseless), so a text without one
    of the words cannot hold the quote. Counting a quote's places across a 1.25M-character document ran every tier on
    every section: 1.9 s a quote; with this, 0.11 s, and outcomes identical on 212,248 pairs (2026-10-09)."""
    words = _quote_words(quote)
    if not words:
        return False
    folded = _remembered("caseless", text, _read_caseless)
    return not all(word in folded for word in words)


def _read_caseless(text: str) -> str:
    return caseless(text.translate(_QUOTE_MAP))


def _ladder(quote: str, text: str, whole: str | None = None) -> Located | None:
    return None if _cannot_hold(quote, text) else _tiers(quote, text, whole)


def _tiers(quote: str, text: str, whole: str | None = None) -> Located | None:
    """The ladder over ``text``, every edge read in ``whole``, the text ``text`` begins (by default ``text`` itself)."""
    if not any(ch.isalnum() for ch in quote):
        return None  # punctuation alone says nothing the text could hold (v11)
    whole = text if whole is None else whole
    found = _find_bounded(text, quote, None, whole)
    if found is not None:
        return Located(found[0], found[1], "exact", found[2])

    norm_text, norm_map = normalize_with_map(text)
    norm_quote = _normalize_quote(quote)
    if not norm_quote:
        return None
    found = _find_bounded(norm_text, norm_quote, norm_map, whole)
    if found is not None:
        return Located(found[0], found[1], "normalized", found[2])

    folded_text, folded_map = fold_with_map(norm_text, norm_map)
    # Case forgives "SECTION 2(a)" for "Section 2(a)", never a clause's letter: "(A)" and "(a)" name two clauses (v11).
    letters = _CLAUSE_LETTER.findall(quote)
    found = _find_bounded(folded_text, norm_quote.casefold(), folded_map, whole, lambda start, end: _CLAUSE_LETTER.findall(whole[start:end]) == letters)
    if found is not None:
        return Located(found[0], found[1], "casefold", found[2])

    typed = locate_tokens(quote, text, _INVISIBLE, keep=lambda start, end: bounded(whole, start, end))
    if typed is not None:
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
    # The first character of the quote that belongs to the text proper: its first letter or digit, or, when that digit
    # begins a number written with a sign, a currency sign or a parenthesis, that character (v8): "Fees: -5%" leaves
    # "-5%", never "5%", which would cut the number's sign off and be refused.
    begin, heading_end = body_map[len(heading_alnum)], body_map[len(heading_alnum) - 1]
    # A heading copied whole ends where a separator follows it (v11): "8 Supplier" is not the start of "Supplier's
    # liability", whose rest, "'s liability", was found in "the Customer's liability"; nor "Schedule 1" of "Schedule 1,500".
    separator = body[heading_end + 1 : heading_end + 2]
    if separator and not (separator.isspace() or separator in _LABEL_ENDS):
        return None
    begin = next((low for low, high in written_numbers(body) if heading_end < low < begin < high), begin)
    remainder = body[begin:].lstrip()
    return remainder or None


def _alnum(text: str) -> str:
    return _remembered("alnum", text, _read_alnum)


def _read_alnum(text: str) -> str:
    return alnum_with_map(text)[0]


def _may_carry_label(quote: str, label: str) -> bool:
    """strip_label can succeed only when the heading's letters and digits stand in the quote's: checked first, once per
    quote and label, instead of normalising the quote again for every section it is tried against."""
    first, _, rest = label.partition(" ")
    heading = rest if _SECTION_NUMBER.fullmatch(first) else label
    heading_alnum = _alnum(heading)
    return len(heading_alnum) >= 2 and heading_alnum in _alnum(quote)


def locate(quote: str, text: str, label: str | None = None, window: int | None = None) -> Located | None:
    """Find ``quote`` in ``text``; None when it is not there under the rules above. With ``window``, only the first
    ``window`` characters are searched (what the model was shown), and every edge is still read in the whole text: the
    end of a window is not the end of the text, so "$1,500" is not found where the window cuts "$1,500,000" (v11)."""
    if not quote or not quote.strip():
        return None
    with verification_pass():
        return _locate(quote, text if window is None else text[:window], label, text)


def _locate(quote: str, text: str, label: str | None, whole: str) -> Located | None:
    found = _ladder(quote, text, whole)
    if found is None and label and _may_carry_label(quote, label):
        stripped = strip_label(quote, label)
        if stripped is not None:
            found = _ladder(stripped, text, whole)
            if found is not None:
                found = Located(found.start, found.end, f"unprefixed:{found.method}", found.count)
    return found
