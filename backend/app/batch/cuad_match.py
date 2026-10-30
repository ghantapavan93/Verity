"""How a located citation is matched against the experts' spans of CUAD, how a retrieved section is judged to carry a
span, which of a run's findings is the answer that is scored, and what each (contract, question) pair counts as.
Pre-registered in docs/CUAD.md. The batch reports the answer `answer_index` picks (batch.service.value_for),
scripts/score_cuad.py scores it, and the SkillOpt environment (research/skillopt/workbench_env/rollout.py) scores its
own proposals by the same two functions, so the three agree on the unit and on the rule.

The scorer once took the located texts of every asserting finding of a run and the rollout only the first one's: the
docstring here said they scored the same way, and on CUAD-30 two values the batch reported as answers that missed the
experts' span were counted correct through a later finding (stress test EVL-4, 2026-10-30).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal, get_args

JACCARD = 0.5  # a citation hits an expert span when they share at least half of their word tokens
RETRIEVED_COVERAGE = 0.8  # a retrieved section carries a span when 80% of the span's tokens are in it

# The statuses that assert the contract addresses the point; a finding with one of them can be the run's answer.
ANSWERING = frozenset({"pass", "needs_review"})

Outcome = Literal["correct", "cited elsewhere", "missed", "correct absence", "asserted where experts found none", "failed", "in progress", "not run"]
OUTCOMES: tuple[Outcome, ...] = get_args(Outcome)
# A pair the recording did not finish: a failed run, one still in progress, or no run at all. Each is a miss for recall
# and none can carry the pre-registered verdict (stress test EVL-5, 2026-10-30).
UNFINISHED: frozenset[Outcome] = frozenset({"failed", "in progress", "not run"})


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", normalise(text)))


def hits(located: str, experts: Sequence[str]) -> bool:
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


def answer_index(findings: Sequence[tuple[str, Sequence[str]]]) -> int | None:
    """Which finding is the run's answer: the first, in the run's order, that asserts the point and has a verified quote
    with located text. ``findings`` holds (status, located texts) for each finding; None when no finding answers."""
    return next((index for index, (status, texts) in enumerate(findings) if status in ANSWERING and texts), None)


def answered_texts(findings: Sequence[tuple[str, Sequence[str]]]) -> list[str] | None:
    """The located texts of the run's answer, the only texts that are scored; None when no finding answers."""
    index = answer_index(findings)
    return None if index is None else list(findings[index][1])


def outcome(value: str, texts: Sequence[str], experts: Sequence[str]) -> Outcome:
    """What one (contract, question) pair counts as under docs/CUAD.md. ``value`` is what the batch reports for the pair
    (answered, not_found, withheld, failed, in_progress) or not_run when it holds no run for it; ``texts`` are the
    located texts of the answer; ``experts`` the experts' spans, empty where they found no such clause."""
    if value == "answered":
        if not experts:
            return "asserted where experts found none"
        return "correct" if any(hits(text, experts) for text in texts) else "cited elsewhere"
    if value in ("not_found", "withheld"):
        return "missed" if experts else "correct absence"
    if value == "failed":
        return "failed"
    if value == "in_progress":
        return "in progress"
    if value == "not_run":
        return "not run"
    raise ValueError(f"no outcome for a value reported as {value!r}")
