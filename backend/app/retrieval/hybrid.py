"""Hybrid retrieval: BM25 and a local embedding model fused by reciprocal rank.

Measured before it was written (docs/RETRIEVAL.md): on 164 CUAD cases with experts' spans, BM25 alone
handed the model the right section in 85% of the top six; fused with nomic-embed-text it is 95%, and
the goldens' 92% became 97%. It runs behind ``WORKBENCH_RETRIEVAL=hybrid`` until the goldens are
re-run under it. Embeddings come from Ollama; a missing model fails the run with a reason.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from ..config import settings
from ..providers.base import ProviderError
from .lexical import Candidate, LexicalIndex

RRF_K = 60
EMBED_BATCH = 64
QUERY_PREFIX = "search_query: "  # nomic-embed-text's asymmetric convention; sections carry no prefix
MAX_EMBED_CHARS = 2000

Embedder = Callable[[list[str]], list[list[float]]]


def ollama_embed(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        try:
            response = httpx.post(
                f"{settings.ollama_url}/api/embed", json={"model": settings.embed_model, "input": texts[start : start + EMBED_BATCH]}, timeout=600.0
            )
            response.raise_for_status()
            vectors += response.json()["embeddings"]
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise ProviderError(f"embedding with {settings.embed_model} failed: {error}") from error
    return vectors


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def fuse(rankings: list[list[int]], k: int) -> list[int]:
    """Reciprocal rank fusion: each ranking votes 1 / (RRF_K + rank) for every index it lists."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, index in enumerate(ranking, start=1):
            scores[index] = scores.get(index, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores, key=lambda i: (-scores[i], i))[:k]


@dataclass
class HybridIndex:
    """Sections ranked by BM25 and by embedding similarity, fused. ``embed`` is injectable for tests."""

    sections: list[tuple[str, str]]
    embed: Embedder = ollama_embed

    def __post_init__(self) -> None:
        self._lexical = LexicalIndex(self.sections)
        self._vectors = self.embed([f"{heading} {text[:MAX_EMBED_CHARS]}" for heading, text in self.sections]) if self.sections else []

    def search(self, query: str, k: int) -> list[Candidate]:
        if not self.sections:
            return []
        lexical = [c.index for c in self._lexical.search(query, len(self.sections))]
        query_vector = self.embed([QUERY_PREFIX + query])[0]
        similarities = [cosine(query_vector, vector) for vector in self._vectors]
        dense = sorted(range(len(self.sections)), key=lambda i: (-similarities[i], i))
        rankings = [ranking for ranking in (lexical, dense) if ranking]
        return [Candidate(i, similarities[i]) for i in fuse(rankings, k)]
