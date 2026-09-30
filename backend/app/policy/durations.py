"""Durations as contracts write them, parsed by code, with their unit and their doubts.

    "thirty (30) days"            → 30 calendar days
    "20 Working Days"             → 20 business days
    "twenty-one (21) days"        → 21 calendar days
    "twenty-one (30) days"        → ambiguous: the words and the digits disagree
    "one month"                   → 1 month, which is not 30 days
    "promptly"                    → nothing: no duration is stated

Numbers are Decimal, never float. Weeks convert to days exactly (7); months and years do not convert, and business
days are not calendar days: such comparisons are reported as incomparable rather than guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


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
    """One duration as the text wrote it. ``duration`` is None when the mention is ambiguous."""

    surface: str
    start: int
    end: int
    duration: Duration | None
    ambiguity: str | None = None


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
# Number words only, longest first, so "within thirty (30) days" reads "thirty" and never "within thirty".
_NUMBER_WORD = "|".join(sorted([*_ONES, *_TENS, "hundred", "thousand"], key=len, reverse=True))
_WORD = rf"(?:a|an|(?:{_NUMBER_WORD})(?:[\s-]+(?:and[\s-]+)?(?:{_NUMBER_WORD}))*)"
_NUMBER = r"\d+(?:\.\d+)?"
_UNIT = r"(?P<unit>calendar\s+days?|business\s+days?|working\s+days?|days?|weeks?|months?|years?)"
# digits, optionally followed by the words in parentheses: "30 days", "30 (thirty) days"
_DIGITS_FIRST = re.compile(rf"(?<![\w.])(?P<digits>{_NUMBER})\s*(?:\(\s*(?P<words>{_WORD})\s*\))?\s*{_UNIT}\b", re.IGNORECASE)
# words, optionally followed by the digits in parentheses: "thirty days", "thirty (30) days", "twenty-one (21) days"
_WORDS_FIRST = re.compile(rf"\b(?P<words>{_WORD})\s*(?:\(\s*(?P<digits>{_NUMBER})\s*\))?\s+{_UNIT}\b", re.IGNORECASE)
_ARTICLE = re.compile(r"^(?:a|an|the)$", re.IGNORECASE)


def words_to_number(text: str) -> Decimal | None:
    """ "thirty", "forty-five", "twenty one", "one hundred twenty", "a" (as in "a month") → the number, else None."""
    tokens = [t for t in re.split(r"[\s-]+", text.strip().lower()) if t and t != "and"]
    if not tokens:
        return None
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


def _mention(match: re.Match[str]) -> DurationMention | None:
    digits_text, words_text = match.group("digits"), match.group("words")
    digits = Decimal(digits_text) if digits_text else None
    words = words_to_number(words_text) if words_text else None
    if words_text and words is None and digits is None:
        return None  # "several days", "reasonable days": words that are not a number
    surface = match.group(0)
    unit = _unit(match.group("unit"))
    if digits is not None and words is not None and digits != words:
        return DurationMention(surface, match.start(), match.end(), None, f"the words say {words} and the digits say {digits}")
    value = digits if digits is not None else words
    if value is None:
        return None
    return DurationMention(surface, match.start(), match.end(), Duration(value, unit))


def parse_durations(text: str | None) -> list[DurationMention]:
    """Every duration mention in the text, in order of appearance, digits or words, with parenthesised restatements
    checked against each other."""
    if not text:
        return []
    mentions: dict[int, DurationMention] = {}
    for pattern in (_DIGITS_FIRST, _WORDS_FIRST):
        for match in pattern.finditer(text):
            mention = _mention(match)
            if mention is None:
                continue
            # The two patterns can see the same mention ("thirty (30) days"); the one that starts earlier covers it.
            if any(m.start <= mention.start < m.end for m in mentions.values()):
                continue
            mentions[mention.start] = mention
    return [mentions[start] for start in sorted(mentions)]


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


_MAXIMUM = re.compile(
    r"(?:≤|<=|at most|no more than|not more than|maximum of|a maximum|or less|or fewer|or shorter|within"
    r"|no longer than|not longer than|not to exceed|up to|no later than|not later than)",
    re.IGNORECASE,
)
_MINIMUM = re.compile(r"(?:≥|>=|at least|no less than|not less than|minimum of|a minimum|or more|or longer|not shorter than)", re.IGNORECASE)
_EXACT = re.compile(r"(?:exactly|precisely)", re.IGNORECASE)


def parse_rule(guidance: str | None) -> GuidanceRule | None:
    """The first duration in the guidance with the comparison the guidance states around it. A notice requirement with no
    comparison word is a floor ("30 days' notice" means at least 30), which is written down here, not assumed elsewhere."""
    mentions = [m for m in parse_durations(guidance) if m.duration is not None]
    if not mentions or guidance is None:
        return None
    mention = mentions[0]
    window = guidance[max(0, mention.start - 40) : mention.end + 20]
    if _EXACT.search(window):
        operator = Operator.EXACT
    elif _MAXIMUM.search(window):
        operator = Operator.MAXIMUM
    elif _MINIMUM.search(window):
        operator = Operator.MINIMUM
    else:
        operator = Operator.MINIMUM
    assert mention.duration is not None
    return GuidanceRule(operator, mention.duration, mention.surface)


def observed_fact(quote: str, stated: str | None = None) -> ObservedFact | None:
    """The notice period a verified quote provides. When the quote carries several durations, the one the model stated
    (``stated``, its own words) selects among them; the model chooses which, the quote decides what it is. A quote
    with no duration yields no fact; a quote whose only candidate is ambiguous yields an ambiguous fact."""
    mentions = parse_durations(quote)
    if not mentions:
        return None
    chosen = mentions[0]
    if stated and len(mentions) > 1:
        wanted = [m.duration for m in parse_durations(stated) if m.duration is not None]
        for mention in mentions:
            if mention.duration is not None and mention.duration in wanted:
                chosen = mention
                break
    return ObservedFact("notice_period", chosen.duration, chosen.surface, chosen.start, chosen.end, chosen.ambiguity)


@dataclass(frozen=True)
class PolicyEvaluation:
    outcome: str  # pass | needs_review | ambiguous | incomparable
    reason: str
    observed: ObservedFact | None
    rule: GuidanceRule | None


def evaluate(observed: ObservedFact | None, rule: GuidanceRule | None) -> PolicyEvaluation:
    if rule is None:
        return PolicyEvaluation("incomparable", "the guidance states no duration to compare with", observed, rule)
    if observed is None:
        return PolicyEvaluation("incomparable", "the verified quote states no duration", observed, rule)
    if observed.duration is None:
        return PolicyEvaluation("ambiguous", f"the quote is internally inconsistent: {observed.ambiguity}", observed, rule)
    left, right = observed.duration, rule.duration
    if left.unit != right.unit:
        left_days, right_days = left.in_days(), right.in_days()
        if left_days is None or right_days is None:
            return PolicyEvaluation(
                "incomparable", f"{left.unit.value.replace('_', ' ')}s cannot be compared with {right.unit.value.replace('_', ' ')}s", observed, rule
            )
        a, b = left_days, right_days
    else:
        a, b = left.value, right.value
    if rule.operator is Operator.MINIMUM:
        ok, verb = a >= b, "at least"
    elif rule.operator is Operator.MAXIMUM:
        ok, verb = a <= b, "at most"
    else:
        ok, verb = a == b, "exactly"
    left_unit, right_unit = left.unit.value.replace("_", " "), right.unit.value.replace("_", " ")
    reason = f"the contract provides {left.value} {left_unit}s; the guidance requires {verb} {right.value} {right_unit}s"
    return PolicyEvaluation("pass" if ok else "needs_review", reason, observed, rule)
