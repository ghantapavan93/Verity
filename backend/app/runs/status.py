"""Code decides the status. Where the observed and required positions are day counts, they
are compared; otherwise the model's hint is used and the source is recorded as such."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..analysis.schema import StatusHint
from ..models import FindingStatusName

DAYS = re.compile(r"(\d+)\s*(?:\(\s*\d+\s*\))?\s*(?:calendar\s+|business\s+)?days?", re.IGNORECASE)
WORD_NUMBERS = {
    "five": 5,
    "seven": 7,
    "ten": 10,
    "fourteen": 14,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty-five": 45,
    "forty five": 45,
    "sixty": 60,
    "ninety": 90,
}
AT_LEAST = re.compile(r"(?:≥|>=|at least|no less than|not less than|minimum of|a minimum|or more|or longer)", re.IGNORECASE)
AT_MOST = re.compile(r"(?:≤|<=|at most|no more than|not more than|maximum of|a maximum|or less|or fewer|within)", re.IGNORECASE)


@dataclass(frozen=True)
class Decision:
    status: FindingStatusName
    source: str  # computed_days | model_hint | no_evidence


def days_in(text: str | None) -> int | None:
    if not text:
        return None
    match = DAYS.search(text)
    if match:
        return int(match.group(1))
    lowered = text.lower()
    for word, value in WORD_NUMBERS.items():
        if re.search(rf"\b{re.escape(word)}\b\s*(?:\(\d+\))?\s*days?", lowered):
            return value
    return None


def decide(status_hint: StatusHint, observed: str | None, required: str | None, guidance_present: bool, all_spans_verified: bool) -> Decision:
    if not all_spans_verified:
        return Decision("unresolved", "no_evidence")
    if guidance_present and observed and required:
        observed_days, required_days = days_in(observed), days_in(required)
        if observed_days is not None and required_days is not None:
            if AT_MOST.search(required):
                return Decision("pass" if observed_days <= required_days else "needs_review", "computed_days")
            # "at least" is the default reading for a notice-period requirement.
            return Decision("pass" if observed_days >= required_days else "needs_review", "computed_days")
    return Decision(status_hint, "model_hint")
