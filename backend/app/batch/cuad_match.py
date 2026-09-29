"""How a located citation is matched against the experts' spans of CUAD, and how a retrieved section
is judged to carry a span. Pre-registered in docs/CUAD.md; used by the scorer and by the SkillOpt
environment so both score the same way.
"""

from __future__ import annotations

import re

JACCARD = 0.5  # a citation hits an expert span when they share at least half of their word tokens
RETRIEVED_COVERAGE = 0.8  # a retrieved section carries a span when 80% of the span's tokens are in it


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", normalise(text)))


def hits(located: str, experts: list[str]) -> bool:
    """One contains the other after normalisation, or the two share at least JACCARD of their tokens."""
    a = normalise(located)
    ta = tokens(a)
    for expert in experts:
        b = normalise(expert)
        if a and b and (a in b or b in a):
            return True
        tb = tokens(b)
        if ta and tb and len(ta & tb) / len(ta | tb) >= JACCARD:
            return True
    return False


def retrieved_carries(section_text: str, expert: str) -> bool:
    if normalise(expert) in normalise(section_text):
        return True
    te = tokens(expert)
    return bool(te) and len(te & tokens(section_text)) / len(te) >= RETRIEVED_COVERAGE
