"""The values an answer states that none of its verified quotes state: what code can see of the gap between a located
quote and a supported answer (holdout audit, 2026-10-09: "one (1) day of service credit" on a quote that stops before
the credit).

Values are compared by value, not by spelling: "thirty (30) days", "30 days" and "thirty days" are one value,
"$1,500,000", "USD 1.5 million" another, "January 1, 2024" and "1st day of January, 2024" a third. A date is one value
and is shown as written, never as a loose day number. The answer is read for the values it states: dates, digits,
money, percentages, and number words before a unit ("two years"); what points rather than states ("§6.4", "Sections 2,
11, and 13", "Exhibit No. 10.1", "regulation 72(9)", "sec_7", an enumerator "(2)") is set aside. A quote is read whole,
every number word included, so nothing it states is missed. The reader's own question and guidance count as stated:
an answer may repeat them.

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
# "$1.5 million" is 1,500,000: the word is part of the value, on both sides (triage, 2026-10-09).
_MAGNITUDE = re.compile(r"\s*(thousand|million|billion|trillion)\b", re.IGNORECASE)
_SCALE = {"thousand": Decimal(10) ** 3, "million": Decimal(10) ** 6, "billion": Decimal(10) ** 9, "trillion": Decimal(10) ** 12}

_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"
)  # fmt: skip
_MONTH = (
    r"(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
_ORDINAL = r"(?:st|nd|rd|th)?"
# "January 1, 2024", "1 January 2024", "the 1st day of January, 2024", "March 2025": one value each.
_DATE = re.compile(
    rf"\b{_MONTH}\s+(?P<day>\d{{1,2}}){_ORDINAL},?\s+(?P<year>\d{{4}})\b"
    rf"|\b(?P<day2>\d{{1,2}}){_ORDINAL}\s+(?:day\s+of\s+)?{_MONTH.replace('month', 'month2')},?\s+(?P<year2>\d{{4}})\b"
    rf"|\b{_MONTH.replace('month', 'month3')},?\s+(?P<year3>\d{{4}})\b",
    re.IGNORECASE,
)
# "2024-01-01" and "13/01/2024" are one value each too (triage, 2026-10-09: an ISO date showed as 2024 and 01).
_ISO_DATE = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b")
_SLASH_DATE = re.compile(r"\b(?P<a>\d{1,2})[/.](?P<b>\d{1,2})[/.](?P<year>\d{4})\b")

# Letters in a pointer are capitals or a bracketed sub-item: "Schedule B", "8.1(a)", never the next word ("fees").
_REF = r"(?-i:[\dA-Z]{1,6})(?![A-Za-z])(?:\.\d{1,6}){0,6}(?:\([a-z0-9]{1,4}\)){0,4}"
_POINTER_WORDS = (
    r"sections?|subsections?|clauses?|articles?|schedules?|exhibits?|attachments?|riders?|addend(?:um|a)|appendix|appendices"
    r"|annex(?:es|ures?)?|paragraphs?|parts?|chapters?|items?|regulations?|rules?"
)
# Where an answer points rather than states.
_POINTERS = re.compile(
    rf"(?:§§?\s*|\b(?:{_POINTER_WORDS})\s+(?:no\.?\s*|number\s+)?){_REF}(?:\s*(?:,\s*(?:and|or)?|and|or|to|through|&)\s*{_REF}){{0,40}}"
    r"|\bsec_\d+|\(part \d+\)|\(\s*\d{1,2}\s*\)|(?<!\d)\.\d+",
    re.IGNORECASE,
)


def _number(surface: str) -> Decimal | None:
    digits = re.sub(r"[^\d.]", "", surface.replace(",", ""))
    try:
        return Decimal(digits) if digits else None
    except InvalidOperation:
        return None


def _key(value: Decimal) -> str:
    return f"n:{value.normalize()}"


def _month(name: str) -> int:
    return next(i for i, full in enumerate(_MONTH_NAMES, start=1) if full.startswith(name.lower().rstrip(".")[:3]))


def _dates(text: str) -> list[tuple[str | None, int, int]]:
    """Each date in ``text`` as (key, start, end). The key is None for a slash date whose day and month could be either
    way round ("01/02/2024"): it is set aside, never compared and never split into numbers."""
    found: list[tuple[str | None, int, int]] = []
    for iso in _ISO_DATE.finditer(text):
        found.append((f"d:{iso['year']}-{int(iso['month']):02d}-{int(iso['day']):02d}", iso.start(), iso.end()))
    for slash in _SLASH_DATE.finditer(text):
        a, b = int(slash["a"]), int(slash["b"])
        key: str | None = None
        if a > 12 >= b:
            key = f"d:{slash['year']}-{b:02d}-{a:02d}"
        elif b > 12 >= a or a == b:
            key = f"d:{slash['year']}-{a:02d}-{b:02d}"
        found.append((key, slash.start(), slash.end()))
    for match in _DATE.finditer(text):
        groups = match.groupdict()
        if groups["year"]:
            key = f"d:{groups['year']}-{_month(groups['month']):02d}-{int(groups['day']):02d}"
        elif groups["year2"]:
            key = f"d:{groups['year2']}-{_month(groups['month2']):02d}-{int(groups['day2']):02d}"
        else:
            key = f"d:{groups['year3']}-{_month(groups['month3']):02d}"
        found.append((key, match.start(), match.end()))
    return found


def _blank(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def _stated(text: str, words: re.Pattern[str]) -> list[tuple[str, int, int]]:
    """(key, start, end) of each value ``text`` states, offsets into ``text``. Dates first, then what is left."""
    dates = _dates(text)
    found = [(key, start, end) for key, start, end in dates if key is not None]
    rest = _blank(text, ((start, end) for _, start, end in dates))
    for token in tokenize(rest):
        if token.kind in (Kind.NUMBER, Kind.CURRENCY, Kind.PERCENT):
            value = _number(rest[token.start : token.end])
            if value is None:
                continue
            end = token.end
            scale = _MAGNITUDE.match(rest, end) if token.kind is not Kind.PERCENT else None
            if scale:
                value, end = value * _SCALE[scale.group(1).lower()], scale.end()
            found.append((_key(value), token.start, end))
    for match in words.finditer(rest):
        value = words_to_number(match.group("words"))
        if value is None:
            continue
        end = match.end()
        scale = _MAGNITUDE.match(rest, end)
        if scale:
            value, end = value * _SCALE[scale.group(1).lower()], scale.end()
        found.append((_key(value), match.start(), end))
    return found


def _keys(text: str) -> set[str]:
    return {key for key, _, _ in _stated(text, _ANY_WORDS)}


def unquoted_values(answer: str | None, quotes: Iterable[str], readers_text: Iterable[str] = ()) -> list[str]:
    """The values ``answer`` states that no quote and none of the reader's own text (question, guidance) states, each as
    the answer writes it ("45 days", "$78,600.00", "one (1) day", "January 1, 2024"), in the answer's order, once each."""
    if not answer:
        return []
    given: set[str] = set()
    for text in (*quotes, *readers_text):
        given |= _keys(text)
    # Pointers are blanked to spaces, not removed, so offsets still index the answer as written.
    blanked = _POINTERS.sub(lambda m: " " * len(m.group(0)), answer)
    shown: list[str] = []
    seen: set[str] = set()
    for key, start, end in sorted(_stated(blanked, _ANSWER_WORDS), key=lambda found: found[1]):
        if key in given or key in seen:
            continue
        seen.add(key)
        unit = _TRAILING_UNIT.match(blanked, end) if key.startswith("n:") else None
        shown.append(answer[start : unit.end() if unit else end].strip())
    return shown
