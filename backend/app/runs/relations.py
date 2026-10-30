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
(runs.status.check_replaced) acts on a question about the agreement as it stands, answered from text the contract
replaced in full, without the replacement; since policy-v16 `check_old_value` lowers a pass that quotes the replacement
but states only values the replaced wording states. The first-visitor acceptance test (2026-10-14) is why: the
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
from .values import NOT_A_QUANTITY, date_spans, stated_values, wording_values

RelationKind = Literal["replaces", "precedence"]
Effect = Literal["replaced", "scoped", "precedence", "dated", "old_value", "context"]
Perspective = Literal["historical", "dated", "current", "unstated"]
# What code raises against a finding and cannot resolve (runs.account): a limit, a ranking, a time the question names, an
# answer that quotes the replacement and states only the replaced values, where it did not lower a pass (policy-v16:
# runs.status.check_old_value). "replaced" sets the status; "context" is none.
CONCERNS: frozenset[Effect] = frozenset({"scoped", "precedence", "dated", "old_value"})

# A provision named, then the verb that replaces it: "clause 3.2 of the Agreement is deleted in its entirety and …". One
# family since policy-v17: "is amended to read (in its entirety) as follows", "shall read as follows" and "is amended by
# deleting the definition of 'X' … and replacing it" were not read, and a pass quoting the text they replace stood with
# code's own day count of it (stress test, 2026-10-30; in the local EDGAR corpus, 0 of 25 and 52 of 315 such statements
# were located). The part a statement names after "amended by deleting" is its `part`.
_REPLACED_VERB = re.compile(
    r"\b(?:is|are|shall\s+be|will\s+be)\s+(?:hereby\s+)?"
    r"(?:deleted(?:\s+in\s+(?:its|their)\s+entirety)?(?:\s+and\s+replaced)?|replaced(?:\s+in\s+(?:its|their)\s+entirety)?|superseded"
    r"|amended\s+and\s+restated|amended\s+to\s+read|substituted"
    r"|amended\s+by\s+(?:deleting|striking)\s+(?P<part>the\s+definition\s+of\s+[\"“][^\"”]{1,60}[\"”]|the\s+words\s+[\"“][^\"”]{1,80}[\"”])"
    r"[^.;:]{0,60}?\s+and\s+(?:replacing|substituting|inserting))\b"
    r"|\b(?:shall|will)\s+(?:hereby\s+)?read\s+(?:in\s+(?:its|their)\s+entirety\s+)?as\s+follows\b",
    re.IGNORECASE,
)
# The verb, then the provision: "… amended by deleting Section 3.2 in its entirety and replacing it with …", "… and
# inserting the following in lieu thereof".
_DELETING = re.compile(
    rf"\bdeleting\s+(?P<ref>{REFERENCE.pattern}(?:\([a-z0-9]{{1,4}}\))*)[^.;:]{{0,40}}?\s+and\s+(?:(?:replacing|substituting)\s+(?:it|the\s+same)|inserting)\b",
    re.IGNORECASE,
)
# One definition of a clause, named by the statement ('the definition of "Notice Period"'), and where the clause states it.
_DEFINITION_NAMED = re.compile(r"\bdefinition\s+of\s+[\"“](?P<term>[^\"”]{1,60})[\"”]", re.IGNORECASE)
_DEFINITION_ENDS = re.compile(r"[.;](?=\s|$)|\n")
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
    r"[^.;:\"“]{0,60}?(?:\b(?:with|by|to\s+read)\b(?:\s+as\s+follows|\s+(?:the\s+)?following(?:[^;:\"“\n]{0,40}?(?=:))?)?"
    r"|\bas\s+follows\b|\bthe\s+following\s+is\s+substituted\b|\bthe\s+following\s+in\s+lieu\s+thereof\b)\s*:?\s*",
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
# A term the document defines in brackets after what defines it: 'dated September 18, 2025 (the "Amendment Date")'.
_DEFINED_TERM = re.compile(r"\(\s*(?:the\s+)?[\"“](?P<term>[^\"”]*)[\"”]\s*\)")
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
    rf"(?:(?:the\s+)?(?:calendar\s+|financial\s+|fiscal\s+)?year\s+)?(?:19|20)\d{{2}}\b{NOT_A_QUANTITY}",
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
    starts: tuple[str, ...] = ()  # replaces: every start code read in the statement (ISO dates), reached or not


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
    """The sections and, each built once when first needed, where each clause number opens, which sections are numbered
    so, and the dates the document's defined terms name: no section is re-read per statement. Until policy-v17 a
    provision's section and a start named by a defined term were each found by scanning every section once per
    statement, so a document of many statements cost the square of its length, in the request thread (stress test,
    2026-10-30: 65 s to locate a crafted 5 MB upload)."""

    def __init__(self, sections: Sequence[Readable]) -> None:
        self.sections = sections
        self._opened: dict[str, list[int]] | None = None
        self._openings: dict[int, list[tuple[str, int]]] = {}
        self._numbered: dict[str, list[int]] | None = None
        self._defined: dict[str, set[str]] | None = None
        self._definitions: dict[str, Passage] | None = None
        self._index: dict[str, int] | None = None

    def index_of(self, section_id: str) -> int:
        if self._index is None:
            self._index = {section.id: index for index, section in enumerate(self.sections)}
        return self._index[section_id]

    def definition(self, term: str, parts: dict[str, str]) -> Passage | None:
        """Where the body of the agreement (no amendment) first defines ``term``: from its term to the end of its sentence."""
        if self._definitions is None:
            self._definitions = {}
            for section in self.sections:
                if parts.get(section.id) == "amendment":
                    continue
                whole = Passage(section.id, _label(section), 0, len(section.text), section.text)
                for match in _FRESH_DEFINITION.finditer(section.text):
                    found = _definition_in(whole, f'the definition of "{match.group("term")}"')
                    if found is not None:
                        self._definitions.setdefault(match.group("term"), found)
        return self._definitions.get(term)

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
        if self._numbered is None:
            self._numbered = {}
            for index, section in enumerate(self.sections):
                self._numbered.setdefault(section.number, []).append(index)
        numbered = [i for i in self._numbered.get(number, []) if self.sections[i].id != besides]
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
        if self._defined is None:
            self._defined = {}
            for section in self.sections:
                text = section.text
                for match in _DEFINED_TERM.finditer(text):
                    dates = {v for v in stated_values(text[max(0, match.start() - 60) : match.start()]) if v.startswith("d:")}
                    self._defined.setdefault(match.group("term"), set()).update(dates)
        found = self._defined.get(term, set())
        return _first_day(next(iter(found))) if len(found) == 1 else None


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
            if verb.group("part"):  # "Section 1 … is amended by deleting the definition of 'X' … and replacing it"
                only = verb.group("part")
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
    stated_once: set[tuple[int, str]] = set()
    for named_at, target, verb_end, only in statements:
        head, tail = _sentence(text, named_at, verb_end, colon_ends=True)
        # "… is deleted and the following is substituted" is one statement, not two (stress test, 2026-10-30).
        if (head, target) in stated_once:
            continue
        stated_once.add((head, target))
        wording = _new_wording(text, verb_end)
        stated = text[head : min(tail, wording[0]) if wording else tail]  # limits are read in the statement, not in the new wording
        # One paragraph of a clause ("Paragraph (b) of clause 6.1", "clause 6.1(b)") is a limit on the clause, as written:
        # code locates the clause and does not decide which of its words a quote leans on.
        limits = ([" ".join(only.split())] if only else []) + [" ".join(m.group(0).split()) for m in _LIMIT.finditer(stated)]
        replaced = document.provision(target, section.id)
        # One definition of the clause, where the clause states it, is the replaced text, and no limit: a quote of it is a
        # quote of replaced text, and a quote of another definition in the clause is not (policy-v17). A definition the
        # clause does not state stays a limit, as written (FAILURE-ENVELOPE: never generalised to the clause).
        definition = _definition_in(replaced, only) if replaced is not None and only else None
        if definition is not None:
            replaced, limits = definition, limits[1:]
        effective, starts = _started(document, stated, as_of, limits)
        yield Relation(
            "replaces",
            Passage(section.id, _label(section), head, tail, text[head:tail]),
            target=target,
            replaced=replaced,
            replacement=Passage(section.id, _label(section), wording[0], wording[1], text[wording[0] : wording[1]]) if wording else None,
            scope="; ".join(limits) or None,
            effective=effective,
            starts=tuple(starts),
        )


def _started(document: _Document, stated: str, as_of: date, limits: list[str]) -> tuple[str | None, list[str]]:
    """The start a statement states and code found already reached ("2025-09-18, the Amendment Date"), and every start it
    read (ISO dates); a start code cannot read, or one not yet reached, is added to ``limits``, as written."""
    effective = None
    starts: list[str] = []
    for begins in _STARTS.finditer(stated):
        when, said = document.date_named(begins.group("when")), " ".join(begins.group(0).split())
        if when is not None:
            starts.append(when.isoformat())
        if when is not None and when <= as_of:
            effective = f"{when.isoformat()}, {' '.join(begins.group('when').split())}"
        else:
            limits.append(said if when is None else f"{said} ({when.isoformat()}, not reached on {as_of.isoformat()})")
    return effective, starts


# A definition stated afresh: the term in quotation marks, then its defining verb, "now" or "shall" allowed between
# ("With effect from the Amendment Date, "Notice Period" means thirty (30) days", "… so that "Notice Period" now means …").
_FRESH_DEFINITION = re.compile(
    r"[\"“](?P<term>[^\"”]{1,60})[\"”]\s+(?:(?:shall\s+)?now\s+|shall\s+(?:hereby\s+)?)?(?:means?|has\s+the\s+meaning|refers?\s+to)\b", re.IGNORECASE
)


def _fresh_definitions(document: _Document, section: Readable, as_of: date, located: Sequence[Relation], parts: dict[str, str]) -> Iterator[Relation]:
    """A term an amendment defines afresh that the body of the agreement defines already: the body's definition is
    replaced text and the amendment's the replacement (policy-v17). Until then a fresh '"Notice Period" means thirty (30)
    days' in an amendment was no statement at all, and a pass quoting the body's ninety days stood with code's day count
    of it (stress test, 2026-10-30). Not a statement: a term the body does not define ("Amendment Date"), or a definition
    inside the new wording another statement quotes, which that statement already locates."""
    text = section.text
    for match in _FRESH_DEFINITION.finditer(text):
        if any(
            r.replacement is not None and r.replacement.section_id == section.id and r.replacement.start <= match.start() < r.replacement.end for r in located
        ):
            continue
        replaced = document.definition(match.group("term"), parts)
        if replaced is None or any(r.replaced == replaced for r in located):
            continue
        head, tail = _sentence(text, match.start(), match.end(), colon_ends=False)
        stop = _DEFINITION_ENDS.search(text, match.end())
        end = stop.end() if stop is not None and stop.group(0) != "\n" else (stop.start() if stop is not None else len(text))
        limits = [" ".join(m.group(0).split()) for m in _LIMIT.finditer(text[head : match.start()])]
        effective, starts = _started(document, text[head : match.start()], as_of, limits)
        yield Relation(
            "replaces",
            Passage(section.id, _label(section), head, tail, text[head:tail]),
            target=document.sections[document.index_of(replaced.section_id)].number or None,
            replaced=replaced,
            replacement=Passage(section.id, _label(section), match.start(), end, text[match.start() : end]),
            scope="; ".join(limits) or None,
            effective=effective,
            starts=tuple(starts),
        )


def _definition_in(provision: Passage, named: str) -> Passage | None:
    """The definition a statement names ('the definition of "Notice Period"'), where the provision states it: from its
    term to the end of its sentence. None when the statement names no definition or the provision does not state it."""
    term = _DEFINITION_NAMED.search(named)
    if term is None:
        return None
    opens = re.search(rf"[\"“]{re.escape(term.group('term'))}[\"”]\s+(?:shall\s+)?(?:means?|has\s+the\s+meaning|refers?\s+to)\b", provision.text, re.IGNORECASE)
    if opens is None:
        return None
    stop = _DEFINITION_ENDS.search(provision.text, opens.end())
    end = stop.end() if stop is not None and stop.group(0) != "\n" else (stop.start() if stop is not None else len(provision.text))
    start = provision.start + opens.start()
    return Passage(provision.section_id, provision.label, start, provision.start + end, provision.text[opens.start() : end])


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
    a target is found through a clause index built once, only when some statement names one. In an amendment, a term
    the body defines that it defines afresh is a replacement of that definition (`_fresh_definitions`)."""
    document = _Document(sections)
    parts = parts_of(sections)
    found: list[Relation] = []
    for section in sections:
        here = list(_replacements(document, section, as_of))
        if parts.get(section.id) == "amendment":
            here += _fresh_definitions(document, section, as_of, here, parts)
        found += here
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


def _without_number(text: str, number: str | None) -> str:
    """``text`` without the clause number it opens with, when it opens with ``number`` and that is no quantity ("5 Business
    Days' notice …" keeps its 5)."""
    return re.sub(rf"^\s*{re.escape(number)}(?!\d|\.\d){NOT_A_QUANTITY}", "", text, flags=re.IGNORECASE) if number else text


def _excerpt(text: str, limit: int = 180) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def assess(
    relations: Sequence[Relation],
    spans: Sequence[tuple[str, int, int]],
    answer: str,
    question: str,
    parts: dict[str, str],
    observed: str | None = None,
    conclusion: str | None = None,
) -> list[Note]:
    """What each relation means for one finding. ``spans`` are its verified quotes as (section id, start, end) in the
    stored text: an unverified quote grounds nothing. ``answer`` is the model's conclusion and stated position;
    ``observed`` is the value the model gave as what the contract says, when it gave one, and ``conclusion`` the
    conclusion alone, which the reader sees."""
    notes: list[Note] = []
    said = stated_values(answer, answer=True)
    position = stated_values(observed, answer=True) if observed else set()
    concluded = stated_values(conclusion, answer=True) if conclusion else set()
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
        # A clause's number is its name, not a value of either wording: the number a wording opens with ("1.2 Either party
        # …" against a replacement quoted without it) and every number a pointer names ("… under Section 7.3"), read alike
        # in the answer (review of policy-v16: "Under clause 1.2 as amended, 90 days" and "Under Sections 7.2 and 7.3" were
        # told they state a value only the replaced wording states).
        new_values = wording_values(_without_number(relation.replacement.text, relation.target)) if relation.replacement else set()
        old_values = wording_values(_without_number(relation.replaced.text, relation.target)) if relation.replaced else set()
        only_new, only_old = new_values - old_values, old_values - new_values
        # The model's stance is its own stated value when that names one of the values the two texts differ in: an answer
        # can mention both ("30 days; the amendment's 60 days does not apply") while its stated value is the replaced one.
        # Otherwise everything the answer states is read. No phrase in the prose is interpreted.
        # Each sentence names the source it read: "the value it gives as the contract's" when the stated value decided,
        # "states" when the whole answer did. A sentence about the whole answer is false when the prose names both values.
        by_position = bool(position & (only_new | only_old))
        stance = position if by_position else said
        states_new, states_old = bool(stance & only_new), bool(stance & only_old)
        gives_old = (
            "the value it gives as the contract's includes one only the replaced wording states and none only the new wording states"
            if by_position
            else "states a value only the replaced wording states and none only the new wording states"
        )
        # The conclusion is read on its own too: a stated value that names the replacement's value does not take back a
        # conclusion the reader sees that states only the replaced one (stress test, 2026-10-30: concluded "90 days",
        # stated "60 days", and the pass stood). Read together, the two would leave that hole open.
        concludes_old = bool(concluded & only_old) and not concluded & only_new
        if concludes_old and not (states_old and not states_new):
            gives_old = "its conclusion states a value only the replaced wording states and none only the new wording states"
        if asked == "historical":
            original = f"the quoted {target} is the original wording; {where} later replaced it, and the question asks about the original agreement"
            notes.append(Note(index, "context", original if old else new_wording))
        elif relation.scope:
            notes.append(Note(index, "context", new_wording))
        elif asked == "dated":
            quoted = f"the quoted {target} is text that {where} {does}{since}" if old else f"{new_wording}{since}"
            notes.append(Note(index, "dated", f"{quoted}; the question names a time (“{when}”), and which wording applied then is not decided by code"))
        elif new and ((states_old and not states_new) or concludes_old):
            notes.append(
                Note(
                    index,
                    "old_value",
                    f"the answer quotes the new wording of {target} that {where} gives, but {gives_old}; which wording governs is not decided by code",
                )
            )
        elif not old:
            notes.append(Note(index, "context", new_wording))
        elif new or states_new:
            seen = (
                "also quotes the replacement"
                if new
                else "gives as the contract's a value that includes one only the replacement states"
                if by_position
                else "states a value only the replacement states"
            )
            notes.append(Note(index, "context", f"the quoted {target} was replaced by {where}, and the answer {seen}"))
        else:
            asks = (
                "the question asks about the agreement as it stands"
                if asked == "current"
                else "the question names no time and does not say it asks about the original agreement"
            )
            neither = (
                "the answer does not quote the replacement, the value it gives as the contract's includes one only the replaced wording states and "
                "none only the replacement states, and "
                if by_position
                else "the answer neither quotes the replacement nor states a value only it states, and "
            )
            unquoted = neither if does == "replaces in full" else ""
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


def replacement_starts(sections: Sequence[Readable]) -> tuple[str, ...]:
    """Every start the document's replacement statements give (ISO dates, sorted), reached or not. Which statements a
    document holds does not depend on the day, only whether their starts are reached, so this is read once per document
    (application.start_run keeps it)."""
    return tuple(sorted({start for relation in locate_relations(sections, date.min) for start in relation.starts}))


def reached_start(starts: Sequence[str], as_of: date) -> str | None:
    """The latest of ``starts`` already reached on ``as_of``, or None. It changes exactly when another start is reached,
    so it can stand for every start comparison a run makes: a run asked before an amendment takes effect is not handed
    back as the answer after it."""
    return max((start for start in starts if start <= as_of.isoformat()), default=None)


def latest_start_reached(sections: Sequence[Readable], as_of: date) -> str | None:
    """The latest start a replacement statement in the document gives that is already reached on ``as_of``."""
    return reached_start(replacement_starts(sections), as_of)


def relevant(relations: Sequence[Relation], section_ids: set[str]) -> list[Relation]:
    """The relations a run records: those whose statement, provision or new wording is in a section it read or quoted,
    then the rest, up to MAX_RELATIONS, in reading order."""
    # By position, never by comparing relations: list membership through the dataclass's equality was quadratic.
    near = [i for i, r in enumerate(relations) if any(p is not None and p.section_id in section_ids for p in (r.statement, r.replaced, r.replacement))]
    chosen = set(near)
    return [relations[i] for i in near + [i for i in range(len(relations)) if i not in chosen]][:MAX_RELATIONS]


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
            starts=tuple(r.get("starts") or ()),
            parts=tuple(r.get("parts") or ()),
        )
        for r in data.get("relations", [])
    )
    return Recorded(relations, {int(k): tuple(Note(**n) for n in v) for k, v in data.get("notes", {}).items()})
