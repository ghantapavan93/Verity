"""Use case: verify a recorded run again, from its stored raw output and stored sections, without a
model call, and report what would change. The run is not touched; runs are immutable. This is how a
change to the verifier is measured against the record before it is kept.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..analysis.schema import AnalysisOut
from ..errors import NotFound
from ..models import EvidenceSpan, Run, Section
from ..runs.service import verify_evidence


@dataclass(frozen=True)
class SpanReplay:
    finding: int
    span: int
    quote: str
    cited: str
    stored_method: str
    stored_verified: bool
    method: str
    verified: bool
    section: str  # "§5.3.1" or the heading, where the quote is now located; "" when nowhere

    @property
    def change(self) -> str:
        if self.verified and not self.stored_verified:
            return "gained"
        if self.stored_verified and not self.verified:
            return "lost"
        return "moved" if self.verified and self.method != self.stored_method else "same"


@dataclass
class Replay:
    run_id: str
    question: str
    prompt_version: str
    spans: list[SpanReplay] = field(default_factory=list)
    problem: str | None = None  # raw output missing or invalid: nothing to replay

    @property
    def gained(self) -> int:
        return sum(1 for s in self.spans if s.change == "gained")

    @property
    def lost(self) -> int:
        return sum(1 for s in self.spans if s.change == "lost")


def reverify_run(session: Session, run_id: str) -> Replay:
    run = session.get(Run, run_id)
    if run is None:
        raise NotFound("run", run_id)
    replay = Replay(run_id=run.id, question=run.question, prompt_version=run.prompt_version)
    if not run.raw_output:
        replay.problem = "no raw output on this run"
        return replay
    try:
        proposal = AnalysisOut.model_validate(json.loads(run.raw_output))
    except (ValueError, ValidationError) as error:
        replay.problem = f"raw output is not a valid proposal: {str(error)[:120]}"
        return replay

    candidates = json.loads(run.candidates_json or "[]")
    chosen: list[Section] = []
    by_label: dict[str, Section] = {}
    for candidate in candidates:
        section = session.get(Section, candidate["section_id"])
        if section is not None:
            chosen.append(section)
            by_label[candidate["label"]] = section
    stored: dict[tuple[int, int], EvidenceSpan] = {(f.ordinal, s.ordinal): s for f in run.findings for s in f.spans}

    for finding_ordinal, item in enumerate(proposal.findings):
        for span_ordinal, evidence in enumerate(item.evidence):
            section, located, method = verify_evidence(evidence.quote, evidence.section_id, by_label, chosen)
            was = stored.get((finding_ordinal, span_ordinal))
            replay.spans.append(
                SpanReplay(
                    finding=finding_ordinal,
                    span=span_ordinal,
                    quote=evidence.quote,
                    cited=evidence.section_id,
                    stored_method=was.method if was else "none",
                    stored_verified=bool(was.verified) if was else False,
                    method=method,
                    verified=located is not None,
                    section=("" if section is None or located is None else (f"§{section.number}" if section.number else section.heading)),
                )
            )
    return replay
