"""A document's type is the type its bytes were checked as, recorded as its media type; its name is only what a person
reads. Found by the QA campaign of 2026-10-08: a 269-character name ending ".txt" was cut to 255 characters, through the
extension. The stored bytes, the reading again (coverage, trust) and the evidence pack all took their type from the name,
and the documents list showed the whole name as the file-type badge.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app import db as db_module
from app.application.ingest_document import coverage_of, original_path, reading_name
from app.application.trust_run import _read_again
from app.ingest import MAX_NAME, PARSER_VERSION, base_name
from app.models import Document
from tests.support import CONTRACT

TEXT = b"1. Term\n\nThe term is two years.\n\n2. Fees\n\nFees are due monthly.\n"
STEM = st.text(alphabet=st.sampled_from(list("abcdefghij-_ 0123456789.")), min_size=1, max_size=400)


@settings(max_examples=300, deadline=None)
@given(stem=STEM, suffix=st.sampled_from([".pdf", ".docx", ".txt", ".PDF", ".Txt"]))
def test_a_stored_name_keeps_a_supported_extension_whatever_its_length(stem: str, suffix: str) -> None:
    name = base_name(f"x{stem}{suffix}")
    assert name.endswith(suffix) and len(name) <= MAX_NAME


def test_controls_a_short_name_is_unchanged_and_other_endings_are_cut_as_before() -> None:
    assert base_name("Master Services Agreement.pdf") == "Master Services Agreement.pdf"
    assert base_name("a" * 300) == "a" * MAX_NAME  # no extension: nothing to keep
    assert base_name("a" * 300 + ".exe") == "a" * MAX_NAME  # not a supported type: only part of the name
    assert base_name("." + "a" * 300) == "." + "a" * (MAX_NAME - 1)  # a dot with no stem is not an extension


def test_a_long_name_is_stored_with_its_type_and_its_bytes_under_it(client: TestClient) -> None:
    name = "Master-Services-Agreement-" + "between-the-parties-" * 14 + "final.txt"
    assert len(name) > MAX_NAME
    stored = client.post("/api/documents", files={"file": (name, TEXT, "text/plain")}).json()
    assert stored["name"].endswith(".txt") and len(stored["name"]) == MAX_NAME
    with db_module.SessionLocal() as session:
        document = session.get(Document, stored["id"])
        assert document is not None
        assert original_path(document).name.endswith(".txt") and original_path(document).is_file()
    listed = next(d for d in client.get("/api/documents").json() if d["id"] == stored["id"])
    assert listed["fileType"] == "txt"


def legacy(client: TestClient, cut_name: str) -> tuple[str, str]:
    """A document as one stored before the fix: its name cut through the extension, its bytes where that name put them.
    Made so before its run, since a document a finished run has read is immutable; then a run reads it."""
    document_id = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()["id"]
    with db_module.SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        kept = original_path(document)
        document.name = cut_name
        document.coverage_json = None  # an early reading, so the coverage is reconstructed from the bytes
        session.commit()
        kept.rename(kept.with_name(f"{document.sha256}{Path(cut_name).suffix.lower()}"))
    started = client.post("/api/runs", json={"documentId": document_id, "question": "What notice period applies to termination for convenience?"})
    assert started.status_code == 202, started.text
    return document_id, started.json()["id"]


@pytest.mark.parametrize(
    "cut_name",
    ["Master-Services-Agreement-" + "x" * 229, "Master-Services-Agreement-" + "x" * 216 + ".final-signed"],
    ids=["no-extension", "a-fragment-for-an-extension"],
)
def test_a_document_stored_under_a_cut_name_is_still_read_as_its_type(client: TestClient, cut_name: str) -> None:
    document_id, run_id = legacy(client, cut_name)
    with db_module.SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        original = original_path(document)
        assert original.is_file(), "the bytes kept under the cut name are found"
        assert coverage_of(document) is not None, "the coverage is reconstructed, not reported as unreadable"
        assert _read_again(original, reading_name(document), PARSER_VERSION) is not None
        # Control: the old way, by the cut name, reports readable bytes as unreadable.
        assert _read_again(original, document.name, PARSER_VERSION) is None
    pack = zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/evidence-pack").content))
    originals = [n for n in pack.namelist() if n.startswith("document/")]
    assert len(originals) == 1 and originals[0].endswith(".txt")
    listed = next(d for d in client.get("/api/documents").json() if d["id"] == document_id)
    assert listed["fileType"] == "txt" and listed["name"] == cut_name


def test_control_a_document_with_an_ordinary_name_is_where_it_always_was(client: TestClient) -> None:
    stored = client.post("/api/documents", files={"file": ("terms.txt", TEXT, "text/plain")}).json()
    with db_module.SessionLocal() as session:
        document = session.get(Document, stored["id"])
        assert document is not None
        assert original_path(document).name == f"{document.sha256}.txt" and reading_name(document) == "terms.txt"
