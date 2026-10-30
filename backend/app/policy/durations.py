"""Durations as contracts write them, parsed by code, with their unit and their doubts.

    "thirty (30) days"            → 30 calendar days
    "20 Working Days"             → 20 business days
    "twenty-one (21) days"        → 21 calendar days
    "twenty-one (30) days"        → ambiguous: the words and the digits disagree
    "one month"                   → 1 month, which is not 30 days
    "promptly"                    → nothing: no duration is stated

Numbers are Decimal, never float. Weeks convert to days exactly (7); months, years and business days do not convert to
one number of calendar days, and are never guessed as one. Since policy-v10 (2026-10-14) each is placed on the calendar
as the range of calendar days it can span (`calendar_days`): a month is 28 to 31 days, a year 365 or 366, and N business
days at least N + 2 × ⌊(N − 1) / 5⌋ days where the contract's own definition makes a Business Day a weekday
(`business_week`). Two periods in different units are then in order only when their ranges are; otherwise code cannot
say, and says why.
"""

from __future__ import annotations

import bisect
import calendar
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from ..ingest.invisible import IGNORABLE


class DurationUnit(StrEnum):
    CALENDAR_DAY = "calendar_day"
    BUSINESS_DAY = "business_day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class Operator(StrEnum):
    MINIMUM = "minimum"  # "at least 30 days": the contract's figure must be this or more
    MAXIMUM = "maximum"  # "no more than 30 days": this or less
    EXACT = "exact"


@dataclass(frozen=True)
class Duration:
    value: Decimal
    unit: DurationUnit

    def in_days(self) -> Decimal | None:
        """Calendar days when the unit converts exactly; None for business days, months and years."""
        if self.unit is DurationUnit.CALENDAR_DAY:
            return self.value
        if self.unit is DurationUnit.WEEK:
            return self.value * 7
        return None


@dataclass(frozen=True)
class DurationMention:
    """One duration as the text wrote it. ``duration`` is None when the mention is ambiguous; ``readings`` are the values
    it can be read as either way (its duration, or the words' and the digits' when they disagree), so no reader drops an
    ambiguous period as if it were not there (stress test, 2026-10-30). ``in_range`` is its end of a range the text
    writes as one ("between 30 and 90 days", "30-90 days"), and ``window`` the stretch of text its own comparison words
    are read in: from the period before it to the period after it, so "at least" before 30 is not read as 90's."""

    surface: str
    start: int
    end: int
    duration: Duration | None
    ambiguity: str | None = None
    readings: tuple[Duration, ...] = ()
    in_range: Literal["low", "high"] | None = None
    window: tuple[int, int | None] = (0, None)


_UNITS = {
    "calendar_day": DurationUnit.CALENDAR_DAY,
    "day": DurationUnit.CALENDAR_DAY,
    "business_day": DurationUnit.BUSINESS_DAY,
    "working_day": DurationUnit.BUSINESS_DAY,
    "week": DurationUnit.WEEK,
    "month": DurationUnit.MONTH,
    "year": DurationUnit.YEAR,
}
_ONES = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
# A number written in words, by its grammar: "forty-five", "one hundred and twenty", "two thousand five hundred". Until
# policy-v17 any run of number words was one number, with "and" anywhere in it, so "between thirty and sixty days" was
# ninety days, a figure neither text states (stress test, 2026-10-30). Now "and" joins only after "hundred" or
# "thousand", a tens word takes at most one ones word after it, and anything else ends the number: "thirty and sixty"
# is two numbers. Longest word first, and each word whole, so "seventeen" is never "seven". The pattern is bounded and
# atomic: a hostile run of "one and one and …" is read one word at a time, linear in the text (hostile review, 2026-10-01).
_UNDER_TWENTY = "|".join(sorted(_ONES, key=len, reverse=True))
_SMALL = rf"(?:(?:{'|'.join(_TENS)})\b(?:[\s-]+(?:one|two|three|four|five|six|seven|eight|nine)\b)?|(?:{_UNDER_TWENTY})\b)"
_HUNDREDS = rf"(?:{_SMALL}[\s-]+)?hundred\b(?:[\s-]+(?:and[\s-]+)?{_SMALL})?"
_BELOW_THOUSAND = rf"(?:{_HUNDREDS}|{_SMALL})"
NUMBER_WORDS = rf"(?>{_BELOW_THOUSAND}[\s-]+thousand\b(?:[\s-]+(?:and[\s-]+)?{_BELOW_THOUSAND})?|(?:{_BELOW_THOUSAND}[\s-]+)?thousand\b|{_BELOW_THOUSAND})"
_WORD = rf"(?:\ba\b|\ban\b|{NUMBER_WORDS})"
_WORD_NUMBER = re.compile(rf"(?:a|an|{NUMBER_WORDS})", re.IGNORECASE)
# Digits, grouped in thousands or not: "1,095 days" is 1,095 days, never 95 (the verifier's skeptic, 2026-10-30).
_NUMBER = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_UNIT = r"(?P<unit>calendar\s+days?|business\s+days?|working\s+days?|days?|weeks?|fortnights?|months?|years?)"
# digits, optionally followed by the words in parentheses: "30 days", "30 (thirty) days", "30-day"
_DIGITS_FIRST = re.compile(rf"(?<![\w.,])(?P<digits>{_NUMBER})[\s-]*(?:\(\s*(?P<words>{_WORD})\s*\))?[\s-]*{_UNIT}\b", re.IGNORECASE)
# words, optionally followed by the digits in parentheses: "thirty days", "thirty (30) days", "twenty-one (21) days"
_WORDS_FIRST = re.compile(rf"\b(?P<words>{_WORD})\s*(?:\(\s*(?P<digits>{_NUMBER})\s*\))?[\s-]+{_UNIT}\b", re.IGNORECASE)
# A number with no unit of its own, as written before another period that carries one: the 30 of "between 30 and 90
# days", "30 to 90 days", "thirty (30) or sixty (60) days". Never an article: "a" is one only before a unit.
_BARE = re.compile(
    rf"(?<![\w.,])(?P<digits>{_NUMBER})(?:\s*\(\s*(?P<words>{NUMBER_WORDS})\s*\))?(?![\w%]|[.,]\d)"
    rf"|\b(?P<words2>{NUMBER_WORDS})(?:\s*\(\s*(?P<digits2>{_NUMBER})\s*\))?(?!\w)",
    re.IGNORECASE,
)
# What points or prices, not counts: "Section 12 and 30 days" is no period of twelve days.
_POINTS_BEFORE = re.compile(
    r"(?:§§?|\b(?:sections?|clauses?|articles?|schedules?|exhibits?|annex(?:es)?|appendix|paragraphs?|items?|parts?|rules?|nos?\.?|number)|[#$€£¥])\s*$",
    re.IGNORECASE,
)
_PERCENT_AFTER = re.compile(r"\s*(?:%|percent\b|per\s*cent\b)", re.IGNORECASE)
# What may stand between two periods the text writes together ("30 and 90", "30, 60 or 90", "30 but no more than 90"):
# the words that join them and the words that compare, and nothing else, within one sentence and a few words.
_JOINER = re.compile(r",|-|&|\b(?:and|or|to|through|thru|until|nor|but)\b", re.IGNORECASE)
_COMPARING_GLUE = (
    r"no|not|never|at|most|least|more|less|fewer|greater|longer|shorter|than|maximum|minimum|max|min|up|exceed\w*|under|over|above|below|within|equal"
)
_GLUE = re.compile(rf"(?:\s|['’]|{_JOINER.pattern}|\b(?:{_COMPARING_GLUE}|a|an|the|of)\b)*+", re.IGNORECASE)
_COMPARES_IN_GLUE = re.compile(rf"\b(?:{_COMPARING_GLUE})\b", re.IGNORECASE)
_RANGE_JOINER = re.compile(r"\s*(?:-|to|through|thru|until)\s*", re.IGNORECASE)
_BETWEEN = re.compile(r"\b(?:between|from)\s+$", re.IGNORECASE)
_MAX_GLUE = 40
# Termination with no notice at all: a zero-day notice period, so a floor in the guidance can be compared with it.
_ZERO = re.compile(r"\b(?:immediately|with immediate effect|without (?:prior )?notice|no notice)\b", re.IGNORECASE)
# The words-first pattern is only worth running when a unit word exists at all.
_ANY_UNIT = re.compile(_UNIT, re.IGNORECASE)
_ARTICLE = re.compile(r"^(?:a|an|the)$", re.IGNORECASE)

# ----------------------------------------------------------------------------- what code reads (policy-v17)
#
# Code reads a period from the characters a reader sees. The stress test of 2026-10-30 (hostile model, verifier): a
# contract's "9\u200e0 days" displays as 90 and was read as 0, "15\u200d days" was read as no period, and
# "forty‑five (45)" as "five", so a mark the reader keeps, or a dash a typesetter chose, made code assert a
# shortfall the contract does not state or hide one it does. Before any number is read, every format character
# (category Cf: direction marks, joiners, zero-width spaces, a byte-order mark) and every other default-ignorable code
# point is deleted, and every dash is a hyphen. Offsets still index the text as written.
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−﹘﹣－"), "-")
_DEFAULT_IGNORABLE = re.compile(f"[{IGNORABLE}]")


def seen(text: str) -> tuple[str, list[int] | None]:
    """The text as code reads values from it, and, for each of its characters, where it is in ``text`` (None when the
    text is ASCII and nothing changes)."""
    if text.isascii():
        return text, None
    kept: list[str] = []
    where: list[int] = []
    for index, char in enumerate(text):
        if not char.isascii():
            if unicodedata.category(char) == "Cf" or _DEFAULT_IGNORABLE.match(char):
                continue
            char = char.translate(_DASHES)
        kept.append(char)
        where.append(index)
    return "".join(kept), where


def seen_text(text: str) -> str:
    """`seen` without the map: the text as code reads values from it."""
    return seen(text)[0]


def words_to_number(text: str) -> Decimal | None:
    """ "thirty", "forty-five", "twenty one", "one hundred twenty", "a" (as in "a month") → the number; None for words that
    are not one number by the grammar above ("several", "thirty and sixty")."""
    if not _WORD_NUMBER.fullmatch(text.strip()):
        return None
    tokens = [t for t in re.split(r"[\s-]+", text.strip().lower()) if t and t != "and"]
    if len(tokens) == 1 and _ARTICLE.match(tokens[0]):
        return Decimal(1)
    total = 0
    current = 0
    for token in tokens:
        if token in _ONES:
            current += _ONES[token]
        elif token in _TENS:
            current += _TENS[token]
        elif token == "hundred":
            current = (current or 1) * 100
        elif token == "thousand":
            total += (current or 1) * 1000
            current = 0
        else:
            return None
    return Decimal(total + current)


def _unit(text: str) -> DurationUnit:
    key = re.sub(r"\s+", "_", text.strip().lower())
    key = key[:-1] if key.endswith("s") else key
    return _UNITS[key]


@dataclass(frozen=True)
class _Written:
    """A number as the text writes it, in `seen` offsets, with the unit written after it, if one is."""

    start: int
    end: int
    digits: str | None
    words: str | None
    unit: str | None


def _covered(starts: list[int], ends: list[int], at: int) -> bool:
    index = bisect.bisect_right(starts, at) - 1
    return index >= 0 and at < ends[index]


def _written(read: str) -> list[_Written]:
    """Every period the text writes with its unit, and every number written without one; in order. The two patterns can
    see the same period ("thirty (30) days"); the one that starts earlier covers it."""
    found: list[_Written] = []
    if not _ANY_UNIT.search(read):
        return found
    starts: list[int] = []
    ends: list[int] = []

    def add(item: _Written) -> None:
        index = bisect.bisect_left(starts, item.start)
        starts.insert(index, item.start)
        ends.insert(index, item.end)
        found.insert(index, item)

    for pattern in (_DIGITS_FIRST, _WORDS_FIRST):
        for match in pattern.finditer(read):
            digits, words = match.group("digits"), match.group("words")
            if words and words_to_number(words) is None and not digits:
                continue  # "several days", "reasonable days": words that are not a number
            if not _covered(starts, ends, match.start()):
                add(_Written(match.start(), match.end(), digits, words, match.group("unit")))
    if found:  # a number without a unit is read only beside a period
        for match in _BARE.finditer(read):
            if _covered(starts, ends, match.start()) or _POINTS_BEFORE.search(read[max(0, match.start() - 24) : match.start()]):
                continue
            if _PERCENT_AFTER.match(read, match.end()):
                continue
            add(_Written(match.start(), match.end(), match.group("digits") or match.group("digits2"), match.group("words") or match.group("words2"), None))
    return found


def _together(read: str, previous: _Written, item: _Written) -> bool:
    """Whether two numbers are written as one statement of periods: only joining and comparing words between them."""
    between = read[previous.end : item.start]
    return len(between) <= _MAX_GLUE and _JOINER.search(between) is not None and _GLUE.fullmatch(between) is not None


def _mention(read: str, item: _Written, unit_text: str, where: list[int] | None) -> DurationMention | None:
    digits = Decimal(item.digits.replace(",", "")) if item.digits else None
    words = words_to_number(item.words) if item.words else None
    if item.words and words is None and digits is None:
        return None
    fortnight = unit_text.strip().lower().startswith("fortnight")
    unit = DurationUnit.WEEK if fortnight else _unit(unit_text)
    readings = tuple(dict.fromkeys(Duration(value * 2 if fortnight else value, unit) for value in (digits, words) if value is not None))
    if not readings:
        return None
    start, end = (where[item.start], where[item.end - 1] + 1) if where is not None else (item.start, item.end)
    surface = read[item.start : item.end] if item.unit else f"{read[item.start : item.end]} {unit_text}"
    if digits is not None and words is not None and digits != words:
        return DurationMention(surface, start, end, None, f"the words say {words} and the digits say {digits}", readings)
    return DurationMention(surface, start, end, readings[0], None, readings)


def parse_durations(text: str | None) -> list[DurationMention]:
    """Every duration mention in the text, in order of appearance, digits or words, with parenthesised restatements
    checked against each other, read from the characters a reader sees (`seen`), offsets into ``text`` as written.

    Periods written together share what is written once: "between 30 and 90 days", "30 to 90 days", "30, 60 or 90
    days" and "at least 30 and no more than 90 days" state two or three periods in days, never only the last (stress
    test, 2026-10-30: "between 30 and 90 days" was read as 90 days alone, a floor, and 60 days a shortfall of code's).
    Two numbers joined by "to", "through" or a dash, or by "and" after "between", are the ends of one range."""
    if not text:
        return []
    return list(_parsed(text))


@lru_cache(maxsize=512)
def _parsed(text: str) -> tuple[DurationMention, ...]:
    read, where = seen(text)
    items = _written(read)
    groups: list[list[_Written]] = []
    for index, item in enumerate(items):
        if index and _together(read, items[index - 1], item):
            groups[-1].append(item)
        else:
            groups.append([item])
    mentions: list[DurationMention] = []
    for group in groups:
        units: list[str | None] = []
        carried: str | None = None
        for item in reversed(group):  # a unit written once belongs to the numbers before it
            carried = item.unit or carried
            units.append(carried)
        units.reverse()
        ranged = len(group) == 2 and (
            _RANGE_JOINER.fullmatch(read[group[0].end : group[1].start]) is not None
            or (
                read[group[0].end : group[1].start].strip().lower() == "and" and _BETWEEN.search(read[max(0, group[0].start - 12) : group[0].start]) is not None
            )
        )
        read_here: list[DurationMention] = []
        for item, unit in zip(group, units, strict=True):
            mention = _mention(read, item, unit, where) if unit else None
            if mention is not None:
                read_here.append(mention)
        if ranged and len(read_here) == 2:
            read_here = [replace(read_here[0], in_range="low"), replace(read_here[1], in_range="high")]
        mentions += read_here
    # Each period's comparison words are its own: read from the period before it to the period after it.
    return tuple(replace(m, window=(mentions[i - 1].end if i else 0, mentions[i + 1].start if i + 1 < len(mentions) else None)) for i, m in enumerate(mentions))


@dataclass(frozen=True)
class ObservedFact:
    """What a verified quote provides, parsed from the quote itself."""

    kind: str  # "notice_period"
    duration: Duration | None
    surface: str
    start: int  # offsets into the quote text
    end: int
    ambiguity: str | None = None


@dataclass(frozen=True)
class GuidanceRule:
    operator: Operator
    duration: Duration
    surface: str
    # A ceiling stated in the same sentence as the floor ("at least 30 but no more than 90 days"): a range.
    maximum: Duration | None = None
    # The other periods the same sentence states as rules of their own ("at least 30 days' notice, or 90 days for
    # enterprise agreements"): which binds is a reading of the guidance, so code reports a shortfall only against them all.
    alternatives: tuple[GuidanceRule, ...] = ()


# A ceiling is never to be read as a floor (the holdout audit of 2026-10-09: "must not exceed 60 days" was): every
# phrasing that bounds from above is listed here, its negated forms with it, so the "not" in them is not a negation.
# The negated forms carry "to be" too ("not to be less than"), and the windows they are matched in have their whitespace
# collapsed (window_before): a line break inside "not less than" read it as a ceiling (bug hunt, 2026-10-09).
_NEGATED = r"(?:no|not|nor|never)(?: to)?(?: be)?"
_MAXIMUM = re.compile(
    rf"(?:≤|<=|at most|at the most|{_NEGATED} (?:more|longer|greater) than|(?:less|shorter|fewer) than or equal to|\bmaximum\b|\bmax\b\.?"
    r"|or less|or fewer|or shorter|or sooner|within|(?:not|never)(?: to)? exceed(?:ing|s)?|capped at|a cap of|limited to|up to"
    r"|no later than|not later than)",
    re.IGNORECASE,
)
_MINIMUM = re.compile(
    rf"(?:≥|>=|at least|at the least|{_NEGATED} (?:less|fewer|shorter) than|(?:more|longer|greater) than or equal to|\bminimum\b"
    r"|\bmin\b\.?|or more|or longer)",
    re.IGNORECASE,
)
# Any word that compares. A guidance period beside one that neither pattern above recognised is not read at all: a
# bare period is a floor only when nothing beside it compares ("maximum 60 days" fell through to a floor; bug hunt).
_COMPARES = re.compile(
    r"\b(?:max\w*|min\w*|limit\w*|cap\w*|ceiling|floor|exceed\w*|sooner|later|earlier|most|least|more|less|fewer|greater|longer"
    r"|shorter|approx\w*|about|around|near(?:ly)?|roughly|up to|within|under|over|above|below|beyond)\b",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")
_TRAILING_MAXIMUM = re.compile(r"\b(?:or less|or fewer|or shorter|or sooner|at the most|at most|maximum|max)\b", re.IGNORECASE)
_TRAILING_MINIMUM = re.compile(r"\b(?:or more|or longer|at the least|at least|minimum|min)\b", re.IGNORECASE)
# "less than 30 days" with no negation before it: an upper bound, stated strictly.
BELOW = re.compile(
    r"(?<!not )(?<!no )(?<!nor )(?<!never )(?<!not be )(?<!never be )(?<!not to be )(?<!never to be )"
    r"\b(?:less than|fewer than|shorter than|under|below)\s*\(?\s*$",
    re.IGNORECASE,
)
# A bare comparative before a guidance period says which side the sentence is about, not which side it allows: "must
# be less than 60 days" is a ceiling, "anything below 30 days requires review" a floor. The predicate decides, and
# code does not read predicates; a period so stated is not a rule.
_STRICT = re.compile(
    r"(?<!not )(?<!no )(?<!nor )(?<!never )(?<!not be )(?<!never be )(?<!not to )(?<!never to )(?<!not to be )(?<!never to be )"
    r"\b(?:(?:less|fewer|shorter|more|longer|greater) than|under|below|over|above|in excess of|exceed(?:ing|s)?|beyond)\s*\(?\s*$",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(?:not|no|never|without|nor|neither|cannot|waives?|waived)\b", re.IGNORECASE)
_EXACT = re.compile(r"(?:exactly|precisely)", re.IGNORECASE)
_LATER_THAN = re.compile(r"(?:no|not) later than", re.IGNORECASE)
_BEFORE = re.compile(r"\b(?:before|prior to|ahead of)\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.;!?])\s+|\n+")
_NOTICE = re.compile(r"\b(?:notice|notif|terminat|cancel)", re.IGNORECASE)
_WINDOW_BEFORE = 40
_WINDOW_AFTER = 24
_PARTIAL_WORD = re.compile(r"^\w+")
_PARTIAL_END = re.compile(r"\w+$")


def window_before(text: str, mention: DurationMention) -> str:
    """The words before a period, back to the period before it, as code reads them (`seen`), whole words only: a window
    cut inside "Termination" read "mination" as a comparing word (`_COMPARES`: "min…"; stress test, 2026-10-30)."""
    start = max(mention.window[0], mention.start - _WINDOW_BEFORE)
    words = text[start : mention.start]
    if start > 0 and text[start - 1].isalnum():
        words = _PARTIAL_WORD.sub("", words)
    return _WHITESPACE.sub(" ", seen_text(words))


def window_after(text: str, mention: DurationMention) -> str:
    """The words after a period, up to the period after it, as code reads them (`seen`)."""
    stop = mention.end + _WINDOW_AFTER if mention.window[1] is None else min(mention.end + _WINDOW_AFTER, mention.window[1])
    words = text[mention.end : stop]
    if stop < len(text) and text[stop].isalnum() and stop > mention.end and text[stop - 1].isalnum():
        words = _PARTIAL_END.sub("", words)
    return _WHITESPACE.sub(" ", seen_text(words))


def without_comparisons(text: str) -> str:
    """The text with its comparison phrases blanked, so the "not" of "not less than" is not read as a negation."""
    return _MINIMUM.sub(" ", _MAXIMUM.sub(" ", text))


def counts_back(text: str, mention: DurationMention) -> bool:
    """Whether the period is counted back from an event ("90 days before the anniversary"): a deadline, not a length of notice."""
    return _BEFORE.search(window_after(text, mention)) is not None


def explicit_operator(text: str, mention: DurationMention) -> Operator | None:
    """The comparison word nearest the duration: the closest phrase in the forty characters before it, or a suffix
    ("or more", "or less") in the characters after it; None when the text states none. "No later than 30 days before"
    is a floor, because the thirty days are counted back from an event."""
    before = window_before(text, mention)
    after = _closing(text, mention)
    if _EXACT.search(before):
        return Operator.EXACT
    candidates: list[tuple[int, Operator]] = []
    for pattern, operator in ((_MAXIMUM, Operator.MAXIMUM), (_MINIMUM, Operator.MINIMUM)):
        for match in pattern.finditer(before):
            distance = len(before) - match.end()
            if pattern is _MAXIMUM and _LATER_THAN.fullmatch(match.group(0)) and _BEFORE.search(after):
                operator = Operator.MINIMUM
            candidates.append((distance, operator))
        suffix = pattern.match(after.lstrip())
        if suffix is not None:
            candidates.append((0, operator))
    # A trailing qualifier a word or two on ("30 days' notice or more", "60 days' notice at the most"): only the phrases
    # that close a period, so "within" or "up to" after it never read as its bound.
    for pattern, operator in ((_TRAILING_MAXIMUM, Operator.MAXIMUM), (_TRAILING_MINIMUM, Operator.MINIMUM)):
        trailing = pattern.search(after)
        if trailing is not None:
            candidates.append((trailing.start(), operator))
    if not candidates:
        return None
    return min(candidates, key=lambda c: c[0])[1]


# A comparison phrase that runs up to the next period opens that period: in "not less than 30 nor more than 60 days",
# "nor more than" is 60's, never a suffix of 30's (stress test, 2026-10-30, once periods written together are read apart).
_OPENS_NEXT = re.compile(
    rf"(?:{_MAXIMUM.pattern}|{_MINIMUM.pattern}|{_EXACT.pattern}|(?:less|fewer|shorter|more|longer|greater) than|under|below|over|above|in excess of"
    r"|exceed(?:ing|s)?|beyond)\s*\(?\s*$",
    re.IGNORECASE,
)


def _closing(text: str, mention: DurationMention) -> str:
    """The words after a period that can close it ("or more", "at the most"): `window_after`, less the phrase that opens
    the next period when that one follows within it."""
    after = window_after(text, mention)
    if mention.window[1] is not None and mention.window[1] <= mention.end + _WINDOW_AFTER:
        opening = _OPENS_NEXT.search(after)
        if opening is not None:
            after = after[: opening.start()]
    return after


def stated_operator(text: str, mention: DurationMention) -> Operator | None:
    """The comparison the text states around a period: "less than 30 days" first (an upper bound), then the nearest
    comparison phrase; None when it states none. One reading for the guidance and the contract alike."""
    if BELOW.search(window_before(text, mention)):
        return Operator.MAXIMUM
    return explicit_operator(text, mention)


def negation_near(text: str, mention: DurationMention, *, after: bool = True) -> str | None:
    """A negation word beside the period, once the comparison phrases that carry one ("not less than") are set aside;
    with ``after=False``, only one before it."""
    found = NEGATION.search(without_comparisons(window_before(text, mention))) or (
        NEGATION.search(without_comparisons(window_after(text, mention))) if after else None
    )
    return found.group(0).lower() if found else None


def _comparison(text: str, mention: DurationMention) -> tuple[Operator | None, bool]:
    """The comparison a guidance sentence states around one of its periods, and whether code reads what stands beside it:
    (operator, True) for a stated comparison, (None, True) for a bare period, (None, False) where a negation code does
    not read stands beside it: before a stated comparison ("must not be at least 60 days"), or on either side of a bare
    period ("more than 60 days are not acceptable"); after a bare comparative ("less than 60 days", see _STRICT); and
    beside any comparing word the patterns did not recognise (_COMPARES). A guidance bound is read as written or not
    read at all."""
    if _STRICT.search(window_before(text, mention)):
        return None, False
    stated = explicit_operator(text, mention)
    if stated is not None:
        return (None, False) if negation_near(text, mention, after=False) else (stated, True)
    if negation_near(text, mention) or _COMPARES.search(f"{window_before(text, mention)} {window_after(text, mention)}"):
        return None, False
    return None, True


def _in_order(low: Duration, high: Duration) -> bool:
    """Whether a floor is no more than a ceiling, where code can tell; a pair it cannot put in order is left to evaluate."""
    if low.unit == high.unit:
        return low.value <= high.value
    low_days, high_days = low.in_days(), high.in_days()
    return low_days is None or high_days is None or low_days <= high_days


def _sentence_rule(text: str, inside: Sequence[DurationMention]) -> GuidanceRule | None:
    """The rule one sentence of the guidance states, or None when code does not read it whole.

    One period with no comparison word is a floor: a notice requirement states the least notice that will do (written
    here once). Where a sentence states several, each is read by its own words (`DurationMention.window`) and a bare one
    is a floor only when it is alone. The ends of a range written as one are its floor and its ceiling ("between 30 and
    90 days", "30-90 days"); a bare period after a stated comparison takes it ("at least 30 days' notice, or 90 days for
    enterprise agreements"); several bare periods ("30, 60 or 90 days"), a period code cannot read (an ambiguous
    "thirty (60) days", a negation it does not read) or floors and ceilings that do not pair are no rule, never part of
    one: until policy-v17 the read periods of such a sentence were kept and the others dropped, so "between 30 and 90
    days" was a floor of 90 (stress test, 2026-10-30). One floor and one ceiling are a range; other periods the
    sentence states are the rule's `alternatives`."""
    if not inside or any(m.duration is None for m in inside):
        return None
    if len(inside) == 1:
        operator, readable = _comparison(text, inside[0])
        assert inside[0].duration is not None
        return GuidanceRule(operator or Operator.MINIMUM, inside[0].duration, inside[0].surface) if readable else None
    read: list[tuple[DurationMention, Operator]] = []
    carried: Operator | None = None
    for mention in inside:
        operator, readable = _comparison(text, mention)
        if not readable:
            return None
        if operator is not None:
            carried = operator
        elif mention.in_range is not None:
            operator = Operator.MINIMUM if mention.in_range == "low" else Operator.MAXIMUM
        elif carried is not None:
            operator = carried
        else:
            return None
        read.append((mention, operator))
    floors = [m for m, op in read if op is Operator.MINIMUM]
    ceilings = [m for m, op in read if op is Operator.MAXIMUM]
    if len(read) == 2 and len(floors) == 1 and len(ceilings) == 1:
        floor, ceiling = floors[0].duration, ceilings[0].duration
        assert floor is not None and ceiling is not None
        return GuidanceRule(Operator.MINIMUM, floor, floors[0].surface, maximum=ceiling) if _in_order(floor, ceiling) else None
    if floors and ceilings:
        return None
    rules = [GuidanceRule(op, m.duration, m.surface) for m, op in read if m.duration is not None]
    return replace(rules[0], alternatives=tuple(rules[1:]))


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    position = 0
    for piece in _SENTENCE_END.split(text):
        if piece:
            start = text.index(piece, position)
            spans.append((start, start + len(piece)))
            position = start + len(piece)
    return spans


def _periods_by_sentence(text: str) -> list[tuple[int, int, list[DurationMention]]]:
    """Each sentence of the text that states a period, with its periods, ambiguous ones included."""
    mentions = parse_durations(text)
    out = []
    for start, end in _sentence_spans(text) if mentions else []:
        inside = [m for m in mentions if start <= m.start < end]
        if inside:
            out.append((start, end, inside))
    return out


def period_sentences(guidance: str | None) -> list[str]:
    """The sentences of the guidance that state a period: what a quote must be about before code compares it with one."""
    if not guidance:
        return []
    return [guidance[start:end] for start, end, _ in _periods_by_sentence(guidance)]


def _topic_tokens(topic: str | None) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", (topic or "").lower()))


def parse_rule(guidance: str | None, topic: str | None = None) -> GuidanceRule | None:
    """The duration the guidance states about the finding's topic, with the comparison the guidance states around it.

    The guidance may carry several durations ("Payment terms are 30 days. Termination needs at least 90 days'
    notice."). The sentence that names the topic, or a notice period, is the one the rule comes from; the first
    sentence with a duration otherwise, an ambiguous one included: a sentence code cannot read is no rule, never
    another sentence's (policy-v4; since policy-v17 a period written "thirty (60) days" no longer hands the choice to
    the payment sentence). Within that sentence the rule is read by `_sentence_rule`."""
    if not guidance:
        return None
    wanted = _topic_tokens(topic)
    best: tuple[int, list[DurationMention]] | None = None
    for start, end, inside in _periods_by_sentence(guidance):
        sentence = guidance[start:end].lower()
        score = 2 * sum(1 for w in wanted if w in sentence) + (1 if _NOTICE.search(sentence) else 0)
        if best is None or score > best[0]:
            best = (score, inside)
    return _sentence_rule(guidance, best[1]) if best is not None else None


def stated_rules(guidance: str | None) -> list[GuidanceRule]:
    """Every period the guidance states, as the rules its sentences state (a range is one rule). `parse_rule` picks the
    one about the topic; this is what it picked from, so a caller can see whether the choice mattered ("at least 30
    days' notice, or 90 days for enterprise agreements" states two floors, and which applies to this agreement is not
    something the text of the guidance settles). A sentence code does not read states no rule here: `unread_periods`
    names its periods."""
    if not guidance:
        return []
    rules: list[GuidanceRule] = []
    for _, _, inside in _periods_by_sentence(guidance):
        rule = _sentence_rule(guidance, inside)
        if rule is not None:
            rules += [replace(rule, alternatives=()), *rule.alternatives]
    return rules


def unread_periods(guidance: str | None) -> list[DurationMention]:
    """The periods of the sentences of the guidance that code does not read whole (`_sentence_rule` is None): a rule it
    cannot read is still a rule, and a pass is not consistent with "the guidance" while one stands unread beside it."""
    if not guidance:
        return []
    return [m for _, _, inside in _periods_by_sentence(guidance) if _sentence_rule(guidance, inside) is None for m in inside]


def _zero(quote: str) -> tuple[str, int, int] | None:
    """A phrase saying the notice is none ("immediately", "without notice"), as read (`seen`), with its offsets in ``quote``."""
    read, where = seen(quote)
    found = _ZERO.search(read)
    if found is None:
        return None
    start, end = (where[found.start()], where[found.end() - 1] + 1) if where is not None else found.span()
    return found.group(0), start, end


_NO_NOTICE = Duration(Decimal(0), DurationUnit.CALENDAR_DAY)


def stated_periods(quote: str) -> set[Duration]:
    """Every period a quote states: its durations, every reading of an ambiguous one ("sixty (20) days" states 60 and 20
    as far as code can tell), and a period of zero days when it also says the notice is none ("on 90 days' notice,
    except that Provider may terminate immediately"). `observed_fact` reads the zero only from a quote with no other
    duration; here it stands beside them, because a carve-out with no number is still a period."""
    periods = {reading for m in parse_durations(quote) for reading in m.readings}
    if _zero(quote) is not None:
        periods.add(_NO_NOTICE)
    return periods


def same_period(a: Duration, b: Duration) -> bool:
    """Whether two periods are one: equal, or the same number of calendar days ("8 weeks" and "56 days", stress test,
    2026-10-30: the model writing a quote's eight weeks as 56 days was told its position is not in the quote)."""
    if a == b:
        return True
    a_days, b_days = a.in_days(), b.in_days()
    return a_days is not None and a_days == b_days


def observed_fact(quote: str, stated: str | None = None) -> ObservedFact | None:
    """The notice period a verified quote provides. When the quote carries several durations, the one the model stated
    (``stated``, its own words) selects among them; the model chooses which, the quote decides what it is. A quote
    with no duration yields no fact, unless it says the notice is none ("immediately", "without notice"), which is a
    period of zero days; a quote whose only candidate is ambiguous yields an ambiguous fact."""
    mentions = parse_durations(quote)
    if not mentions:
        zero = _zero(quote)
        if zero is None:
            return None
        return ObservedFact("notice_period", _NO_NOTICE, *zero)
    chosen = mentions[0]
    if stated and len(mentions) > 1:
        wanted = [reading for m in parse_durations(stated) for reading in m.readings]
        chosen = next((m for m in mentions if m.duration is not None and any(same_period(m.duration, w) for w in wanted)), chosen)
    return ObservedFact("notice_period", chosen.duration, chosen.surface, chosen.start, chosen.end, chosen.ambiguity)


def negation_beside(quote: str, fact: ObservedFact) -> str | None:
    """A negation word beside the period a fact was read from, once the comparison phrases that carry one are set aside
    ("Customer is not required to give thirty (30) days' notice", "Provider waives the 30 days' notice period"); for a
    period of no notice, one before its phrase ("Provider may not terminate without prior notice"). None when there is
    none. Code does not read what a negation negates, so it never claims such a period as what the contract provides.
    "Without" denies the word after it ("without cause upon sixty (60) days' notice" states sixty days), so it counts
    only right before the period ("without thirty (30) days' notice")."""
    mention = next((m for m in parse_durations(quote) if m.start == fact.start and m.end == fact.end), None)
    floor, ceiling = mention.window if mention is not None else (0, None)
    # The rest of the period's sentence, a few words either way: "Thirty (30) days' notice of termination for convenience
    # is not required" denies its period further on than a comparison word stands from the one it qualifies.
    first = max(floor, fact.start - _DENIAL_WINDOW, max((m.end() for m in _SENTENCE_END.finditer(quote, 0, fact.start)), default=0))
    stop = min(len(quote), fact.end + _DENIAL_WINDOW, ceiling if ceiling is not None else len(quote))
    stop = next((m.start() for m in _CLAUSE_END.finditer(quote, fact.end, stop)), stop)
    before = without_comparisons(_WHITESPACE.sub(" ", seen_text(quote[first : fact.start])))
    after = without_comparisons(_WHITESPACE.sub(" ", seen_text(quote[fact.end : stop])))
    found = _DENIES.search(before) or _DENIES.search(after) or (_WITHOUT_IT.search(before) if mention is not None else None)
    return found.group(0).strip().lower() if found else None


_DENIAL_WINDOW = 80
_CLAUSE_END = re.compile(r"[.;!?](?=\s|$)")


# The words that deny what stands beside them, for `negation_beside`: NEGATION less "without", which denies the next word.
_DENIES = re.compile(r"\b(?:not|no|never|nor|neither|cannot|waives?|waived)\b", re.IGNORECASE)
_WITHOUT_IT = re.compile(r"\bwithout\s+(?:(?:the|a|an|any|giving|providing)\s+)?$", re.IGNORECASE)


@dataclass(frozen=True)
class PolicyEvaluation:
    outcome: str  # pass | needs_review | ambiguous | incomparable
    reason: str
    observed: ObservedFact | None
    rule: GuidanceRule | None


def evaluate(observed: ObservedFact | None, rule: GuidanceRule | None, week: BusinessWeek | None = None) -> PolicyEvaluation:
    """Compare the period a verified quote provides with the guidance's rule. Periods in one unit, or in units that
    convert exactly (days and weeks), compare as numbers; any other pair is placed on the calendar (`_on_the_calendar`),
    where ``week`` is the contract's own definition of a Business Day, if it gives one (`business_week`)."""
    if rule is None:
        return PolicyEvaluation("incomparable", "the guidance states no duration to compare with", observed, rule)
    if observed is None:
        return PolicyEvaluation("incomparable", "the verified quote states no duration", observed, rule)
    if observed.duration is None:
        return PolicyEvaluation("ambiguous", f"the quote is internally inconsistent: {observed.ambiguity}", observed, rule)
    left, right = observed.duration, rule.duration
    bounds = [d for d in (right, rule.maximum) if d is not None]
    if not all(_exact_pair(left, other) for other in bounds):
        return _on_the_calendar(observed, rule, week)
    # One unit for every number compared: the raw values when all three periods share one, calendar days otherwise.
    # Until policy-v17 the floor was converted and the ceiling kept raw whenever its unit was the quote's, so 6 weeks
    # against "at least 14 days and no more than 8 weeks" was compared as 42 days against 14 and 8 (stress test, 2026-10-30).
    one_unit = all(d.unit == left.unit for d in bounds)

    def number(duration: Duration) -> Decimal:
        value = duration.value if one_unit else duration.in_days()
        assert value is not None  # an exact pair
        return value

    a, b = number(left), number(right)
    left_unit, right_unit = left.unit.value.replace("_", " "), right.unit.value.replace("_", " ")
    if rule.maximum is not None:
        top = number(rule.maximum)
        ok = b <= a <= top
        top_unit = rule.maximum.unit.value.replace("_", " ")
        between = (
            f"{right.value} and {rule.maximum.value} {right_unit}s"
            if rule.maximum.unit == right.unit
            else f"{right.value} {right_unit}s and {rule.maximum.value} {top_unit}s"
        )
        reason = f"the contract provides {left.value} {left_unit}s; the guidance requires between {between}"
        return PolicyEvaluation("pass" if ok else "needs_review", reason, observed, rule)
    if rule.operator is Operator.MINIMUM:
        ok, verb = a >= b, "at least"
    elif rule.operator is Operator.MAXIMUM:
        ok, verb = a <= b, "at most"
    else:
        ok, verb = a == b, "exactly"
    reason = f"the contract provides {left.value} {left_unit}s; the guidance requires {verb} {right.value} {right_unit}s"
    return PolicyEvaluation("pass" if ok else "needs_review", reason, observed, rule)


# ----------------------------------------------------------------------------- periods on the calendar (policy-v10)
#
# The legal pilot's H4-Q5 (2026-10-14): a contract's "30 days" against guidance of "at least 30 Business Days" came back
# incomparable, and the model's "meets the guidance" stood (policy-v9 sends it to review). It is not a judgement call:
# however the days fall, 30 Business Days are at least 40 calendar days when a Business Day is a weekday, so 30 calendar
# days fall short. What code needs to say so is the contract's own definition of a Business Day; without it, it says
# what follows if a Business Day is a weekday, and leaves the comparison to a person.


@dataclass(frozen=True)
class BusinessWeek:
    """What the contract says a Business Day is, read by code from its own definition: at most ``days`` of any seven
    can be Business Days ("any day other than a Saturday, a Sunday or a public holiday" is at most five). A source
    fact, with the sentence and the place it was read from; never assumed."""

    days: int
    sentence: str
    where: str  # "§1.1", or the heading of the section when it has no number


_DEFINED = re.compile(
    r"\b(?:business|working)\s+days?\b[\"”’']?\s*(?:\([^)]{0,80}\)\s*)?(?:means|shall mean|is defined as|has the meaning|refers to|shall be)\b",
    re.IGNORECASE,
)
_WEEKEND_DAY = re.compile(r"\b(saturday|sunday|weekend)s?\b", re.IGNORECASE)
_EXCLUDING = re.compile(r"\b(?:other than|excluding|except(?: for)?|save|not (?:a|an|being)|which is not|that is not|is not)\b", re.IGNORECASE)
_INCLUDING = re.compile(r"\binclud", re.IGNORECASE)
_DEFINITION_SPAN = 400  # characters of a definition read past its defining verb
_CLAUSE_OPENING = re.compile(r"(\d+(?:\.\d+)+)\.?\s")
# The days a definition names as Business Days, before anything it excludes: a run of them ("Monday to Friday", "Sunday
# through Thursday") or a list ("a Monday, Tuesday, Wednesday, Thursday or Friday"). Until the first-visitor acceptance
# test (2026-10-14) only "Monday to Friday" was read; a manufacturing agreement that listed its five weekdays was said
# by code not to define a Business Day by the days of the week, and two periods went uncompared.
_WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DAY = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?"
_DAY_RUN = re.compile(rf"\b{_DAY}\s*(?:to|through|thru|until|-|–|—)\s*{_DAY}\b", re.IGNORECASE)
_DAY_NAMED = re.compile(rf"\b{_DAY}\b", re.IGNORECASE)
# A definition's list of exclusions may run on past a semicolon: "other than (a) a Saturday; (b) a Sunday; or (c) …".
_LIST_GOES_ON = re.compile(r";\s*(?:(?:and|or)\s+)?\([a-z0-9]{1,4}\)", re.IGNORECASE)


def _definition_at(text: str, start: int) -> str:
    """The definition sentence that opens at ``start``: up to its end, or ``_DEFINITION_SPAN`` characters. A semicolon
    that goes on to the next item of a lettered list does not end it."""
    tail = text[start : start + _DEFINITION_SPAN]
    end = next((m for m in re.finditer(r"[.;](?:\s|$)|\n", tail) if not _LIST_GOES_ON.match(tail, m.start())), None)
    head_start = max(text.rfind("\n", 0, start), text.rfind(". ", 0, start) + 1, 0)
    return " ".join(text[head_start : start + (end.end() if end else len(tail))].split())


def _clause_where(text: str, start: int, where: str) -> str:
    """The clause a definition sits in when its line opens with a clause number ("1.2 Interpretation. … 'days' …" is
    §1.2), else the section it was read from."""
    clause = _CLAUSE_OPENING.match(text[text.rfind("\n", 0, start) + 1 : start].strip() + " ")
    return f"§{clause.group(1)}" if clause else where


def _named_days(sentence: str) -> int | None:
    """How many days of the week the definition names as Business Days, read between its defining verb and the first
    thing it excludes: a run of days counted inclusively around the week ("Sunday to Thursday" is five), or a list of two
    or more. What it then excludes (holidays, a bank closing) only takes days away, so the count stays an upper bound."""
    verb = _DEFINED.search(sentence)
    named = sentence[verb.end() if verb else 0 :]
    excluded = _EXCLUDING.search(named)
    named = named[: excluded.start()] if excluded else named
    run = _DAY_RUN.search(named)
    if run:
        first, last = _WEEK.index(run.group(1).casefold()), _WEEK.index(run.group(2).casefold())
        return (last - first) % 7 + 1
    days = {match.group(1).casefold() for match in _DAY_NAMED.finditer(named)}
    return len(days) if len(days) >= 2 else None


def _week_of(sentence: str) -> int | None:
    """How many days of any seven the definition allows to be Business Days: as many as it names (a run or a list of
    days), five when it excludes Saturdays and Sundays (or weekends), six when it excludes Sundays only; None for
    anything else, a definition by banks being open, or one that mentions including a weekend day."""
    if _INCLUDING.search(sentence):
        return None
    listed = _named_days(sentence)
    if listed is not None:
        return listed
    first = _WEEKEND_DAY.search(sentence)
    if first is None or not _EXCLUDING.search(sentence, 0, first.start()):
        return None
    named = {match.group(1).casefold() for match in _WEEKEND_DAY.finditer(sentence)}
    if "weekend" in named or {"saturday", "sunday"} <= named:
        return 5
    return 6 if named == {"sunday"} else None


def business_week(sections: Iterable[tuple[str, str]]) -> BusinessWeek | None:
    """The contract's own definition of a Business Day (or Working Day) as ``(where, text)`` sections give it, when it
    fixes how many days of a week can be one; None when the contract has none, has one that does not say (a day on
    which banks are open in London), or has two that disagree."""
    found: list[BusinessWeek | None] = []
    for where, text in sections:
        for match in _DEFINED.finditer(text):
            sentence = _definition_at(text, match.start())
            days = _week_of(sentence)
            # "1.1 "Business Day" means …" inside §1 is cited as §1.1, where the reader finds it.
            found.append(BusinessWeek(days, sentence, _clause_where(text, match.start(), where)) if days is not None else None)
    if not found or None in found or len({week.days for week in found if week is not None}) != 1:
        return None
    return found[0]


@dataclass(frozen=True)
class Span:
    """The calendar days a period can take: at least ``lo``, at most ``hi`` (None: no upper bound code knows, as for
    business days, which public holidays lengthen)."""

    lo: Decimal
    hi: Decimal | None

    def words(self) -> str:
        if self.hi is None:
            return f"at least {self.lo} calendar days"
        return f"{self.lo} calendar days" if self.lo == self.hi else f"{self.lo} to {self.hi} calendar days"


# Start dates from 2072 to 2127: every arrangement of month lengths and leap years, the non-leap 2100 among them, so a
# span of up to fifty years is read on every calendar it can fall on.
_FIRST_START, _LAST_START = date(2072, 1, 1), date(2128, 1, 1)
_MAX_MONTHS = 600


def _add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))  # 31 January + 1 month: 28 or 29 February


@lru_cache(maxsize=128)
def _months_span(months: int) -> Span:
    """The fewest and the most calendar days ``months`` months can take, over every start date: one month is 28 to 31."""
    lo = hi = None
    day = _FIRST_START
    while day < _LAST_START:
        days = (_add_months(day, months) - day).days
        lo, hi = days if lo is None else min(lo, days), days if hi is None else max(hi, days)
        day += timedelta(days=1)
    assert lo is not None and hi is not None
    return Span(Decimal(lo), Decimal(hi))


def _whole(value: Decimal) -> int | None:
    return int(value) if value == value.to_integral_value() and value >= 0 else None


def calendar_days(duration: Duration, week: BusinessWeek | None) -> Span | None:
    """The calendar days a period can take, or None when code cannot place it: business days with no definition of a
    Business Day that fixes the days of the week, a fraction of a month or of a business day, or a span past fifty years."""
    days = duration.in_days()
    if days is not None:
        return Span(days, days)
    count = _whole(duration.value)
    if count is None:
        return None
    if duration.unit in (DurationUnit.MONTH, DurationUnit.YEAR):
        months = count * (12 if duration.unit is DurationUnit.YEAR else 1)
        return _months_span(months) if 0 < months <= _MAX_MONTHS else (Span(Decimal(0), Decimal(0)) if months == 0 else None)
    if week is None:
        return None
    if count == 0:
        return Span(Decimal(0), Decimal(0))
    # In any L consecutive days at most d·⌊L/7⌋ + min(L mod 7, d) are business days, so N of them take at least
    # N + (7 − d)·⌊(N − 1)/d⌋ calendar days; public holidays only add days, so there is no upper bound.
    return Span(Decimal(count + (7 - week.days) * ((count - 1) // week.days)), None)


def _exact_pair(a: Duration, b: Duration) -> bool:
    return a.unit == b.unit or (a.in_days() is not None and b.in_days() is not None)


def _say(duration: Duration) -> str:
    unit = duration.unit.value.replace("_", " ")
    return f"{duration.value} {unit}" if duration.value == 1 else f"{duration.value} {unit}s"


def _placed(duration: Duration, span: Span, week: BusinessWeek | None) -> str:
    """'30 business days (at least 40 calendar days, a Business Day as §1.1 defines it)'; a period already in days as is."""
    if duration.in_days() is not None:
        return _say(duration)
    basis = f", a Business Day as {week.where} defines it" if duration.unit is DurationUnit.BUSINESS_DAY and week is not None else ""
    return f"{_say(duration)} ({span.words()}{basis})"


def _on_the_calendar(observed: ObservedFact, rule: GuidanceRule, week: BusinessWeek | None) -> PolicyEvaluation:
    """Two periods in units that do not convert, compared by the calendar days each can take. A pass only when the
    contract's period meets the guidance however the days fall; a shortfall only when it misses it however they fall;
    otherwise incomparable, with the ranges in the reason."""
    assert observed.duration is not None
    left, right, top_unit = observed.duration, rule.duration, rule.maximum
    a, b = calendar_days(left, week), calendar_days(right, week)
    top = calendar_days(top_unit, week) if top_unit is not None else None
    if a is None or b is None or (top_unit is not None and top is None):
        return PolicyEvaluation("incomparable", _unplaced(observed, rule), observed, rule)
    contract = f"the contract provides {_placed(left, a, week)}"
    if top_unit is not None and top is not None:
        required = f"the guidance requires between {_placed(right, b, week)} and {_placed(top_unit, top, week)}"
        meets = b.hi is not None and a.lo >= b.hi and a.hi is not None and a.hi <= top.lo
        misses = (a.hi is not None and a.hi < b.lo) or (top.hi is not None and a.lo > top.hi)
    elif rule.operator is Operator.MINIMUM:
        required = f"the guidance requires at least {_placed(right, b, week)}"
        meets = b.hi is not None and a.lo >= b.hi
        misses = a.hi is not None and a.hi < b.lo
    elif rule.operator is Operator.MAXIMUM:
        required = f"the guidance requires at most {_placed(right, b, week)}"
        meets = a.hi is not None and a.hi <= b.lo
        misses = b.hi is not None and a.lo > b.hi
    else:
        required = f"the guidance requires exactly {_placed(right, b, week)}"
        meets = a.lo == a.hi == b.lo == b.hi
        misses = (a.hi is not None and a.hi < b.lo) or (b.hi is not None and b.hi < a.lo)
    if misses:
        return PolicyEvaluation("needs_review", f"{contract}; {required}, so it falls short on any calendar", observed, rule)
    if meets:
        return PolicyEvaluation("pass", f"{contract}; {required}", observed, rule)
    return PolicyEvaluation(
        "incomparable", f"{contract}; {required}: whether it meets the guidance depends on the dates it falls on, which code does not know", observed, rule
    )


def _unplaced(observed: ObservedFact, rule: GuidanceRule) -> str:
    """Why code could not place a period, and, for business days the contract does not define, what would follow if a
    Business Day were a weekday: said beside the reason, never decided on."""
    assert observed.duration is not None
    left, right = observed.duration, rule.duration
    reason = f"{left.unit.value.replace('_', ' ')}s cannot be compared with {right.unit.value.replace('_', ' ')}s"
    if DurationUnit.BUSINESS_DAY not in {d.unit for d in (left, right, rule.maximum) if d is not None}:
        return reason
    # Said of what code read, never of the contract: a definition code cannot read is still a definition (acceptance
    # test, 2026-10-14: "the contract does not define a Business Day by the days of the week" over one that listed them).
    reason += ": code could not read from the contract which days of the week are Business Days"
    a, b = calendar_days(left, _WEEKDAYS), calendar_days(right, _WEEKDAYS)
    if a is not None and b is not None and _on_the_calendar(observed, rule, _WEEKDAYS).outcome == "needs_review":
        reason += f". If a Business Day is a weekday, the contract provides {_placed(left, a, None)} against {_placed(right, b, None)}, and falls short"
    return reason


_WEEKDAYS = BusinessWeek(5, "", "")  # the reading a reason may name as an "if", never one a decision rests on


# ----------------------------------------------------------------------------- what "days" means in this contract (policy-v10)
#
# A contract may say what its bare "days" are: "a reference in this Agreement to 'days' is to Business Days" (an
# unfamiliar licence, 2026-10-14: its royalty reports are due "within forty-five (45) days", and code reported "the
# contract provides 45 calendar days"), or "the word 'days' means 'calendar days'". Where it says Business Days, a quote's
# bare "days" are read as Business Days; a quote that says "calendar days" is read as it says. The guidance is the
# reader's own words, not the contract's, and is read as written.


@dataclass(frozen=True)
class DayConvention:
    """What the contract's bare "days" are, read by code from its own words, with the place it says so."""

    unit: DurationUnit  # BUSINESS_DAY or CALENDAR_DAY
    sentence: str
    where: str

    @property
    def note(self) -> str:
        return f'"days" are {"Business Days" if self.unit is DurationUnit.BUSINESS_DAY else "calendar days"} in this contract ({self.where})'


_DAYS_ARE = re.compile(
    r"[\"“'‘]days?[\"”'’]\s*(?:shall\s+)?(?:is|are|means?|mean|refers?\s+to|shall\s+be\s+(?:construed|read)\s+as)\s+(?:to\s+|a\s+reference\s+to\s+)?"
    r"[\"“'‘]?(business|working|calendar)\s+days?\b",
    re.IGNORECASE,
)


def day_convention(sections: Iterable[tuple[str, str]]) -> DayConvention | None:
    """The contract's own statement of what its bare "days" are; None when it makes none, or two that disagree."""
    found: list[DayConvention] = []
    for where, text in sections:
        for match in _DAYS_ARE.finditer(text):
            unit = DurationUnit.CALENDAR_DAY if match.group(1).casefold() == "calendar" else DurationUnit.BUSINESS_DAY
            found.append(DayConvention(unit, _definition_at(text, match.start()), _clause_where(text, match.start(), where)))
    if not found or len({c.unit for c in found}) != 1:
        return None
    return found[0]


def _bare_days(surface: str) -> bool:
    return (
        re.search(r"\bdays?\b", surface, re.IGNORECASE) is not None and re.search(r"\b(?:calendar|business|working)\s+days?\b", surface, re.IGNORECASE) is None
    )


def read_as_the_contract_does(fact: ObservedFact, convention: DayConvention | None) -> ObservedFact:
    """The fact with its bare "days" read as the contract defines them; unchanged otherwise."""
    if convention is None or convention.unit is not DurationUnit.BUSINESS_DAY or fact.duration is None:
        return fact
    if fact.duration.unit is not DurationUnit.CALENDAR_DAY or not _bare_days(fact.surface):
        return fact
    return ObservedFact(fact.kind, Duration(fact.duration.value, DurationUnit.BUSINESS_DAY), fact.surface, fact.start, fact.end, fact.ambiguity)


def periods_as_the_contract_reads(quote: str, convention: DayConvention | None) -> set[Duration]:
    """`stated_periods`, with bare "days" read as the contract defines them."""
    if convention is None or convention.unit is not DurationUnit.BUSINESS_DAY:
        return stated_periods(quote)
    periods: set[Duration] = set()
    for mention in parse_durations(quote):
        for value in mention.readings:
            reading = read_as_the_contract_does(ObservedFact("notice_period", value, mention.surface, mention.start, mention.end), convention)
            assert reading.duration is not None
            periods.add(reading.duration)
    if _zero(quote) is not None:
        periods.add(_NO_NOTICE)
    return periods
