"""Section-aware lexical retrieval: BM25 over section text with the heading counted three
times, so a question that names a clause finds it, and exact phrases in contracts score.

Vectors are not here on purpose. They are added when a measurement on real runs shows
lexical retrieval missing the section the answer lives in (ADR 0004).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
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


@dataclass(frozen=True)
class Candidate:
    index: int
    score: float


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS]


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
