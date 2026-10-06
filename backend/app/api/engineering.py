"""Engineering records that are not runs: the golden set judged against recorded runs, and the
pre-registered experiments that preceded this product. The experiments are read from the
results.json the ivo-experiments repository builds from its own committed files; nothing here
is retyped."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..application.citation_record import citation_record
from ..config import BACKEND_DIR, settings
from ..db import get_session
from ..families.service import DEFAULT_THRESHOLD
from ..families.service import report as families_report
from ..goldens.service import report
from ..hashing import sha256_text
from ..schemas import (
    CitationRecordOut,
    ExperimentPage,
    ExperimentRecord,
    ExperimentsOut,
    FamiliesOut,
    GoldensOut,
    LineageArrival,
    LineageOut,
    LineagePortfolio,
    LineageSummary,
)
from .access import current_workspace

router = APIRouter(prefix="/api/engineering", tags=["engineering"])

# The sibling checkout on a development machine; WORKBENCH_EXPERIMENTS_RESULTS overrides it.
DEFAULT_RESULTS = BACKEND_DIR.parents[1] / "ivo-experiments" / "docs" / "results.json"


def results_path() -> Path:
    return settings.experiments_results or DEFAULT_RESULTS


def _record(row: dict[str, object]) -> ExperimentRecord:
    return ExperimentRecord(
        id=str(row.get("id", "")),
        code=str(row.get("code", "")),
        title=str(row.get("title", "")),
        date=str(row.get("date", "")),
        expected=str(row.get("expected", "")),
        gate=str(row.get("gate", "")),
        observed=str(row.get("observed", "")),
    )


def load_experiments(path: Path) -> ExperimentsOut:
    if not path.exists():
        return ExperimentsOut(
            available=False, source=path.name, detail="results.json not found; build it with `python -m results_page.build` in ivo-experiments"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return ExperimentsOut(available=False, source=path.name, detail=f"results.json unreadable: {type(error).__name__}")
    board = data.get("board")
    if not isinstance(board, list) or not board:
        return ExperimentsOut(available=False, source=path.name, detail="results.json has no board; rebuild it with the current results_page")
    page = data.get("page") or {}
    return ExperimentsOut(
        available=True,
        source=path.name,
        page_url=settings.experiments_url or page.get("repo_url") or None,
        page=ExperimentPage(**{k: page.get(k) for k in ("title", "subtitle", "author", "period", "repo_url", "branch")}),
        repo_head=data.get("repo_head"),
        generated_at=data.get("generated_at"),
        board=[_record(r) for r in board],
        baselines=[_record(r) for r in data.get("baselines") or []],
    )


@router.get("/experiments", response_model=ExperimentsOut)
def experiments() -> ExperimentsOut:
    return load_experiments(results_path())


# The lineage record: a recording of measured arrivals the contract-lineage experiment exports. The sibling checkout
# on a development machine; WORKBENCH_LINEAGE_ARRIVALS overrides it. Read as a file: none of the experiment's code
# runs here, and nothing in the record is recomputed.
DEFAULT_ARRIVALS = BACKEND_DIR.parents[1] / "ivo-experiments" / "experiments" / "contract-lineage" / "results" / "lineage-arrivals.json"
LINEAGE_SCHEMA = "lineage-arrivals/1"


def arrivals_path() -> Path:
    return settings.lineage_arrivals or DEFAULT_ARRIVALS


def load_lineage(path: Path) -> LineageOut:
    if not path.exists():
        return LineageOut(
            available=False,
            source=path.name,
            detail="lineage-arrivals.json not found; export it with `python -m evals.export_arrivals` in the contract-lineage experiment",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return LineageOut(available=False, source=path.name, detail=f"lineage-arrivals.json unreadable: {type(error).__name__}")
    if not isinstance(data, dict) or data.get("schema") != LINEAGE_SCHEMA:
        return LineageOut(available=False, source=path.name, detail=f"the file is not a {LINEAGE_SCHEMA} record")
    # The record carries the sha256 of its own body (sorted keys, UTF-8); a copy matches, an edit does not.
    body = {key: value for key, value in data.items() if key != "sha256"}
    digest = sha256_text(json.dumps(body, sort_keys=True, ensure_ascii=False))
    try:
        portfolio = LineagePortfolio(**data["portfolio"])
        summary = LineageSummary(**data["summary"])
        arrivals = [LineageArrival(**row) for row in data.get("arrivals") or []]
    except (ValidationError, KeyError, TypeError) as error:
        return LineageOut(available=False, source=path.name, detail=f"the record does not fit {LINEAGE_SCHEMA}: {type(error).__name__}")
    return LineageOut(
        available=True,
        source=path.name,
        schema_version=str(data.get("schema")),
        source_commit=str(data["source_commit"]) if data.get("source_commit") else None,
        generated_at=str(data["generated_at"]) if data.get("generated_at") else None,
        sha256=str(data["sha256"]) if data.get("sha256") else None,
        sha256_verified=digest == data.get("sha256"),
        what_this_is=str(data["what_this_is"]) if data.get("what_this_is") else None,
        portfolio=portfolio,
        summary=summary,
        candidate_generation_held_out=data.get("candidate_generation_held_out") or {},
        adjudication_held_out=data.get("adjudication_held_out") or {},
        arrivals=arrivals,
    )


@router.get("/lineage", response_model=LineageOut)
def lineage() -> LineageOut:
    return load_lineage(arrivals_path())


@router.get("/citations", response_model=CitationRecordOut)
def citations(session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> CitationRecordOut:
    """How often the model's quotes were found, by which method, and how often a finding was withheld, over the runs
    this workspace may read: its own and the curated record."""
    return citation_record(session, workspace)


@router.get("/families", response_model=FamiliesOut)
def families(threshold: float = Query(default=DEFAULT_THRESHOLD, ge=0.0, le=1.0), session: Session = Depends(get_session)) -> FamiliesOut:
    """Structural families among the labeled corpus documents at a threshold, with the evaluation against the labels."""
    return families_report(session, threshold)


@router.get("/goldens", response_model=GoldensOut)
def goldens(session: Session = Depends(get_session)) -> GoldensOut:
    """The golden set with each golden's run and verdict per prompt version, and the latest comparison."""
    return report(session)
