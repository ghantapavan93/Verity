"""The sections a clause depends on, where the contract itself says which (retrieval-v2, 2026-10-14).

BM25 hands the model the sections whose words match the question. A clause's meaning can sit elsewhere, and the contract
says where: a defined term ("Business Day", "Initial Term"), an amendment that replaces or overrides it ("Section 4.1 of
the Lease is replaced", "Notwithstanding Section 8.2"), a clause or schedule it cites ("subject to Section 8.5", "as set
out in Schedule C"). None of these shares the question's words, so none was handed. Measured on 49 hand-labelled
questions over 10 unfamiliar agreements in three formats (outside the
repository): every passage an answer needs was handed in 121 of 147 cases; definitions in 28 of 42; and once a PDF
reading handed the superseded rent ($8,450) without the amendment that changed it ($7,980).

So after the BM25 ranking, the top ``SEEDS`` sections are followed one hop along those links, and at most
``MAX_LINKS`` linked sections are added after the ranked ones, amendments first, then definitions, then references; a
link is added only while the handed text stays within what ``k`` full sections may already carry, so the prompt's worst
case does not grow. Measured: 121 → 137 of 147, definitions 42 of 42, the superseded-without-amendment case gone; on the
197 labelled control cases (CUAD-30, SkillOpt-30, goldens) recall 0.954 → 0.959 for 14% more section text. Replacing
the lowest ranks instead of adding lowered recall (0.944) and was rejected; so was a wider list of amending words.

Each linked section carries why it was handed (the kind, the seed, the term or the reference), recorded on the run.

retrieval-v3 (2026-10-30, the stress test's retrieval corner): an amendment that changes what is handed is handed with
it. The amendments of every ranked section come first, and a section added as a link brings its own next, so a
definition or a cited clause no longer arrives in its superseded wording without the amendment that changed it. An
amendment is found by the clause it names or that clause's numbered parent, and by the definition it restates or names.
A definition is read in every pair of quotation marks; a word of construction is not a term.
"""

from __future__ import annotations

import heapq
import itertools
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, Protocol

from ..ingest.sections import stated_clause_numbers
from .status import ATTACHMENT, references

SEEDS = 3  # the top ranked sections whose definitions and references are followed; amendments from every handed one
MAX_LINKS = 2  # linked sections added after the ranked ones, at most

# retrieval-v3: an "amendment" changes the text of what it names; an "override" ranks above it or reaches into another
# instrument without saying it changes it ("Notwithstanding Section 8.2", "Section 4.1 of the Lease"); an "amended
# definition" is a definition of a term the clause uses, restated by an amending sentence.
LinkKind = Literal["amendment", "override", "amended definition", "definition", "reference"]
_PRIORITY: dict[LinkKind, int] = {"amendment": 0, "override": 0, "amended definition": 1, "definition": 1, "reference": 2}

# A defining sentence: the term between a pair of quotation marks, up to three words, then a defining verb. Every pair a
# contract is drafted with (retrieval-v3, stress test 2026-10-30, retrieval corner): until then only double quotes were
# read, so a definition in single quotes or guillemets, as UK and EU drafting writes them, was never linked. A single
# quotation mark opens a term only where no letter precedes it and closes one only where none follows, so an apostrophe
# never does ("the Parties' and the Members' interest includes"), and a term may hold one ("‘Customer’s Data’").
_QUOTED = (
    r"(?:[“\"](?P<double>[^”\"]{1,60})[”\"]"
    r"|(?<!\w)‘(?P<curly>(?:[^‘’\n]|’(?=\w)){1,60}?)’(?!\w)"
    r"|(?<![\w'])'(?P<straight>(?:[^'\n]|'(?=\w)){1,60}?)'(?!\w)"
    r"|«\s?(?P<guillemet>[^«»\n]{1,60}?)\s?»"
    r"|„(?P<low>[^„“”\n]{1,60})[“”])"
)
_DEFINES = re.compile(_QUOTED + r"(?:\s+[\w-]+){0,3}?\s+(?:means|mean|shall mean|has the meaning|have the meaning|is to|are to|refers to|includes)\b")
# How an amending sentence names a definition it changes without restating it: 'the definition of "Cut-Off Date"'.
_NAMES_DEFINITION = re.compile(r"\bdefinitions?\s+of\s+(?:the\s+(?:term|word)s?\s+)?" + _QUOTED, re.IGNORECASE)
# The words of construction an interpretation clause defines ('"including" means "including without limitation"', '"to"
# means "to but excluding"'). They are not terms: every clause uses them, so their definition took one of the two link
# places from whatever the clause cites (CUAD, 2026-10-30: 198 of 17,850 runs).
_CONSTRUCTION = frozenset(
    {"to", "from", "until", "till", "through", "include", "includes", "including", "or", "and", "any", "will", "shall", "may"}
    | {"herein", "hereof", "hereunder", "hereto", "hereby", "to the extent"}
)
_OPENING_QUOTE = "“\"‘'«„"
_CAPITALS_AROUND = 80  # characters either side of a use in capitals that must read as capitals
# The verbs that change another clause's text or override it, or a reference into another instrument ("Section 4.1 of
# the Lease"), which is how an amendment names what it changes. A wider list (modify, prevail, reduced …) added no case
# and more false links on CUAD.
_AMENDS = re.compile(
    r"\b(?:amend(?:ed|s)?|replac(?:e|ed|es|ing)|delet(?:e|ed|es)|restat(?:e|ed)|supersed(?:e|ed|es)|substitut(?:e|ed)|in lieu of|notwithstanding)\b"
    r"|\b(?:Section|Clause|Article)s?\s+\d+(?:\.\d+)*(?:\([a-z0-9]{1,4}\))*\s+of\s+the\s+(?:[A-Z][\w-]*\s+){0,3}(?:Agreement|Lease|Contract|Licence|License|Plan)\b",
    re.IGNORECASE,
)
# A sentence that changes the text of a provision it names, and so reaches every section handed (retrieval-v3): the
# provision, then its change ("Section 1.3 of the Agreement is hereby amended", "The definition of "Cut-Off Date" is
# deleted and replaced"), or the change, then the provision ("amend Article 16", "replacing the definition of"). The
# rest of ``_AMENDS`` is followed from the top ranked sections only, as in retrieval-v2. Measured on CUAD-510: followed
# from every handed section, any sentence with an amending word took the place of the definitions the answers used
# (definition recall 0.595 -> 0.538): most name a clause in passing ("Notwithstanding Section 8.2", "in accordance with
# Section 2.4 of the Loan Agreement", "substitute goods ... Sections 2.7 and 8", "as amended from time to time in
# accordance with Section 20.3"). A permission is not a change: "this Agreement may be amended only in writing".
_CHANGES = re.compile(
    r"\b(?:Section|Clause|Article|Paragraph|definition)s?\b.{0,160}?\b(?:is|are|(?<!may )(?<!may only )(?<!can )(?<!might )(?<!could )be)\s+(?:\w+\s+){0,2}?"
    r"(?:amended|deleted|replaced|restated|superseded|substituted|cancell?ed|revoked)\b"
    r"|\b(?:amend|amends|amending|delete|deletes|deleting|replace|replaces|replacing|restate|restates|restating|supersede|supersedes"
    r"|superseding|substitute|substitutes|substituting)\s+(?:and\s+\w+\s+)?(?:the\s+)?(?:(?:Section|Clause|Article|Paragraph)s?\s+\d|definitions?\s+of)",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.;!?])\s+")
_NAMING_LINE = re.compile(r"^[ \t]*(?:Section|Clause|Article)[ \t]+(\d+(?:\.\d+)*)[ \t]+of\b", re.IGNORECASE | re.MULTILINE)


class Readable(Protocol):
    number: str
    heading: str
    text: str


@dataclass(frozen=True)
class Link:
    index: int  # the linked section's position in the document's sections
    kind: LinkKind
    seed: int  # the section it was followed from: a ranked one, or for an amendment the handed section it amends
    by: str  # the term, or the reference, the link was made by


@dataclass(frozen=True)
class Amendments:
    """What amends what in one document (retrieval-v3), read once per call: by the section amended, a link to each
    section with a sentence that amends or overrides it, in document order; by defined term, the sections whose amending
    sentence restates or names its definition."""

    of: dict[int, list[Link]] = field(default_factory=dict)
    of_term: dict[str, list[int]] = field(default_factory=dict)


def _definitions(sections: Sequence[Readable]) -> dict[str, int]:
    """Each defined term, with the first section that defines it. Read once for a run's seeds, not kept between runs: a
    cache keyed by the texts held 64 whole contracts in memory to save 30 ms against a model call of seconds (a 3.4 MB
    filing, backend audit, 2026-10-19)."""
    found: dict[str, int] = {}
    for index, text in enumerate(s.text for s in sections):
        for match in _DEFINES.finditer(text):
            term = _term(match, text)
            if term and term not in found:
                found[term] = index
    return found


def _term(match: re.Match[str], text: str) -> str | None:
    """The term a defining sentence defines, or None when it defines a word of construction: one of ``_CONSTRUCTION``, a
    lower-case word the definition quotes again ('"including" means "including without limitation"'), or no word at all
    ('"$" means', '"[***]" means')."""
    term = (match.group(match.lastgroup or 0) or "").strip()
    if not any(ch.isalpha() for ch in term) or term.casefold() in _CONSTRUCTION:
        return None
    if term.islower() and re.compile(rf"\s*[{_OPENING_QUOTE}]\s?{re.escape(term)}(?!\w)", re.IGNORECASE).match(text, match.end()):
        return None
    return term


def _plural(term: str) -> str:
    """The term and its plural as a pattern: "Party" or "Parties", "Fee" or "Fees", "Business" or "Businesses"."""
    if len(term) > 1 and term[-1] in "yY" and term[-2].lower() not in "aeiou":
        return re.escape(term[:-1]) + ("(?:Y|IES)" if term[-1] == "Y" else "(?:y|ies)")
    return re.escape(term) + ("(?:S|ES)?" if term.isupper() else "(?:s|es)?")


@lru_cache(maxsize=8192)
def _use_of(term: str) -> re.Pattern[str]:
    """How a term is used: a capitalised term as written, its plural too; a lower-case one as written, its case included
    (retrieval-v3: in any case until then, so '"control" means' was used by every "Control"). Compiled once per term: a
    long agreement defines hundreds, and the module's own pattern cache holds 512 (a 4 MB filing, 2026-10-14)."""
    if term[:1].isupper():
        return re.compile(rf"(?<![\w{_OPENING_QUOTE}]){_plural(term)}\b")
    return re.compile(rf"\b{re.escape(term)}\b")


@lru_cache(maxsize=8192)
def _capitals_of(term: str) -> re.Pattern[str]:
    """A capitalised term as a clause printed in capitals writes it: "FEES", "PARTIES"."""
    return re.compile(rf"(?<![\w{_OPENING_QUOTE}]){_plural(term.upper())}\b")


def _in_capitals(text: str, start: int, end: int) -> bool:
    """Whether the text around a span reads as capitals: four upper-case letters or more to every lower-case one."""
    around = text[max(0, start - _CAPITALS_AROUND) : end + _CAPITALS_AROUND]
    return sum(ch.isupper() for ch in around) >= 4 * sum(ch.islower() for ch in around)


def _uses(text: str, term: str) -> int | None:
    """Where the text uses the term, or None. A capitalised term is also used in capitals where the text around it is
    printed in capitals (retrieval-v3: a limitation clause in capitals used "FEES" and was never linked to "Fees"); an
    acronym in mixed text ("the ACT standard") is not the term "Act"."""
    match = _use_of(term).search(text)
    at = match.start() if match else None
    if term[:1].isupper() and not term.isupper():
        for capitals in _capitals_of(term).finditer(text, 0, len(text) if at is None else at):
            if _in_capitals(text, capitals.start(), capitals.end()):
                return capitals.start()
    return at


@dataclass(frozen=True)
class _Amending:
    """A sentence that amends or overrides: the clauses it names; whether it changes their text (``_CHANGES``); and, when
    it does, the defined terms it restates or names the definition of ('"Cut-Off Date" means', 'the definition of
    "Cut-Off Date"')."""

    clauses: list[str]
    changes: bool
    terms: list[str]


def _amending(sections: Sequence[Readable]) -> list[list[_Amending]]:
    """For each section, each of its sentences that amends or overrides, in order. Read once for every seed (each seed
    re-read the whole agreement, 2.8 s on a 4 MB filing)."""
    found: list[list[_Amending]] = []
    for section in sections:
        sentences = _SENTENCE.split(" ".join(section.text.split()))
        found.append([_amending_sentence(sentence) for sentence in sentences if _AMENDS.search(sentence)])
    return found


def _amending_sentence(sentence: str) -> _Amending:
    if not _CHANGES.search(sentence):
        return _Amending(references(sentence), False, [])
    defined = [term for match in _DEFINES.finditer(sentence) if (term := _term(match, sentence))]
    named = [term for match in _NAMES_DEFINITION.finditer(sentence) if (term := (match.group(match.lastgroup or 0) or "").strip())]
    return _Amending(references(sentence), True, list(dict.fromkeys(defined + named)))


def _stated(sections: Sequence[Readable]) -> list[set[str]]:
    """The clause numbers each section's text opens (`stated_clause_numbers`), read once per call."""
    return [stated_clause_numbers([section.text]) for section in sections]


def _opened(sections: Sequence[Readable], stated: list[set[str]] | None = None) -> dict[str, list[int]]:
    """The sections whose text opens each clause number, the first two of each: read once per call (each reference read
    every section again, 1.6 s of 2.2 on a 2.7 MB filing)."""
    opened: dict[str, list[int]] = {}
    for index, numbers in enumerate(stated if stated is not None else _stated(sections)):
        for number in numbers:
            places = opened.setdefault(number, [])
            if len(places) < 2:
                places.append(index)
    return opened


def _amendments(sections: Sequence[Readable], amending: list[list[_Amending]], defined: dict[str, int], stated: list[set[str]]) -> Amendments:
    """What each amending sentence amends or overrides: every section numbered as a clause it names, or opening it. A
    sentence that changes text reaches further (retrieval-v3, stress test 2026-10-30, retrieval corner): when no section
    is numbered so or opens it, the nearest numbered parent, so "Section 1.3" reaches §1 when the reader left 1.3 inside
    it, as a definitions list read from TXT or PDF is left; and a definition it restates or names, in the section that
    defines the term, whether or not a clause is named ('The definition of "Cut-Off Date" is hereby amended to read ...').
    Until then an amendment matched only the numbers its target opened."""
    owners: dict[str, list[int]] = {}
    numbered: dict[str, list[int]] = {}
    for index, section in enumerate(sections):
        # A line that opens "Section 5.4 of the Agreement is deleted …" reads as opening 5.4 (ingest.sections): the clause
        # it names is not its own, or every amendment of 5.4 would amend the others and none the agreement's clause.
        names = set(_NAMING_LINE.findall(section.text))
        for number in (stated[index] - names) | ({section.number} if section.number else set()):
            owners.setdefault(number, []).append(index)
        if section.number:
            numbered.setdefault(section.number, []).append(index)
    found = Amendments()
    for index, sentences in enumerate(amending):
        targets: dict[int, tuple[LinkKind, str]] = {}  # each section named, with how and by what the first sentence names it
        for sentence in sentences:
            kind: LinkKind = "amendment" if sentence.changes else "override"
            for reference in sentence.clauses:
                for target in _named(reference, index, owners, numbered if sentence.changes else {}):
                    if target not in targets or (sentence.changes and targets[target][0] == "override"):
                        targets[target] = (kind, f"§{reference}")
            for term in sentence.terms:
                target = defined.get(term, index)
                if target != index:
                    targets.setdefault(target, ("amendment", f'the definition of "{term}"'))
                    if index not in (amenders := found.of_term.setdefault(term, [])):
                        amenders.append(index)
        for target, (kind, named) in targets.items():
            found.of.setdefault(target, []).append(Link(index, kind, target, named))
    return found


def _named(reference: str, owner: int, owners: dict[str, list[int]], numbered: dict[str, list[int]]) -> list[int]:
    """The sections an amending sentence's reference names: each numbered so or opening that clause; else, among
    ``numbered``, the nearest numbered parent ("1.3" is in §1). Never the amending section itself."""
    found = [i for i in owners.get(reference, []) if i != owner]
    parts = reference.split(".")
    for end in range(len(parts) - 1, 0, -1):
        if found:
            break
        found = [i for i in numbered.get(".".join(parts[:end]), []) if i != owner]
    return found


def _resolve(reference: str, sections: Sequence[Readable], owner: int, opened: dict[str, list[int]] | None = None) -> list[int]:
    """The section a reference names: numbered exactly so; else the one whose text opens that clause; else the nearest
    numbered parent ("8.5.2" is in §8.5). ``opened`` is `_opened(sections)`, when the caller has it already."""
    exact = [i for i, s in enumerate(sections) if i != owner and s.number == reference]
    if exact:
        return exact
    first = [i for i in (opened if opened is not None else _opened(sections)).get(reference, []) if i != owner]
    if first:
        return first[:1]
    parents = [(len(s.number), i) for i, s in enumerate(sections) if i != owner and s.number and reference.startswith(s.number + ".")]
    return [max(parents)[1]] if parents else []


def links_of(
    sections: Sequence[Readable],
    seed: int,
    opened: dict[str, list[int]] | None = None,
    defined: dict[str, int] | None = None,
    amendments: Amendments | None = None,
) -> list[Link]:
    """Every link from one section, in the order found: amendments of it, definitions it uses (a definition an amending
    sentence restates before the one it restates), what it cites. ``opened``, ``defined`` and ``amendments`` are
    `_opened`, `_definitions` and `_amendments` of the sections, when the caller has them already."""
    defined = defined if defined is not None else _definitions(sections)
    if amendments is None:
        stated = _stated(sections)
        amendments, opened = _amendments(sections, _amending(sections), defined, stated), _opened(sections, stated)
    found = list(amendments.of.get(seed, []))
    own = sections[seed]
    used = sorted((at, term) for term, where in defined.items() if where != seed and (at := _uses(own.text, term)) is not None)
    for _, term in used:
        found += [Link(index, "amended definition", seed, term) for index in amendments.of_term.get(term, []) if index != seed]
        found.append(Link(defined[term], "definition", seed, term))
    cited = references(own.text)
    if cited and opened is None:
        opened = _opened(sections)
    for reference in cited:
        found += [Link(index, "reference", seed, f"§{reference}") for index in _resolve(reference, sections, seed, opened)]
    for kind, mark in ATTACHMENT.findall(own.text):
        name = re.compile(rf"^\s*{re.escape(kind)}\s+{re.escape(mark)}\b", re.IGNORECASE)
        found += [Link(index, "reference", seed, f"{kind} {mark}") for index, s in enumerate(sections) if index != seed and name.match(s.heading)]
    return found


def linked(sections: Sequence[Readable], ranked: Sequence[int], window: int) -> list[Link]:
    """The sections to add after the ranked ones, at most ``MAX_LINKS``, and only while the handed text stays within
    ``len(ranked)`` full windows: first the amendments of every ranked section and the overrides of the top ``SEEDS``, in
    rank order; then what the top ``SEEDS`` use and cite, definitions before references. A section added brings its own
    amendments next, ahead of any further definition or reference (retrieval-v3, stress test 2026-10-30, retrieval
    corner): links were followed one hop from the top three, so a definition or a cited clause handed as a link came in
    its superseded wording, and the amendment that changed it never did."""
    stated = _stated(sections)
    defined = _definitions(sections)
    amendments = _amendments(sections, _amending(sections), defined, stated)
    opened = _opened(sections, stated)
    queue: list[tuple[tuple[int, int, int], int, Link]] = []
    order = itertools.count()
    for rank, seed in enumerate(ranked):
        followed = links_of(sections, seed, opened, defined, amendments) if rank < SEEDS else _changes_of(amendments, seed)
        for place, link in enumerate(followed):
            heapq.heappush(queue, ((_PRIORITY[link.kind], rank, place), next(order), link))
    chosen: list[Link] = []
    handed = set(ranked)
    used = sum(min(len(sections[i].text), window) for i in ranked)
    budget = len(ranked) * window
    while queue and len(chosen) < MAX_LINKS:
        link = heapq.heappop(queue)[2]
        size = min(len(sections[link.index].text), window)
        if link.index in handed or used + size > budget:
            continue
        chosen.append(link)
        handed.add(link.index)
        used += size
        for place, amendment in enumerate(_changes_of(amendments, link.index)):
            heapq.heappush(queue, ((0, len(ranked) + len(chosen), place), next(order), amendment))
    return chosen


def _changes_of(amendments: Amendments, index: int) -> list[Link]:
    return [link for link in amendments.of.get(index, []) if link.kind == "amendment"]


def because(link: Link, sections: Sequence[Readable]) -> str:
    """Why a linked section was handed, in words: 'the definition of "Business Day", used in §2.7'."""
    seed = sections[link.seed]
    where = f"§{seed.number}" if seed.number else seed.heading
    if link.kind == "definition":
        return f'the definition of "{link.by}", used in {where}'
    if link.kind == "amended definition":
        return f'the definition of "{link.by}" as amended, used in {where}'
    if link.kind in ("amendment", "override"):
        return f"it amends or overrides {link.by}, handed as {where}"
    return f"{where} refers to {link.by}"
