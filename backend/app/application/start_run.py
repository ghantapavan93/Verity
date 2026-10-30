"""Use case: start an analysis run, or hand back the run that already answers the same question.

Identity of a run's inputs is the fingerprint: document, guidance, question, prompt hash,
decoding and retrieval options, and the versions of the rules that decide the answer (runs.versions).
A repeated request with the same fingerprint reuses the running or completed
run instead of spending another model call; a failed run is not reused, so it can be retried.
The database enforces the same rule with a unique index over non-failed runs. A new run is written
through quotas.admit: the lookup is made again under the store's write lock, with the day's quotas,
so of two requests racing each other the second is handed the first's run, and no quota is passed.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ..analysis.service import MAX_SECTION_CHARS_IN_PROMPT, load_prompt
from ..config import settings
from ..errors import InvalidInput, NotFound
from ..hashing import fingerprint
from ..ingest.invisible import visible_text
from ..models import Document, Guidance, Run, Section, new_id, utcnow
from ..providers.base import ModelProvider
from ..retrieval.aliases import ALIASES_SHA256
from ..routing.router import ModelRouter, task_for
from ..runs.owner import this_process
from ..runs.relations import reached_start, replacement_starts
from ..runs.versions import SEMANTIC_VERSIONS
from .quotas import admit, run_quotas
from .recover_runs import run_ended, run_started
from .visible_input import has_visible_text
from .workspace import require_document, require_guidance

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


# The replacement starts each document's statements give. A document's sections never change (its id and sha256 name
# its text), so they are read once per process, not on every request: a repeated question is handed its run without
# reading the document again.
_STARTS: OrderedDict[tuple[str, str], tuple[str, ...]] = OrderedDict()
_STARTS_KEPT = 256
_STARTS_LOCK = threading.Lock()
# One reading of a document's starts at a time: concurrent questions on a document not yet read each read it, in the
# request before admission, so three at once on a fresh 1.85 MB document took 32, 39 and 71 s (stress test, 2026-10-30).
# The others wait for the one and are handed its answer. A lock per document, dropped once it is read.
_READING_STARTS: dict[tuple[str, str], threading.Lock] = {}


def _document_starts(session: Session, document: Document) -> tuple[str, ...]:
    key = (document.id, document.sha256)
    with _STARTS_LOCK:
        if key in _STARTS:
            _STARTS.move_to_end(key)
            return _STARTS[key]
        reading = _READING_STARTS.setdefault(key, threading.Lock())
    with reading:
        with _STARTS_LOCK:
            if key in _STARTS:  # read by the request this one waited for
                return _STARTS[key]
        try:
            sections = session.query(Section).filter(Section.document_id == document.id).order_by(Section.ordinal).all()
            starts = replacement_starts(sections)
            with _STARTS_LOCK:
                _STARTS[key] = starts
                while len(_STARTS) > _STARTS_KEPT:
                    _STARTS.popitem(last=False)
        finally:
            with _STARTS_LOCK:
                _READING_STARTS.pop(key, None)
    return starts


def identity_options(session: Session, document: Document, model: str | None, now: datetime) -> RunOptions:
    """The options that are a run's identity on ``now``: run_options, and the latest replacement start the document gives
    that is already reached. Whether a start is reached decides what a run says (runs.relations), so a run is the same
    run only while the same starts are reached; the key enters only when there is one, so a document with no dated start
    keeps the fingerprint it always had. Every lookup of a run by its inputs uses this (start_run, goldens.run_for)."""
    options = run_options(model)
    reached = reached_start(_document_starts(session, document), now.date())
    if reached is not None:
        options["latest_start_reached"] = reached
    return options


def router() -> ModelRouter:
    return ModelRouter(default_model=settings.model, policy=settings.routing_policy)


def compute_fingerprint(document_id: str, guidance_id: str | None, question: str, prompt_hash: str, options: RunOptions, workspace: str | None = None) -> str:
    """A curated run (no workspace) keeps the fingerprint it always had; a workspace's run carries the workspace, so the
    same question from another workspace is another run and is never handed this one."""
    if workspace is None:
        return fingerprint(FINGERPRINT_KIND, document_id, guidance_id, question, prompt_hash, json.dumps(options, sort_keys=True))
    return fingerprint(FINGERPRINT_KIND, document_id, guidance_id, question, prompt_hash, json.dumps(options, sort_keys=True), workspace)


def start_run(
    session: Session,
    document_id: str,
    guidance_id: str | None,
    question: str,
    provider: ModelProvider,
    prompt_version: str | None = None,
    model: str | None = None,
    workspace: str | None = None,
) -> StartedRun:
    """``workspace`` is the asker's: it must be able to read the document and the guidance, and the run is its. None is
    the project itself (goldens, batches), whose runs are curated."""
    document: Document | None
    guidance: Guidance | None
    if workspace is not None:
        document = require_document(session, document_id, workspace)
        guidance = require_guidance(session, guidance_id, workspace) if guidance_id else None
    else:
        document = session.get(Document, document_id)
        if document is None:
            raise NotFound("document", document_id)
        guidance = session.get(Guidance, guidance_id) if guidance_id else None
        if guidance_id and guidance is None:
            raise NotFound("guidance", guidance_id)

    question = visible_text(question).strip()
    # The length check before this counted invisible characters: a question of nothing but zero-width spaces passed it,
    # was stored empty and cost a model call. What is left once they are removed is what is asked.
    # Nor did a question of characters that render nothing alone (a joiner, a direction mark): it started a run (stress test,
    # 2026-10-30).
    if not has_visible_text(question):
        raise InvalidInput("The question has no visible text. Type a question about the contract.")
    prompt = load_prompt(prompt_version)
    task = task_for(guidance is not None)
    decision = router().select(task, model)
    # One instant for the identity and the run: the relation step reads the run's created_at as the day it was asked, so
    # the starts that entered the identity are the starts the run is assessed against, even across midnight.
    now = utcnow()
    options = identity_options(session, document, decision.model, now)
    key = compute_fingerprint(document.id, guidance.id if guidance else None, question, prompt.sha256, options, workspace)

    run = Run(
        id=new_id(),  # known before the row is written: the run is held for its worker under this id (write below)
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
        workspace_id=workspace,
        created_at=now,
        owner=this_process().render(),
    )

    def write() -> Run:
        # Held for its worker before its row commits, so no read sees a run of this process that no one holds
        # (application/recover_runs.py); the caller that starts its worker lets it go when the worker ends.
        run_started(run.id)
        session.add(run)
        return run

    # A question asked before is handed its run before any quota is counted: it creates nothing and calls no model.
    try:
        written, created = admit(session, run_quotas(workspace), write, find=lambda: active_run(session, key))
    except BaseException:
        run_ended(run.id)  # never written
        raise
    if not created:
        run_ended(run.id)
    return StartedRun(written, created=created)


def active_run(session: Session, key: str) -> Run | None:
    """The running or completed run for this fingerprint, if any. Failed runs are retryable."""
    return session.query(Run).filter(Run.fingerprint == key, Run.stage != "failed").order_by(Run.created_at.desc()).first()
