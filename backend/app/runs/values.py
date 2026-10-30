"""The values an answer states that none of its verified quotes state: what code can see of the gap between a located
quote and a supported answer (holdout audit, 2026-10-09: "one (1) day of service credit" on a quote that stops before
the credit).

Values are compared by value, not by spelling: "thirty (30) days", "30 days" and "thirty days" are one value,
"$1,500,000", "USD 1.5 million" another, "January 1, 2024" and "1st day of January, 2024" a third. A date is one value
and is shown as written, never as a loose day number. The answer is read for the values it states: dates, digits,
money, percentages, and number words before a unit ("two years"); what points rather than states ("§6.4", "Sections 2,
11, and 13", "Exhibit No. 10.1", "regulation 72(9)", "sec_7", an enumerator "(2)"), and the number of an instrument
("Amendment No. 1", "Change Order #7"), is set aside. A quote is read whole,
every number word included, so nothing it states is missed. Text the caller passes as the reader's own counts as
stated: the guidance, which an answer is compared with. The question is not passed since policy-v6: it is what was
asked, and an answer that repeats its figure has repeated a premise, not quoted the contract.

Shown beside every answer as a disclosure. Since policy-v6 it also decides: a pass whose conclusion states a value no
verified quote states, or gives a redaction mark as its value, is lowered to needs review when the run is decided
(`runs.status.check_values`). Finding nothing claims nothing: a quote can state the right number for the wrong band (a
service-credit table holds both 5% and 10%).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from ..policy.durations import NUMBER_WORDS, words_to_number
from ..verify.tokens import Kind, tokenize

# A number in words, by policy.durations' grammar: "thirty and sixty days" states thirty and sixty, never ninety
# (policy-v17, stress test 2026-10-30). Atomic and bounded there, so a hostile answer of "one and one and …" is linear.
_WORD_RUN = rf"\b{NUMBER_WORDS}"
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
_NUMERIC_DATE = re.compile(r"\b(?P<a>\d{1,4})(?P<sep>[-/.\u2013\u2014])(?P<b>\d{1,2})(?P=sep)(?P<c>\d{1,4})\b")

# Letters in a pointer are capitals or a bracketed sub-item: "Schedule B", "8.1(a)", never the next word ("fees").
_REF = r"(?-i:[\dA-Z]{1,6})(?![\dA-Za-z])(?:\.\d{1,6}){0,6}(?:\([a-z0-9]{1,4}\)){0,4}"
_POINTER_WORDS = (
    r"sections?|subsections?|clauses?|articles?|schedules?|exhibits?|attachments?|riders?|addend(?:um|a)|appendix|appendices"
    r"|annex(?:es|ures?)?|paragraphs?|parts?|chapters?|items?|regulations?|rules?"
)
# An instrument or a document named by a number that a mark sets out: "Amendment No. 1", "Change Order #7", "Contract
# No. 98-1234". The number is its name, not a value (the amendment challenge, 2026-10-17: "Amendment No. 1" was reported
# as the value 1). Only the mark makes it one: "Amendment 2 renewals" may be a count, so an unmarked number stays a value,
# as before, and so does one after "Number", which after a plural is the verb ("the licences number 250", review of
# policy-v15).
_NUMBERED_NAMES = (
    r"amendments?|supplements?|modifications?|restatements?|side\s+letters?|statements?\s+of\s+work|sows?|orders?"
    r"|(?:change|work|purchase|task|service|sales)\s+orders?|order\s+forms?|contracts?|agreements?|invoices?|patents?"
    r"|polic(?:y|ies)|leases?|certificates?|licen[cs]es?|registrations?|accounts?"
)
# A name, its mark and its number stand on one line: "the Agreement\n\n# 2 renewals" is a heading and a count.
_SPACE = r"[^\S\r\n\x0b\x0c\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]"
# "No." with its full stop ("no 30-day period" is a negation), or "#".
_NO = rf"(?:no\.{_SPACE}*+|#{_SPACE}*+)"
# The marked number read whole, however long or joined by hyphens ("4500012345", "98-1234"). A value is never one: a
# grouped number ("Amendment No. 1,500 additional units"), a date ("No. 1 March 2026", "No. 2024-01-15") and a currency
# ("No. USD 10,000") are read as before, and a number that a comma cuts ("7,12") is no name.
_MONTH_WORD = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
_MARKED_ID = (
    r"(?!\d{1,4}(?:-\d{1,2}-|/\d{1,2}/|\.\d{1,2}\.|\N{EN DASH}\d{1,2}\N{EN DASH}|\N{EM DASH}\d{1,2}\N{EM DASH})\d{1,4}\b"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?{_MONTH_WORD}(?!\w)|(?:USD|EUR|GBP|CHF|CAD|AUD)\b)"
    r"(?>(?-i:[\dA-Z][\dA-Z-]{0,23})(?![\dA-Za-z]|,\d)(?:\.\d{1,6}){0,6}(?:\([a-z0-9]{1,4}\)){0,4}(?![\dA-Za-z]|[.,]\d))"
)
# A number before a unit, a magnitude or a percent sign, with any restatement in brackets between, is a quantity, never
# a name: "Amendment No. 30 (thirty) days", "Amendment No. 2 million".
_NOT_A_NAME = rf"(?![\s-]*+(?:\([^()]{{1,40}}\)[\s-]*+)?(?:%|{_UNIT}|(?:thousand|million|billion|trillion|USD|EUR|GBP|CHF|CAD|AUD)\b))"
_JOIN = rf"{_SPACE}*+(?:,{_SPACE}*+(?:(?:and|or|to|through)\b{_SPACE}*+|&{_SPACE}*+)?|(?:(?:and|or|to|through)\b|&){_SPACE}*+)"
# Each number of the name carries its own mark ("Amendment No. 1 and No. 2"), so a count after it, however joined, is the
# answer's: "Under Amendment No. 1, 2 renewals". "Amendments Nos. 1 and 2" is read as before, its numbers as values: after
# "Nos." a bare count cannot be told from one more number.
_IDENTIFIERS = re.compile(
    rf"\b(?:{_NUMBERED_NAMES}){_SPACE}++{_NO}{_MARKED_ID}{_NOT_A_NAME}(?:{_JOIN}{_NO}{_MARKED_ID}{_NOT_A_NAME})*+",
    re.IGNORECASE,
)
# Where an answer points rather than states: v14's reading of provisions, whitespace taken possessively (two runs that
# could share it split a long one quadratically: 7 s for one read of 20,000 spaces after "Section 1,", review of
# policy-v15), and the marked names above.
_POINTERS = re.compile(
    # A list of pointers runs on ("Sections 1, 2 and 3") but never over a quantity: "Under Section 4.2, 90 days" (bug hunt).
    rf"(?:§§?\s*+|\b(?:{_POINTER_WORDS})\s++(?:no\.?\s*+|number\s++)?){_REF}"
    rf"(?:\s*+(?:,\s*+(?:and|or)?|and|or|to|through|&)\s*+{_REF}(?![\s-]*(?:%|{_UNIT}))){{0,40}}"
    rf"|{_IDENTIFIERS.pattern}"
    r"|\bsec_\d+(?:[.,]\d+)*|\(part \d+\)|\(\s*\d{1,2}\s*\)|(?<!\d)\.\d+",
    re.IGNORECASE,
)
# What names a provision or an instrument: runs.relations' reading of an answer and of a clause's wordings (policy-v16).
# A plural opens a list, as v14 reads one ("Sections 7.2 and 7.3", review of policy-v16); one name takes its own number
# only, so a count after its comma stays ("Under clause 1.2, 3 delivery trucks", review of policy-v15).
_PLURAL_POINTER_WORDS = (
    r"sections|subsections|clauses|articles|schedules|exhibits|attachments|riders|addenda|appendices|annex(?:es|ures)"
    r"|paragraphs|parts|chapters|items|regulations|rules"
)
_NAMES = re.compile(
    rf"(?:§§\s*+|\b(?:{_PLURAL_POINTER_WORDS})\s++(?:nos?\.?\s*+|numbers?\s++)?){_REF}"
    rf"(?:\s*+(?:,\s*+(?:and|or)?|and|or|to|through|&)\s*+{_REF}(?![\s-]*(?:%|{_UNIT}))){{0,40}}"
    rf"|(?:§\s*+|\b(?:{_POINTER_WORDS})\s++(?:no\.?\s*+|number\s++)?){_REF}|{_IDENTIFIERS.pattern}|\bsec_\d+(?:[.,]\d+)*",
    re.IGNORECASE,
)


# No contract states a value of more digits than this; a longer run is set aside, so arithmetic on it can neither
# overflow nor round two different numbers into one at Decimal's 28-digit precision (review, 2026-10-09).
MAX_VALUE_DIGITS = 24


# Thousands grouping, the only comma a value may hold: "1,5%" is a European 1.5%, unreadable here, so set aside rather
# than read as 15% (bug hunt, 2026-10-09).
_GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
# A number glued to what follows ("$1.5M", "100m", "1st") is one run; the tokenizer stops inside it ("$1" of "$1.5M").
# Money with a magnitude suffix is read whole; any other glued run is set aside, never reported cut short.
_GLUED = re.compile(r"[.,]?[^\W_]")
_GLUED_MONEY = re.compile(r"(?:[$€£¥]|(?:USD|EUR|GBP|CHF|CAD|AUD)\s?)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(k|mm|m|bn|b)(?![^\W_])", re.IGNORECASE)
# Thousands grouped by spaces, as much of Europe writes money, read as one sum where a currency stands beside them:
# "1 500 000 €" was three values (bug hunt). Without a currency a spaced group stays separate numbers.
_CURRENCY_MARK = r"(?:[$€£¥]|USD|EUR|GBP|CHF|CAD|AUD)"
_SPACED_MONEY = re.compile(
    rf"{_CURRENCY_MARK}\s?(?P<before>\d{{1,3}}(?:[ \u00a0\u202f]\d{{3}})+)(?![\d,.])"
    rf"|(?<![\d,.])(?P<after>\d{{1,3}}(?:[ \u00a0\u202f]\d{{3}})+)\s?{_CURRENCY_MARK}",
)
_SUFFIX = {"k": Decimal(10) ** 3, "m": Decimal(10) ** 6, "mm": Decimal(10) ** 6, "b": Decimal(10) ** 9, "bn": Decimal(10) ** 9}


def _number(surface: str) -> Decimal | None:
    raw = re.sub(r"[^\d.,]", "", surface)
    if "," in raw and not _GROUPED.fullmatch(raw):
        return None
    digits = raw.replace(",", "")
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


def date_spans(text: str) -> list[tuple[int, int]]:
    """Where ``text`` writes a date, in reading order: every date `stated_values` reads, one either way round included."""
    return sorted((start, end) for _, start, end in _dates(text))


# A four-digit year that is a year, not a quantity or part of a numeric date ("after 2000 hours", "2025-03-01").
NOT_A_QUANTITY = (
    r"(?![-/.]\d)(?![\s-]*(?:[%$€£]|(?:calendar\s+|business\s+|working\s+)?"
    r"(?:days?|weeks?|months?|years?|hours?|minutes?|units?|items?|tonnes?|cases?|pieces?)\b))"
)
# The time a question asks at, as its frame: "What was the deadline in June 2026?". An answer that repeats it ("In June
# 2026 the deadline was …") says when it answers for; it takes no figure from the question (policy-v12: the dated
# journey of 2026-10-15 was lowered for repeating "June 2026", while the same answer without those words kept its pass,
# so the status hung on the wording). A question that asks to confirm ("Is the fee payable in June 2026?") and a date
# the question gives as a property ("the payment due on 1 March 2027") are still premises (test_value_support).
_FRAME_LEAD = re.compile(
    r"(?:\b(?P<before>[\w'-]+)\s+)?(?:in|during|throughout|on|at|as\s+of|as\s+at)\s+"
    r"(?:(?:the\s+)?(?:calendar\s+|financial\s+|fiscal\s+)?year\s+)?$",
    re.IGNORECASE,
)
_FRAME_YEAR = re.compile(rf"(?<![\w-])(?:19|20)\d{{2}}\b{NOT_A_QUANTITY}")
_CONFIRMS = re.compile(
    r"^\W*(?:(?:in|during|on|at|as\s+of|as\s+at)\b[^,?]{1,60},\s*)?"
    r"(?:is|are|was|were|does|do|did|can|could|will|would|must|has|have|had|should|shall|may|might)\b",
    re.IGNORECASE,
)
_PROPERTY = frozenset((
    "due", "payable", "paid", "made", "signed", "dated", "effective", "expiring", "expires", "ending", "ends", "starting",
    "starts", "commencing", "commences", "beginning", "begins", "delivered", "received", "given", "served", "issued",
    "executed", "entered", "held", "scheduled", "falling", "falls", "occurring", "occurs", "terminating", "terminates",
    "renewing", "renews", "closing", "closes", "sent", "filed",
))  # fmt: skip


def frame_times(question: str | None) -> list[str]:
    """The times ``question`` asks at, as written ("June 2026", "1 March 2027", "2024"): a date, month or year that a
    question asking what, when or how much puts after "in", "during", "throughout", "on", "at", "as of" or "as at".
    None of a question that asks to confirm, and none the question gives as a property of something ("due on")."""
    if not question or _CONFIRMS.match(question):
        return []
    found = []
    for start, end in sorted(date_spans(question) + [m.span() for m in _FRAME_YEAR.finditer(question)]):
        lead = _FRAME_LEAD.search(question, 0, start)
        if lead is not None and (lead.group("before") or "").casefold() not in _PROPERTY:
            found.append(question[start:end])
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
    # Money with a glued magnitude is read straight from the text: the tokenizer splits "$1.5M" into "$1" and "5M", and
    # gives "$3M" no number at all.
    glued_until: dict[int, int] = {}
    for glued in _GLUED_MONEY.finditer(rest):
        amount = _number(glued.group(1))
        if amount is not None:
            found.append((_key(amount * _SUFFIX[glued.group(2).casefold()]), glued.start(), glued.end(), "money"))
            glued_until[glued.start()] = glued.end()
    for spaced in _SPACED_MONEY.finditer(rest):
        amount = _number(re.sub(r"\s", "", spaced.group("before") or spaced.group("after")))
        if amount is not None and spaced.start() not in glued_until:
            found.append((_key(amount), spaced.start(), spaced.end(), "money"))
            glued_until[spaced.start()] = spaced.end()
    covered = sorted(glued_until.items())
    for token in tokenize(rest):
        if token.kind in (Kind.NUMBER, Kind.CURRENCY, Kind.PERCENT):
            end = token.end
            if any(start <= token.start < stop for start, stop in covered):
                continue
            if token.kind is not Kind.PERCENT and _GLUED.match(rest, end):
                continue  # glued to what follows ("100m", "1st"): set aside, never reported cut short
            value = _number(rest[token.start : token.end])
            if value is None:
                continue
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


def _without_pointers(text: str) -> str:
    """The text with what points blanked, to spaces so offsets still index it as written: "Under Section 10" in a
    question names no value (review R1, 2026-10-09), nor "Amendment No. 1" in an answer. The value check, the choices
    and the reader's own text read through it; a quote is read whole."""
    return _POINTERS.sub(lambda m: " " * len(m.group(0)), text)


def _without_names(text: str) -> str:
    """The text with what names a provision or an instrument blanked, each pointer's own number only ("clause 1.2",
    "Amendment No. 1"): how runs.relations reads an answer. A list's further numbers stay, so "Under clause 1.2, 3
    delivery trucks" keeps its 3 (review of policy-v15); "clause 1.2" is no value of either wording (review of policy-v16)."""
    return _NAMES.sub(lambda m: " " * len(m.group(0)), text)


def _keys(text: str) -> set[str]:
    return {key for key, _, _, _ in _stated(text, words_need_a_unit=False)}


def _kinds_of(text: str, *, words_need_a_unit: bool) -> dict[str, set[str]]:
    """For each value ``text`` states (its "n:" or "d:" key), the kinds it is stated as: a percentage, money, a duration
    in one unit family, or "plain" where code reads no kind (a number with no unit, "30 (thirty) days")."""
    group_at = {start: group for _, group, _, _, start, _ in _kinded(text, words_need_a_unit=words_need_a_unit)}
    kinds: dict[str, set[str]] = {}
    for key, start, _, _ in _stated(text, words_need_a_unit=words_need_a_unit):
        kinds.setdefault(key, set()).add(group_at.get(start, "plain"))
    return kinds


def wording_values(text: str | None) -> set[str]:
    """The values a contract's wording states, what names a provision or an instrument set aside: runs.relations compares
    a replaced clause with its replacement so (policy-v16). "… notice under Section 7.3" names 7.3 and states none."""
    return {key for key, *_ in _stated(_without_names(text or ""), words_need_a_unit=False)}


def stated_values(text: str | None, *, answer: bool = False) -> set[str]:
    """The values ``text`` states, each as its comparable key ("n:45", "d:2027-12-27"): the reading every check here
    shares. In an answer (``answer``) what names a provision or an instrument is set aside, a pointer's own number only
    ("clause 1.2", "Amendment No. 1" state no value), and a number word counts only before a unit, as `_stated` reads one."""
    text = text or ""
    return {key for key, *_ in _stated(_without_names(text) if answer else text, words_need_a_unit=answer)}


def unquoted_values(answer: str | None, quotes: Iterable[str], readers_text: Iterable[str] = (), clause_numbers: Iterable[str] = ()) -> list[str]:
    """The values ``answer`` states that no quote and none of the reader's own text the caller passes (the guidance) states, each as
    the answer writes it ("45 days", "$78,600.00", "one (1) day", "January 1, 2024"), in the answer's order, once each.

    A value is quoted by the same number stated as the same kind, or stated with no kind code can read: "5%" is not
    quoted by "within 5 business days" (review, 2026-10-09: an answer of 5% over a quote whose 5 is days, beside a credit
    of 10%, was told nothing), while "30 days" is quoted by "30 (thirty) days", whose unit code does not read. A duration
    is also quoted by its equivalent in the same unit family: "1 year" by "twelve (12) months" (review of policy-v6,
    2026-10-10). Across families code does not compare: "3 months" is not "ninety days". A dotted number written exactly
    as one of the document's ``clause_numbers``, with no unit, points rather than states ("(11.5)" after a clause
    heading); a whole number is not set aside this way, since "6 Machines" is a value even where a clause 6 exists."""
    if not answer:
        return []
    sources = (*quotes, *(_without_pointers(text) for text in readers_text))
    given: dict[str, set[str]] = {}
    for text in sources:
        for key, kinds in _kinds_of(text, words_need_a_unit=False).items():
            given.setdefault(key, set()).update(kinds)
    # The same values in their kind's base unit ("t:months:12" for "one year" and for "twelve (12) months").
    given_kinded = {key for text in sources for _, _, key, _, _, _ in _kinded(text, words_need_a_unit=False)}
    blanked = _without_pointers(answer)
    kinded_answer = _kinded(blanked, words_need_a_unit=True)
    group_at = {start: group for _, group, _, _, start, _ in kinded_answer}
    base_key_at = {start: key for _, _, key, _, start, _ in kinded_answer}
    clause_set = set(clause_numbers)
    shown: list[str] = []
    seen: set[tuple[str, str]] = set()
    for key, start, end, _ in sorted(_stated(blanked, words_need_a_unit=True), key=lambda found: found[1]):
        kind = group_at.get(start, "plain")
        stated_as = given.get(key, set())
        quoted = bool(stated_as) and (kind == "plain" or kind in stated_as or "plain" in stated_as)
        quoted = quoted or base_key_at.get(start) in given_kinded
        pointer = kind == "plain" and "." in answer[start:end] and answer[start:end].strip() in clause_set
        if quoted or pointer or (key, kind) in seen:
            continue
        seen.add((key, kind))
        unit = _TRAILING_UNIT.match(blanked, end) if key.startswith("n:") else None
        shown.append(answer[start : unit.end() if unit else end].strip())
    return shown


# What a filed contract prints where it withholds a figure: "[***]", "[*]", "[ * ]", "[REDACTED]", or a run of asterisks.
# Bracketed only: a bare run of asterisks is as often emphasis ("***Important***") as a redaction (review, 2026-10-10).
REDACTION_MARK = re.compile(r"\[\s*(?:\*+|redacted)\s*\]", re.IGNORECASE)
# Words with which an answer says the figure is withheld rather than giving the mark as the figure. Read only in the
# mark's own sentence, the mark itself left out: "Confidential Information is defined in §1" elsewhere in the answer, or
# the mark "[REDACTED]", says nothing about whether this figure is given as known.
_SAYS_WITHHELD = re.compile(r"\b(?:redact\w*|omitted|withheld|not\s+disclosed|undisclosed|not\s+stated|cannot\s+be\s+determined)\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")  # not ";": "the [*] period; the period is not disclosed" is one statement


def redaction_given_as_value(answer: str | None) -> str | None:
    """The redaction mark an answer gives as if it were the figure ("set at [***]%", "the cap is [***]"), or None. An
    answer that says the figure is withheld ("redacted ([***]) in this copy") gives no value, and is not this."""
    if not answer:
        return None
    for mark in REDACTION_MARK.finditer(answer):
        start = max((m.end() for m in _SENTENCE_END.finditer(answer, 0, mark.start())), default=0)
        stop = next((m.start() for m in _SENTENCE_END.finditer(answer, mark.end())), len(answer))
        if not _SAYS_WITHHELD.search(answer[start : mark.start()] + " " + answer[mark.end() : stop]):
            return mark.group(0)
    return None


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


def _readers_values(texts: Iterable[str]) -> tuple[set[str], set[str]]:
    """The values the reader's own text states, pointers aside: by kind ("within 30 days" is days, not 30%; "one hour" is
    the passages' "sixty minutes"), and as plain numbers where code reads no kind, which match any kind (bug hunt
    rerun, 2026-10-09: the question's values were compared by bare number)."""
    kinded: set[str] = set()
    plain: set[str] = set()
    for text in texts:
        bare = _without_pointers(text)
        kinded |= {key for _, _, key, _, _, _ in _kinded(bare, words_need_a_unit=False)}
        plain |= {number for number, kinds in _kinds_of(bare, words_need_a_unit=False).items() if "plain" in kinds}
    return kinded, plain


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
    return [choice for choice, _ in _choices(answer, _Offer.of(quotes, question, guidance))]


@dataclass(frozen=True)
class _Offer:
    """What the passages offer, read once: each group's distinct values (key -> as written, in the passages' order),
    the reader's values set aside."""

    offered: dict[str, dict[str, str]]
    standard_kinded: set[str]
    standard_plain: set[str]

    @classmethod
    def of(cls, quotes: Iterable[str], question: Iterable[str], guidance: Iterable[str]) -> _Offer:
        asked_kinded, asked_plain = _readers_values(question)
        guide_kinded, guide_plain = _readers_values(guidance)
        # Dicts, not scans: a quote of thousands of values stays linear.
        offered: dict[str, dict[str, str]] = {}
        for quote in quotes:
            for _, group, key, number, start, end in _kinded(quote, words_need_a_unit=False):
                if key not in asked_kinded and number not in asked_plain:
                    offered.setdefault(group, {}).setdefault(key, quote[start:end].strip())
        return cls(offered, asked_kinded | guide_kinded, asked_plain | guide_plain)


def _choices(answer: str, offer: _Offer) -> list[tuple[ValueChoice, set[str]]]:
    """The answer's choices among what the passages offer, each with the keys of the values the answer used."""
    blanked = _without_pointers(answer)
    used: dict[str, tuple[ChoiceKind, dict[str, str]]] = {}
    for kind, group, key, number, start, end in _kinded(blanked, words_need_a_unit=True):
        if key in offer.standard_kinded or number in offer.standard_plain or key not in offer.offered.get(group, {}):
            continue
        used.setdefault(group, (kind, {}))[1].setdefault(key, answer[start:end].strip())
    choices: list[tuple[ValueChoice, set[str]]] = []
    for group, (kind, chosen) in used.items():
        values = list(offer.offered[group].values())
        # A choice is some of the values used and others left out: an answer that gives them all chose nothing.
        if len(values) >= 2 and len(chosen) < len(values):
            shown = values[:MAX_CHOICES_SHOWN]
            choices.append((ValueChoice(kind, ", ".join(chosen.values()), shown, len(values) - len(shown)), set(chosen)))
    return choices


# A subject that takes in every party to the agreement: "each party", "either of the parties", "both sides", "the parties",
# "neither party", and two named parties joined under "both" ("both Customer and Provider"; names are capitalised).
_EVERY_PARTY = re.compile(
    r"(?i:\b(?:each|either|both|every|all|neither)\s+(?:of\s+the\s+)?(?:two\s+)?(?:part(?:y|ies)|sides?)\b|\bthe\s+parties\b)"
    r"|\b(?i:both)\s+(?:the\s+)?[A-Z][a-z]+\s+and\s+(?:the\s+)?[A-Z][a-z]+\b"
)
# Where one statement ends: a sentence, or a clause after a semicolon ("Customer must give 45 days; Provider must give 60").
_STATEMENT_END = re.compile(r"(?<=[.;!?])\s+")


@dataclass(frozen=True)
class UniformChoice:
    """A statement of the answer that gives every party one value where its passages state several of that kind."""

    phrase: str  # how the answer names every party, as written ("Each party")
    choice: ValueChoice


def uniform_party_choices(answer: str | None, quotes: Iterable[str], question: Iterable[str] = (), guidance: Iterable[str] = ()) -> list[UniformChoice]:
    """Each statement of the answer that names every party and gives it some, not all, of the values of a kind its
    passages state, when no statement of the passages gives that value to every party (blind contract stress test,
    2026-10-16: "Each party must give … 45 calendar days" over "Customer must give … forty-five (45) …; Provider must give
    … sixty (60) …"). Statements are read one by one: a later one naming the other value does not take back the first.
    A value the contract itself gives to every party ("Either party may terminate on thirty (30) days' notice") is not a
    generalisation, whatever else the passages state. Code reads the subject's words, never who the parties are."""
    if not answer:
        return []
    quotes = list(quotes)
    offer = _Offer.of(quotes, question, guidance)
    general = {
        key
        for quote in quotes
        for statement in _STATEMENT_END.split(quote)
        if _EVERY_PARTY.search(statement)
        for _, _, key, _, _, _ in _kinded(statement, words_need_a_unit=False)
    }
    found: list[UniformChoice] = []
    for statement in _STATEMENT_END.split(answer):
        subject = _EVERY_PARTY.search(statement)
        if subject is None:
            continue
        found += [UniformChoice(subject.group(0), choice) for choice, used in _choices(statement, offer) if not used & general]
    return found
