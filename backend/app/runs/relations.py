"""What the contract itself says about how its provisions act on one another, located in its text (policy-v11).

Retrieval-v2 (runs.links) follows definitions, amendments and references to hand the model more context, and records
why a section was handed; it does not say what one provision does to another. This module reads the two kinds of
statement whose words a reader can check, and records where each is:

- replaces: a numbered provision is deleted, replaced, superseded or amended and restated ("clause 3.2 of the
  Agreement is deleted in its entirety and replaced with the following: …"), with the new wording when the statement
  quotes it, and any limit it states ("for the second Contract Year only", a start not yet reached, one paragraph);
- precedence: the contract ranks its parts for a conflict ("(a) these clauses; (b) Schedule 2; and (c) Schedule 1").

A mention is not a statement: "subject to", "notwithstanding", "as amended from time to time", "remains unchanged", an
exception, a definition or a cross-reference records nothing here (they stay ordinary context). A located statement is
a fact about the text, not a ruling on its legal effect. `assess` says what follows for one finding; the status rule
(runs.status.check_replaced) acts on one case only: a question about the agreement as it stands, answered from text
the contract replaced in full, without the replacement. The first-visitor acceptance test (2026-10-14) is why: the
local model answered a renewal question from a clause an amendment had deleted and replaced, and nothing said so. "As it
stands" is the run's date only for a question that names no time; one that names a time ("in June 2025") is not placed
against a replacement's start, and raises a concern.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Literal, Protocol

from ..ingest.sections import clause_openings
from .status import REFERENCE
from .values import date_spans, stated_values

RelationKind = Literal["replaces", "precedence"]
Effect = Literal["replaced", "scoped", "precedence", "dated", "old_value", "context"]
Perspective = Literal["historical", "dated", "current", "unstated"]
# What code raises against a finding and cannot resolve (runs.account): a limit, a ranking, a time the question names, an
# answer that quotes the replacement and states only the replaced values. "replaced" sets the status; "context" is none.
CONCERNS: frozenset[Effect] = frozenset({"scoped", "precedence", "dated", "old_value"})

# A provision named, then the verb that replaces it: "clause 3.2 of the Agreement is deleted in its entirety and …".
_REPLACED_VERB = re.compile(
    r"\b(?:is|are|shall\s+be|will\s+be)\s+(?:hereby\s+)?"
    r"(?:deleted(?:\s+in\s+(?:its|their)\s+entirety)?(?:\s+and\s+replaced)?|replaced(?:\s+in\s+(?:its|their)\s+entirety)?|superseded"
    r"|amended\s+and\s+restated|substituted)\b",
    re.IGNORECASE,
)
# The verb, then the provision: "… amended by deleting Section 3.2 in its entirety and replacing it with …".
_DELETING = re.compile(
    rf"\bdeleting\s+(?P<ref>{REFERENCE.pattern}(?:\([a-z0-9]{{1,4}}\))*)[^.;:]{{0,40}}?\s+and\s+(?:replacing|substituting)\s+(?:it|the\s+same)\b",
    re.IGNORECASE,
)
_SUB_ITEMS = re.compile(r"(?:\([a-z0-9]{1,4}\))+")
# A part of a clause named before it: one paragraph, one definition, one sentence, some words ("The definition of
# 'Applicable Margin' in Section 1.01 is amended and restated": a real EDGAR amendment, one definition of many in 1.01).
_PARAGRAPH_OF = re.compile(
    r"(?:\b(?:paragraph|sub-?paragraph|sub-?clause|item)\s*\([a-z0-9]{1,4}\)(?:\s*\([a-z0-9]{1,4}\))*"
    r"|\bthe\s+definition\s+of\s+[\"“][^\"”]{1,60}[\"”](?:\s*\([^)]{1,40}\))?"
    r"|\bthe\s+(?:first|second|third|fourth|last|final)\s+(?:sentence|paragraph)"
    r"|\bthe\s+words\s+[\"“][^\"”]{1,80}[\"”])\s+(?:of|in)\s+$",
    re.IGNORECASE,
)
_PART_AFTER = re.compile(r"\bthe\s+(?:words?|figure|number|amount|sum|date|period|definition|reference|expression|phrase)\b", re.IGNORECASE)
# Only words deemed changed ("as if the words '48 hours' read …", "as if references to X were …"); "the consequences in
# Clause 14.5.1 apply as if the contract had been terminated" deems a circumstance, and is no change to 14.5.1 (corpus).
_AS_IF = re.compile(
    r"\b(?:applies|shall\s+apply|will\s+apply|is\s+to\s+be\s+read|shall\s+be\s+read|will\s+be\s+read|is\s+read)\s+as\s+if\s+"
    r"(?:the\s+(?:words?|figures?|numbers?|amounts?|dates?|references?)|references?\s+to)\b",
    re.IGNORECASE,
)
# How the new wording is introduced after the verb: "with the following:", "by", "to read as follows:".
_INTRODUCES = re.compile(
    r"[^.;:\"“]{0,60}?\b(?:with|by|to\s+read)\b(?:\s+as\s+follows|\s+(?:the\s+)?following(?:[^;:\"“\n]{0,40}?(?=:))?)?\s*:?\s*",
    re.IGNORECASE,
)
_QUOTE_OPEN = '"“'
_QUOTED_END = re.compile(r"[.;!?][\"”]")  # a quoted provision ends where a sentence inside it ends with the quote mark
# A limit the statement states, as written. A stated start is a limit only while code cannot read it or it is ahead.
_LIMIT = re.compile(
    r"\bfor\s+the\s+[\w\s()-]{1,40}?\s+only\b|\bonly\s+(?:for|in\s+respect\s+of|with\s+respect\s+to|as\s+it\s+applies\s+to|to\s+the\s+extent)\b[^,;:]{0,80}"
    r"|\bsolely\s+(?:for|in\s+respect\s+of|with\s+respect\s+to|as\s+it\s+applies\s+to)\b[^,;:]{0,80}|\bin\s+respect\s+of\s+[^,;:]{1,80}"
    r"|\bwith\s+respect\s+to\s+[^,;:]{1,80}|\bas\s+it\s+applies\s+to\s+[^,;:]{1,80}|\bto\s+the\s+extent\s+[^,;:]{1,80}|\bin\s*so\s*far\s+as\s+[^,;:]{1,80}"
    r"|\bfor\s+(?:the|any)\s+period\s+[^,;:]{1,80}|\buntil\s+[^,;:]{1,60}",
    re.IGNORECASE,
)
# A comma ends the start, unless a year follows it ("September 18, 2025": cut at its comma, it was never read).
_STARTS = re.compile(r"\b(?:with\s+effect\s+(?:from|on|as\s+of)|effective\s+(?:from|on|as\s+of))\s+(?P<when>(?:[^,;:]|,(?=\s*\d{4}\b)){3,60})", re.IGNORECASE)
_NAMED_DATE = re.compile(r"[\"“](?P<term>[^\"”]{2,40})[\"”]|\bthe\s+(?P<bare>[A-Z]\w*(?:\s+[A-Z]\w*){0,3})")

_PRECEDENCE = re.compile(
    r"\border\s+of\s+precedence\b|\b(?:take|takes|taking)\s+precedence\b|\bprevail(?:s|ing)?\b|\b(?:shall|will)\s+(?:govern|control)\b", re.IGNORECASE
)
_CONFLICT = re.compile(r"\b(?:conflict|inconsisten)", re.IGNORECASE)
# The nouns that name a part of a contract ("the Order Form", "these General Terms", "Schedule 2", "this Amendment").
_PART_NOUN = r"(?:Agreement|Amendment|Addendum|Schedules?|Annex(?:es)?|Exhibits?|Append(?:ix|ices)|Terms|Conditions|Form|Work|Specifications?|Clauses|Contract)"
_PART = re.compile(rf"\b(?:Schedule|Annex|Exhibit|Appendix)\s+[A-Z0-9]{{1,3}}\b|\b(?:the|these|this)\s+(?:(?:[A-Z][\w-]*\s+){{0,3}}{_PART_NOUN}|clauses)\b")
_PART_HEADING = re.compile(
    r"^\s*(?:(?P<kind>SCHEDULE|ANNEX|EXHIBIT|APPENDIX)\s+(?P<id>[A-Z0-9]{1,3})\b|(?P<amendment>AMENDMENT|ADDENDUM)\b"
    r"|(?P<named>ORDER\s+FORM|STATEMENT\s+OF\s+WORK|SPECIFICATION|SERVICE\s+DESCRIPTION)\b)",
    re.IGNORECASE,
)
_BODY = {"clauses", "agreement", "contract", "terms", "conditions", "terms and conditions", "general terms", "general terms and conditions", "body"}
_SENTENCE_START = re.compile(r"(?<=[.;!?])\s+|\n")

_HISTORICAL = re.compile(
    r"\b(?:originally|initially|as\s+(?:first\s+|originally\s+)?(?:signed|executed|drafted)|before\s+(?:the|any|it\s+was)\s+(?:amendment|amended)"
    r"|prior\s+to\s+(?:the|any)\s+amendment|(?:the|its)\s+original\s+(?:agreement|contract|terms?|version|wording|clause))\b",
    re.IGNORECASE,
)
_CURRENT = re.compile(r"\b(?:now|currently|today|as\s+amended|at\s+present|as\s+it\s+stands)\b", re.IGNORECASE)
# A time the question names besides now. Only a question that names none is read at the run's date ("as it stands"): a
# run's date is when it was asked, not the time a question asks about ("What was the deadline in June 2025?"), and code
# does not place a time a question names against a replacement's start (external review of the owner note, 2026-10-14).
# A written date counts, unless it names a document ("the amendment dated 18 September 2025", "the January 2025
# addendum"); a year counts after a word that places the question in time, never as a quantity ("after 2000 hours"); so
# does a time relative to now. One of the contract's own periods counts after such a word ("during the first Contract
# Year"), never as what the question is about ("When does the Initial Term end?", read in 440 stored questions), nor
# every one of them ("each Contract Year").
_YEAR_TIME = re.compile(
    r"\b(?:in|during|throughout|between|as\s+(?:of|at)|until|till|before|after|since|prior\s+to|through)\s+"
    r"(?:(?:the\s+)?(?:calendar\s+|financial\s+|fiscal\s+)?year\s+)?(?:19|20)\d{2}\b(?![-/.]\d)"
    r"(?![\s-]*(?:[%$€£]|(?:calendar\s+|business\s+|working\s+)?(?:days?|weeks?|months?|years?|hours?|minutes?|units?|items?|tonnes?|cases?|pieces?)\b))",
    re.IGNORECASE,
)
_RELATIVE_TIME = re.compile(
    r"\b(?:last|previous|prior|next|following|coming)\s+(?:year|month|quarter|season|week)\b"
    r"|\b(?:\d{1,2}|a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:years?|months?|weeks?)\s+ago\b"
    r"|\b(?:previously|formerly|used\s+to|in\s+the\s+past|back\s+then|at\s+that\s+time)\b",
    re.IGNORECASE,
)
_PERIOD_TIME = re.compile(
    r"\b(?:in|during|for|throughout|within|by|before|after|until|till|since|over)\s+(?:(?:the|its|their|that|this)\s+)?"
    r"(?:(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|final|last|initial|\d{1,2}(?:st|nd|rd|th))\s+"
    r"(?:(?:contract|service|lease|licen[cs]e|agreement|financial|fiscal|calendar|subscription|supply|renewal)\s+)?(?:year|season|quarter|term)"
    r"|(?:contract|service|lease|financial|fiscal|subscription)\s+year\s+\d{1,2})\b",
    re.IGNORECASE,
)
_NAMES_A_DOCUMENT = re.compile(r"\b(?:dated|made\s+on|signed\s+on|executed\s+on|entered\s+into\s+on)\s*$", re.IGNORECASE)
_A_DOCUMENT_NAMED = re.compile(
    r"\s*(?:addendum|amendment|agreement|contract|letter|deed|version|draft|edition|lease|licen[cs]e|order\s+form|statement\s+of\s+work)\b",
    re.IGNORECASE,
)

MAX_RELATIONS = 24  # a run records at most this many, those touching the sections read first: bounded on any filing


class Readable(Protocol):
    id: str
    number: str
    heading: str
    text: str


@dataclass(frozen=True)
class Passage:
    """Where a statement or a provision is: offsets into the stored text of its section."""

    section_id: str
    label: str  # "§3", or the section's heading when it has no number
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Relation:
    kind: RelationKind
    statement: Passage
    target: str | None = None  # replaces: the clause the statement names ("3.2"); a paragraph or words of it are in `scope`
    replaced: Passage | None = None  # replaces: that provision's own text where the document opens it; None if not found
    replacement: Passage | None = None  # replaces: the new wording the statement quotes, if it quotes one
    scope: str | None = None  # replaces: the limits the statement states, verbatim; None when it is unqualified
    effective: str | None = None  # replaces: a stated start code read and found already reached ("2025-09-18, the Amendment Date")
    parts: tuple[str, ...] = ()  # precedence: the parts it ranks, as written, in its order


@dataclass(frozen=True)
class Note:
    """What one recorded relation means for one finding, in code's words."""

    relation: int  # index into the run's recorded relations
    effect: Effect
    sentence: str


@dataclass(frozen=True)
class Recorded:
    """A run's relations and, by finding ordinal, what each means for that finding: written once, when the run finishes."""

    relations: tuple[Relation, ...] = ()
    notes: dict[int, tuple[Note, ...]] = field(default_factory=dict)


# ----------------------------------------------------------------------------- reading the statements


def _label(section: Readable) -> str:
    return f"§{section.number}" if section.number else section.heading


def _sentence(text: str, start: int, end: int, *, colon_ends: bool) -> tuple[int, int]:
    """The sentence holding text[start:end]. A colon ends it where new wording follows one (a replacement); a ranked
    list after "order of precedence:" is part of its sentence."""
    head = max((m.end() for m in _SENTENCE_START.finditer(text, 0, start)), default=0)
    stop = re.compile(r"[.!?;](?=\s|$)|:\s|\n" if colon_ends else r"[.!?](?=\s|$)|\n\n").search(text, end)
    return head, (stop.end() if stop else len(text))


def _new_wording(text: str, at: int) -> tuple[int, int] | None:
    """The new wording a statement quotes after its verb (``at``), up to the sentence that closes the quotation; None
    when it quotes none (a deletion, or a pointer such as "superseded by Section 7 of this Amendment")."""
    introduced = _INTRODUCES.match(text, at)
    if introduced is None:
        return None
    begin = introduced.end()
    if begin >= len(text) or text[begin] not in _QUOTE_OPEN:
        return None
    closed = _QUOTED_END.search(text, begin + 1)
    return (begin + 1, closed.start() + 1) if closed else None


class _Document:
    """The sections and, built once when first needed, where each clause number opens: no section is re-read per relation."""

    def __init__(self, sections: Sequence[Readable]) -> None:
        self.sections = sections
        self._opened: dict[str, list[int]] | None = None
        self._openings: dict[int, list[tuple[str, int]]] = {}

    def openings(self, index: int) -> list[tuple[str, int]]:
        if index not in self._openings:
            self._openings[index] = clause_openings(self.sections[index].text)
        return self._openings[index]

    def opened(self, number: str) -> list[int]:
        if self._opened is None:
            self._opened = {}
            for index in range(len(self.sections)):
                for opened, _ in self.openings(index):
                    self._opened.setdefault(opened, []).append(index)
        return self._opened.get(number, [])

    def provision(self, number: str, besides: str) -> Passage | None:
        """The provision's own text: the section numbered so, else the first other section that opens it. Never the
        statement's own section, which may quote the new wording under the same number."""
        numbered = [i for i, s in enumerate(self.sections) if s.number == number and s.id != besides]
        for index in numbered + [i for i in self.opened(number) if i not in numbered and self.sections[i].id != besides]:
            found = self._extent(index, number)
            if found is not None:
                section = self.sections[index]
                return Passage(section.id, _label(section), found[0], found[1], section.text[found[0] : found[1]])
        return None

    def _extent(self, index: int, number: str) -> tuple[int, int] | None:
        """From the clause's opening to the next clause that is not one of its own sub-clauses (the whole section when it
        is numbered so)."""
        section = self.sections[index]
        if section.number == number:
            start, end = 0, len(section.text)
        else:
            openings = self.openings(index)
            at = next((i for i, (n, _) in enumerate(openings) if n == number), None)
            if at is None:
                return None
            start = openings[at][1]
            end = next((offset for n, offset in openings[at + 1 :] if not n.startswith(number + ".")), len(section.text))
        return start, end

    def date_named(self, when: str) -> date | None:
        """The date a stated start names: written in it ("1 July 2027"), or a term the contract defines by a date
        ('dated September 18, 2025 (the "Amendment Date")'). None when code reads none, or more than one."""
        written = [v for v in stated_values(when) if v.startswith("d:")]
        if written:
            return _first_day(written[0]) if len(written) == 1 else None
        named = _NAMED_DATE.search(when)
        term = (named.group("term") or named.group("bare")) if named else None
        if not term:
            return None
        definition = re.compile(rf"\(\s*(?:the\s+)?[\"“]{re.escape(term)}[\"”]\s*\)")
        found = set()
        for section in self.sections:
            for match in definition.finditer(section.text):
                found |= {v for v in stated_values(section.text[max(0, match.start() - 60) : match.start()]) if v.startswith("d:")}
        return _first_day(found.pop()) if len(found) == 1 else None


def _first_day(key: str) -> date | None:
    """The first day a date key names ("d:2027-07-01"; "d:2026-03" for "March 2026", from its 1st). None for a day no
    calendar has ("February 30, 2026"): code reads no start there, and the start stays a limit."""
    try:
        return date.fromisoformat(key[2:] if key.count("-") == 2 else f"{key[2:]}-01")
    except ValueError:
        return None


def _replacements(document: _Document, section: Readable, as_of: date) -> Iterator[Relation]:
    text = section.text
    # (where the provision is named, its clause number, where the verb ends, the paragraph named if only one is).
    statements: list[tuple[int, str, int, str | None]] = []
    for verb in _REPLACED_VERB.finditer(text):
        head, _ = _sentence(text, verb.start(), verb.end(), colon_ends=True)
        named = list(REFERENCE.finditer(text, head, verb.start()))
        if named:
            items = _SUB_ITEMS.match(text, named[-1].end())
            paragraph = _PARAGRAPH_OF.search(text, head, named[-1].start())
            start = paragraph.start() if paragraph else named[-1].start()
            only = text[start : items.end() if items else named[-1].end()] if paragraph or items else None
            # "In Section 4.1, the words 'thirty (30) days' are replaced …": what is replaced is named after the clause.
            if _PART_AFTER.search(text, named[-1].end(), verb.start()):
                only = text[named[-1].start() : verb.start()].rstrip(" ,")
            statements.append((start, named[-1].group(1), verb.end(), only))
    for deleting in _DELETING.finditer(text):
        reference = REFERENCE.search(deleting.group("ref"))
        if reference is not None:
            only = deleting.group("ref") if _SUB_ITEMS.search(deleting.group("ref")) else None
            statements.append((deleting.start(), reference.group(1), deleting.end(), only))
    # "… Section 4.3 of the Agreement applies as if the words '48 hours' read '72 hours'": a deeming change of some words,
    # never a whole clause, and limited by whatever the sentence puts before it (a fresh holdout agreement, 2026-10-14).
    for deeming in _AS_IF.finditer(text):
        head, _ = _sentence(text, deeming.start(), deeming.end(), colon_ends=True)
        named = list(REFERENCE.finditer(text, head, deeming.start()))
        if named:
            lead = text[head : named[-1].start()].strip().rstrip(",")
            words = text[deeming.start() : _sentence(text, deeming.start(), deeming.end(), colon_ends=True)[1]].strip().rstrip(".;")
            statements.append((head, named[-1].group(1), deeming.end(), "; ".join(part for part in (lead, words) if part)))
    for named_at, target, verb_end, only in statements:
        head, tail = _sentence(text, named_at, verb_end, colon_ends=True)
        wording = _new_wording(text, verb_end)
        stated = text[head : min(tail, wording[0]) if wording else tail]  # limits are read in the statement, not in the new wording
        # One paragraph of a clause ("Paragraph (b) of clause 6.1", "clause 6.1(b)") is a limit on the clause, as written:
        # code locates the clause and does not decide which of its words a quote leans on.
        limits = ([" ".join(only.split())] if only else []) + [" ".join(m.group(0).split()) for m in _LIMIT.finditer(stated)]
        replaced = document.provision(target, section.id)
        effective = None
        for begins in _STARTS.finditer(stated):
            when, said = document.date_named(begins.group("when")), " ".join(begins.group(0).split())
            if when is not None and when <= as_of:
                effective = f"{when.isoformat()}, {' '.join(begins.group('when').split())}"
            else:
                limits.append(said if when is None else f"{said} ({when.isoformat()}, not reached on {as_of.isoformat()})")
        yield Relation(
            "replaces",
            Passage(section.id, _label(section), head, tail, text[head:tail]),
            target=target,
            replaced=replaced,
            replacement=Passage(section.id, _label(section), wording[0], wording[1], text[wording[0] : wording[1]]) if wording else None,
            scope="; ".join(limits) or None,
            effective=effective,
        )


def _precedences(section: Readable) -> Iterator[Relation]:
    text, seen = section.text, set()
    for marker in _PRECEDENCE.finditer(text):
        head, tail = _sentence(text, marker.start(), marker.end(), colon_ends=False)
        sentence = text[head:tail]
        if head in seen or not (_CONFLICT.search(sentence) or "precedence" in marker.group(0).lower()):
            continue
        parts = tuple(dict.fromkeys(" ".join(m.group(0).split()) for m in _PART.finditer(sentence)))
        if len(parts) >= 2:
            seen.add(head)
            yield Relation("precedence", Passage(section.id, _label(section), head, tail, sentence), parts=parts)


def locate_relations(sections: Sequence[Readable], as_of: date) -> list[Relation]:
    """Every replacement and precedence statement in the document, in reading order. One regex pass over each section;
    a target is found through a clause index built once, only when some statement names one."""
    document = _Document(sections)
    found: list[Relation] = []
    for section in sections:
        found += _replacements(document, section, as_of)
        found += _precedences(section)
    return found


# ----------------------------------------------------------------------------- what follows for a finding


def asked_time(question: str) -> str | None:
    """The first time the question names besides now, as written ("June 2025", "during 2024", "last year", "the first
    Contract Year"); None when it names none."""
    found = [
        (start, end) for start, end in date_spans(question) if not _NAMES_A_DOCUMENT.search(question[:start]) and not _A_DOCUMENT_NAMED.match(question, end)
    ]
    found += [match.span() for pattern in (_YEAR_TIME, _RELATIVE_TIME, _PERIOD_TIME) for match in pattern.finditer(question)]
    if not found:
        return None
    start, end = min(found)
    return " ".join(question[start:end].split())


def perspective(question: str) -> Perspective:
    """Whether the question asks about the agreement as first made, at a time it names, as it stands, or does not say.
    Only the last two are read at the run's date."""
    if _HISTORICAL.search(question):
        return "historical"
    if asked_time(question) is not None:
        return "dated"
    return "current" if _CURRENT.search(question) else "unstated"


def parts_of(sections: Sequence[Readable]) -> dict[str, str]:
    """section id → the part of the document it is in: "body", "schedule 1", "annex b", "amendment", "order form". A part
    runs from its heading to the next; a heading that names no part (RECITALS, a clause title) changes nothing."""
    part, out = "body", {}
    for section in sections:
        heading = _PART_HEADING.match(section.heading or "")
        if heading is not None:
            if heading.group("kind"):
                part = f"{heading.group('kind').casefold()} {heading.group('id').casefold()}"
            else:
                part = "amendment" if heading.group("amendment") else " ".join(heading.group("named").casefold().split())
        out[section.id] = part
    return out


def _ranks(ranked: str, part: str) -> bool:
    """Whether a part a precedence statement names ("Schedule 1", "the Schedules", "these General Terms", "the Order
    Form", "this Amendment") is ``part``."""
    key = re.sub(r"^(?:the|these|this)\s+", "", " ".join(ranked.casefold().split()))
    if part == "body":
        return key in _BODY
    if part == "amendment":
        return key.endswith(("amendment", "addendum"))
    kind = part.split()[0]
    if kind in ("schedule", "annex", "exhibit", "appendix"):
        return key == part or key == {"appendix": "appendices", "annex": "annexes"}.get(kind, kind + "s")
    return key == part


def _inside(span: tuple[str, int, int], passage: Passage | None) -> bool:
    section_id, start, end = span
    return passage is not None and section_id == passage.section_id and start < passage.end and end > passage.start


def _excerpt(text: str, limit: int = 180) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def assess(relations: Sequence[Relation], spans: Sequence[tuple[str, int, int]], answer: str, question: str, parts: dict[str, str]) -> list[Note]:
    """What each relation means for one finding. ``spans`` are its verified quotes as (section id, start, end) in the
    stored text: an unverified quote grounds nothing. ``answer`` is the model's conclusion and stated position."""
    notes: list[Note] = []
    said = stated_values(answer, answer=True)
    asked, when = perspective(question), asked_time(question)
    explained: set[tuple[str, int, int]] = set()
    for index, relation in enumerate(relations):
        if relation.kind != "replaces":
            continue
        old = [s for s in spans if _inside(s, relation.replaced)]
        new = [s for s in spans if _inside(s, relation.replacement)]
        if not old and not new:
            continue
        explained.update(old + new)
        where = f"{relation.statement.label} (“{_excerpt(relation.statement.text)}”)"
        target = f"clause {relation.target}"
        if old and relation.scope:
            notes.append(
                Note(
                    index,
                    "scoped",
                    f"the quoted {target} is changed by {where} only within a stated limit ({relation.scope}); "
                    "whether that limit applies to this question is not established by code",
                )
            )
            continue
        since = f", in effect from {relation.effective}" if relation.effective else ""
        does = "replaces in full" if relation.replacement or "replac" in relation.statement.text.lower() else "deletes"
        new_wording = f"the quoted passage is the new wording of {target} that {where} gives"
        # What code sees in the answer, and no more: whether it quotes the replacement, and the values it states that only
        # one side states (one both state, such as an unchanged "45 days", shows nothing either way). Neither says which
        # wording the answer applies: an answer can quote the replacement and conclude from the replaced wording.
        new_values = stated_values(relation.replacement.text) if relation.replacement else set()
        old_values = stated_values(relation.replaced.text) if relation.replaced else set()
        states_new, states_old = bool(said & (new_values - old_values)), bool(said & (old_values - new_values))
        if asked == "historical":
            original = f"the quoted {target} is the original wording; {where} later replaced it, and the question asks about the original agreement"
            notes.append(Note(index, "context", original if old else new_wording))
        elif relation.scope:
            notes.append(Note(index, "context", new_wording))
        elif asked == "dated":
            quoted = f"the quoted {target} is text that {where} {does}{since}" if old else f"{new_wording}{since}"
            notes.append(Note(index, "dated", f"{quoted}; the question names a time (“{when}”), and which wording applied then is not decided by code"))
        elif new and states_old and not states_new:
            notes.append(
                Note(
                    index,
                    "old_value",
                    f"the answer quotes the new wording of {target} that {where} gives, but states a value only the replaced wording states "
                    "and none only the new wording states; which wording governs is not decided by code",
                )
            )
        elif not old:
            notes.append(Note(index, "context", new_wording))
        elif new or states_new:
            seen = "also quotes the replacement" if new else "states a value only the replacement states"
            notes.append(Note(index, "context", f"the quoted {target} was replaced by {where}, and the answer {seen}"))
        else:
            asks = (
                "the question asks about the agreement as it stands"
                if asked == "current"
                else "the question names no time and does not say it asks about the original agreement"
            )
            unquoted = "the answer neither quotes the replacement nor states a value only it states, and " if does == "replaces in full" else ""
            notes.append(
                Note(
                    index,
                    "replaced",
                    f"the quoted {target} is text that {where} {does}{since}; {unquoted}{asks}. "
                    "The quote is still where it was found; which wording governs is not decided by code",
                )
            )
    involved = sorted({parts.get(s[0], "body") for s in spans if s not in explained})
    if len(involved) >= 2:
        for index, relation in enumerate(relations):
            if relation.kind == "precedence" and all(any(_ranks(ranked, part) for ranked in relation.parts) for part in involved):
                notes.append(
                    Note(
                        index,
                        "precedence",
                        f"the quoted passages come from {' and '.join(involved)}, and {relation.statement.label} ranks those parts for a conflict "
                        f"(“{_excerpt(relation.statement.text)}”); whether they conflict on this point, and which applies, is not decided by code",
                    )
                )
    return notes


# ----------------------------------------------------------------------------- the record


def relevant(relations: Sequence[Relation], section_ids: set[str]) -> list[Relation]:
    """The relations a run records: those whose statement, provision or new wording is in a section it read or quoted,
    then the rest, up to MAX_RELATIONS, in reading order."""
    near = [r for r in relations if any(p is not None and p.section_id in section_ids for p in (r.statement, r.replaced, r.replacement))]
    return (near + [r for r in relations if r not in near])[:MAX_RELATIONS]


def dump(recorded: Recorded) -> str:
    return json.dumps(
        {"relations": [asdict(r) for r in recorded.relations], "notes": {str(k): [asdict(n) for n in v] for k, v in recorded.notes.items() if v}},
        ensure_ascii=False,
    )


def load(raw: str | None) -> Recorded:
    """A run's recorded relations: empty for a run recorded before policy-v11 (null), which is never re-derived."""
    if not raw:
        return Recorded()
    data = json.loads(raw)

    def passage(value: dict[str, object] | None) -> Passage | None:
        return Passage(**value) if value else None  # type: ignore[arg-type]

    relations = tuple(
        Relation(
            kind=r["kind"],
            statement=Passage(**r["statement"]),
            target=r.get("target"),
            replaced=passage(r.get("replaced")),
            replacement=passage(r.get("replacement")),
            scope=r.get("scope"),
            effective=r.get("effective"),
            parts=tuple(r.get("parts") or ()),
        )
        for r in data.get("relations", [])
    )
    return Recorded(relations, {int(k): tuple(Note(**n) for n in v) for k, v in data.get("notes", {}).items()})
