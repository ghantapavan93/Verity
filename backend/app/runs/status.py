"""Code decides the status. Where the observed and required positions are day counts, they
are compared; otherwise the model's hint is used and the source is recorded as such."""

from __future__ import annotations

import re
from collections.abc import Iterable
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
    source: str  # computed_days | model_hint | no_evidence | reference_check


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


# "§14.2", "Section 14.2", "clause 14.2", "Article 14": the ways a conclusion points a reader at a section.
REFERENCE = re.compile(r"(?:§|\bSection\s+|\bClause\s+|\bArticle\s+)(\d+(?:\.\d+)*)", re.IGNORECASE)


def unknown_references(text: str | None, section_numbers: Iterable[str], handed_ids: Iterable[str]) -> list[str]:
    """Section numbers the text points at that exist neither in the document nor among the ids the model was
    handed. A model that writes "§73" for "sec_73" is confused about labels, not inventing a clause, so those
    are not reported. A number is known when a section number equals it or ends with it, so a reader whose
    numbering carries a prefix ("0.15.11" for clause 15.11) raises no false alarm. Measured over 398 recorded
    findings on 2026-09-29: four unknown references, all wrong (docs/GOLDENS.md)."""
    numbers = [n for n in section_numbers if n]
    ids = {handle.removeprefix("sec_") for handle in handed_ids}
    unknown: list[str] = []
    for reference in REFERENCE.findall(text or ""):
        reference = reference.rstrip(".")
        if reference in ids or any(number == reference or number.endswith("." + reference) for number in numbers):
            continue
        if reference not in unknown:
            unknown.append(reference)
    return unknown


def check_references(decision: Decision, conclusion: str | None, section_numbers: Iterable[str], handed_ids: Iterable[str]) -> Decision:
    """A pass that sends the reader to a section the document does not have is not a pass: the quote may be
    real, the reference is not, and a person must look. Other statuses already ask for that."""
    if decision.status != "pass" or not unknown_references(conclusion, section_numbers, handed_ids):
        return decision
    return Decision("needs_review", "reference_check")
