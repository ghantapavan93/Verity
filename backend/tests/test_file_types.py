"""A file is read as the type its bytes are; the name only claims it. The same bytes are only ever read one way, so a
document, known by its bytes and its reader, is one reading whatever name each upload carried and in whatever order.

Found by the QA campaign of 2026-10-08 (a real PDF pair from CUAD): a PDF uploaded as .txt was stored as a text
"document" of 44 sections of its own binary, and the same bytes uploaded afterwards as .pdf were handed that reading.
"""

from __future__ import annotations

import contextlib
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ingest import UnsupportedFile
from app.ingest.readers import content_type, file_type

PDF = (Path(__file__).with_name("fixtures") / "services-agreement.pdf").read_bytes()
SAMPLE_DOCX = (Path(__file__).parents[2] / "public" / "samples" / "cloud-service-agreement.docx").read_bytes()
TEXT = b"MASTER AGREEMENT\n\n1. Term\n\nThis Agreement begins on the Effective Date and continues for two years.\n"


def documents(client: TestClient) -> int:
    return len(client.get("/api/documents").json())


@pytest.mark.parametrize(
    ("data", "wrong_name", "right_name"),
    [
        (PDF, "agreement.txt", "agreement.pdf"),  # the original: a PDF named as text
        (PDF, "agreement.docx", "agreement.pdf"),
        (SAMPLE_DOCX, "agreement.txt", "agreement.docx"),
        (SAMPLE_DOCX, "agreement.pdf", "agreement.docx"),
        (TEXT, "agreement.pdf", "agreement.txt"),
        (TEXT, "agreement.docx", "agreement.txt"),
    ],
    ids=["pdf-as-txt", "pdf-as-docx", "docx-as-txt", "docx-as-pdf", "txt-as-pdf", "txt-as-docx"],
)
@pytest.mark.parametrize("wrong_first", [True, False], ids=["wrong-first", "right-first"])
def test_a_name_its_bytes_contradict_is_refused_in_either_order(client: TestClient, data: bytes, wrong_name: str, right_name: str, wrong_first: bool) -> None:
    """Whichever upload comes first, the wrongly named one is a 422 and the rightly named one is the only reading."""
    order = [(wrong_name, False), (right_name, True)] if wrong_first else [(right_name, True), (wrong_name, False)]
    readings = set()
    for name, accepted in order:
        response = client.post("/api/documents", files={"file": (name, data, "application/octet-stream")})
        if accepted:
            assert response.status_code == 201, response.text
            readings.add(response.json()["id"])
        else:
            assert response.status_code == 422, f"{name} was {response.status_code}: {response.text[:200]}"
    assert len(readings) == 1 and documents(client) == 1


def test_the_refusal_names_what_the_file_is(client: TestClient) -> None:
    detail = client.post("/api/documents", files={"file": ("agreement.txt", PDF, "text/plain")}).json()["detail"]
    assert "is a PDF, not plain text" in detail and "upload it as .pdf" in detail


def test_binary_named_as_text_is_refused_and_utf16_text_is_not(client: TestClient) -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10" + bytes(range(256)) * 4
    response = client.post("/api/documents", files={"file": ("scan.txt", png, "text/plain")})
    assert response.status_code == 422 and "binary" in response.json()["detail"]
    # Control: UTF-16 carries NUL bytes and is text; it is decoded, not refused.
    utf16 = "﻿1. Payment\n\nFees are due within thirty (30) days of invoice.\n".encode("utf-16-le")
    assert client.post("/api/documents", files={"file": ("terms.txt", utf16, "text/plain")}).status_code == 201


def test_controls_a_pdf_header_after_leading_bytes_and_text_that_talks_about_pdfs_are_read() -> None:
    # Readers accept a header anywhere in the first kilobyte; so does the type check.
    assert content_type(b"\r\n" * 100 + PDF) == ".pdf"
    assert file_type("agreement.pdf", b"\r\n" * 100 + PDF) == ".pdf"
    # A text that mentions PDFs (no signature) is text.
    assert file_type("notes.txt", b"Deliver the report as a PDF file.\n") == ".txt"
    assert file_type("x.TXT", TEXT) == ".txt"


def test_a_docx_package_is_a_zip_but_a_bare_zip_name_is_not_supported() -> None:
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("readme.txt", "hello")
    assert content_type(package.getvalue()) == ".docx"  # a zip: the .docx reader decides whether it is a package
    with pytest.raises(UnsupportedFile, match=r"unsupported file type \.zip"):
        file_type("bundle.zip", package.getvalue())


SIGNATURES = st.sampled_from([b"", b"%PDF-1.7\n", b"PK\x03\x04", b"  \n%PDF-1.4", b"plain words "])


@settings(max_examples=300, deadline=None)
@given(head=SIGNATURES, body=st.binary(max_size=200))
def test_the_same_bytes_are_accepted_under_at_most_one_type(head: bytes, body: bytes) -> None:
    """The property behind the fix: for any bytes, the claimed types that pass the check are at most one."""
    data = head + body
    accepted = set()
    for name in ("x.pdf", "x.docx", "x.txt"):
        with contextlib.suppress(UnsupportedFile):
            accepted.add(file_type(name, data))
    assert len(accepted) <= 1
