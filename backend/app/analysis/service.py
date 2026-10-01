"""Build the prompt, call the provider, validate the shape. Truth-checking of quotes lives in
`verify`, status decisions in `runs.status`; this module only produces a validated proposal."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ..config import settings
from ..hashing import sha256_text
from ..providers.base import Generation, ModelProvider, ProviderError
from .schema import ANALYSIS_SCHEMA, AnalysisOut

PROMPTS_DIR = Path(__file__).with_name("prompts")
# The window of every run recorded before `section_window` existed (2026-10-01). The setting decides new runs; this
# constant decides how an old run is read back, so it must never move.
MAX_SECTION_CHARS_IN_PROMPT = 5000


def window_of(options: Mapping[str, object] | None) -> int:
    """The section window a run was made with: its recorded option, or the default for every run recorded before the option existed."""
    value = (options or {}).get("section_window", MAX_SECTION_CHARS_IN_PROMPT)
    return int(value) if isinstance(value, (int, float, str)) else MAX_SECTION_CHARS_IN_PROMPT


# A transport failure (connection refused, timeout) is retried once after a pause; a second failure is the run's failure.
PROVIDER_RETRY_DELAY_S = 2.0

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptPackage:
    version: str
    system: str
    sha256: str


@dataclass
class SectionForPrompt:
    label: str  # "sec_3", what the model cites
    number: str
    heading: str
    text: str


@dataclass
class AnalysisResult:
    proposal: AnalysisOut | None
    generation: Generation
    validation_error: str | None
    attempts: int


def load_prompt(version: str | None = None) -> PromptPackage:
    name = version or settings.prompt_version
    path = PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    return PromptPackage(version=name, system=text, sha256=sha256_text(text))


def build_user_message(
    question: str, guidance: str | None, document_name: str, sections: list[SectionForPrompt], window: int = MAX_SECTION_CHARS_IN_PROMPT
) -> str:
    lines = [f"QUESTION: {question.strip()}", ""]
    lines.append(f"LEGAL GUIDANCE: {guidance.strip()}" if guidance and guidance.strip() else "LEGAL GUIDANCE: none supplied")
    lines += ["", f"CONTRACT: {document_name}", "", "SECTIONS (cite by the id in brackets):"]
    for section in sections:
        title = f"{section.number} {section.heading}".strip()
        body = section.text if len(section.text) <= window else section.text[:window] + " […]"
        lines += ["", f"[{section.label}] {title}".rstrip(), body]
    return "\n".join(lines)


def _generate(provider: ModelProvider, system: str, message: str, retry_delay_s: float) -> tuple[Generation, int]:
    """One model call, retried once when the provider itself fails; returns the generation and the
    number of calls it took. The second failure propagates."""
    try:
        return provider.generate_json(system, message, ANALYSIS_SCHEMA), 1
    except ProviderError as error:
        log.warning("provider failed, retrying once in %.0f s: %s", retry_delay_s, error)
        time.sleep(retry_delay_s)
        return provider.generate_json(system, message, ANALYSIS_SCHEMA), 2


def analyze(provider: ModelProvider, prompt: PromptPackage, user_message: str, max_attempts: int = 2, retry_delay_s: float | None = None) -> AnalysisResult:
    """One call, one retry that feeds the validation error back. Never repairs output silently."""
    last_error: str | None = None
    generation: Generation | None = None
    attempts = 0  # model calls made, including a transport retry
    rounds = 0  # validation rounds: the first answer and one corrected retry
    message = user_message
    while rounds < max_attempts:
        rounds += 1
        generation, calls = _generate(provider, prompt.system, message, PROVIDER_RETRY_DELAY_S if retry_delay_s is None else retry_delay_s)
        attempts += calls
        try:
            proposal = AnalysisOut.model_validate(json.loads(generation.text))
            return AnalysisResult(proposal=proposal, generation=generation, validation_error=None, attempts=attempts)
        except (json.JSONDecodeError, ValidationError) as error:
            last_error = str(error)[:800]
            message = f"{user_message}\n\nYour previous answer was not valid ({last_error}). Return JSON matching the schema exactly."
    if generation is None:
        raise ProviderError("no generation produced")
    return AnalysisResult(proposal=None, generation=generation, validation_error=last_error, attempts=attempts)
