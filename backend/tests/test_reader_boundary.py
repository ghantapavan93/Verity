"""Every file of a supported type ends as a reading or as a refusal with a reason; a parser's own failure on damaged
bytes is never a 500. The parsers fail in many shapes (pypdf: AssertionError, KeyError, TypeError, NotImplementedError,
PdfReadError, PdfStreamError, LimitReachedError; python-docx and zipfile: zlib.error), so the rule lives once, where
untrusted bytes meet them: ``readers.read``. Found by the QA campaign of 2026-10-08: 112 of 300 mutations of a real
contract PDF and 21 of 200 of a real DOCX escaped as unhandled exceptions."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf.errors import LimitReachedError

from app.ingest import UnsupportedFile, ingest, readers

PDF = (Path(__file__).with_name("fixtures") / "services-agreement.pdf").read_bytes()
DOCX = (Path(__file__).parents[2] / "public" / "samples" / "cloud-service-agreement.docx").read_bytes()


def mutations(data: bytes, count: int, seed: int) -> list[bytes]:
    """Damaged copies: bytes flipped, a slice cut out, a slice repeated. Deterministic, so a failure reproduces."""
    rng = random.Random(seed)
    out = []
    for i in range(count):
        damaged = bytearray(data)
        if i % 3 == 0:
            for _ in range(rng.randint(1, 40)):
                damaged[rng.randrange(len(damaged))] = rng.randrange(256)
        elif i % 3 == 1:
            start = rng.randrange(len(damaged))
            del damaged[start : start + rng.randint(1, 2000)]
        else:
            start = rng.randrange(len(damaged))
            damaged[start:start] = damaged[start : start + rng.randint(1, 2000)]
        out.append(bytes(damaged))
    return out


@pytest.mark.parametrize(("name", "data"), [("contract.pdf", PDF), ("contract.docx", DOCX)], ids=["pdf", "docx"])
def test_every_damaged_copy_is_read_or_refused_never_raised(name: str, data: bytes) -> None:
    outcomes = {"read": 0, "refused": 0}
    for damaged in mutations(data, 120, seed=20261008):
        try:
            ingest(name, damaged)
            outcomes["read"] += 1
        except UnsupportedFile:  # TooLargeToRead included: a damaged page count is the file's own claim
            outcomes["refused"] += 1
    assert outcomes["refused"] > 0, "the mutations must reach the parsers' failure paths for this test to mean anything"


def test_a_damaged_upload_is_a_422_with_the_reason_and_leaves_no_row(client: TestClient) -> None:
    refused = 0
    for damaged in mutations(PDF, 40, seed=7):
        response = client.post("/api/documents", files={"file": ("contract.pdf", damaged, "application/pdf")})
        # 413 is a damaged page count the file itself claims ("the PDF has 4294967 pages; the limit is 2000").
        assert response.status_code in (201, 200, 413, 422), f"{response.status_code}: {response.text[:200]}"
        if response.status_code == 422:
            refused += 1
            assert response.json()["detail"] == "the file is not a readable PDF"
    assert refused > 0
    assert all(d["sections"] > 0 for d in client.get("/api/documents").json())


def test_a_parser_limit_on_damaged_structure_is_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    """pypdf raises LimitReachedError for damaged structure too ("Invalid CID width range: 8..1."), not only for size."""

    def limited(_data: bytes) -> readers.ReadResult:
        raise LimitReachedError("Invalid CID width range: 8..1.")

    monkeypatch.setattr(readers, "read_pdf", limited)
    with pytest.raises(UnsupportedFile, match="not a readable PDF"):
        readers.read("contract.pdf", PDF)


def test_controls_an_intact_file_reads_and_a_reason_raised_by_a_reader_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    assert ingest("contract.pdf", PDF).sections
    assert ingest("contract.docx", DOCX).sections

    def encrypted(_data: bytes) -> readers.ReadResult:
        raise UnsupportedFile("the PDF is encrypted; remove the password and upload it again")

    monkeypatch.setattr(readers, "read_pdf", encrypted)
    with pytest.raises(UnsupportedFile, match="encrypted"):
        readers.read("contract.pdf", PDF)
