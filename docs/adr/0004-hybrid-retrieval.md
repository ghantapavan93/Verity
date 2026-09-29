# ADR 0004: Retrieval is lexical first, vectors second, fused

## Context

Contracts are full of exact phrases ("fifteen (15) days' written notice", "terminate for
convenience") that lexical search finds precisely. Questions are also phrased in the
reviewer's words, which lexical search misses. Both signals are cheap locally.

## Decision

Candidate sections are the union of BM25 results (`rank_bm25` over section text) and
nearest neighbours from pgvector (embeddings from `nomic-embed-text` through Ollama), fused
by reciprocal rank and de-duplicated, then passed to the model with their section ids. The
number of candidates is a named constant with a comment. The union, the ranks and the chosen
candidates are stored on the run.

## Consequences

- The first slice may run on BM25 alone if measurement shows vectors add nothing on the
  fixtures; the fusion code accepts an empty vector list.
- No reranker model in v0. If retrieval misses are the dominant failure in Runs, that is the
  next measured change.
- Postgres with pgvector is the one datastore: documents, sections, embeddings and runs.
