"""Who decided a finding's status, and what code raised about it: the one account every surface reads.

The answer card, the findings list, the memo and the evidence pack each used to rebuild this from the status, its
source and its reason, and they drifted (authority review, 2026-10-14): the memo counted only a needs-review or
not-found finding as flagged, so a pass whose recorded reason said "code does not confirm that as a pass" was printed
under "No automated check flagged a finding", and the answer's value checks (a value no quote states; several values,
one chosen) never reached it. The account reads the record once:

- ``decided_by``: "code" where a check set the status (a period shortfall, a value or a section the evidence does not
  establish, a quote with no one period); "model" where the status is the model's hint, a pass among them; "withheld"
  where no quote was found in the sections handed over.
- ``concerns``: every sentence code wrote against the status or could not establish, in the record's own words.
- ``flagged``: a status other than a pass, or a pass with a concern. An unflagged finding is the model's answer with
  nothing raised against it, never a cleared one.

Read from the record, so a run decided under an earlier policy reads as it was decided. Nothing here decides a status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import object_session

from ..models import Finding, Guidance
from .relations import CONCERNS, Note, load
from .status import basis
from .values import ValueChoice, frame_times, unquoted_values, value_choices


def notes_of(finding: Finding) -> tuple[Note, ...]:
    """What the run recorded its located relations to mean for this finding; nothing for a run recorded before policy-v11."""
    return load(finding.run.relations_json).notes.get(finding.ordinal, ())


DecidedBy = Literal["code", "model", "withheld"]

# The status sources under which a check, not the model, set the status (explain_run DETERMINISTIC_SOURCES).
DECIDED_BY_CODE = frozenset({"computed_days", "position_check", "ambiguous_fact", "reference_check"})
# What a check did when the record carries no sentence of its own (a run recorded before reasons were kept).
_CHECK_DID = {
    "computed_days": "code found the contract's period and the guidance's in conflict",
    "position_check": "code found that the evidence shown does not establish the model's answer",
    "ambiguous_fact": "code found that the quote does not state one period",
    "reference_check": "code found that the answer names a section this document does not have",
}
NOT_CONFIRMED = ", but code does not confirm that as a pass: "  # runs.status.decide: a pass with reasons against it


@dataclass(frozen=True)
class Account:
    status: str
    decided_by: DecidedBy
    concerns: tuple[str, ...]
    unquoted: tuple[str, ...]  # values the shown answer states that no verified quote or guidance states
    choices: tuple[ValueChoice, ...]  # quotes that offer several values of a kind the answer gives

    @property
    def flagged(self) -> bool:
        return self.status != "pass" or bool(self.concerns)


def value_checks(finding: Finding, clause_numbers: frozenset[str] = frozenset()) -> tuple[list[str], list[ValueChoice]]:
    """What code can say about the values the shown answer states, read now from the record (runs.values): the values
    no verified quote and no guidance states (the question is what was asked, not evidence: policy-v6 reads it the same
    way); and each verified quote that offers several values of a kind the answer gives. Read now, they change no
    status; a run decided under policy-v6 was lowered on the same reading. A point reported as not found states none."""
    if finding.status == "missing":
        return [], []
    quotes = [span.quote for span in finding.spans if span.verified]
    if not quotes:
        return [], []
    run = finding.run
    session = object_session(finding)
    guidance = session.get(Guidance, run.guidance_id) if session is not None and run.guidance_id else None
    choices = value_choices(finding.shown_conclusion, quotes, [run.question], [guidance.text] if guidance else [])
    # The time the question asks at counts as stated, as the status reads it (policy-v12, `values.frame_times`).
    stated = [guidance.text if guidance else "", *frame_times(run.question)]
    return unquoted_values(finding.shown_conclusion, quotes, stated, clause_numbers), list(choices)


def _choice_sentence(choice: ValueChoice) -> str:
    stated = ", ".join(choice.values) + (f" and {choice.more} more" if choice.more else "")
    return f"the passages state {stated}; the answer gives {choice.answer}, and which applies is the model's reading"


def account_of(finding: Finding, clause_numbers: frozenset[str] = frozenset()) -> Account:
    """The account of one finding. ``clause_numbers`` are the document's clause numbers, so a value written as a clause
    number ("Section 5.2") is not taken for an unquoted value (runs.values)."""
    unquoted, choices = value_checks(finding, clause_numbers)
    source, reason = finding.status_source or "", finding.status_reason or ""
    concerns: list[str] = []
    decided_by: DecidedBy
    if finding.status == "unresolved" or source == "no_evidence":
        decided_by = "withheld"
        concerns.append("no quote of it was found in the sections handed to the model, so it is withheld")
    elif source in DECIDED_BY_CODE:
        decided_by = "code"
        concerns.append(f"code: {reason}" if reason else _CHECK_DID[source])
    else:
        decided_by = "model"
        if finding.status == "needs_review":
            concerns.append("the model asked for review")
        elif finding.status == "missing":
            concerns.append("the model reported the point not found in the sections it was handed; code does not check an absence")
        if NOT_CONFIRMED in reason:
            concerns.append("code does not confirm the pass: " + reason.split(NOT_CONFIRMED, 1)[1])
    unseen = basis(source, reason).unseen
    if unseen and not any(unseen in concern for concern in concerns):
        concerns.append(f"code found that {unseen}; the answer may depend on it, and nothing checked that")
    if unquoted:
        concerns.append(f"the answer states {', '.join(unquoted)}, which no verified quote or guidance states")
    concerns += [_choice_sentence(choice) for choice in choices]
    # What the contract's own replacement and precedence statements mean for it, as recorded with the run (policy-v11): a
    # limit code cannot apply, a ranking of the parts quoted, a time the question names, or an answer that quotes the
    # replacement and states only the replaced values, is a concern (relations.CONCERNS). A note that set the status is its
    # reason, or opens it, shown once (since policy-v16 an old_value note can be either, by when its run was decided).
    concerns += [f"code: {note.sentence}" for note in notes_of(finding) if note.effect in CONCERNS and note.sentence not in reason]
    return Account(finding.status, decided_by, tuple(concerns), tuple(unquoted), tuple(choices))
