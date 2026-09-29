from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..application.evidence_pack import build_evidence_pack
from ..application.recover_runs import recover_interrupted_runs
from ..application.start_run import start_run
from ..db import SessionLocal, get_session
from ..errors import NotFound
from ..models import Finding, Run, iso
from ..providers import make_provider
from ..providers.base import ModelProvider
from ..runs.events import TERMINAL, bus
from ..runs.service import execute_run
from ..schemas import CandidateOut, FindingOut, RunDetail, RunIn, RunOut, RunSummary, SpanOut, StageOut
from .deps import get_provider
from .findings import review_out

router = APIRouter(prefix="/api/runs", tags=["runs"])
HEARTBEAT_SECONDS = 15


# ----------------------------------------------------------------------------- mapping


def finding_out(finding: Finding) -> FindingOut:
    return FindingOut(
        id=finding.id,
        topic=finding.topic,
        status=finding.status,
        status_source=finding.status_source,
        evidence_kind="coverage" if finding.status == "missing" else "passage",
        review=review_out(finding.review),
        conclusion=finding.conclusion,
        spans=[
            SpanOut(
                section_id=s.section_id,
                start=s.start,
                end=s.end,
                quote=s.quote,
                verified=s.verified,
                method=s.method,
                cited_section_label=s.cited_section_label,
            )
            for s in finding.spans
        ],
        guidance_reference=finding.guidance_reference,
        observed=finding.observed,
        required=finding.required,
        suggested_position=finding.suggested_position,
    )


def run_out(run: Run) -> RunOut:
    # Unresolved findings are kept on the run but not shown as answers.
    shown = [finding_out(f) for f in run.findings if f.status != "unresolved"] if run.stage == "complete" else []
    return RunOut(
        id=run.id,
        question=run.question,
        stage=run.stage,
        findings=shown,
        withheld=[finding_out(f) for f in run.findings if f.status == "unresolved"],
        model=run.model,
        prompt_version=run.prompt_version,
        prompt_hash=run.prompt_hash,
        latency_ms=run.latency_ms,
        note=run.note,
        error=run.error,
        reason=run.reason,
    )


def run_detail(run: Run) -> RunDetail:
    base = run_out(run).model_dump(by_alias=False)
    base["findings"] = [finding_out(f) for f in run.findings]
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


def _worker(run_id: str, provider: ModelProvider) -> None:
    with SessionLocal() as session:
        execute_run(session, run_id, provider_for(session.get(Run, run_id), provider))


def provider_for(run: Run | None, default: ModelProvider) -> ModelProvider:
    """The default provider when the run's model is its model; otherwise one for the run's model. Tests keep their fake."""
    if run is None or run.model == default.model or default.name != "ollama":
        return default
    return make_provider(default.name, run.model)


@router.post("", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    body: RunIn, response: Response, background: BackgroundTasks, session: Session = Depends(get_session), provider: ModelProvider = Depends(get_provider)
) -> RunOut:
    """202 with a new run, or 200 with the running or completed run that already has these inputs."""
    started = start_run(session, body.document_id, body.guidance_id, body.question, provider)
    if started.created:
        background.add_task(_worker, started.run.id, provider)
    else:
        response.status_code = status.HTTP_200_OK
    out = run_out(started.run)
    out.reused = not started.created
    return out


@router.get("", response_model=list[RunSummary])
def list_runs(session: Session = Depends(get_session)) -> list[RunSummary]:
    recover_interrupted_runs(session)
    runs = session.query(Run).order_by(Run.created_at.desc()).limit(200).all()
    return [run_summary(r) for r in runs]


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunOut:
    recover_interrupted_runs(session)
    run = session.get(Run, run_id)
    if run is None:
        raise NotFound("run", run_id)
    return run_out(run)


@router.get("/{run_id}/detail", response_model=RunDetail)
def get_run_detail(run_id: str, session: Session = Depends(get_session)) -> RunDetail:
    recover_interrupted_runs(session)
    run = session.get(Run, run_id)
    if run is None:
        raise NotFound("run", run_id)
    return run_detail(run)


@router.get("/{run_id}/evidence-pack")
def evidence_pack(run_id: str, session: Session = Depends(get_session)) -> Response:
    """A zip with the original bytes, the canonical sections, the run record, every located span and a stdlib verify.py."""
    pack = build_evidence_pack(session, run_id)
    return Response(content=pack.data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{pack.filename}"'})


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """Stage transitions only. Replays what already happened, then streams until the run ends."""

    async def stream() -> AsyncIterator[str]:
        queue = bus.subscribe(run_id)
        try:
            with SessionLocal() as session:
                run = session.get(Run, run_id)
                if run is None:
                    yield _sse("error", {"detail": "run not found"})
                    return
                for row in run.stages:
                    yield _sse("stage", {"runId": run_id, "stage": row.stage, "detail": row.detail})
                if run.stage in TERMINAL:
                    yield _sse("stage", {"runId": run_id, "stage": run.stage, "final": True})
                    return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                final = event.stage in TERMINAL
                yield _sse("stage", {"runId": run_id, "stage": event.stage, "detail": event.detail, "final": final})
                if final:
                    return
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
