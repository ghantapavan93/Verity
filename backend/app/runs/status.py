"""Code decides the status. The notice period a verified quote provides and the position the guidance requires are
parsed by code (policy.durations), never copied from the model's `observed` and `required`: those two may only point
at which of the quote's durations the model means, and a count they state that the evidence does not carry lowers
the finding to needs review (`position_check`). Where a rule and a fact exist and are comparable, the evaluation
decides (`computed_days`) and its sentence is kept on the finding; an ambiguous fact ("twenty-one (30) days") is
`ambiguous_fact`; anything else is the model's hint, recorded as such (2026-09-29, wired after the CUAD-30 chain).
Measured before the wiring: nine recorded statuses had been computed from day counts, none disagreeing with its quote.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..analysis.schema import StatusHint
from ..models import FindingStatusName
from ..policy.durations import Duration, ObservedFact, evaluate, observed_fact, parse_durations, parse_rule


@dataclass(frozen=True)
class Decision:
    status: FindingStatusName
    source: str  # computed_days | model_hint | no_evidence | reference_check | position_check | ambiguous_fact
    reason: str = ""


def _durations(text: str | None) -> set[Duration]:
    return {m.duration for m in parse_durations(text) if m.duration is not None}


def _periods(durations: set[Duration]) -> str:
    return ", ".join(f"{d.value} {d.unit.value.replace('_', ' ')}s" for d in sorted(durations, key=lambda d: (d.unit.value, d.value)))


def decide(
    status_hint: StatusHint,
    observed: str | None,
    required: str | None,
    guidance_present: bool,
    all_spans_verified: bool,
    quotes: Sequence[str] = (),
    guidance: str | None = None,
    topic: str | None = None,
) -> Decision:
    if not all_spans_verified:
        return Decision("unresolved", "no_evidence")
    # The model's stated positions are checked against the record before anything is computed.
    stated, in_quotes = _durations(observed), set().union(*(_durations(q) for q in quotes)) if quotes else set()
    if stated and in_quotes and not stated & in_quotes:
        return Decision("needs_review", "position_check", "the position the model stated is not in the verified quote")
    stated_required, in_guidance = _durations(required), _durations(guidance)
    if stated_required and in_guidance and not stated_required & in_guidance:
        return Decision("needs_review", "position_check", "the requirement the model stated is not in the guidance")
    rule = parse_rule(guidance, topic) if guidance_present else None
    fact = next((f for f in (observed_fact(q, stated=observed) for q in quotes) if f is not None), None)
    if rule is not None and fact is not None:
        # A quote that states more than one period ("90 days' notice, unless …, in which case 10 days") may be decided
        # by code only when every period it states leads to the same result. Until 2026-10-02 the first period, or the
        # one the model pointed at, decided alone, and "90 days unless … 10 days" was a computed pass against a 90-day
        # minimum. Which period governs is a reading of the clause; code does not make it. (No recorded finding rested
        # on such a quote: 12 computed passes, none with a second period.)
        outcomes = {evaluate(ObservedFact("notice_period", d, "", 0, 0), rule).outcome for d in in_quotes}
        if len(outcomes) > 1:
            return Decision(
                "needs_review", "ambiguous_fact", f"the quote states more than one period ({_periods(in_quotes)}) and they do not all meet the guidance alike"
            )
        evaluation = evaluate(fact, rule)
        if evaluation.outcome in ("pass", "needs_review"):
            return Decision("pass" if evaluation.outcome == "pass" else "needs_review", "computed_days", evaluation.reason)
        if evaluation.outcome == "ambiguous":
            return Decision("needs_review", "ambiguous_fact", evaluation.reason)
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
