"""A document is a row and its original bytes, and the row must not exist without them.

The row used to be committed before the bytes were written. Fault injection on 2026-10-02 failed the write: the row
stayed, the upload was a 500, and every retry was handed the row "already stored" without the write being tried
again, so the run's evidence pack had no original document in it. The bytes now go to disk first, and an upload of
bytes whose row has no file completes it.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.application.evidence_pack import pack_name
from app.config import settings
from app.db import SessionLocal
from app.hashing import sha256_bytes
from app.models import Document

from .support import CONTRACT, GUIDANCE, upload_and_ask

BYTES = CONTRACT.encode("utf-8")


def _originals() -> list[str]:
    folder = settings.data_dir / "documents"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def _upload(client: TestClient, name: str = "agreement.txt") -> int:
    return int(client.post("/api/documents", files={"file": (name, BYTES, "text/plain")}).status_code)


def test_a_write_that_fails_leaves_no_document_and_the_retry_is_whole(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    real_write = Path.write_bytes
    armed = {"on": True}

    def failing_write(self: Path, data: bytes) -> int:
        if armed["on"] and "documents" in self.parts:
            armed["on"] = False
            raise OSError("injected: no space left on device")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write)
    with pytest.raises(OSError, match="injected"):
        _upload(client)
    with SessionLocal() as session:
        assert session.query(Document).count() == 0, "no row was written for bytes that never reached the disk"
    assert _originals() == [], "no partial file is left under the hash's name"

    assert _upload(client) == 201
    assert _originals() == [f"{sha256_bytes(BYTES)}.txt"]


def test_an_upload_of_bytes_whose_row_has_no_file_puts_the_file_back(client: TestClient) -> None:
    assert _upload(client) == 201
    original = settings.data_dir / "documents" / f"{sha256_bytes(BYTES)}.txt"
    original.unlink()  # a row left without its bytes, as the old order could leave it
    assert _upload(client) == 200, "the same bytes are the same document"
    assert original.read_bytes() == BYTES


def test_the_pack_names_its_document_so_that_any_system_can_unpack_it(client: TestClient, tmp_path: Path) -> None:
    assert pack_name('<img src=x onerror=alert(1)>:"|?*.txt') == "_img src=x onerror=alert(1)______.txt"
    hostile = "<img src=x onerror=alert(1)>:|?*.txt"  # as uploaded: a multipart header cannot carry the quotation mark as written
    assert pack_name(hostile) == "_img src=x onerror=alert(1)_____.txt"
    assert pack_name("CON.txt") == "_CON.txt" and pack_name("report. ") == "report" and pack_name("../../x.txt") == "x.txt"

    uploaded = client.post("/api/documents", files={"file": (hostile, BYTES, "text/plain")})
    assert uploaded.status_code == 201 and uploaded.json()["name"] == hostile, "the record keeps the name as given"
    guidance = client.post("/api/guidance", json={"text": GUIDANCE}).json()["id"]
    started = client.post(
        "/api/runs", json={"documentId": uploaded.json()["id"], "guidanceId": guidance, "question": "How much notice to terminate for convenience?"}
    )
    pack = client.get(f"/api/runs/{started.json()['id']}/evidence-pack")
    folder = tmp_path / "pack"
    with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
        assert "document/_img src=x onerror=alert(1)_____.txt" in archive.namelist()
        archive.extractall(folder)  # raised OSError on Windows before
    record = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert record["document"]["name"] == hostile and (folder / record["document"]["file"]).read_bytes() == BYTES
    verified = subprocess.run([sys.executable, str(folder / "verify.py")], capture_output=True, text=True, check=False, cwd=folder)
    assert verified.returncode == 0, verified.stdout + verified.stderr


def test_a_pack_whose_guidance_was_edited_fails_on_the_guidance_hash(client: TestClient, tmp_path: Path) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    folder = tmp_path / "pack"
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{result['run_id']}/evidence-pack").content)) as archive:
        archive.extractall(folder)
    clean = subprocess.run([sys.executable, str(folder / "verify.py")], capture_output=True, text=True, check=False, cwd=folder)
    assert clean.returncode == 0 and "PASS guidance: sha256" in clean.stdout
    guidance = folder / "guidance.txt"
    guidance.write_text(guidance.read_text(encoding="utf-8").replace("30", "3"), encoding="utf-8")
    tampered = subprocess.run([sys.executable, str(folder / "verify.py")], capture_output=True, text=True, check=False, cwd=folder)
    assert tampered.returncode == 1 and "FAIL guidance: sha256" in tampered.stdout
