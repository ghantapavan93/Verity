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
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

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
# Every run of number words. The answer keeps only those a unit follows ("one (1) day", "two years"), checked at the
# run's end: a lookahead after the run was retried from every word of it, quadratic, and a 50 KB answer of "one one
# one …" held the API for 13 s (security audit, 2026-10-09).
_ANY_WORDS = re.compile(rf"(?P<words>{_WORD_RUN})", re.IGNORECASE)
# What follows a value and belongs to it when it is shown: its unit, with the digits a contract repeats in brackets.
_TRAILING_UNIT = re.compile(rf"(?:\s*\(\s*[\d.,]{{1,24}}\s*\))?[\s-]*{_UNIT}", re.IGNORECASE)
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
# Any run of three numbers joined by one separator ("2024-01-01", "13/01/2024", "1/2/24") is a date: one value when its
# order is certain, set aside when not, never loose numbers (triage, 2026-10-09: "2024-01-01" showed as 2024 and 01).
_NUMERIC_DATE = re.compile(r"\b(?P<a>\d{1,4})(?P<sep>[-/.])(?P<b>\d{1,2})(?P=sep)(?P<c>\d{1,4})\b")

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


# No contract states a value of more digits than this; a longer run is set aside, so arithmetic on it can neither
# overflow nor round two different numbers into one at Decimal's 28-digit precision (review, 2026-10-09).
MAX_VALUE_DIGITS = 24


def _number(surface: str) -> Decimal | None:
    digits = re.sub(r"[^\d.]", "", surface.replace(",", ""))
    if not digits or len(digits) > MAX_VALUE_DIGITS:
        return None
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _key(value: Decimal) -> str:
    return f"n:{value.normalize()}"


# The patterns match case-insensitively, which in Python folds Unicode case ("ſep" matches "sep"); every lookup by the
# matched text therefore casefolds too, and falls back rather than raising: "ſep 2024" raised StopIteration on every
# read of a run whose question held it (bug hunt, 2026-10-09).
def _month(name: str) -> int | None:
    folded = name.casefold().rstrip(".")[:3]
    return next((i for i, full in enumerate(_MONTH_NAMES, start=1) if full.startswith(folded)), None)


def _scale(word: str) -> Decimal | None:
    return _SCALE.get(word.casefold())


def _numeric_date_key(first: str, middle: str, last: str) -> str | None:
    """A key for a numeric date whose order is certain: year first (y-m-d), or a four-digit year last with a day above 12
    (or day and month equal). Two-digit years and either-way-round days are None."""
    b = int(middle)
    if len(first) == 4 and len(last) <= 2:
        month, day = b, int(last)
        return f"d:{first}-{month:02d}-{day:02d}" if 1 <= month <= 12 and 1 <= day <= 31 else None
    if len(last) == 4 and len(first) <= 2:
        a = int(first)
        if a > 12 >= b >= 1 and a <= 31:
            return f"d:{last}-{b:02d}-{a:02d}"
        if (b > 12 >= a >= 1 and b <= 31) or (a == b and 1 <= a <= 12):
            return f"d:{last}-{a:02d}-{b:02d}"
    return None


def _dates(text: str) -> list[tuple[str | None, int, int]]:
    """Each date in ``text`` as (key, start, end). The key is None for a slash date whose day and month could be either
    way round ("01/02/2024"): it is set aside, never compared and never split into numbers."""
    found: list[tuple[str | None, int, int]] = []
    for numeric in _NUMERIC_DATE.finditer(text):
        found.append((_numeric_date_key(numeric["a"], numeric["b"], numeric["c"]), numeric.start(), numeric.end()))
    for match in _DATE.finditer(text):
        groups = match.groupdict()
        month = _month(groups["month"] or groups["month2"] or groups["month3"])
        key: str | None = None  # a month no table names is set aside as a date, never split into numbers
        if month is not None and groups["year"]:
            key = f"d:{groups['year']}-{month:02d}-{int(groups['day']):02d}"
        elif month is not None and groups["year2"]:
            key = f"d:{groups['year2']}-{month:02d}-{int(groups['day2']):02d}"
        elif month is not None:
            key = f"d:{groups['year3']}-{month:02d}"
        found.append((key, match.start(), match.end()))
    return found


def _blank(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def _stated(text: str, *, words_need_a_unit: bool) -> list[tuple[str, int, int, str]]:
    """(key, start, end, written) of each value ``text`` states, offsets into ``text``; ``written`` says how the value
    was written: "date", "percent", "money", "number" or "words". Dates first, then what is left. Number words count
    only before a unit when ``words_need_a_unit`` (an answer); everywhere otherwise (a quote)."""
    dates = _dates(text)
    found = [(key, start, end, "date") for key, start, end in dates if key is not None]
    rest = _blank(text, ((start, end) for _, start, end in dates))
    for token in tokenize(rest):
        if token.kind in (Kind.NUMBER, Kind.CURRENCY, Kind.PERCENT):
            value = _number(rest[token.start : token.end])
            if value is None:
                continue
            end = token.end
            scale = _MAGNITUDE.match(rest, end) if token.kind is not Kind.PERCENT else None
            factor = _scale(scale.group(1)) if scale else None
            if scale and factor is not None:
                value, end = value * factor, scale.end()
            written = "percent" if token.kind is Kind.PERCENT else "money" if token.kind is Kind.CURRENCY else "number"
            found.append((_key(value), token.start, end, written))
    for match in _ANY_WORDS.finditer(rest):
        if words_need_a_unit and not _TRAILING_UNIT.match(rest, match.end()):
            continue
        value = words_to_number(match.group("words"))
        if value is None:
            continue
        end = match.end()
        scale = _MAGNITUDE.match(rest, end)
        factor = _scale(scale.group(1)) if scale else None
        if scale and factor is not None:
            value, end = value * factor, scale.end()
        found.append((_key(value), match.start(), end, "words"))
    return found


def _keys(text: str) -> set[str]:
    return {key for key, _, _, _ in _stated(text, words_need_a_unit=False)}


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
    for key, start, end, _ in sorted(_stated(blanked, words_need_a_unit=True), key=lambda found: found[1]):
        if key in given or key in seen:
            continue
        seen.add(key)
        unit = _TRAILING_UNIT.match(blanked, end) if key.startswith("n:") else None
        shown.append(answer[start : unit.end() if unit else end].strip())
    return shown


# ----------------------------------------------------------------------------------------------- choices among values

# A duration is compared only within its unit family, in that family's base unit, so that equivalents are one value
# ("one year" is "twelve months") and a term and a notice are not a choice ("12 months" against "30 days"): a month is
# not a fixed number of days, so across families code cannot compare exactly (triage, 2026-10-09).
_DURATION_FAMILIES: dict[str, tuple[str, int]] = {
    "second": ("clock", 1), "minute": ("clock", 60), "hour": ("clock", 3600),
    "day": ("days", 1), "week": ("days", 7), "fortnight": ("days", 14),
    "month": ("months", 1), "year": ("months", 12),
}  # fmt: skip
_MONEY_UNITS = {"dollar", "euro", "pound"}
# The kinds a choice is disclosed for: a band of percentages, a schedule of fees, a set of periods.
ChoiceKind = Literal["percent", "money", "duration"]
CHOICE_KINDS: tuple[ChoiceKind, ...] = ("percent", "money", "duration")
MAX_CHOICES_SHOWN = 8


@dataclass(frozen=True)
class ValueChoice:
    """Several values of a kind the answer gives, stated by a finding's verified passages, and the answer's value(s)
    among them."""

    kind: ChoiceKind
    answer: str  # the answer's value(s) of this kind that the passages state, as written in the answer
    values: list[str]  # the passages' distinct values of this kind, as written, in their order, at most MAX_CHOICES_SHOWN
    more: int  # how many further distinct values the passages state


def _kinded(text: str, *, words_need_a_unit: bool) -> list[tuple[ChoiceKind, str, str, str, int, int]]:
    """(kind, group, key, number, start, end) of each percentage, sum of money and duration ``text`` states, in its
    order, with the span covering its unit. Values compare within a group: a kind, and for a duration its unit family
    in that family's base unit. ``number`` is the value as written ("n:60" for sixty minutes, keyed 3600 seconds)."""
    out: list[tuple[ChoiceKind, str, str, str, int, int]] = []
    for key, start, end, written in sorted(_stated(text, words_need_a_unit=words_need_a_unit), key=lambda found: found[1]):
        if written == "date":
            continue
        value = Decimal(key.removeprefix("n:"))
        unit = _TRAILING_UNIT.match(text, end)
        word = re.sub(r"s$", "", unit.group(0).split()[-1].lower().strip("-")) if unit else ""
        through = unit.end() if unit else end
        if written == "percent":
            out.append(("percent", "percent", f"p:{value.normalize()}", key, start, end))
        elif written == "money":
            out.append(("money", "money", f"m:{value.normalize()}", key, start, end))
        elif word in ("percent", "cent"):
            out.append(("percent", "percent", f"p:{value.normalize()}", key, start, through))
        elif word in _MONEY_UNITS:
            out.append(("money", "money", f"m:{value.normalize()}", key, start, through))
        elif word in _DURATION_FAMILIES:
            family, factor = _DURATION_FAMILIES[word]
            out.append(("duration", f"duration:{family}", f"t:{family}:{(value * factor).normalize()}", key, start, through))
    return out


def value_choices(answer: str | None, quotes: Iterable[str], question: Iterable[str] = (), guidance: Iterable[str] = ()) -> list[ValueChoice]:
    """For each kind of value the answer gives (a percentage, money, a duration), the distinct values of that kind the
    finding's verified passages state together, when there are two or more and the answer uses one of them
    (evaluation workstream, 2026-10-09: a band table quoted word for word held 5%, 10% and 25%, and the answer chose 5%
    where the band gives 10%; a discount table split over two quotes held 5% and 8%). Which value applies is the
    model's reading; code says only that the passages offered several and which of them the answer used. An answer
    value the passages do not state chose nothing among them (a computed total): `unquoted_values` names it.

    The reader's own values are not the answer's choice. A value the question names is the condition asked about ("below
    99.5%"), set aside on both sides; a value the guidance names stays among the passages', since a guidance's 90 days
    beside a contract's 30 is the very conflict to show (triage and the fresh evaluation, 2026-10-09)."""
    if not answer:
        return []
    asked: set[str] = set()
    for text in question:
        asked |= _keys(text)
    standard: set[str] = set(asked)
    for text in guidance:
        standard |= _keys(text)
    # Per group: each distinct value once (key -> as written, in the passages' order). Dicts, not scans: a quote of
    # thousands of values stays linear.
    offered: dict[str, dict[str, str]] = {}
    for quote in quotes:
        for _, group, key, number, start, end in _kinded(quote, words_need_a_unit=False):
            if number not in asked:
                offered.setdefault(group, {}).setdefault(key, quote[start:end].strip())
    blanked = _POINTERS.sub(lambda m: " " * len(m.group(0)), answer)
    used: dict[str, tuple[ChoiceKind, dict[str, str]]] = {}
    for kind, group, key, number, start, end in _kinded(blanked, words_need_a_unit=True):
        if number in standard or key not in offered.get(group, {}):
            continue
        used.setdefault(group, (kind, {}))[1].setdefault(key, answer[start:end].strip())
    choices: list[ValueChoice] = []
    for group, (kind, chosen) in used.items():
        values = list(offered[group].values())
        # A choice is some of the values used and others left out: an answer that gives them all chose nothing.
        if len(values) >= 2 and len(chosen) < len(values):
            shown = values[:MAX_CHOICES_SHOWN]
            choices.append(ValueChoice(kind, ", ".join(chosen.values()), shown, len(values) - len(shown)))
    return choices
