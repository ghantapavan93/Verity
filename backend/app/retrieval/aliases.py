"""Deterministic legal aliases for the retrieval query.

The two categories where BM25 misses most (CUAD-30 Recall@6: uncapped liability 0.44, non-compete 0.69,
docs/RETRIEVAL.md) are the ones whose question shares no vocabulary with the clause: a clause that lifts the cap
says "shall not apply" or "nothing in this section limits", never "uncapped"; a non-compete says "shall not,
directly or indirectly, engage in". This table is the model-free form of query expansion: when a question names
a concept by any of its phrases, the other phrases of that concept join the query. It is data, hand-written,
versioned by its hash, and recorded on every run that used it (`retrieval_aliases` in the run's options), so a
run's candidates stay reproducible after the table changes. Off by default until the measurement in
docs/RETRIEVAL.md adopts it (`WORKBENCH_RETRIEVAL_ALIASES`).
"""

from __future__ import annotations

import json

from ..hashing import sha256_text
from .lexical import tokenize

# Each group: phrases that name one concept in contracts. Order and spelling matter for the hash only.
ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    (
        "non-compete",
        "non-competition",
        "noncompete",
        "noncompetition",
        "covenant not to compete",
        "restrictive covenant",
        "restraint of trade",
        "compete",
        "competing",
        "competitive",
        "competitor",
        "non-solicitation",
        "nonsolicitation",
        "solicit",
    ),
    (
        "uncapped liability",
        "unlimited liability",
        "excluded from the cap",
        "no cap",
        "not limited",
        "shall not apply",
        "notwithstanding the foregoing",
        "exclusions from limitation",
        "gross negligence",
        "willful misconduct",
        "wilful misconduct",
        "fraud",
        "indemnification obligations",
        "breach of confidentiality",
    ),
    (
        "cap on liability",
        "limitation of liability",
        "limit of liability",
        "aggregate liability",
        "shall not exceed",
        "maximum liability",
        "liable for",
        "consequential damages",
        "indirect damages",
        "incidental damages",
        "total liability",
    ),
    (
        "governing law",
        "governed by",
        "laws of the state",
        "construed in accordance",
        "jurisdiction",
        "venue",
        "courts of",
        "arbitration",
        "disputes",
        "forum",
        "choice of law",
    ),
    (
        "termination for convenience",
        "terminate for convenience",
        "without cause",
        "for any reason",
        "at any time",
        "for no reason",
        "prior written notice",
        "days notice",
        "days' notice",
    ),
    (
        "change of control",
        "change in control",
        "merger",
        "acquisition",
        "acquired by",
        "assign this agreement",
        "assignment",
        "successor",
        "controlling interest",
    ),
    (
        "most favored nation",
        "most favoured nation",
        "mfn",
        "no less favorable",
        "no less favourable",
        "most favorable terms",
        "best pricing",
        "lowest price",
    ),
)

ALIASES_SHA256 = sha256_text(json.dumps(ALIAS_GROUPS, sort_keys=True))


def _phrase_in(tokens: list[str], phrase_tokens: list[str]) -> bool:
    n = len(phrase_tokens)
    if n == 0 or n > len(tokens):
        return False
    return any(tokens[i : i + n] == phrase_tokens for i in range(len(tokens) - n + 1))


def expand_query(query: str) -> str:
    """The query with the other phrases of every concept it names appended, once each, in table order.
    A query that names no concept is returned unchanged, so a run without a match keeps its candidates."""
    tokens = tokenize(query)
    extra: list[str] = []
    seen = set(tokens)
    for group in ALIAS_GROUPS:
        phrases = [tokenize(p) for p in group]
        if not any(_phrase_in(tokens, p) for p in phrases if p):
            continue
        for phrase_tokens in phrases:
            for token in phrase_tokens:
                if token not in seen:
                    seen.add(token)
                    extra.append(token)
    return query if not extra else f"{query} {' '.join(extra)}"
