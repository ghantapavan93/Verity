from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..application.clause_location import ClauseLocator
from ..application.create_memo import review_head
from ..application.evidence_pack import build_evidence_pack
from ..application.explain_run import explain_run
from ..application.recover_runs import recover_interrupted_runs
from ..application.review_finding import review_out
from ..application.start_run import start_run
from ..application.workspace import require_run, visible_runs
from ..db import SessionLocal, get_session
from ..models import Finding, Run, iso
from ..providers import make_provider
from ..providers.base import ModelProvider
from ..runs.events import TERMINAL, bus
from ..runs.service import execute_run
from ..schemas import CandidateOut, FindingOut, RunDetail, RunExplanation, RunIn, RunOut, RunSummary, SpanOut, StageOut
from .access import current_workspace
from .deps import get_provider

router = APIRouter(prefix="/api/runs", tags=["runs"])
HEARTBEAT_SECONDS = 15


# ----------------------------------------------------------------------------- mapping


def finding_out(finding: Finding, locator: ClauseLocator | None = None) -> FindingOut:
    locator = locator or ClauseLocator(finding.run.document.sections)
    return FindingOut(
        id=finding.id,
        topic=finding.topic,
        status=finding.status,
        status_source=finding.status_source,
        status_reason=finding.status_reason,
        evidence_kind="coverage" if finding.status == "missing" else "passage",
        review=review_out(finding.review),
        conclusion=finding.shown_conclusion,
        model_conclusion=finding.conclusion,
        spans=[
            SpanOut(
                section_id=s.section_id,
                start=s.start,
                end=s.end,
                quote=s.quote,
                verified=s.verified,
                method=s.method,
                match_count=s.match_count,
                cited_section_label=s.cited_section_label,
                clause_label=locator.label(s),
            )
            for s in finding.spans
        ],
        guidance_reference=finding.guidance_reference,
        observed=finding.observed,
        required=finding.required,
        suggested_position=finding.suggested_position,
    )


def run_out(run: Run, locator: ClauseLocator | None = None) -> RunOut:
    # Unresolved findings are kept on the run but not shown as answers.
    locator = locator or ClauseLocator(run.document.sections)
    shown = [finding_out(f, locator) for f in run.findings if f.status != "unresolved"] if run.stage == "complete" else []
    return RunOut(
        id=run.id,
        question=run.question,
        shared=run.workspace_id is None,
        stage=run.stage,
        findings=shown,
        withheld=[finding_out(f, locator) for f in run.findings if f.status == "unresolved"],
        model=run.model,
        prompt_version=run.prompt_version,
        prompt_hash=run.prompt_hash,
        latency_ms=run.latency_ms,
        note=run.note,
        error=run.error,
        reason=run.reason,
        has_guidance=run.guidance_id is not None,
        review_head=review_head(run),
        guidance_text=run.guidance.text if run.guidance else None,
        sections_read=len(json.loads(run.candidates_json)) if run.candidates_json else None,
        retrieval_mode=run.retrieval_mode,
        sections_requested=json.loads(run.options_json or "{}").get("retrieval_k"),
    )


def run_detail(run: Run) -> RunDetail:
    locator = ClauseLocator(run.document.sections)
    base = run_out(run, locator).model_dump(by_alias=False)
    base["findings"] = [finding_out(f, locator) for f in run.findings]
    spans = [s for f in run.findings for s in f.spans]
    return RunDetail(
        **base,
        document_id=run.document_id,
        guidance_id=run.guidance_id,
        provider=run.provider,
        options=json.loads(run.options_json or "{}"),
        document_name=run.document.name,
        document_parse_ms=run.document.parse_ms,
        task=run.task,
        routing_reason=run.routing_reason,
        verified_spans=sum(1 for s in spans if s.verified),
        total_spans=len(spans),
        document_sha256=run.document_sha256,
        guidance_sha256=run.guidance_sha256,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        candidates=[CandidateOut(**c) for c in json.loads(run.candidates_json or "[]")],
        raw_output=run.raw_output,
        stages=[
            StageOut(
                stage=s.stage,
                at=iso(s.at) or "",
                detail=s.detail,
                completed_at=iso(s.completed_at),
                duration_ms=s.duration_ms,
                status=s.status,
                attempt=s.attempt,
                input_hash=s.input_hash,
                output_hash=s.output_hash,
                error_code=s.error_code,
            )
            for s in run.stages
        ],
        created_at=iso(run.created_at) or "",
        finished_at=iso(run.finished_at),
    )


def run_summary(run: Run) -> RunSummary:
    shown = [f for f in run.findings if f.status != "unresolved"] if run.stage == "complete" else []
    return RunSummary(
        id=run.id,
        question=run.question,
        shared=run.workspace_id is None,
        stage=run.stage,
        model=run.model,
        prompt_version=run.prompt_version,
        prompt_hash=run.prompt_hash,
        latency_ms=run.latency_ms,
        reason=run.reason,
        findings=len(shown),
        has_guidance=run.guidance_id is not None,
        document_id=run.document_id,
        document_name=run.document.name,
        created_at=iso(run.created_at) or "",
    )


# ------------------------------------------------------------------------------ routes


# Runs execute on their own threads, not the request threadpool: a run holds its thread through the admission
# queue and up to four model calls, and forty of them starved every other route (hostile review, 2026-10-01).
RUN_EXECUTOR = ThreadPoolExecutor(max_workers=64, thread_name_prefix="run")


def _worker(run_id: str, provider: ModelProvider) -> None:
    with SessionLocal() as session:
        execute_run(session, run_id, provider_for(session.get(Run, run_id), provider))


async def _run_on_own_thread(run_id: str, provider: ModelProvider) -> None:
    await asyncio.get_running_loop().run_in_executor(RUN_EXECUTOR, _worker, run_id, provider)


def provider_for(run: Run | None, default: ModelProvider) -> ModelProvider:
    """The default provider when the run's model is its model; otherwise one for the run's model. Tests keep their fake."""
    if run is None or run.model == default.model or default.name != "ollama":
        return default
    return make_provider(default.name, run.model, workload=getattr(default, "workload", "interactive"))


@router.post("", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    body: RunIn,
    response: Response,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    provider: ModelProvider = Depends(get_provider),
    workspace: str = Depends(current_workspace),
) -> RunOut:
    """202 with a new run, or 200 with this workspace's running or completed run that already has these inputs."""
    started = start_run(session, body.document_id, body.guidance_id, body.question, provider, workspace=workspace)
    if started.created:
        background.add_task(_run_on_own_thread, started.run.id, provider)
    else:
        response.status_code = status.HTTP_200_OK
    out = run_out(started.run)
    out.reused = not started.created
    # The request's session lives until the background task ends (FastAPI closes yield-dependencies after
    # the response, and Starlette runs background tasks inside the response). Reading the run after the
    # commit began a new transaction, and that transaction pinned a pool connection for the whole run:
    # at twenty concurrent starts the pool of fifteen ran dry (docs/SCALE.md). Ending it here frees the connection.
    session.commit()
    return out


@router.get("", response_model=list[RunSummary])
def list_runs(session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> list[RunSummary]:
    """This workspace's runs and the curated ones, newest first, the latest 200."""
    recover_interrupted_runs(session)
    runs = session.query(Run).filter(visible_runs(workspace)).order_by(Run.created_at.desc()).limit(200).all()
    return [run_summary(r) for r in runs]


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> RunOut:
    recover_interrupted_runs(session)
    return run_out(require_run(session, run_id, workspace))


@router.get("/{run_id}/detail", response_model=RunDetail)
def get_run_detail(run_id: str, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> RunDetail:
    recover_interrupted_runs(session)
    return run_detail(require_run(session, run_id, workspace))


@router.get("/{run_id}/explanation", response_model=RunExplanation)
def get_run_explanation(run_id: str, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> RunExplanation:
    """Why this answer: what was read, what retrieval chose, the exact model input, the model's proposal, each
    SourceMatch and the recorded policy evaluation, all from the record. Read-only; nothing is recomputed as fact."""
    recover_interrupted_runs(session)
    require_run(session, run_id, workspace)
    return explain_run(session, run_id)


@router.get("/{run_id}/evidence-pack")
def evidence_pack(run_id: str, session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> Response:
    """A zip with the original bytes, the canonical sections, the run record, every located span and a stdlib verify.py."""
    require_run(session, run_id, workspace)
    pack = build_evidence_pack(session, run_id)
    return Response(content=pack.data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{pack.filename}"'})


def _sse(event: str, data: dict[str, object], event_id: int | None = None) -> str:
    # A stored stage row carries its id, so a client that reconnects sends it back as Last-Event-ID and is
    # replayed only what it has not seen. Live bus events carry no id; the record is the sequence.
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n"


def _ended_in_the_record(run_id: str) -> str | None:
    """The terminal stage of a run that another writer ended: a batch runner or staleness recovery in another
    process, whose events never reach this process's bus. Read at every heartbeat so no stream outlives its run
    (found while tracing, 2026-09-29)."""
    with SessionLocal() as session:
        run = session.get(Run, run_id)
    return run.stage if run is not None and run.stage in TERMINAL else None


@router.get("/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    """Stage transitions only. Replays what already happened, then streams until the run ends, by this process's
    bus or, at the latest, one heartbeat after the record says it ended."""

    after_text = request.headers.get("last-event-id") or request.query_params.get("after")
    after = int(after_text) if after_text and after_text.isdigit() else None
    workspace = current_workspace(request)
    # Authorised before anything is subscribed to: a run another workspace may not read answers as one that does not exist.
    with SessionLocal() as session:
        require_run(session, run_id, workspace)

    async def stream() -> AsyncIterator[str]:
        queue = bus.subscribe(run_id)
        try:
            with SessionLocal() as session:
                run = session.get(Run, run_id)
                if run is None:
                    yield _sse("error", {"detail": "run not found"})
                    return
                for row in run.stages:
                    if after is not None and row.id <= after:
                        continue
                    yield _sse("stage", {"runId": run_id, "stage": row.stage, "detail": row.detail}, event_id=row.id)
                if run.stage in TERMINAL:
                    yield _sse("stage", {"runId": run_id, "stage": run.stage, "final": True})
                    return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    ended = _ended_in_the_record(run_id)
                    if ended is not None:
                        yield _sse("stage", {"runId": run_id, "stage": ended, "final": True})
                        return
                    yield ": keep-alive\n\n"
                    continue
                final = event.stage in TERMINAL
                yield _sse("stage", {"runId": run_id, "stage": event.stage, "detail": event.detail, "final": final})
                if final:
                    return
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
