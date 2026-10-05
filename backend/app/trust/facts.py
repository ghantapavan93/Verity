"""The typed values a passage states: periods, amounts, percentages and dates, as code reads them.

Each parser is one this application already trusts or a strict one: periods are `policy.durations` (words and
digits checked against each other; an ambiguous mention states nothing), amounts and percentages are the typed
tokens of `verify.tokens` (a number is a value, an amount keeps its currency), and a date is a day, month and year
written out or in ISO form, and only a date the calendar has.

A fact is what the text states. Whether it is the fact a finding is about is not decided here.
"""

from __future__ import annotations

import re
from datetime import date

from ..policy.durations import parse_durations
from ..verify.tokens import Kind, tokenize
from .model import Fact, FactKind

_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
_MONTH = "|".join(_MONTHS)
_DATE = re.compile(
    rf"\b(?:(?P<m1>{_MONTH})\s+(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y1>\d{{4}})"
    rf"|(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?(?P<m2>{_MONTH}),?\s+(?P<y2>\d{{4}})"
    rf"|(?P<y3>\d{{4}})-(?P<m3>\d{{2}})-(?P<d3>\d{{2}}))\b",
    re.IGNORECASE,
)


def _dates(text: str) -> list[tuple[int, Fact]]:
    found = []
    for match in _DATE.finditer(text):
        if match.group("m1"):
            year, month, day = int(match.group("y1")), _MONTHS.index(match.group("m1").lower()) + 1, int(match.group("d1"))
        elif match.group("m2"):
            year, month, day = int(match.group("y2")), _MONTHS.index(match.group("m2").lower()) + 1, int(match.group("d2"))
        else:
            year, month, day = int(match.group("y3")), int(match.group("m3")), int(match.group("d3"))
        try:
            stated = date(year, month, day)
        except ValueError:
            continue  # the thirty-first of a short month is not a date
        found.append((match.start(), Fact(FactKind.DATE, stated.isoformat(), match.group(0))))
    return found


def facts_in(text: str) -> tuple[Fact, ...]:
    """Every typed value the text states, in the order it states them."""
    found: list[tuple[int, Fact]] = []
    for mention in parse_durations(text):
        if mention.duration is not None:
            unit = mention.duration.unit.value.replace("_", " ")
            found.append((mention.start, Fact(FactKind.DURATION, f"{mention.duration.value.normalize():f} {unit}s", mention.surface)))
    for token in tokenize(text):
        if token.kind is Kind.CURRENCY:
            found.append((token.start, Fact(FactKind.MONEY, token.canonical, text[token.start : token.end])))
        elif token.kind is Kind.PERCENT:
            found.append((token.start, Fact(FactKind.PERCENT, token.canonical, text[token.start : token.end])))
    found += _dates(text)
    return tuple(fact for _, fact in sorted(found, key=lambda item: item[0]))
