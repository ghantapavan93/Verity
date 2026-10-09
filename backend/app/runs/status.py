"""Code decides the status. The notice period a verified quote provides and the position the guidance requires are
parsed by code (policy.durations), never copied from the model's `observed` and `required`: those two may only point
at which of the quote's durations the model means, and a count they state that the evidence does not carry lowers
the finding to needs review (`position_check`). Where a rule and a fact exist and are comparable, the evaluation
decides (`computed_days`) and its sentence is kept on the finding; an ambiguous fact ("twenty-one (30) days") is
`ambiguous_fact`; anything else is the model's hint, recorded as such (2026-09-29, wired after the CUAD-30 chain).
Measured before the wiring: nine recorded statuses had been computed from day counts, none disagreeing with its quote.
Code compares periods; it does not know what a period is about. So it stays out where the comparison would be a
reading: a finding the model reported as not found (its quote is the closest provision, not a position), and a pass
against guidance that states several periods the quote does not all meet. Both are the model's hint, with the reason.

The two directions are not held to the same standard, and they are not owned alike (policy-v2, 2026-10-02).

A shortfall is code's decision (`computed_days`): where the model offered the quote as the contract's position, code
reports that its period falls short of the guidance whether the model hinted pass or needs review.

A pass is never code's decision alone. The model proposes it; code confirms it (`confirmed_days`) when the period
meets the guidance and nothing in the source text stands against it: `policy.proof.pass_blockers` reads the quotes,
their sentences and the guidance for that, and a passage that points at a section the model was not handed blocks it
as well. Hold the quote and the guidance still and change only the model's hint from pass to needs review, and there
is no pass: so the record does not say code decided one. An unconfirmed pass is the model's hint, shown as its view,
with the reasons. None of the model's words about the quote (topic, observed, required) can earn a confirmation;
they can only lose one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..analysis.schema import StatusHint
from ..models import STATUSES_BY_SOURCE, FindingStatusName, StatusSourceName
from ..policy.durations import Duration, ObservedFact, evaluate, observed_fact, parse_durations, parse_rule, stated_periods, stated_rules
from ..policy.proof import pass_blockers, same_point

# The version of the rules in this module and in `policy`: what a status means. Part of a run's identity
# (runs.versions), so a question answered under one version is asked again, not handed back, under the next.
# policy-v1 is every run recorded before the version was (to 2026-10-02): the status was the first comparable period's.
# policy-v2: a point reported as not found is never evaluated; a numberless carve-out is a period; a pass is the
# model's, confirmed by code only when every period of the guidance is met and the source text, the sentences around
# the quote and the run's related findings give no reason against it. Changing what any of this means is a new
# version: tests/test_semantic_versions.py fails until the version and its fingerprint are recorded together.
# policy-v4 (2026-10-09): a guidance bound is read as written or not at all. "Must not exceed 60 days" was a floor;
# every ceiling phrasing is now a ceiling, and a period beside a negation or a bare comparative code does not read
# ("more than 60 days are not acceptable") states no rule. Replayed over the 63 recorded findings with guidance: none
# changed. A reference is unknown only when the document's text never opens a clause with it either (§12.3 inside §12
# was "a section this document does not have"); replayed over 1,229 recorded findings, 21 references became known, each
# printed as a clause opening in its document.
POLICY_VERSION = "policy-v4"


@dataclass(frozen=True)
class Decision:
    status: FindingStatusName
    source: StatusSourceName
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES_BY_SOURCE.get(self.source, ()):
            raise ValueError(f"{self.source!r} cannot decide {self.status!r}")


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
    dependencies: Sequence[str] = (),
    passages: Sequence[str] = (),
) -> Decision:
    """``quotes`` are the verified quotes and ``guidance`` the guidance text: the source facts. ``status_hint``,
    ``observed``, ``required`` and ``topic`` are the model's. ``passages`` are the whole sentences of the stored
    section text that the quotes sit in (`enclosing_sentences`), and ``dependencies`` the sections those sentences
    point at that the model was not handed (`unseen_references`); the caller computes both from the record."""
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
        if status_hint == "missing":
            # The model reported the point as not found, and the prompt (rule 8) has it cite the closest provision it
            # read. That quote is not the contract's position, so there is nothing for code to compare: until
            # 2026-10-02 a cure period quoted under "no most favoured nation clause was found" was a computed pass
            # against a termination rule (run 5ff255e1c3154792, 1 of the 12 computed passes on record).
            return Decision(
                "missing",
                "model_hint",
                "the model reported the point as not found, so the quoted passage is the closest provision read, not the contract's position; "
                "code compared no periods",
            )
        # A quote that states more than one period ("90 days' notice, unless …, in which case 10 days") may be decided
        # by code only when every period it states leads to the same result. Until 2026-10-02 the first period, or the
        # one the model pointed at, decided alone, and "90 days unless … 10 days" was a computed pass against a 90-day
        # minimum. Which period governs is a reading of the clause; code does not make it. (No recorded finding rested
        # on such a quote: 12 computed passes, none with a second period.) A carve-out with no number is a period too:
        # "90 days' notice, except that Provider may terminate immediately" was a computed pass, by the live model.
        periods: set[Duration] = set().union(*(stated_periods(q) for q in quotes))
        outcomes = {evaluate(ObservedFact("notice_period", d, "", 0, 0), rule).outcome for d in periods}
        if len(outcomes) > 1:
            return Decision(
                "needs_review", "ambiguous_fact", f"the quote states more than one period ({_periods(periods)}) and they do not all meet the guidance alike"
            )
        evaluation = evaluate(fact, rule)
        if evaluation.outcome == "needs_review":
            # A shortfall is code's to report: 60 days where the guidance requires 90 sends the finding to a person. What
            # code established is the conflict between the two periods. That the quoted period is the guidance's subject
            # (a termination notice, not a payment term) is the model's reading, and the reason says so (policy v3): the
            # live policy owned "Invoices must be paid within 60 days" as a termination shortfall, numerically right and
            # about the wrong clause.
            return Decision("needs_review", "computed_days", f"{evaluation.reason}; {SUBJECT_IS_THE_MODELS}")
        if evaluation.outcome == "pass":
            assert guidance is not None
            blockers: list[str] = []
            if status_hint != "pass":
                # The model read the clause and did not call it a pass. Code compared two numbers; it does not overrule a reading.
                blockers.append("the model asked for review")
            if any(evaluate(fact, other).outcome != "pass" for other in stated_rules(guidance)):
                # "At least 30 days' notice; enterprise agreements require 90": which period binds this agreement is a
                # reading of the guidance, and code does not make it.
                blockers.append(f"the guidance states more than one period ({_periods(in_guidance)}) and the quote does not meet them all")
            blockers += pass_blockers(quotes, guidance, rule, dependencies, passages)
            if blockers:
                return Decision(status_hint, "model_hint", f"{evaluation.reason}, but code does not confirm that as a pass: {'; '.join(blockers)}")
            # Policy v3: code no longer owns a pass. The checks above are lexical (shared word stems, operators, negation,
            # carve-outs), and a lexical check cannot establish that a quote and a guidance sentence concern the same
            # point: "Following a material breach, Company shall provide 30 days' written notice of an audit" passed every
            # one of them against "a material breach must allow at least 30 days to cure", and 30 days of audit notice is
            # not a cure period. The pass stays the model's; code says what it found and what it did not establish.
            return Decision("pass", "model_hint", f"{evaluation.reason}; code found the day counts consistent, and {SUBJECT_IS_THE_MODELS}")
        if evaluation.outcome == "ambiguous":
            return Decision("needs_review", "ambiguous_fact", evaluation.reason)
    return Decision(status_hint, "model_hint")


# The one thing a day comparison cannot establish, said the same way wherever code reports one.
SUBJECT_IS_THE_MODELS = "that the quoted period and the guidance concern the same point is the model's reading, not code's"


@dataclass(frozen=True)
class Grounds:
    """What one finding's decision rests on, as far as another finding's decision may depend on it."""

    quotes: tuple[str, ...] = ()
    passages: tuple[str, ...] = ()  # the whole sentences the verified quotes sit in
    sections: tuple[tuple[str, str], ...] = ()  # (id, number) of the sections the verified quotes were found in


def _bears_on(short: Grounds, confirmed: Grounds, guidance: str | None) -> str | None:
    """How a finding code found short relates to a finding code confirmed, or None when no relation shows. Being
    findings of the same run is not one: a question may ask two unrelated things."""
    if {section_id for section_id, _ in short.sections} & {section_id for section_id, _ in confirmed.sections}:
        return "another finding that cites the same section falls short of the guidance"
    numbers = [number for _, number in confirmed.sections if number]
    for reference in (r.rstrip(".") for passage in short.passages for r in REFERENCE.findall(passage)):
        if any(number == reference or number.endswith("." + reference) for number in numbers):
            return f"another finding, whose clause refers to §{reference}, falls short of the guidance"
    if guidance and same_point(short.quotes, guidance):
        return "another finding about the same point falls short of the guidance"
    return None


def settle_together(decisions: Sequence[Decision], grounds: Sequence[Grounds], guidance: str | None) -> list[Decision]:
    """A pass whose day counts code found consistent does not stand unremarked beside a shortfall code found in a
    finding that bears on it: the live model, handed "60 days" in one section and "notwithstanding Section 4, 10 days"
    in another, returned the first as a pass and the second as needing review (2026-10-02), and the two sat side by
    side. Which clause governs is a reading; the pass stays the model's, and its reason names the shortfall.

    What bears on it is structural, never "the same run": the two cite the same section, the short one's clause
    refers to the section the pass cites, or the short one's quote is about the same point of the guidance
    (`policy.proof.same_point`). A shortfall in an unrelated finding, a payment term measured against a termination
    rule, takes nothing from a pass on termination. Under policy v2 this lowered a code-confirmed pass to the
    model's view; under v3 every pass is already the model's, so only the reason changes."""
    settled = list(decisions)
    shorts = [g for d, g in zip(decisions, grounds, strict=True) if d.status == "needs_review" and d.source in ("computed_days", "ambiguous_fact")]
    for index, (decision, own) in enumerate(zip(decisions, grounds, strict=True)):
        if decision.status != "pass" or not (decision.reason or "").startswith("the contract provides"):
            continue
        relation = next((r for r in (_bears_on(short, own, guidance) for short in shorts) if r is not None), None)
        if relation is not None:
            settled[index] = Decision("pass", "model_hint", f"{decision.reason}, but code does not confirm that as a pass: {relation}")
    return settled


# "§14.2", "Section 14.2", "clause 14.2", "Article 14": the ways a conclusion points a reader at a section.
REFERENCE = re.compile(r"(?:§|\bSection\s+|\bClause\s+|\bArticle\s+)(\d+(?:\.\d+)*)", re.IGNORECASE)


def unknown_references(text: str | None, section_numbers: Iterable[str], handed_ids: Iterable[str], stated: Iterable[str] = ()) -> list[str]:
    """Section numbers the text points at that exist neither in the document nor among the ids the model was
    handed. A model that writes "§73" for "sec_73" is confused about labels, not inventing a clause, so those
    are not reported. A number is known when a section number equals it, ends with it (a reader whose numbering
    carries a prefix: "0.15.11" for clause 15.11) or sits under it ("6.1" for Section 6); or when the document's text
    opens a clause with it, or with one under it (``stated``, `ingest.sections.stated_clause_numbers`: "12.3" inside
    §12, "6." in a reading without numbering). Measured over 398 recorded findings on 2026-09-29: four unknown
    references, all wrong (docs/GOLDENS.md); the audit of 2026-10-09 found four false ones, all printed in the text."""
    numbers = [n for n in section_numbers if n]
    printed = [n for n in stated if n]
    ids = {handle.removeprefix("sec_") for handle in handed_ids}
    unknown: list[str] = []
    for reference in REFERENCE.findall(text or ""):
        reference = reference.rstrip(".")
        if reference in ids:
            continue
        if any(n == reference or n.endswith("." + reference) or n.startswith(reference + ".") for n in numbers):
            continue
        if any(n == reference or n.startswith(reference + ".") for n in printed):
            continue
        if reference not in unknown:
            unknown.append(reference)
    return unknown


# "Schedule B", "Exhibit A", "Appendix 2": the parts of an agreement a clause points at by name.
ATTACHMENT = re.compile(r"\b(Schedule|Exhibit|Appendix|Annexure|Annex|Attachment)\s+([A-Z]\b|\d+)", re.IGNORECASE)
_PASSAGE_END = re.compile(r"(?<=[.;!?])\s+|\n+")


def enclosing_sentences(text: str, start: int, end: int) -> str:
    """The whole sentences of ``text`` that the span touches. A quote is the shortest passage that carries the point
    (prompt rule 1), so the words that qualify it ("Subject to Section 14.3, …") are often just outside it."""
    first, last = 0, len(text)
    for boundary in _PASSAGE_END.finditer(text):
        if boundary.end() <= start:
            first = boundary.end()
        elif boundary.start() >= end:
            last = boundary.start()
            break
    return text[first:last]


def unseen_references(passage: str, sections: Iterable[tuple[str, str]], handed: Iterable[tuple[str, str]]) -> list[str]:
    """What a verified passage points at that exists in the document and was not among the sections handed to the
    model: "§14.3", "Schedule B". ``sections`` and ``handed`` are (number, heading) pairs. A reference that names
    nothing this reading of the document has (another agreement's section, a schedule that is a separate file) is
    not reported: code cannot say it went unseen. A section split into parts counts as handed only when every part
    was. No reference is followed; the model is not shown more, the pass is only not code's to give."""
    every, seen = list(sections), list(handed)
    unseen: list[str] = []
    for reference in REFERENCE.findall(passage):
        reference = reference.rstrip(".")
        targets = [pair for pair in every if pair[0] and (pair[0] == reference or pair[0].endswith("." + reference))]
        if targets and any(pair not in seen for pair in targets) and f"§{reference}" not in unseen:
            unseen.append(f"§{reference}")
    for kind, mark in ATTACHMENT.findall(passage):
        name = re.compile(rf"^\s*{re.escape(kind)}\s+{re.escape(mark)}\b", re.IGNORECASE)
        targets = [pair for pair in every if name.match(pair[1])]
        label = f"{kind.capitalize()} {mark.upper()}"
        if targets and any(pair not in seen for pair in targets) and label not in unseen:
            unseen.append(label)
    return unseen


def check_references(
    decision: Decision, conclusion: str | None, section_numbers: Iterable[str], handed_ids: Iterable[str], stated: Iterable[str] = ()
) -> Decision:
    """A pass that sends the reader to a section the document does not have is not a pass: the quote may be
    real, the reference is not, and a person must look. Other statuses already ask for that."""
    if decision.status != "pass" or not unknown_references(conclusion, section_numbers, handed_ids, stated):
        return decision
    return Decision("needs_review", "reference_check")
