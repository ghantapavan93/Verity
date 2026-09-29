"""Batch extraction records: the runs a batch made over a corpus and the numbers they add up to.
Batches are started from the command line (scripts/run_batch.py), never from the interface."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..batch.service import list_batches, report
from ..db import get_session
from ..schemas import BatchOut, BatchSummary

router = APIRouter(prefix="/api/batches", tags=["batches"])


@router.get("", response_model=list[BatchSummary])
def batches(session: Session = Depends(get_session)) -> list[BatchSummary]:
    return list_batches(session)


@router.get("/{batch_id}", response_model=BatchOut)
def batch(batch_id: str, session: Session = Depends(get_session)) -> BatchOut:
    return report(session, batch_id)


@router.get("/{batch_id}/values.csv", response_class=PlainTextResponse)
def batch_values_csv(batch_id: str, session: Session = Depends(get_session)) -> PlainTextResponse:
    """One row per document and field: the value, its status, the citation and how it was located, and the run."""
    out = report(session, batch_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["document", "field", "outcome", "value", "status", "citation", "method", "run_id"])
    for row in out.rows:
        for field in out.fields:
            value = row.values[field.key]
            writer.writerow(
                [row.document_name, field.key, value.outcome, value.value or "", value.status or "", value.citation or "", value.method or "", value.run_id]
            )
    return PlainTextResponse(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="batch-{batch_id}-values.csv"'})
