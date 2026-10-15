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
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Protocol

from ..ingest.sections import stated_clause_numbers
from .status import ATTACHMENT, references

SEEDS = 3  # the top ranked sections whose links are followed
MAX_LINKS = 2  # linked sections added after the ranked ones, at most

LinkKind = Literal["amendment", "definition", "reference"]
_PRIORITY: dict[LinkKind, int] = {"amendment": 0, "definition": 1, "reference": 2}

# A defining sentence: the term in quotes, up to three words, then a defining verb.
_DEFINES = re.compile(
    r"[“\"]([^”\"]{1,60})[”\"](?:\s+[\w-]+){0,3}?\s+(?:means|mean|shall mean|has the meaning|have the meaning|is to|are to|refers to|includes)\b"
)
# The verbs that change another clause's text or override it, or a reference into another instrument ("Section 4.1 of
# the Lease"), which is how an amendment names what it changes. A wider list (modify, prevail, reduced …) added no case
# and more false links on CUAD.
_AMENDS = re.compile(
    r"\b(?:amend(?:ed|s)?|replac(?:e|ed|es|ing)|delet(?:e|ed|es)|restat(?:e|ed)|supersed(?:e|ed|es)|substitut(?:e|ed)|in lieu of|notwithstanding)\b"
    r"|\b(?:Section|Clause|Article)s?\s+\d+(?:\.\d+)*(?:\([a-z0-9]{1,4}\))*\s+of\s+the\s+(?:[A-Z][\w-]*\s+){0,3}(?:Agreement|Lease|Contract|Licence|License|Plan)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.;!?])\s+")


class Readable(Protocol):
    number: str
    heading: str
    text: str


@dataclass(frozen=True)
class Link:
    index: int  # the linked section's position in the document's sections
    kind: LinkKind
    seed: int  # the ranked section it was followed from
    by: str  # the term, or the reference, the link was made by


def _clause_numbers(section: Readable) -> set[str]:
    numbers = set(stated_clause_numbers([section.text]))
    if section.number:
        numbers.add(section.number)
    return numbers


@lru_cache(maxsize=64)
def _definitions(texts: tuple[str, ...]) -> dict[str, int]:
    """Each defined term, with the first section that defines it."""
    found: dict[str, int] = {}
    for index, text in enumerate(texts):
        for match in _DEFINES.finditer(text):
            term = match.group(1).strip()
            if term and term not in found:
                found[term] = index
    return found


@lru_cache(maxsize=8192)
def _use_of(term: str) -> re.Pattern[str]:
    """How a term is used: a capitalised term as written (a plural too), a lower-case one in any case. Compiled once per
    term: a long agreement defines hundreds, and the module's own pattern cache holds 512 (a 4 MB filing, 2026-10-14)."""
    if term[:1].isupper():
        return re.compile(rf"(?<![\w“\"]){re.escape(term)}s?\b")
    return re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)


def _uses(text: str, term: str) -> int | None:
    """Where the text uses the term, or None."""
    match = _use_of(term).search(text)
    return match.start() if match else None


def _amending(sections: Sequence[Readable]) -> list[list[list[str]]]:
    """For each section, the references of each of its sentences that amends or overrides, in order: read once for every
    seed (each seed re-read the whole agreement, 2.8 s on a 4 MB filing)."""
    found: list[list[list[str]]] = []
    for section in sections:
        sentences = _SENTENCE.split(" ".join(section.text.split()))
        found.append([references(sentence) for sentence in sentences if _AMENDS.search(sentence)])
    return found


def _opened(sections: Sequence[Readable]) -> dict[str, list[int]]:
    """The sections whose text opens each clause number, the first two of each: read once per call (each reference read
    every section again, 1.6 s of 2.2 on a 2.7 MB filing)."""
    opened: dict[str, list[int]] = {}
    for index, section in enumerate(sections):
        for number in stated_clause_numbers([section.text]):
            places = opened.setdefault(number, [])
            if len(places) < 2:
                places.append(index)
    return opened


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


def links_of(sections: Sequence[Readable], seed: int, amending: list[list[list[str]]] | None = None, opened: dict[str, list[int]] | None = None) -> list[Link]:
    """Every link from one section, in the order found: amendments of it, definitions it uses, what it cites.
    ``amending`` and ``opened`` are `_amending(sections)` and `_opened(sections)`, when the caller has them already."""
    found: list[Link] = []
    own = sections[seed]
    mine = _clause_numbers(own)
    for index, sentences in enumerate(amending if amending is not None else _amending(sections)):
        if index == seed:
            continue
        for named_in_sentence in sentences:
            if named := next((r for r in named_in_sentence if r in mine), None):
                found.append(Link(index, "amendment", seed, f"§{named}"))
                break
    defined = _definitions(tuple(s.text for s in sections))
    used = sorted((at, term) for term, where in defined.items() if where != seed and (at := _uses(own.text, term)) is not None)
    found += [Link(defined[term], "definition", seed, term) for _, term in used]
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
    """The sections to add after the ranked ones: followed from the top ``SEEDS``, amendments first, at most
    ``MAX_LINKS``, and only while the handed text stays within ``len(ranked)`` full windows."""
    candidates: list[tuple[tuple[int, int, int], Link]] = []
    amending = _amending(sections)
    opened: dict[str, list[int]] | None = None
    for rank, seed in enumerate(ranked[:SEEDS]):
        if opened is None and references(sections[seed].text):
            opened = _opened(sections)
        candidates += [((_PRIORITY[link.kind], rank, order), link) for order, link in enumerate(links_of(sections, seed, amending, opened))]
    chosen: list[Link] = []
    used = sum(min(len(sections[i].text), window) for i in ranked)
    budget = len(ranked) * window
    for _, link in sorted(candidates, key=lambda pair: pair[0]):
        if len(chosen) == MAX_LINKS:
            break
        if link.index in ranked or any(c.index == link.index for c in chosen):
            continue
        size = min(len(sections[link.index].text), window)
        if used + size <= budget:
            chosen.append(link)
            used += size
    return chosen


def because(link: Link, sections: Sequence[Readable]) -> str:
    """Why a linked section was handed, in words: 'the definition of "Business Day", used in §2.7'."""
    seed = sections[link.seed]
    where = f"§{seed.number}" if seed.number else seed.heading
    if link.kind == "definition":
        return f'the definition of "{link.by}", used in {where}'
    if link.kind == "amendment":
        return f"it amends or overrides {link.by}, handed as {where}"
    return f"{where} refers to {link.by}"
