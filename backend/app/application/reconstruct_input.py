"""Use case: rebuild, from the record alone, the exact system and user messages a run's model call was given,
and check them against the hash the checking stage recorded when it ran.

A run stores its question, its guidance, its prompt version and hash, and the candidates it handed to the
model (`candidates_json`: label, section id, number, heading, in rank order); the sections keep their text
under the immutability triggers once the run has finished. From those the user message is a pure function
(`analysis.service.build_user_message`), so the record can answer "show me exactly what the model saw"
without a copy of the contract text ever being written to a log. The reconstruction also yields the
ContextSlice of every candidate: the part of its text the prompt actually carried, which is at most
`MAX_SECTION_CHARS_IN_PROMPT` characters, and whether it was truncated.

The check is strict: a prompt file rewritten in place since the run, a section whose text changed, or a
candidate that no longer exists all surface as a mismatch with the reason, never as a repaired answer.

What is rebuilt is the first round's message, the one the checking stage hashed. The output a run keeps (`raw_output`,
and the findings made from it) answered that message only when the model's first answer passed validation. When it
did not, the model was asked again with that message plus a note quoting why the answer was rejected, and the record
keeps neither the rejected answer nor the note: the input of the kept output is then not reconstructable, and
`answered` says so, with the reason, for every surface that presents the rebuilt messages as the model's input (F-14,
2026-10-13). A transport retry sends the same message again and changes nothing here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..analysis.service import MAX_SECTION_CHARS_IN_PROMPT, PROMPTS_DIR, SectionForPrompt, build_user_message, load_prompt, window_of
from ..document_names import run_prompt_name
from ..errors import NotFound
from ..hashing import sha256_text
from ..models import Run, RunStage, Section


@dataclass(frozen=True)
class ContextSlice:
    """The part of a candidate section that the model was shown, in rank order."""

    label: str
    section_id: str
    rank: int
    start: int
    end: int
    truncated: bool
    content_sha256: str


@dataclass
class Reconstruction:
    run_id: str
    prompt_version: str
    recorded_input_sha256: str | None  # the checking stage's input hash, if the run reached that stage
    system: str | None = None
    user: str | None = None
    input_sha256: str | None = None
    slices: list[ContextSlice] = field(default_factory=list)
    problem: str | None = None
    calls: int | None = None  # model calls the checking stage recorded, a transport retry included
    rounds: int | None = None  # validation rounds, as recorded or as the record determines them; None when it cannot
    # Why the rebuilt messages are not, or cannot be shown to be, the input of the output the run kept.
    answer_problem: str | None = None

    @property
    def matches(self) -> bool:
        """The rebuilt messages hash to what the checking stage recorded: the first round's message."""
        return self.problem is None and self.recorded_input_sha256 is not None and self.input_sha256 == self.recorded_input_sha256

    @property
    def answered(self) -> bool:
        """The rebuilt messages are the exact input of the output the run kept (or of a call that kept none)."""
        return self.matches and self.answer_problem is None

    @property
    def answered_problem(self) -> str | None:
        """Everything standing between the rebuilt messages and that claim, in one sentence; None when nothing does."""
        return "; ".join(p for p in (self.problem, self.answer_problem) if p) or None


NO_RECORDED_HASH = "the run recorded no input hash (it predates the record of one), so the rebuilt input has nothing to be checked against"

# How every checking stage written before `run_stages.rounds` (2026-10-13) made its calls, frozen like the window of
# analysis.service: at most two validation rounds, each one call plus at most one transport retry. These decide how an
# old row is read back, so they must never move with the code that makes new ones.
_ROUNDS_BEFORE_RECORDED = 2
_CALLS_PER_ROUND_BEFORE_RECORDED = 2


def later_round(rounds: int) -> str:
    return (
        f"the recorded answer came from validation round {rounds}: the first answer failed validation and the model was "
        "asked again with the first message plus a note quoting why it was rejected. The run kept neither the first "
        "answer nor that message, so the input of the recorded answer is not reconstructable; the first message is what "
        "the recorded input hash covers"
    )


def rounds_not_recorded(calls: int | None) -> str:
    made = f"made {calls} model calls and recorded calls, not validation rounds" if calls is not None else "recorded neither its calls nor its rounds"
    return (
        f"the run {made}: a later call may have resent the same message after a transport failure or carried a corrected "
        "message after a rejected answer, which the run did not keep, so the record cannot show which input the recorded "
        "answer was given"
    )


def validation_rounds(checking: RunStage, run: Run) -> int | None:
    """The checking stage's validation rounds: as recorded, or, on a row written before they were, what the record
    determines. One call is one round; more calls than one round can make, or a run that ended with an invalid answer
    (every round was used), is two. Two calls otherwise are either, and the answer is None."""
    if checking.rounds is not None:
        return checking.rounds
    calls = checking.attempt
    if calls is None:
        return None
    if calls == 1:
        return 1
    if calls > _CALLS_PER_ROUND_BEFORE_RECORDED or run.reason == "invalid_output":
        return _ROUNDS_BEFORE_RECORDED
    return None


def _answer_problem(checking: RunStage, rounds: int | None, run: Run) -> str | None:
    if run.raw_output is None:
        return None  # the run kept no answer (the provider failed): the rebuilt messages are what the model was given
    if rounds == 1:
        return None
    return later_round(rounds) if rounds is not None else rounds_not_recorded(checking.attempt)


def context_slice(label: str, section: Section, rank: int, window: int = MAX_SECTION_CHARS_IN_PROMPT) -> ContextSlice:
    end = min(len(section.text), window)
    return ContextSlice(
        label=label,
        section_id=section.id,
        rank=rank,
        start=0,
        end=end,
        truncated=len(section.text) > window,
        content_sha256=sha256_text(section.text[:end]),
    )


def reconstruct_input(session: Session, run_id: str) -> Reconstruction:
    run = session.get(Run, run_id)
    if run is None:
        raise NotFound("run", run_id)
    checking = session.query(RunStage).filter_by(run_id=run.id, stage="checking").order_by(RunStage.id).first()
    result = Reconstruction(run_id=run.id, prompt_version=run.prompt_version, recorded_input_sha256=checking.input_hash if checking else None)
    if checking is None:
        result.problem = "the run never reached the model"
        return result
    result.calls = checking.attempt
    result.rounds = validation_rounds(checking, run)
    result.answer_problem = _answer_problem(checking, result.rounds, run)

    prompt_path = PROMPTS_DIR / f"{run.prompt_version}.md"
    if not prompt_path.exists():
        result.problem = f"prompt file {prompt_path.name} no longer exists"
        return result
    prompt = load_prompt(run.prompt_version)
    if prompt.sha256 != run.prompt_hash:
        result.problem = f"prompt file {prompt_path.name} was rewritten since the run: {prompt.sha256[:12]} now, {run.prompt_hash[:12]} then"
        return result

    window = window_of(json.loads(run.options_json or "{}"))
    try:
        candidates = json.loads(run.candidates_json or "[]")
    except ValueError:
        result.problem = "candidates_json is not valid JSON"
        return result
    sections: list[SectionForPrompt] = []
    for rank, candidate in enumerate(candidates, start=1):
        section = session.get(Section, candidate["section_id"])
        if section is None:
            result.problem = f"candidate section {candidate['section_id']} no longer exists"
            return result
        sections.append(SectionForPrompt(candidate["label"], section.number, section.heading, section.text))
        result.slices.append(context_slice(candidate["label"], section, rank, window))

    guidance_text = run.guidance.text if run.guidance else None
    result.system = prompt.system
    result.user = build_user_message(run.question, guidance_text, run_prompt_name(run), sections, window=window)
    result.input_sha256 = sha256_text(prompt.sha256 + result.user)
    if result.recorded_input_sha256 is None:
        # Not a mismatch: there is nothing to match. The checking stage began recording its input hash on
        # 2026-09-28; the 58 runs before it were being reported as "does not hash to what was recorded", which
        # said a comparison had failed when none could be made (audit, 2026-10-02).
        result.problem = NO_RECORDED_HASH
    elif result.input_sha256 != result.recorded_input_sha256:
        result.problem = "the reconstructed input does not hash to what the checking stage recorded"
    return result
