"""The public artifact shows the frozen record and nothing else: the export refuses any other bytes, and the file it
writes is exactly what the API answers for the same record, so the static page and the product read one record.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from app import config
from app.api.engineering import DEFAULT_CONTRACT_STATE


def load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "export_state.py"
    spec = importlib.util.spec_from_file_location("export_state", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


export_state = load_script()
FROZEN = config.settings.contract_state or DEFAULT_CONTRACT_STATE  # WORKBENCH_CONTRACT_STATE names the lab copy elsewhere
needs_record = pytest.mark.skipif(not FROZEN.is_file(), reason="the lab's frozen record is not beside this checkout")


def built(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir(parents=True)
    (out / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return out


def test_any_bytes_but_the_frozen_record_are_refused_and_nothing_is_written(tmp_path: Path) -> None:
    out = built(tmp_path)
    other = tmp_path / "contract-state.json"
    other.write_text('{"schema": "contract-state/2"}', encoding="utf-8")
    with pytest.raises(export_state.ExportError, match="not the frozen record"):
        export_state.export(other, out)
    assert sorted(p.name for p in out.iterdir()) == ["index.html"]


def test_control_an_export_needs_a_built_page(tmp_path: Path) -> None:
    with pytest.raises(export_state.ExportError, match="no built page"):
        export_state.export(FROZEN, tmp_path)


@needs_record
def test_the_published_file_is_what_the_api_answers_for_the_frozen_record(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = built(tmp_path)
    manifest = export_state.export(FROZEN, out)
    assert manifest["record_file_sha256"] == export_state.PINNED_RECORD_SHA256 and manifest["record_body_sha256_verified"] is True
    monkeypatch.setattr(config.settings, "contract_state", FROZEN)
    answered = client.get("/api/engineering/contract-state").json()
    assert json.loads((out / "contract-state.json").read_text(encoding="utf-8")) == answered
    tampered = tmp_path / "copy.json"
    tampered.write_bytes(FROZEN.read_bytes().replace(b'"portfolio"', b'"portfolio" ', 1))
    with pytest.raises(export_state.ExportError, match="not the frozen record"):
        export_state.export(tampered, built(tmp_path / "again"))
