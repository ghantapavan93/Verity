"""Section-aware lexical retrieval: BM25 over section text with the heading counted three
times, so a question that names a clause finds it, and exact phrases in contracts score.

Vectors are not here on purpose. They are added when a measurement on real runs shows
lexical retrieval missing the section the answer lives in (ADR 0004).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from ..verify.spans import _QUOTE_MAP

TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
# Text is read as the verifier's normalized and casefold tiers read it (retrieval-v3, stress test 2026-10-30, retrieval
# corner): its quotation marks folded by the verifier's own table, never a second one, then casefolded. Until then a
# straight possessive was its own word ("party's" never met "Party") and a curly one split into the word and a lone "s"
# that met "U.S." and "Product(s)", so the same question typed on a desktop or a phone handed different sections in 76
# to 98% of CUAD runs. The four apostrophes the verifier's table does not hold yet are folded here too; the verifier is
# the place for them. A change to that table bumps the verifier's version, which is part of every run's identity.
_FOLD = _QUOTE_MAP | str.maketrans({"ʼ": "'", "＇": "'", "`": "'", "´": "'"})
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "what",
        "which",
        "who",
        "whom",
        "does",
        "do",
        "did",
        "how",
        "when",
        "where",
        "under",
        "any",
    ]
)
HEADING_WEIGHT = 3
# What "the sections handed to the model" means: this tokenizer and stopword list, BM25 with the heading counted three
# times, only sections scored above zero, and the opening sections when none is (runs.service). Part of a run's
# identity (runs.versions); changed by hand when any of that changes.
# retrieval-v2 (2026-10-14): after the ranking, the sections the top three ranked ones depend on where the contract says
# which (a definition they use, an amendment of them, a clause or schedule they cite), at most two, within the same
# worst-case text (runs.links). The ranking itself is unchanged.
# retrieval-v3 (2026-10-30, the stress test's retrieval corner): text is read as the verifier reads it, quotation marks
# folded and casefolded, a possessive its word.
RETRIEVAL_VERSION = "retrieval-v3"


@dataclass(frozen=True)
class Candidate:
    index: int
    score: float


def words(text: str) -> list[str]:
    """Every word of the text as retrieval reads it, stopwords kept: folded, casefolded, a possessive "'s" dropped
    ("party's" is "party"; a trailing apostrophe is never part of a word, so "Parties'" is "parties")."""
    return [word[:-2] if word.endswith("'s") else word for word in TOKEN.findall(text.translate(_FOLD).casefold())]


def tokenize(text: str) -> list[str]:
    return [t for t in words(text) if t not in STOPWORDS]


class LexicalIndex:
    def __init__(self, sections: list[tuple[str, str]]) -> None:
        """``sections`` is a list of (heading, text) in document order."""
        self._corpus = [tokenize(heading) * HEADING_WEIGHT + tokenize(text) for heading, text in sections]
        self._bm25 = BM25Okapi(self._corpus) if self._corpus else None

    def search(self, query: str, k: int) -> list[Candidate]:
        if self._bm25 is None:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        return [Candidate(i, float(scores[i])) for i in ranked[:k] if scores[i] > 0]
