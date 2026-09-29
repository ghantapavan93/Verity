"""The evidence pack checks itself: verify.py, with nothing but Python, re-hashes the document and the
sections and re-locates every quote; a tampered pack fails."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from tests.support import upload_and_ask


def run_verify(folder: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(folder / "verify.py")], capture_output=True, text=True, check=False, cwd=folder)


def test_the_pack_verifies_itself_and_a_tampered_pack_fails(client: TestClient, tmp_path: Path) -> None:
    result = upload_and_ask(client, "How much notice does the customer need to give to terminate for convenience?")
    response = client.get(f"/api/runs/{result['run_id']}/evidence-pack")
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/zip")
    folder = tmp_path / "pack"
    with zipfile.ZipFile(io.BytesIO(response.content)) as pack:
        names = set(pack.namelist())
        assert {"README.txt", "run.json", "sections.json", "findings.json", "verify.py", "document/agreement.txt"} <= names
        pack.extractall(folder)

    record = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert record["run_id"] == result["run_id"] and record["document"]["sha256"] == result["document"]["sha256"]
    assert record["verifier"]["ladder"] == ["exact", "normalized", "casefold", "alnum"]

    verified = run_verify(folder)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "PASS document bytes" in verified.stdout and "PASS canonical sections" in verified.stdout
    assert "1 located span(s) checked, 0 withheld, 0 failure(s)" in verified.stdout

    sections = json.loads((folder / "sections.json").read_text(encoding="utf-8"))
    for section in sections:
        section["text"] = section["text"].replace("fifteen (15)", "fifteen (16)")
    (folder / "sections.json").write_text(json.dumps(sections, ensure_ascii=False, indent=1), encoding="utf-8")
    tampered = run_verify(folder)
    assert tampered.returncode == 1
    assert "FAIL canonical sections" in tampered.stdout and "FAIL finding 1 span 1" in tampered.stdout


def test_a_withheld_span_is_reported_not_checked(client: TestClient, tmp_path: Path) -> None:
    client.provider.paraphrase = True
    result = upload_and_ask(client, "Can the customer terminate for convenience?")
    folder = tmp_path / "withheld"
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{result['run_id']}/evidence-pack").content)) as pack:
        pack.extractall(folder)
    verified = run_verify(folder)
    assert verified.returncode == 0
    assert "WITHHELD finding 1 span 1" in verified.stdout and "0 located span(s) checked, 1 withheld" in verified.stdout
    assert client.get("/api/runs/nope/evidence-pack").status_code == 404


def test_a_pack_whose_document_bytes_changed_fails_on_the_document_hash(client: TestClient, tmp_path: Path) -> None:
    result = upload_and_ask(client, "How much notice is required to terminate for convenience?", with_guidance=False)
    pack = client.get(f"/api/runs/{result['run_id']}/evidence-pack")
    assert pack.status_code == 200
    folder = tmp_path / "pack-doc"
    with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
        archive.extractall(folder)
    document = next(folder.glob("document/*"))
    document.write_bytes(document.read_bytes() + b" ")  # one appended byte: sections untouched, bytes changed
    tampered = run_verify(folder)
    assert tampered.returncode == 1
    assert "FAIL document bytes" in tampered.stdout and "PASS canonical sections" in tampered.stdout
