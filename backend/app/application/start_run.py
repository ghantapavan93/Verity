"""Use case: start an analysis run, or hand back the run that already answers the same question.

Identity of a run's inputs is the fingerprint: document, guidance, question, prompt hash,
decoding and retrieval options, and the versions of the rules that decide the answer (runs.versions).
A repeated request with the same fingerprint reuses the running or completed
run instead of spending another model call; a failed run is not reused, so it can be retried.
The database enforces the same rule with a unique index over non-failed runs, so two requests
racing each other cannot both create one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..analysis.service import MAX_SECTION_CHARS_IN_PROMPT, load_prompt
from ..config import settings
from ..errors import NotFound
from ..hashing import fingerprint
from ..models import Document, Guidance, Run
from ..providers.base import ModelProvider
from ..retrieval.aliases import ALIASES_SHA256
from ..routing.router import ModelRouter, task_for
from ..runs.versions import SEMANTIC_VERSIONS

FINGERPRINT_KIND = "run/v1"

# Decoding and retrieval settings that shape the answer, recorded on the run and part of its identity.
RunOptions = dict[str, float | int | str]


@dataclass(frozen=True)
class StartedRun:
    run: Run
    created: bool  # False when an existing running or completed run was reused


def run_options(model: str | None = None) -> RunOptions:
    """The settings that shape an answer and therefore belong to a run's identity, the model among them."""
    options: RunOptions = {
        "model": model or settings.model,
        "temperature": settings.temperature,
        "seed": settings.seed,
        "num_ctx": settings.num_ctx,
        "retrieval_k": settings.retrieval_k,
    }
    if settings.section_window != MAX_SECTION_CHARS_IN_PROMPT:
        # A window other than the one every old run was made with enters the identity; a run without the option was made
        # at that old window, so those runs keep their fingerprints and read back correctly.
        options["section_window"] = settings.section_window
    if settings.retrieval_aliases:
        # The table's hash, so a run's candidates can be reproduced after the table changes.
        options["retrieval_aliases"] = ALIASES_SHA256[:12]
    if settings.retrieval != "bm25":
        # Only a non-default retriever enters the identity, so runs recorded under BM25 keep theirs.
        options["retrieval"] = settings.retrieval
        options["embed_model"] = settings.embed_model
    # The rules that will decide the answer. A run made under other rules is another run (found 2026-10-02: after the
    # status decision was fixed, the same request was still handed the run the old decision had made).
    options.update(SEMANTIC_VERSIONS)
    return options


def router() -> ModelRouter:
    return ModelRouter(default_model=settings.model, policy=settings.routing_policy)


def compute_fingerprint(document_id: str, guidance_id: str | None, question: str, prompt_hash: str, options: RunOptions) -> str:
    return fingerprint(FINGERPRINT_KIND, document_id, guidance_id, question, prompt_hash, json.dumps(options, sort_keys=True))


def start_run(
    session: Session,
    document_id: str,
    guidance_id: str | None,
    question: str,
    provider: ModelProvider,
    prompt_version: str | None = None,
    model: str | None = None,
) -> StartedRun:
    document = session.get(Document, document_id)
    if document is None:
        raise NotFound("document", document_id)
    guidance = session.get(Guidance, guidance_id) if guidance_id else None
    if guidance_id and guidance is None:
        raise NotFound("guidance", guidance_id)

    question = question.strip()
    prompt = load_prompt(prompt_version)
    task = task_for(guidance is not None)
    decision = router().select(task, model)
    options = run_options(decision.model)
    key = compute_fingerprint(document.id, guidance.id if guidance else None, question, prompt.sha256, options)

    existing = active_run(session, key)
    if existing is not None:
        return StartedRun(existing, created=False)

    run = Run(
        document_id=document.id,
        guidance_id=guidance.id if guidance else None,
        question=question,
        stage="reading",
        provider=provider.name,
        model=decision.model,
        task=task,
        routing_reason=decision.reason,
        prompt_version=prompt.version,
        prompt_hash=prompt.sha256,
        options_json=json.dumps(options, sort_keys=True),
        document_sha256=document.sha256,
        guidance_sha256=guidance.sha256 if guidance else None,
        fingerprint=key,
    )
    session.add(run)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent request with the same inputs won; the unique index makes this exact.
        session.rollback()
        existing = active_run(session, key)
        if existing is None:
            raise
        return StartedRun(existing, created=False)
    return StartedRun(run, created=True)


def active_run(session: Session, key: str) -> Run | None:
    """The running or completed run for this fingerprint, if any. Failed runs are retryable."""
    return session.query(Run).filter(Run.fingerprint == key, Run.stage != "failed").order_by(Run.created_at.desc()).first()
