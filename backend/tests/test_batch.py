"""A batch is the same run over a corpus: one run per document and field, bounded concurrency,
reuse of what exists, and a report computed from the run records."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db as db_module
from app.batch.service import load_task, report, run_batch
from tests.support import CONTRACT


def write_corpus(directory: Path) -> Path:
    directory.mkdir()
    (directory / "alpha.txt").write_text(CONTRACT, encoding="utf-8")
    (directory / "beta.txt").write_text(CONTRACT.replace("State of Delaware", "State of New York"), encoding="utf-8")
    (directory / "notes.md").write_text("not a contract", encoding="utf-8")  # ignored: not a supported type
    return directory


def test_the_task_file_is_well_formed() -> None:
    task = load_task("core-fields")
    assert [f.key for f in task.fields] == ["governing_law", "termination", "liability_cap"]
    assert len(task.sha256) == 64


def test_a_batch_runs_every_document_and_field_once_and_reuses_on_repeat(client: TestClient, tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path / "corpus")
    provider = client.provider
    first_id = run_batch(db_module.SessionLocal, provider, [corpus], "core-fields", corpus_label="two-contracts", concurrency=2)
    with db_module.SessionLocal() as session:
        first = report(session, first_id)
    assert (first.documents, first.requested, first.runs_created, first.runs_reused) == (2, 6, 6, 0)
    assert first.answered == 6 and first.verified_spans == 6 and first.withheld_findings == 0
    assert first.finished_at and first.documents_per_minute and first.model_latency_p50_ms is not None
    assert [row.document_name for row in first.rows] == ["alpha.txt", "beta.txt"]
    value = first.rows[0].values["termination"]
    assert value.outcome == "answered" and value.citation == "§2" and value.method == "exact" and value.status == "pass"

    second_id = run_batch(db_module.SessionLocal, provider, [corpus], "core-fields", corpus_label="two-contracts", concurrency=1)
    with db_module.SessionLocal() as session:
        second = report(session, second_id)
    assert (second.runs_created, second.runs_reused) == (0, 6), "the same questions over the same bytes are the same runs"
    assert second.rows[1].values["liability_cap"].run_id == first.rows[1].values["liability_cap"].run_id

    listed = client.get("/api/batches").json()
    assert [b["id"] for b in listed] == [second_id, first_id]
    detail = client.get(f"/api/batches/{first_id}").json()
    assert detail["answered"] == 6 and detail["rows"][0]["values"]["governing_law"]["outcome"] == "answered"
    csv_text = client.get(f"/api/batches/{first_id}/values.csv").text
    assert csv_text.splitlines()[0] == "document,field,outcome,value,status,citation,method,run_id"
    assert len(csv_text.splitlines()) == 7
    assert client.get("/api/batches/nope").status_code == 404


def test_the_same_bytes_in_two_directories_are_one_document(client: TestClient, tmp_path: Path) -> None:
    first = write_corpus(tmp_path / "one")
    second = tmp_path / "two"
    second.mkdir()
    (second / "alpha-copy.txt").write_text(CONTRACT, encoding="utf-8")
    batch_id = run_batch(db_module.SessionLocal, client.provider, [first, second], "core-fields", concurrency=1)
    with db_module.SessionLocal() as session:
        out = report(session, batch_id)
    assert (out.documents, out.requested, out.runs_created, out.runs_reused) == (2, 6, 6, 0)
    assert [row.document_name for row in out.rows] == ["alpha.txt", "beta.txt"]


def test_cuad_matching_rule_containment_jaccard_and_a_clear_miss() -> None:
    from app.batch.cuad_match import hits, retrieved_carries

    expert = ["This Agreement shall be governed by the laws of the State of New York, without regard to its conflict of laws principles."]
    assert hits("governed by the laws of the State of New York", expert)  # contained
    assert hits("This Agreement shall be governed by the laws of the State of New York without regard to conflicts of law rules", expert)  # token overlap
    assert not hits("Either party may terminate this Agreement on thirty days' written notice.", expert)
    assert retrieved_carries("12. Law. " + expert[0] + " 13. Notices.", expert[0])
    assert not retrieved_carries("Payment is due within thirty (30) days of invoice.", expert[0])
