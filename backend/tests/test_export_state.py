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


def build_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **options: str) -> dict[str, str]:
    """The environment `next build` would run under for these options; nothing is built."""
    seen: dict[str, str] = {}

    def run(command: list[str], cwd: Path, env: dict[str, str], check: bool) -> None:
        seen.update(env)
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")

    monkeypatch.setattr(export_state.shutil, "which", lambda name: "npm")
    monkeypatch.setattr(export_state.subprocess, "run", run)
    monkeypatch.setattr(export_state, "verity_commit", lambda: None)
    export_state.build(tmp_path, **options)
    return seen


def test_the_mirror_carries_break_only_with_the_live_workbench_address(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A value left in the shell must not decide what the artifact holds.
    monkeypatch.setenv("NEXT_PUBLIC_WORKBENCH_URL", "https://left-over.example.com")
    monkeypatch.setenv("NEXT_PUBLIC_HOSTING", "cloud")
    alone = build_environment(monkeypatch, tmp_path / "alone")
    assert alone["NEXT_PUBLIC_EXPORT"] == "state"
    assert "NEXT_PUBLIC_WORKBENCH_URL" not in alone and "NEXT_PUBLIC_HOSTING" not in alone
    linked = build_environment(monkeypatch, tmp_path / "linked", workbench_url="https://verity.example.com/", hosting="cloud")
    assert linked["NEXT_PUBLIC_WORKBENCH_URL"] == "https://verity.example.com"
    assert linked["NEXT_PUBLIC_HOSTING"] == "cloud"
    laptop = build_environment(monkeypatch, tmp_path / "laptop", workbench_url="https://verity.example.com")
    assert "NEXT_PUBLIC_HOSTING" not in laptop


@pytest.mark.parametrize("url", ["http://verity.example.com", "verity.example.com", "https://verity.example.com/break", "https://verity.example.com/?x=1", "https://"])
def test_a_workbench_address_is_an_https_origin_and_nothing_else(url: str) -> None:
    with pytest.raises(export_state.ExportError, match="https origin"):
        export_state.workbench_address(url)


def test_control_a_workbench_address_needs_the_build(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        export_state.main(["--workbench-url", "https://verity.example.com"])
    assert stopped.value.code == 2 and "needs --build" in capsys.readouterr().err
