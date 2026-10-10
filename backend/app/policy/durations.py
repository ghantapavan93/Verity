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
    left_unit, right_unit = left.unit.value.replace("_", " "), right.unit.value.replace("_", " ")
    if rule.maximum is not None:
        top = rule.maximum.in_days() if left.unit != rule.maximum.unit else rule.maximum.value
        if top is None:
            return PolicyEvaluation("incomparable", f"{left_unit}s cannot be compared with the ceiling's unit", observed, rule)
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
