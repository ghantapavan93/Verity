"""The values an answer states that none of its verified quotes state: what code can see of the gap between a located
quote and a supported answer (holdout audit, 2026-10-09: "one (1) day of service credit" on a quote that stops before
the credit).

Values are compared by value, not by spelling: "thirty (30) days", "30 days" and "thirty days" are one value, "$1,500"
and "USD 1500.00" another. The answer is read for the values it states: digits, money, percentages, and number words
before a unit ("two years"); what points rather than states ("§6.4", "Sections 2, 11, and 13", "regulation 72(9)",
"sec_7", an enumerator "(2)") is set aside. A quote is read whole, every number word included, so nothing it states is
missed. The reader's own question and guidance count as stated: an answer may repeat them.

This is a disclosure. It changes no status, and finding nothing claims nothing: a quote can state the right number for
the wrong band (a service-credit table holds both 5% and 10%).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from ..policy.durations import words_to_number
from ..verify.tokens import Kind, tokenize

_NUMBER_WORDS = (
    "zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    "|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand"
)
# Atomic, as in policy.durations: a run of number words is consumed once and never re-split, so a hostile answer of
# "one and one and …" is linear.
_WORD_RUN = rf"(?>\b(?:{_NUMBER_WORDS})\b(?:[\s-]+(?:and[\s-]+)?\b(?:{_NUMBER_WORDS})\b)*)"
_UNIT = (
    r"(?:calendar\s+|business\s+|working\s+)?(?:days?|weeks?|fortnights?|months?|years?|hours?|minutes?|seconds?"
    r"|percent|per\s+cent|times|dollars?|euros?|pounds?)\b"
)
# Number words the answer states as a value: before a unit, "one (1) day", "two years".
_ANSWER_WORDS = re.compile(rf"(?P<words>{_WORD_RUN})(?=(?:\s*\(\s*[\d.,]+\s*\))?[\s-]*{_UNIT})", re.IGNORECASE)
# Every run of number words, for a quote or the reader's text.
_ANY_WORDS = re.compile(rf"(?P<words>{_WORD_RUN})", re.IGNORECASE)
# What follows a value and belongs to it when it is shown: its unit, with the digits a contract repeats in brackets.
_TRAILING_UNIT = re.compile(rf"(?:\s*\(\s*[\d.,]+\s*\))?[\s-]*{_UNIT}", re.IGNORECASE)
_REF = r"[\dA-Z]{1,6}(?:\.\d{1,6}){0,6}(?:\([a-z0-9]{1,4}\)){0,4}"
# Where an answer points rather than states.
_POINTERS = re.compile(
    rf"(?:§§?\s*|\b(?:sections?|subsections?|clauses?|articles?|schedules?|exhibits?|appendix|appendices|annex(?:es)?|paragraphs?"
    rf"|parts?|regulations?|rules?)\s+){_REF}(?:\s*(?:,\s*(?:and|or)?|and|or|to|through|&)\s*{_REF}){{0,40}}"
    r"|\bsec_\d+|\(part \d+\)|\(\s*\d{1,2}\s*\)|(?<!\d)\.\d+",
    re.IGNORECASE,
)


def _value(surface: str) -> Decimal | None:
    digits = re.sub(r"[^\d.]", "", surface.replace(",", ""))
    try:
        return Decimal(digits).normalize() if digits else None
    except InvalidOperation:
        return None


def _stated(text: str, words: re.Pattern[str]) -> list[tuple[Decimal, int, int]]:
    """(value, start, end) of each value ``text`` states, offsets into ``text``."""
    found: list[tuple[Decimal, int, int]] = []
    for token in tokenize(text):
        if token.kind in (Kind.NUMBER, Kind.CURRENCY, Kind.PERCENT):
            value = _value(text[token.start : token.end])
            if value is not None:
                found.append((value, token.start, token.end))
    for match in words.finditer(text):
        value = words_to_number(match.group("words"))
        if value is not None:
            found.append((value.normalize(), match.start(), match.end()))
    return found


def _values(text: str) -> set[Decimal]:
    return {value for value, _, _ in _stated(text, _ANY_WORDS)}


def unquoted_values(answer: str | None, quotes: Iterable[str], readers_text: Iterable[str] = ()) -> list[str]:
    """The values ``answer`` states that no quote and none of the reader's own text (question, guidance) states, each as
    the answer writes it ("45 days", "$78,600.00", "one (1) day"), in the answer's order, once each."""
    if not answer:
        return []
    given: set[Decimal] = set()
    for text in (*quotes, *readers_text):
        given |= _values(text)
    # Pointers are blanked to spaces, not removed, so offsets still index the answer as written.
    blanked = _POINTERS.sub(lambda m: " " * len(m.group(0)), answer)
    shown: list[tuple[int, str]] = []
    seen: set[Decimal] = set()
    for value, start, end in sorted(_stated(blanked, _ANSWER_WORDS), key=lambda found: found[1]):
        if value in given or value in seen:
            continue
        seen.add(value)
        unit = _TRAILING_UNIT.match(blanked, end)
        shown.append((start, answer[start : unit.end() if unit else end].strip()))
    return [surface for _, surface in shown]
