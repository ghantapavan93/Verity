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
    ContractStateOut,
    ExperimentPage,
    ExperimentRecord,
    ExperimentsOut,
    FamiliesOut,
    GoldensOut,
    StateArrival,
    StatePortfolio,
    StateSummary,
)
from .access import current_workspace, owner_only

router = APIRouter(prefix="/api/engineering", tags=["engineering"])
# The recorded contract-state experiment, as the public research page shows it: no reader's data, so no session.
public_router = APIRouter(prefix="/api/engineering", tags=["engineering"])

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


# The contract-state record: a recording of measured arrivals the contract-state experiment exports (it supersedes
# the lineage-arrivals record). The sibling checkout on a development machine; WORKBENCH_CONTRACT_STATE overrides it.
# Read as a file: none of the experiment's code runs here, and nothing in the record is recomputed.
DEFAULT_CONTRACT_STATE = BACKEND_DIR.parents[1] / "ivo-experiments" / "experiments" / "contract-lineage" / "results" / "contract-state.json"
CONTRACT_STATE_SCHEMA = "contract-state/2"


def contract_state_path() -> Path:
    return settings.contract_state or DEFAULT_CONTRACT_STATE


def load_contract_state(path: Path) -> ContractStateOut:
    if not path.exists():
        return ContractStateOut(
            available=False,
            source=path.name,
            detail="contract-state.json not found; export it with `python -m evals.export_state` in the contract-lineage experiment",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return ContractStateOut(available=False, source=path.name, detail=f"contract-state.json unreadable: {type(error).__name__}")
    if not isinstance(data, dict) or data.get("schema") != CONTRACT_STATE_SCHEMA:
        return ContractStateOut(available=False, source=path.name, detail=f"the file is not a {CONTRACT_STATE_SCHEMA} record")
    # The record carries the sha256 of its own body (sorted keys, UTF-8); a copy matches, an edit does not.
    body = {key: value for key, value in data.items() if key != "sha256"}
    digest = sha256_text(json.dumps(body, sort_keys=True, ensure_ascii=False))
    try:
        portfolio = StatePortfolio(**data["portfolio"])
        summary = StateSummary(**data["summary"])
        arrivals = [StateArrival(**row) for row in data.get("arrivals") or []]
    except (ValidationError, KeyError, TypeError) as error:
        return ContractStateOut(available=False, source=path.name, detail=f"the record does not fit {CONTRACT_STATE_SCHEMA}: {type(error).__name__}")
    return ContractStateOut(
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
        evidence=data.get("evidence") or {},
        arrivals=arrivals,
    )


# The record is served without a session; a reload must not re-read and re-check ~200 KB each time. Keyed by the
# file's identity, so an edited or replaced file is read (and hash-checked) again.
_contract_state_cache: dict[tuple[str, int, int], ContractStateOut] = {}


@public_router.get("/contract-state", response_model=ContractStateOut)
def contract_state() -> ContractStateOut:
    path = contract_state_path()
    try:
        stat = path.stat()
    except OSError:
        return load_contract_state(path)
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _contract_state_cache.get(key)
    if cached is None:
        cached = load_contract_state(path)
        _contract_state_cache.clear()
        _contract_state_cache[key] = cached
    return cached


@router.get("/citations", response_model=CitationRecordOut)
def citations(session: Session = Depends(get_session), workspace: str = Depends(current_workspace)) -> CitationRecordOut:
    """How often the model's quotes were found, by which method, and how often a finding was withheld, over the runs
    this workspace may read: its own and the curated record."""
    return citation_record(session, workspace)


@router.get("/families", response_model=FamiliesOut, dependencies=[Depends(owner_only)])
def families(threshold: float = Query(default=DEFAULT_THRESHOLD, ge=0.0, le=1.0), session: Session = Depends(get_session)) -> FamiliesOut:
    """Structural families among the labeled corpus documents at a threshold, with the evaluation against the labels."""
    return families_report(session, threshold)


@router.get("/goldens", response_model=GoldensOut, dependencies=[Depends(owner_only)])
def goldens(session: Session = Depends(get_session)) -> GoldensOut:
    """The golden set with each golden's run and verdict per prompt version, and the latest comparison."""
    return report(session)
