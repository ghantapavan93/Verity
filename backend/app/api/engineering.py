"""Engineering records that are not runs: the golden set judged against recorded runs, and the
pre-registered experiments that preceded this product. The experiments are read from the
results.json the ivo-experiments repository builds from its own committed files; nothing here
is retyped."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..application.citation_record import citation_record
from ..config import BACKEND_DIR, settings
from ..db import get_session
from ..families.service import DEFAULT_THRESHOLD
from ..families.service import report as families_report
from ..goldens.service import report
from ..schemas import CitationRecordOut, ExperimentPage, ExperimentRecord, ExperimentsOut, FamiliesOut, GoldensOut

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
            available=False, source=str(path), detail="results.json not found; build it with `python -m results_page.build` in ivo-experiments"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return ExperimentsOut(available=False, source=str(path), detail=f"results.json unreadable: {error}")
    board = data.get("board")
    if not isinstance(board, list) or not board:
        return ExperimentsOut(available=False, source=str(path), detail="results.json has no board; rebuild it with the current results_page")
    page = data.get("page") or {}
    return ExperimentsOut(
        available=True,
        source=str(path),
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


@router.get("/citations", response_model=CitationRecordOut)
def citations(session: Session = Depends(get_session)) -> CitationRecordOut:
    """How often the model's quotes were found, by which method, and how often a finding was withheld."""
    return citation_record(session)


@router.get("/families", response_model=FamiliesOut)
def families(threshold: float = Query(default=DEFAULT_THRESHOLD, ge=0.0, le=1.0), session: Session = Depends(get_session)) -> FamiliesOut:
    """Structural families among the labeled corpus documents at a threshold, with the evaluation against the labels."""
    return families_report(session, threshold)


@router.get("/goldens", response_model=GoldensOut)
def goldens(session: Session = Depends(get_session)) -> GoldensOut:
    """The golden set with each golden's run and verdict per prompt version, and the latest comparison."""
    return report(session)
