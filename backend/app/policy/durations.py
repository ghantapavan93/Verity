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

import calendar
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache


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
# Atomic: a run of number words is consumed once and never re-split by backtracking, so a hostile guidance of
# "one and one and …" is linear in the run, not exponential (hostile review, 2026-10-01).
_WORD = rf"(?:a|an|(?>(?:{_NUMBER_WORD})(?:[\s-]+(?:and[\s-]+)?(?:{_NUMBER_WORD}))*))"
_NUMBER = r"\d+(?:\.\d+)?"
_UNIT = r"(?P<unit>calendar\s+days?|business\s+days?|working\s+days?|days?|weeks?|fortnights?|months?|years?)"
# digits, optionally followed by the words in parentheses: "30 days", "30 (thirty) days"
# "30 days", "30 (thirty) days", "30-day"
_DIGITS_FIRST = re.compile(rf"(?<![\w.])(?P<digits>{_NUMBER})[\s-]*(?:\(\s*(?P<words>{_WORD})\s*\))?[\s-]*{_UNIT}\b", re.IGNORECASE)
# words, optionally followed by the digits in parentheses: "thirty days", "thirty (30) days", "twenty-one (21) days"
_WORDS_FIRST = re.compile(rf"\b(?P<words>{_WORD})\s*(?:\(\s*(?P<digits>{_NUMBER})\s*\))?[\s-]+{_UNIT}\b", re.IGNORECASE)
# "not less than 30 nor more than 60 days", "30 to 60 days", "30-60 days": two durations sharing one unit.
_RANGE = re.compile(rf"(?<![\w.])(?P<lo>{_NUMBER})\s*(?:(?:nor|or|and)\s+(?:more|less)\s+than|to|-|–)\s*(?P<hi>{_NUMBER})\s*{_UNIT}\b", re.IGNORECASE)
# Termination with no notice at all: a zero-day notice period, so a floor in the guidance can be compared with it.
_ZERO = re.compile(r"\b(?:immediately|with immediate effect|without (?:prior )?notice|no notice)\b", re.IGNORECASE)
# The words-first pattern is only worth running when a unit word exists at all.
_ANY_UNIT = re.compile(_UNIT, re.IGNORECASE)
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
    unit_text = match.group("unit")
    fortnight = unit_text.strip().lower().startswith("fortnight")
    unit = DurationUnit.WEEK if fortnight else _unit(unit_text)
    if digits is not None and words is not None and digits != words:
        return DurationMention(surface, match.start(), match.end(), None, f"the words say {words} and the digits say {digits}")
    value = digits if digits is not None else words
    if value is None:
        return None
    return DurationMention(surface, match.start(), match.end(), Duration(value * 2 if fortnight else value, unit))


def parse_durations(text: str | None) -> list[DurationMention]:
    """Every duration mention in the text, in order of appearance, digits or words, with parenthesised restatements
    checked against each other."""
    if not text:
        return []
    mentions: dict[int, DurationMention] = {}
    for match in _RANGE.finditer(text):
        unit = _unit(match.group("unit"))
        # Both numbers share the unit; each mention ends where the range ends, so the later patterns skip it whole.
        for name in ("lo", "hi"):
            start = match.start(name)
            surface = text[start : match.end()] if name == "lo" else match.group(name) + " " + match.group("unit")
            mentions[start] = DurationMention(surface, start, match.end(), Duration(Decimal(match.group(name)), unit))
    patterns = (_DIGITS_FIRST, _WORDS_FIRST) if _ANY_UNIT.search(text) else ()
    for pattern in patterns:
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
    # A ceiling stated in the same sentence as the floor ("at least 30 but no more than 90 days"): a range.
    maximum: Duration | None = None


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


def window_before(text: str, mention: DurationMention) -> str:
    return _WHITESPACE.sub(" ", text[max(0, mention.start - _WINDOW_BEFORE) : mention.start])


def window_after(text: str, mention: DurationMention) -> str:
    return _WHITESPACE.sub(" ", text[mention.end : mention.end + _WINDOW_AFTER])


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
    after = window_after(text, mention)
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


def stated_operator(text: str, mention: DurationMention) -> Operator | None:
    """The comparison the text states around a period: "less than 30 days" first (an upper bound), then the nearest
    comparison phrase; None when it states none. One reading for the guidance and the contract alike."""
    if BELOW.search(window_before(text, mention)):
        return Operator.MAXIMUM
    return explicit_operator(text, mention)


def negation_near(text: str, mention: DurationMention, *, after: bool = True) -> str | None:
    """A negation word beside the period, once the comparison phrases that carry one ("not less than") are set aside;
    with ``after=False``, only one before it."""
    found = NEGATION.search(without_comparisons(window_before(text, mention))) or (NEGATION.search(window_after(text, mention)) if after else None)
    return found.group(0).lower() if found else None


def _operator_near(text: str, mention: DurationMention) -> Operator | None:
    """The comparison a guidance sentence states around its duration. A duration with no comparison word is a floor:
    a notice requirement states the least notice that will do (written here once). None where a negation code does not
    read stands beside it: before a stated comparison ("must not be at least 60 days"), or on either side of a bare
    period ("more than 60 days are not acceptable"); after a bare comparative ("less than 60 days", see _STRICT); and
    beside any comparing word the patterns did not recognise (_COMPARES). A guidance bound is read as written or not
    read at all."""
    if _STRICT.search(window_before(text, mention)):
        return None
    stated = explicit_operator(text, mention)
    if stated is not None:
        return None if negation_near(text, mention, after=False) else stated
    if negation_near(text, mention) or _COMPARES.search(f"{window_before(text, mention)} {window_after(text, mention)}"):
        return None
    return Operator.MINIMUM


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    position = 0
    for piece in _SENTENCE_END.split(text):
        if piece:
            start = text.index(piece, position)
            spans.append((start, start + len(piece)))
            position = start + len(piece)
    return spans


def period_sentences(guidance: str | None) -> list[str]:
    """The sentences of the guidance that state a period: what a quote must be about before code compares it with one."""
    if not guidance:
        return []
    starts = [m.start for m in parse_durations(guidance) if m.duration is not None]
    return [guidance[start:end] for start, end in _sentence_spans(guidance) if any(start <= s < end for s in starts)]


def _topic_tokens(topic: str | None) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", (topic or "").lower()))


def parse_rule(guidance: str | None, topic: str | None = None) -> GuidanceRule | None:
    """The duration the guidance states about the finding's topic, with the comparison the guidance states around it.

    The guidance may carry several durations ("Payment terms are 30 days. Termination needs at least 90 days'
    notice."). The sentence that names the topic, or a notice period, is the one the rule comes from; the first
    sentence with a duration otherwise. Within that sentence a floor and a ceiling together are a range. A notice
    requirement with no comparison word is a floor ("30 days' notice" means at least 30), written down here, not
    assumed elsewhere."""
    if not guidance:
        return None
    mentions = [m for m in parse_durations(guidance) if m.duration is not None]
    if not mentions:
        return None
    sentences = _sentence_spans(guidance)
    wanted = _topic_tokens(topic)
    best: tuple[int, int, list[DurationMention]] | None = None
    for order, (start, end) in enumerate(sentences):
        inside = [m for m in mentions if start <= m.start < end]
        if not inside:
            continue
        sentence = guidance[start:end].lower()
        score = 2 * sum(1 for w in wanted if w in sentence) + (1 if _NOTICE.search(sentence) else 0)
        if best is None or score > best[0]:
            best = (score, order, inside)
    assert best is not None
    chosen = best[2]
    operators = [(m, op) for m, op in ((m, _operator_near(guidance, m)) for m in chosen) if op is not None]
    if not operators:
        return None  # the topic's sentence negates its period in a way code does not read: no rule, never another sentence's
    floors = [m for m, op in operators if op is Operator.MINIMUM]
    ceilings = [m for m, op in operators if op is Operator.MAXIMUM]
    if floors and ceilings:
        floor, ceiling = floors[0], ceilings[0]
        assert floor.duration is not None and ceiling.duration is not None
        return GuidanceRule(Operator.MINIMUM, floor.duration, floor.surface, maximum=ceiling.duration)
    mention, operator = operators[0]
    assert mention.duration is not None
    return GuidanceRule(operator, mention.duration, mention.surface)


def stated_rules(guidance: str | None) -> list[GuidanceRule]:
    """Every period the guidance states, each as a rule of its own with the comparison word nearest it. `parse_rule`
    picks the one about the topic; this is what it picked from, so a caller can see whether the choice mattered
    ("at least 30 days' notice, or 90 days for enterprise agreements" states two floors, and which applies to this
    agreement is not something the text of the guidance settles). A period whose negation code does not read is not
    a rule."""
    if not guidance:
        return []
    rules: list[GuidanceRule] = []
    for mention in parse_durations(guidance):
        operator = _operator_near(guidance, mention)
        if mention.duration is not None and operator is not None:
            rules.append(GuidanceRule(operator, mention.duration, mention.surface))
    return rules


def stated_periods(quote: str) -> set[Duration]:
    """Every period a quote states: its durations, and a period of zero days when it also says the notice is none
    ("on 90 days' notice, except that Provider may terminate immediately"). `observed_fact` reads the zero only from a
    quote with no other duration; here it stands beside them, because a carve-out with no number is still a period."""
    periods = {m.duration for m in parse_durations(quote) if m.duration is not None}
    if _ZERO.search(quote):
        periods.add(Duration(Decimal(0), DurationUnit.CALENDAR_DAY))
    return periods


def observed_fact(quote: str, stated: str | None = None) -> ObservedFact | None:
    """The notice period a verified quote provides. When the quote carries several durations, the one the model stated
    (``stated``, its own words) selects among them; the model chooses which, the quote decides what it is. A quote
    with no duration yields no fact, unless it says the notice is none ("immediately", "without notice"), which is a
    period of zero days; a quote whose only candidate is ambiguous yields an ambiguous fact."""
    mentions = parse_durations(quote)
    if not mentions:
        zero = _ZERO.search(quote)
        if zero is None:
            return None
        return ObservedFact("notice_period", Duration(Decimal(0), DurationUnit.CALENDAR_DAY), zero.group(0), zero.start(), zero.end())
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
    if not all(_exact_pair(left, other) for other in (right, rule.maximum) if other is not None):
        return _on_the_calendar(observed, rule, week)
    if left.unit != right.unit:
        left_days, right_days = left.in_days(), right.in_days()
        assert left_days is not None and right_days is not None  # an exact pair
        a, b = left_days, right_days
    else:
        a, b = left.value, right.value
    left_unit, right_unit = left.unit.value.replace("_", " "), right.unit.value.replace("_", " ")
    if rule.maximum is not None:
        top = rule.maximum.in_days() if left.unit != rule.maximum.unit else rule.maximum.value
        assert top is not None  # an exact pair
        ok = b <= a <= top
        reason = f"the contract provides {left.value} {left_unit}s; the guidance requires between {right.value} and {rule.maximum.value} {right_unit}s"
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
        if mention.duration is None:
            continue
        reading = read_as_the_contract_does(ObservedFact("notice_period", mention.duration, mention.surface, mention.start, mention.end), convention)
        assert reading.duration is not None
        periods.add(reading.duration)
    if _ZERO.search(quote):
        periods.add(Duration(Decimal(0), DurationUnit.CALENDAR_DAY))
    return periods
