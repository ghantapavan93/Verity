"""Replay a committed recording of the golden set through the code in force, without a model.

A recording's raw model outputs are committed (`recordings/*.json`), one per golden. A replay hands each back, by
question, to the start_run and execute_run a live run uses, on today's reading of the sample, so today's reader,
retrieval, verifier, policy and judge decide what the same answers are worth. The golden figure the documents publish
is a replay's result, and tests/test_goldens.py fails when the code moves it: until 2026-10-30 no code derived the
published "37 of 44" at all, and a rule bump or a relabelled set changed what the record read with no test failing
(stress test EVL-2).

A replay makes runs, from answers a model gave to another reading and other rules, under today's identity. They must
never stand in a store a request is answered from, where one would be handed back as today's answer: a replay runs in a
store of its own (the test's, or the temporary one `scripts/run_goldens.py --replay` makes).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..analysis.service import load_prompt
from ..application.save_guidance import save_guidance
from ..application.start_run import start_run
from ..models import Run
from ..providers.base import Generation, ProviderError
from ..runs.service import execute_run
from .service import GoldenSet, Recording, Verdict, ensure_golden_document, judge

RECORDINGS_DIR = Path(__file__).with_name("recordings")


@dataclass(frozen=True)
class Answer:
    run_id: str
    question: str
    raw_output: str | None  # None: the run recorded no answer (it failed before one)


@dataclass(frozen=True)
class CommittedRecording:
    name: str
    label: str  # Recording.label of the recording as the store held it
    model: str
    prompt_version: str
    prompt_hash: str
    answers: dict[str, Answer]  # golden id → the recorded answer
    as_recorded: dict[str, Any]  # the store's runs judged by the judge in force when the file was written: passes, fails
    replayed: dict[str, Any]  # what a replay through the code in force gives: passes, fails; held by tests/test_goldens.py


def outcome_counts(verdicts: Mapping[str, Verdict]) -> dict[str, Any]:
    """A figure as the documents state it: passes of the recorded, the goldens that do not pass, and the passes that rest
    on a finding code lowered to needs review."""
    recorded = [golden_id for golden_id, verdict in verdicts.items() if verdict.outcome != "missing"]
    fails = sorted(golden_id for golden_id in recorded if verdicts[golden_id].outcome != "pass")
    lowered = sorted(golden_id for golden_id in recorded if verdicts[golden_id].outcome == "pass" and verdicts[golden_id].lowered)
    return {"passes": len(recorded) - len(fails), "of": len(recorded), "fails": fails, "lowered": lowered}


def record(recording: Recording, golden_set: GoldenSet, name: str) -> dict[str, Any]:
    """What a committed recording holds, taken from the store's runs of one recording."""
    verdicts = {golden.id: judge(golden, recording.runs.get(golden.id)) for golden in golden_set.goldens}
    return {
        "recording": name,
        "label": recording.label(),
        "model": recording.model,
        "prompt_version": recording.prompt.version,
        "prompt_hash": recording.prompt.sha256,
        "document_sha256": recording.document.sha256,
        "options": recording.options,
        "set_sha256": golden_set.sha256,
        "as_recorded": outcome_counts(verdicts),
        "answers": {golden_id: {"run_id": run.id, "question": run.question, "raw_output": run.raw_output} for golden_id, run in sorted(recording.runs.items())},
    }


def load_recording(path: Path) -> CommittedRecording:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    answers = {str(golden_id): Answer(str(a["run_id"]), str(a["question"]), a.get("raw_output")) for golden_id, a in data["answers"].items()}
    return CommittedRecording(
        name=str(data["recording"]),
        label=str(data["label"]),
        model=str(data["model"]),
        prompt_version=str(data["prompt_version"]),
        prompt_hash=str(data["prompt_hash"]),
        answers=answers,
        as_recorded=dict(data["as_recorded"]),
        replayed=dict(data.get("replayed") or {}),
    )


class RecordedAnswers:
    """A provider that answers a golden's question with the output the recording kept for it, and nothing else."""

    name = "recorded"

    def __init__(self, model: str, by_question: Mapping[str, str | None]) -> None:
        self.model = model
        self.by_question = dict(by_question)

    def healthy(self) -> tuple[bool, str]:
        return True, "recorded answers"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        question = user.splitlines()[0].removeprefix("QUESTION: ")
        text = self.by_question.get(question)
        if text is None:
            raise ProviderError(f"the recording holds no answer to {question!r}")
        return Generation(text=text, input_tokens=None, output_tokens=None, latency_ms=0.0, model=self.model)


def replay(session: Session, golden_set: GoldenSet, recording: CommittedRecording) -> dict[str, Verdict]:
    """Each golden of the set, answered by the recording's output for it and judged; missing where it holds none."""
    prompt = load_prompt(recording.prompt_version)
    if prompt.sha256 != recording.prompt_hash:
        raise ValueError(f"{recording.prompt_version} is not the prompt the recording answered (its hash is {prompt.sha256[:12]})")
    document = ensure_golden_document(session, golden_set)
    provider = RecordedAnswers(recording.model, {answer.question: answer.raw_output for answer in recording.answers.values()})
    verdicts: dict[str, Verdict] = {}
    for golden in golden_set.goldens:
        if golden.id not in recording.answers:
            verdicts[golden.id] = Verdict("missing", "the recording holds no answer to this golden")
            continue
        guidance_id = save_guidance(session, golden.guidance, source="golden").guidance.id if golden.guidance else None
        started = start_run(session, document.id, guidance_id, golden.question, provider, prompt_version=prompt.version, model=recording.model)
        if started.created:
            execute_run(session, started.run.id, provider)
        session.expire_all()
        verdicts[golden.id] = judge(golden, session.get(Run, started.run.id))
    return verdicts
