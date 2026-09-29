"""Record and replay the model's own answers, so the browser tests run the real pipeline in CI
without a GPU.

The default provider stays Ollama. ``WORKBENCH_PROVIDER=record`` wraps Ollama and writes every
answer it gives into the replay file; ``WORKBENCH_PROVIDER=replay`` serves only what was recorded
and fails loudly for anything else, so a changed prompt or a change in the retrieved sections shows
up as a missing key, never as a silently different answer. Nothing here is a mock of the model:
every replayed text was produced by the model named in its record, and the run built from it is
verified, decided and stored exactly as a live run is.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from ..hashing import sha256_text
from .base import Generation, ModelProvider, ProviderError

SEPARATOR = "\n␞\n"  # keeps "system + user" from colliding with a different split of the same text


class RecordedAnswer(TypedDict):
    model: str
    text: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    recorded_at: str
    user_head: str  # the first line of the user message, for a reader of the file; not used to match


def request_key(system: str, user: str) -> str:
    """The identity of a model request: the exact system and user texts, nothing else."""
    return sha256_text(system + SEPARATOR + user)


def load_answers(path: Path) -> dict[str, RecordedAnswer]:
    if not path.exists():
        return {}
    data: dict[str, RecordedAnswer] = json.loads(path.read_text(encoding="utf-8"))
    return data


def save_answers(path: Path, answers: dict[str, RecordedAnswer]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(answers.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


class ReplayProvider:
    """Answers only from the replay file."""

    name = "replay"

    def __init__(self, path: Path, model: str | None = None) -> None:
        self.path = path
        self.answers = load_answers(path)
        recorded_models = sorted({answer["model"] for answer in self.answers.values()})
        self.model = model or (recorded_models[0] if recorded_models else "none recorded")

    def healthy(self) -> tuple[bool, str]:
        if not self.answers:
            return False, f"replay file {self.path} has no recorded answers"
        return True, f"replaying {len(self.answers)} recorded answers from {self.path.name}"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        key = request_key(system, user)
        answer = self.answers.get(key)
        if answer is None:
            raise ProviderError(
                f"no recorded answer for this request (key {key[:12]}…): the prompt or the retrieved sections differ "
                f"from the recording. Re-record with WORKBENCH_PROVIDER=record against Ollama and commit {self.path.name}."
            )
        return Generation(
            text=answer["text"],
            input_tokens=answer["input_tokens"],
            output_tokens=answer["output_tokens"],
            latency_ms=answer["latency_ms"],
            model=answer["model"],
        )


class RecordingProvider:
    """Passes every request to a live provider and writes the answer into the replay file."""

    name = "record"

    def __init__(self, inner: ModelProvider, path: Path) -> None:
        self.inner = inner
        self.path = path
        self.model = inner.model
        self._lock = threading.Lock()

    def healthy(self) -> tuple[bool, str]:
        ok, detail = self.inner.healthy()
        return ok, f"{detail} (recording to {self.path.name})"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        generation = self.inner.generate_json(system, user, schema)
        record: RecordedAnswer = {
            "model": generation.model,
            "text": generation.text,
            "input_tokens": generation.input_tokens,
            "output_tokens": generation.output_tokens,
            "latency_ms": generation.latency_ms,
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "user_head": user.strip().splitlines()[0][:160] if user.strip() else "",
        }
        with self._lock:
            answers = load_answers(self.path)
            answers[request_key(system, user)] = record
            save_answers(self.path, answers)
        return generation
