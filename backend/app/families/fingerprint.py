"""A structural fingerprint of a document: what it is made of, not what it says.

Three views of the same document, each a set so that similarity is a Jaccard index:
- headings: the normalised heading sequence (numbers and punctuation stripped, lower-cased);
- terms: the capitalised terms the text defines ("Deliverables" means …);
- shingles: word 5-grams over the section texts, normalised the same way.

Jaccard is computed exactly. At twenty documents that is cheap and exact; MinHash sketches are
the step to take when a corpus is large enough that the shingle sets do not fit, and not before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Document

SHINGLE_WORDS = 5
_WORD = re.compile(r"[a-z0-9]+")
_NUMBERING = re.compile(r"^\s*(?:(?:section|clause|article|schedule|part)\s+)?[\dA-Za-z]{1,3}(?:\.[\d]{1,3})*[.)]?\s+", re.IGNORECASE)
# “Term” means / "Term" has the meaning / Term: means — the vocabulary a contract builds for itself.
_DEFINED = re.compile(r"[“\"]([A-Z][A-Za-z0-9 \-]{1,60}?)[”\"]\s+(?:means|has the meaning|shall mean|shall have the meaning|will have the meaning|includes)")

# Fixed and disclosed: how the three views combine. Shingles carry the most weight because they
# see the wording; headings and terms see the skeleton and the vocabulary.
WEIGHTS = {"shingles": 0.5, "headings": 0.25, "terms": 0.25}


@dataclass(frozen=True)
class Fingerprint:
    document_id: str
    name: str
    title: str
    sections: int
    chars: int
    headings: frozenset[str]
    terms: frozenset[str]
    shingles: frozenset[str]


@dataclass(frozen=True)
class Similarity:
    shingles: float
    headings: float
    terms: float

    @property
    def combined(self) -> float:
        return round(WEIGHTS["shingles"] * self.shingles + WEIGHTS["headings"] * self.headings + WEIGHTS["terms"] * self.terms, 4)


def normalise_heading(heading: str) -> str:
    stripped = _NUMBERING.sub("", heading)
    return " ".join(_WORD.findall(stripped.lower()))


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def shingles(text: str, size: int = SHINGLE_WORDS) -> set[str]:
    tokens = words(text)
    if len(tokens) < size:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def defined_terms(text: str) -> set[str]:
    return {match.group(1).strip().lower() for match in _DEFINED.finditer(text)}


def fingerprint(document: Document, name: str | None = None) -> Fingerprint:
    headings: set[str] = set()
    terms: set[str] = set()
    grams: set[str] = set()
    chars = 0
    for section in document.sections:
        normalised = normalise_heading(section.heading)
        if normalised:
            headings.add(normalised)
        terms |= defined_terms(section.text)
        grams |= shingles(section.text)
        chars += len(section.text)
    title = next((s.heading for s in document.sections if s.heading), document.name)
    return Fingerprint(
        document_id=document.id,
        name=name or document.name,
        title=title,
        sections=len(document.sections),
        chars=chars,
        headings=frozenset(headings),
        terms=frozenset(terms),
        shingles=frozenset(grams),
    )


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    return round(len(a & b) / len(a | b), 4)


def similarity(a: Fingerprint, b: Fingerprint) -> Similarity:
    return Similarity(shingles=jaccard(a.shingles, b.shingles), headings=jaccard(a.headings, b.headings), terms=jaccard(a.terms, b.terms))
