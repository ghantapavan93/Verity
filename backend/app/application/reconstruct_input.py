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
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..analysis.service import MAX_SECTION_CHARS_IN_PROMPT, PROMPTS_DIR, SectionForPrompt, build_user_message, load_prompt, window_of
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

    @property
    def matches(self) -> bool:
        return self.problem is None and self.recorded_input_sha256 is not None and self.input_sha256 == self.recorded_input_sha256


NO_RECORDED_HASH = "the run recorded no input hash (it predates the record of one), so the rebuilt input has nothing to be checked against"


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
    result.user = build_user_message(run.question, guidance_text, run.document.name, sections, window=window)
    result.input_sha256 = sha256_text(prompt.sha256 + result.user)
    if result.recorded_input_sha256 is None:
        # Not a mismatch: there is nothing to match. The checking stage began recording its input hash on
        # 2026-09-28; the 58 runs before it were being reported as "does not hash to what was recorded", which
        # said a comparison had failed when none could be made (audit, 2026-10-02).
        result.problem = NO_RECORDED_HASH
    elif result.input_sha256 != result.recorded_input_sha256:
        result.problem = "the reconstructed input does not hash to what the checking stage recorded"
    return result
