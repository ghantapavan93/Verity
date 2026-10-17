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

A pass is never code's decision. The model proposes it, and since policy-v3 (2026-10-02) it is recorded as the
model's (`model_hint`) whatever code finds. Code compares the periods and reads the source text for a reason against
the pass: `policy.proof.pass_blockers` reads the quotes, their sentences and the guidance, and a passage that points at
a section the model was not handed counts against it as well; where no period was compared, a pass still names that
section in its reason (policy-v8). A pass that clears every check carries code's sentence
that the day counts are consistent and that the shared subject is the model's reading (`SUBJECT_IS_THE_MODELS`); one
that does not carries the reasons. Those checks are lexical and cannot establish that a quote and the guidance concern
the same point, and holding the quote and the guidance still while the model's hint changes from pass to needs review
leaves no pass: so the record never says code decided or confirmed one. None of the model's words about the quote
(topic, observed, required) can make code vouch for a pass. `confirmed_days`, "confirmed by code", is a record made
under policy-v2 (2026-10-02, before v3 the same day); it is kept for the runs that carry it and nothing writes it now.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from ..analysis.schema import StatusHint
from ..models import STATUSES_BY_SOURCE, FindingStatusName, StatusSourceName
from ..policy.durations import (
    BusinessWeek,
    DayConvention,
    Duration,
    ObservedFact,
    evaluate,
    observed_fact,
    parse_durations,
    parse_rule,
    periods_as_the_contract_reads,
    read_as_the_contract_does,
    stated_rules,
)
from ..policy.proof import CARVE_OUT, concept_stems, pass_blockers, same_point, unseen_reason
from .prose import UNRESOLVED
from .values import frame_times, redaction_given_as_value, uniform_party_choices, unquoted_values

# The version of the rules in this module and in `policy`: what a status means. Part of a run's identity
# (runs.versions), so a question answered under one version is asked again, not handed back, under the next.
# policy-v1 is every run recorded before the version was (to 2026-10-02): the status was the first comparable period's.
# policy-v2: a point reported as not found is never evaluated; a numberless carve-out is a period; a pass is the
# model's, confirmed by code only when every period of the guidance is met and the source text, the sentences around
# the quote and the run's related findings give no reason against it. Changing what any of this means is a new
# version: tests/test_semantic_versions.py fails until the version and its fingerprint are recorded together.
# policy-v3 (2026-10-02, red team): code confirms no pass. The checks a pass must clear are lexical and cannot establish
# that a quote and the guidance concern the same point, so a pass stays the model's (`model_hint`) with code's sentence;
# `confirmed_days` is never written again and is kept for the policy-v2 records that carry it (DECISIONS.md).
# policy-v4 (2026-10-09): a guidance bound is read as written or not at all. "Must not exceed 60 days" was a floor;
# every ceiling phrasing is now a ceiling, and a period beside a negation or a bare comparative code does not read
# ("more than 60 days are not acceptable") states no rule. Replayed over the 63 recorded findings with guidance: none
# changed. A reference is unknown only when the document's text never opens a clause with it either (§12.3 inside §12
# was "a section this document does not have"); replayed over 1,229 recorded findings, 20 became known, each
# printed as a clause opening in its document.
# policy-v5 (2026-10-09, bug hunt): "maximum 60 days", "limited to", "less than or equal to" and "at the most" are
# ceilings; a guidance period beside a comparing word the patterns do not recognise is not read; a qualifier a word or
# two after the period counts ("30 days' notice or more"); whitespace inside a phrase is one space, so "not\nless than"
# in a quote is a floor. References read "§ 99", plurals and lists, and leave statutes ("Section 1542 of the California
# Civil Code") alone. Replayed: 0 of 63 guidance decisions, 0 of 10 guidance rules and 0 of 1,229 references change.
# policy-v6 (2026-10-10, Contract Reality Lab): a pass is lowered to needs review when its conclusion states a value no
# verified quote or guidance states (the question is not evidence), or gives a redaction mark ("[***]") as its value (`check_values`). Both were
# disclosed beside the answer and left the pass standing. Over 896 recorded passes (owner and lab stores): 17 change.
# policy-v7 is the name of the party check that was not adopted (57e4dae); runs recorded under it (the /break headline)
# keep that name, so it is not reused.
# policy-v8 (2026-10-13, war room F-04): a pass whose verified sentence points at a section the model was not handed
# says so ("the sentence points at §14.3, which was not handed to the model", `policy.proof.unseen_reason`) whether or
# not a period was compared; until v6 only a pass whose periods code compared named it, and a pass with no guidance
# carried no reason at all. No status changes; the reason is new. Over 1,623 recorded passes in 12 local stores, 216
# would carry it (135 of 856 in the owner's), none with guidance. A reference names the section numbered exactly so before
# one whose number only ends in it: without that, 5 more would have named a §5.1 that was handed.
# policy-v9 (2026-10-14, the legal pilot's H4-Q5): where the guidance and the verified quote both state a period and code
# cannot compare them (calendar days against Business Days, months against days), a pass the model proposed is lowered
# to needs review with that reason (`position_check`). Until v9 the comparison came back "incomparable" and fell through
# to the model's hint, so "30 days, which meets the guidance" of 30 Business Days stood as within guidance, with no
# reason, on real Qwen output. Replayed over 14,352 recorded findings in 55 local stores (827 with guidance), v9
# changes 3 decisions, all H4-Q5: the pilot's run and two scripted probes of the same clause.
# policy-v10 (2026-10-14, the product mission): periods in units that do not convert are placed on the calendar
# (policy.durations.calendar_days): a month is 28 to 31 days, a year 365 or 366, and N business days at least
# N + 2 × ⌊(N − 1) / 5⌋ when the contract's own definition makes a Business Day a weekday (policy.durations.business_week,
# read from the whole document). A contract period short of the guidance on every calendar is code's shortfall
# (`computed_days`): H4-Q5's 30 days against 30 Business Days, on a contract that defines a Business Day; a pass that
# holds on every calendar stays the model's with the counts consistent; ranges that overlap, or business days whose
# weekdays code cannot read from the contract, stay as v9 sends them, with the ranges, or what follows if a Business Day is a weekday, in
# the reason. A contract that says its bare "days" are Business Days is read so (policy.durations.day_convention). Replayed
# over 14,352 recorded findings in 55 local stores (827 with guidance): 6 change, each from incomparable to a shortfall
# code computes, five of them H4-Q5's clause (its contract defines a Business Day in §1.4) and one two months against
# at least 90 days.
# policy-v11 (2026-10-14, the intent-first mission): the contract's own statements that one provision replaces another, or
# that its parts rank for a conflict, are located and recorded with the run (runs.relations). One status changes: a
# question about the agreement as it stands, answered from text the contract replaced in full, without the replacement,
# is needs review set by code (`check_replaced`, `position_check`), and the quote stays verified. A limited replacement
# or a ranking of parts is a concern only: whether the limit applies, or which part governs, is not code's to decide.
# policy-v12 (2026-10-15): the time a question asks at ("What was the deadline in June 2026?") counts as stated when the
# answer repeats it (`values.frame_times`): repeating when it answers for takes no figure from the question, and the
# status no longer depends on whether the answer says it. A question that asks to confirm a date, or gives one as a
# property ("the payment due on 1 March 2027"), still has its date read as a premise. Everything else is v11's.
# policy-v13 (2026-10-15): (1) the model's own stated value (`observed`) is its stance between a replaced clause and its
# replacement when it names one of the values the two differ in (runs.relations.assess): an answer that quotes both
# and states both, but gives the replaced value as its own, raises a concern. (2) A section handle the model wrote
# that names no section it was given is shown as such and lowers a pass (runs.prose, `check_references`).
# policy-v14 (2026-10-16, the blind contract stress test): two more ways a pass rests on evidence that does not carry it,
# each needs review set by code (`position_check`). (1) One value given to every party ("Each party must give … 45
# calendar days") where the passages state several of that kind and none gives that value to every party (the Customer
# 45, the Provider 60): `check_values`, `values.uniform_party_choices`. (2) A verified quote whose own sentence carries a
# condition outside the quoted words ("Except for the first sixty (60) calendar days of the Initial Term, …") that the
# answer does not state: `check_conditions`, `left_out_condition`. Replay over recorded passes: DECISIONS.md.
# policy-v15 (2026-10-17, the amendment challenge): the number of an instrument or a document named with a mark
# ("Amendment No. 1", "Change Order #7") is not a value the answer states: `check_values` no longer lowers a pass for
# it, and runs.relations no longer counts it as a value of a replaced clause or its replacement. Each number of the
# name carries its own mark, so a count after one stays the answer's. The guidance and the question are read the same
# way, so an answer stating a number they name only as a marked name's can newly be lowered. Against v14: DECISIONS.md.
POLICY_VERSION = "policy-v15"


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
    week: BusinessWeek | None = None,
    days: DayConvention | None = None,
) -> Decision:
    """``quotes`` are the verified quotes and ``guidance`` the guidance text: the source facts. ``status_hint``,
    ``observed``, ``required`` and ``topic`` are the model's. ``passages`` are the whole sentences of the stored
    section text that the quotes sit in (`enclosing_sentences`), and ``dependencies`` the sections those sentences
    point at that the model was not handed (`unseen_references`); the caller computes both from the record. ``week`` is
    the contract's own definition of a Business Day, read from the whole document (`policy.durations.business_week`), and
    ``days`` what the contract says its bare "days" are (`policy.durations.day_convention`)."""
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
    read = read_as_the_contract_does(fact, days) if fact is not None else None
    converted = read is not None and fact is not None and read.duration != fact.duration
    fact = read
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
        periods: set[Duration] = set().union(*(periods_as_the_contract_reads(q, days) for q in quotes))
        outcomes = {evaluate(ObservedFact("notice_period", d, "", 0, 0), rule, week).outcome for d in periods}
        if len(outcomes) > 1:
            return Decision(
                "needs_review", "ambiguous_fact", f"the quote states more than one period ({_periods(periods)}) and they do not all meet the guidance alike"
            )
        evaluation = evaluate(fact, rule, week)
        if converted and days is not None:
            # The quote's "days" are the contract's Business Days: the reason says so, where every reader of it can check it.
            evaluation = replace(evaluation, reason=f"{evaluation.reason} ({days.note})")
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
            if any(evaluate(fact, other, week).outcome != "pass" for other in stated_rules(guidance)):
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
        if evaluation.outcome == "incomparable" and status_hint == "pass":
            # Both sides state a period and code cannot put them in order: units it cannot place on the calendar, or
            # ranges that overlap (a month, 28 to 31 days, against at least 30). The model's "meets the guidance" is then
            # a claim nothing checked: it goes to a person, and the reason says why (policy-v9, v10).
            return Decision("needs_review", "position_check", f"{evaluation.reason}; so the pass the model proposed is not established")
    if status_hint == "pass" and dependencies:
        # A pass rests on what the model read. Where no period was compared (no guidance, guidance with no period, a
        # quote with none) it carried no reason, so "Subject to Section 14.3, …" passed without saying that §14.3 was
        # never handed over (war room F-04, 2026-10-13). The pass stays the model's; the reason says what it did not see.
        return Decision("pass", "model_hint", unseen_reason(dependencies))
    return Decision(status_hint, "model_hint")


# The one thing a day comparison cannot establish, said the same way wherever code reports one.
SUBJECT_IS_THE_MODELS = "that the quoted period and the guidance concern the same point is the model's reading, not code's"

# What a recorded status rests on, read back from its source and the reason code wrote, in every wording `decide` has
# written: whether code compared a period in a verified quote with one in the guidance, and the sentence naming the
# sections the quote's sentence points at that the model was not handed. A pass whose reason only names such sections
# (policy-v8) compared nothing, yet the interface headed it "Code compared", and the memo did not mention it at all
# (release integration, 2026-10-13). Read from the record, so a run made under an earlier policy reads as it was decided.
_COMPARED_A_PERIOD = (", but code does not confirm that as a pass: ", "code found the day counts consistent")
_UNSEEN = (
    re.compile(r"the sentence points at .+?, which (?:were|was) not handed to the model"),  # policy-v8 on (proof.unseen_reason)
    re.compile(r"the quoted passage refers to .+?, which the model was not handed"),  # policy-v3 to policy-v6
)


@dataclass(frozen=True)
class Basis:
    code_compared: bool
    unseen: str | None  # the sentence as code wrote it, or None


def basis(source: str, reason: str | None) -> Basis:
    """What a finding's status rests on (see above): never more than the record says."""
    reason = reason or ""
    compared = source in ("computed_days", "confirmed_days", "ambiguous_fact") or (
        source == "model_hint" and any(phrase in reason for phrase in _COMPARED_A_PERIOD)
    )
    unseen = next((match.group(0) for wording in _UNSEEN if (match := wording.search(reason))), None)
    return Basis(compared, unseen)


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
    for reference in (r for passage in short.passages for r in references(passage)):
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
REFERENCE = re.compile(r"(?:§§?\s*|\b(?:Sections?|Clauses?|Articles?)\s+)(\d+(?:\.\d+)*)", re.IGNORECASE)
# The rest of a list after a reference: "Sections 99 and 98", "§§ 4.1, 4.2".
_MORE_REFERENCES = re.compile(r"(?:\([a-z0-9]{1,4}\))*\s*(?:,\s*(?:and|or)?|and|or|&)\s*(\d+(?:\.\d+)*)", re.IGNORECASE)
# A section of a statute, not of this agreement: "Section 1542 of the California Civil Code", "Section 365 of the
# Bankruptcy Code", "Section 2(a) of the Act" (bug hunt, 2026-10-09: reported as a section this document lacks).
_STATUTE = re.compile(r"(?:\([a-z0-9]{1,4}\))*\s+of\s+(?:the\s+)?(?:[A-Z][\w.'-]*\s+){0,6}(?:Code|Act|Regulations?|Rules|Statutes?|Law|U\.?S\.?C\.?)\b")


def references(text: str | None) -> list[str]:
    """The section numbers ``text`` points at, lists and plurals included, statutes left out, in order."""
    found: list[str] = []
    for match in REFERENCE.finditer(text or ""):
        numbers = [match.group(1)]
        position = match.end()
        while more := _MORE_REFERENCES.match(text or "", position):
            numbers.append(more.group(1))
            position = more.end()
        if _STATUTE.match(text or "", position):
            continue
        found += [n.rstrip(".") for n in numbers]
    return found


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
    for reference in references(text):
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


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    first, last = 0, len(text)
    for boundary in _PASSAGE_END.finditer(text):
        if boundary.end() <= start:
            first = boundary.end()
        elif boundary.start() >= end:
            last = boundary.start()
            break
    return first, last


def enclosing_sentences(text: str, start: int, end: int) -> str:
    """The whole sentences of ``text`` that the span touches. A quote is the shortest passage that carries the point
    (prompt rule 1), so the words that qualify it ("Subject to Section 14.3, …") are often just outside it."""
    first, last = _sentence_bounds(text, start, end)
    return text[first:last]


MAX_CONDITION_CHARS = 200


def left_out_condition(text: str, start: int, end: int) -> str | None:
    """The condition or exception that the span's own sentence carries outside the span (`policy.proof.CARVE_OUT`),
    as written: before the span, from the condition word to where it meets the quote ("Except for the first sixty (60)
    calendar days of the Initial Term" before "Customer may terminate …"); else after it, to the sentence's end ("unless
    Customer has paid"). None when the sentence carries none outside the quote: a condition the quote includes is shown
    with it, and one in another sentence is not this sentence's (blind contract stress test, 2026-10-16)."""
    first, last = _sentence_bounds(text, start, end)
    before, after = text[first:start], text[end:last]
    # A sentence that ends inside quotation marks ('… written notice." Section 5.2 …') ends there too: the words
    # before it are another sentence, often another clause's quoted text (the blind kit's Amendment One).
    if ends := list(_QUOTED_END.finditer(before)):
        before = before[ends[-1].end() :]
    if ends := list(_QUOTED_END.finditer(after)):
        after = after[: ends[0].start() + 1]
    for side, found in ((before, CARVE_OUT.search(before)), (after, CARVE_OUT.search(after))):
        # A condition word with nothing of its own after it ("However, …") is a turn of phrase, not a condition.
        if found is None or not concept_stems(side[found.end() :]):
            continue
        condition = side[found.start() :].strip().rstrip(",;:—–-.").strip()
        if len(condition) > MAX_CONDITION_CHARS:
            cut = condition.rfind(" ", 0, MAX_CONDITION_CHARS)
            condition = condition[: cut if cut > 0 else MAX_CONDITION_CHARS] + "…"
        return condition
    return None


_QUOTED_END = re.compile(r"[.!?][\"”’)]+\s+")
# How many of the condition's own words an answer must carry to state it ("except during the first 60 days of the
# Initial Term" for "Except for the first sixty (60) calendar days of the Initial Term"; "exceptions … indemnification
# obligations, gross negligence" for "EXCEPT FOR (A) A PARTY'S INDEMNIFICATION OBLIGATIONS …, (B) … GROSS NEGLIGENCE").
CONDITION_WORDS_NEEDED = 2


def _states_condition(conclusion: str, condition: str) -> bool:
    """Whether the answer states the condition: it carries words of the condition's own, the condition word aside (an
    answer with "unless Customer is in breach" states some other condition). Measured over the recorded passes:
    DECISIONS.md."""
    word = CARVE_OUT.search(condition)
    own = concept_stems(condition[word.end() :] if word else condition)
    return len(own & concept_stems(conclusion)) >= min(CONDITION_WORDS_NEEDED, len(own))


def check_conditions(decision: Decision, conclusion: str | None, conditions: Sequence[str]) -> Decision:
    """A pass that rests on a quote whose own sentence carries a condition outside the quoted words (``conditions``,
    `left_out_condition`, one per verified span that has one) and that does not state the condition itself is not a pass
    (policy-v14): the quote is real and the answer drops what limits it, as "Customer may terminate … on 30 days' notice"
    did over a sentence opening "Except for the first sixty (60) calendar days of the Initial Term". Whether the condition
    applies is a reading; code says only that the answer leaves it out. Other statuses already ask a person to look."""
    if decision.status != "pass":
        return decision
    unstated = [condition for condition in conditions if not _states_condition(conclusion or "", condition)]
    if not unstated:
        return decision
    return Decision(
        "needs_review", "position_check", _with_earlier(f"the quote leaves out of its sentence “{unstated[0]}”, and the answer does not state it", decision)
    )


def _with_earlier(reason: str, decision: Decision) -> str:
    """A lowered pass keeps what its reason already said ("the sentence points at §8, which was not handed to the
    model"): every surface reads that from the record (`basis`), and a lowered status must not unsay it."""
    return f"{reason}; {decision.reason}" if decision.reason else reason


def unseen_references(passage: str, sections: Iterable[tuple[str, str]], handed: Iterable[tuple[str, str]]) -> list[str]:
    """What a verified passage points at that exists in the document and was not among the sections handed to the
    model: "§14.3", "Schedule B". ``sections`` and ``handed`` are (number, heading) pairs. A reference that names
    nothing this reading of the document has (another agreement's section, a schedule that is a separate file) is
    not reported: code cannot say it went unseen. A section split into parts counts as handed only when every part
    was. No reference is followed; the model is not shown more, the pass is only not code's to give."""
    every, seen = list(sections), list(handed)
    unseen: list[str] = []
    for reference in references(passage):
        reference = reference.rstrip(".")
        # The section numbered so is the one meant. A number that only ends in it ("0.15.11" for clause 15.11) is a
        # reader's prefixed numbering, read only when no section carries the number itself: beside a §5.1 that was
        # handed, an unhanded §5.5.1 made "§5.1" unseen (replay of 2026-10-13: 5 recorded passes, one document).
        targets = [pair for pair in every if pair[0] == reference] or [pair for pair in every if pair[0] and pair[0].endswith("." + reference)]
        if targets and any(pair not in seen for pair in targets) and f"§{reference}" not in unseen:
            unseen.append(f"§{reference}")
    for kind, mark in ATTACHMENT.findall(passage):
        name = re.compile(rf"^\s*{re.escape(kind)}\s+{re.escape(mark)}\b", re.IGNORECASE)
        targets = [pair for pair in every if name.match(pair[1])]
        label = f"{kind.capitalize()} {mark.upper()}"
        if targets and any(pair not in seen for pair in targets) and label not in unseen:
            unseen.append(label)
    return unseen


def check_replaced(decision: Decision, replaced: str | None) -> Decision:
    """A finding answered from text the contract replaced in full, for a question about the agreement as it stands, is
    needs review set by code, with ``replaced``, the sentence runs.relations wrote: code located the replacing statement,
    and does not decide which wording governs. Whatever the status was (a shortfall code computed from the replaced
    period included), it rested on text the contract says no longer stands. A withheld finding stays withheld."""
    if replaced is None or decision.status == "unresolved":
        return decision
    return Decision("needs_review", "position_check", replaced)


def check_references(
    decision: Decision,
    conclusion: str | None,
    section_numbers: Iterable[str],
    handed_ids: Iterable[str],
    stated: Iterable[str] = (),
    unresolved: Sequence[str] = (),
) -> Decision:
    """A pass that sends the reader to a section the document does not have is not a pass: the quote may be
    real, the reference is not, and a person must look. Other statuses already ask for that. ``unresolved`` are section
    handles the model wrote that name no section it was given (runs.prose): the same failure, named in the reason. The
    reason speaks of the reference as the reader sees it, never of the internal handle."""
    if decision.status != "pass":
        return decision
    if unresolved:
        cited = (
            f"a section reference that names no section the model was given; it is shown as “{UNRESOLVED}”"
            if len(unresolved) == 1
            else f"{len(unresolved)} section references that name no section the model was given; each is shown as “{UNRESOLVED}”"
        )
        return Decision("needs_review", "reference_check", f"the answer cites {cited}")
    if not unknown_references(conclusion, section_numbers, handed_ids, stated):
        return decision
    return Decision("needs_review", "reference_check")


def check_values(
    decision: Decision, conclusion: str | None, quotes: Sequence[str], question: str | None, guidance: str | None, clause_numbers: Iterable[str] = ()
) -> Decision:
    """A pass whose conclusion states a value its evidence does not establish is not a pass (policy-v6). Three forms are
    code's to see: a value no verified quote and no guidance states (`values.unquoted_values`), a redaction mark given
    as the value (`values.redaction_given_as_value`), and, since policy-v14, one value given to every party where the
    passages state several of that kind and none gives it to every party (`values.uniform_party_choices`: "Each party must
    give 45 days" over a quote in which the Provider gives 60). The quote may be real; the value it is cited for is not
    in it, or not for everyone the answer gives it to, and a person must look. The value may still be right (a total
    computed from quoted figures, a period stated elsewhere in the contract): code says only that the evidence shown does
    not establish it, never that it is wrong.

    The guidance is a standard the reader set and the answer is compared with, so its values count as stated. The
    question does not: it is what the reader asked, not what the contract says, and a value an answer takes from it
    ("the Buyer's $1,000,000 cash payment") is a premise repeated, which the reason names as such. Other statuses already
    ask a person to look, and a finding with no verified quote was decided before this."""
    if decision.status != "pass" or not quotes:
        return decision
    mark = redaction_given_as_value(conclusion)
    if mark is not None:
        return Decision(
            "needs_review",
            "position_check",
            f"the answer gives {mark}, a redaction mark, as its value: this copy of the contract withholds the figure, so the evidence cannot establish it",
        )
    # The time the question asks at is not a figure taken from it (policy-v12): repeated, it says when the answer is for.
    unsupported = unquoted_values(conclusion, quotes, [guidance or "", *frame_times(question)], clause_numbers)
    if not unsupported:
        uniform = uniform_party_choices(conclusion, quotes, [question or ""], [guidance] if guidance else [])
        if not uniform:
            return decision
        given, values = uniform[0].choice.answer, ", ".join(uniform[0].choice.values)
        more = f" and {uniform[0].choice.more} more" if uniform[0].choice.more else ""
        return Decision(
            "needs_review",
            "position_check",
            _with_earlier(
                f"the answer gives {given} to every party (“{uniform[0].phrase}”); its passages state {values}{more}, and none gives {given} to every party",
                decision,
            ),
        )
    beyond_question = set(unquoted_values(conclusion, quotes, [question or "", guidance or ""], clause_numbers))
    from_question = [v for v in unsupported if v not in beyond_question]
    elsewhere = [v for v in unsupported if v in beyond_question]
    reasons = []
    if elsewhere:
        reasons.append(f"the evidence shown does not establish {', '.join(elsewhere)}: no verified quote or guidance states it")
    if from_question:
        reasons.append(f"{', '.join(from_question)} comes from the question, and no verified quote states it")
    return Decision("needs_review", "position_check", "; ".join(reasons))
