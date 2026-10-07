"""The data audit reads manifests and the store and adds nothing up: each set keeps its own denominator, a person's
upload is a stored reading with no provenance, and the report is the same twice."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient

from app.config import settings
from app.hashing import sha256_text
from app.ingest import PARSER_VERSION
from tests.support import CONTRACT, upload_and_ask


def load_script() -> ModuleType:
    """The audit is a script, loaded by path so that the tests exercise the file the README names."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "data_audit.py"
    spec = importlib.util.spec_from_file_location("data_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


def test_the_audit_keeps_every_denominator_apart_and_names_a_runtime_upload(client: TestClient) -> None:
    upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    script = load_script()
    store = settings.data_dir / "test.db"
    result = script.audit(store)
    assert result.store == str(store)

    named = {what: number for what, number, _ in result.denominators}
    assert named["golden questions"] == "44"
    assert named["cuad-30.json contracts"] == "30" and named["cuad-skillopt.json contracts"] == "30"
    assert named["CUAD-30 questions (one per category)"] == "7" and named["batch fields over the public corpus"] == "3"
    assert named["browser flows"] == "25" and named["hand mutants"] == "24"
    assert named["runs in the store"] == "1"

    # The test contract is a fixture by its text and, once uploaded, a stored reading; it is never counted as evaluation.
    uploaded = result.agreements[sha256_text(CONTRACT)]
    assert "fixture" in uploaded.roles and "evaluation" not in uploaded.roles
    assert uploaded.readings == [PARSER_VERSION] and uploaded.runs == 1

    # The sample is the golden document, under its licence, and never a runtime upload in a fresh store.
    sample = next(a for a in result.agreements.values() if "cloud-service-agreement.docx" in a.names)
    assert result.prefixes["cb72dad74b3af676"] == sample.sha256
    assert sample.licence == "CC BY 4.0" and "golden set" in sample.measurements and "runtime" not in sample.roles

    # CUAD contracts carry the archive's licence and are evaluation only.
    cuad = [a for a in result.agreements.values() if any(s.startswith("CUAD") for s in a.sources)]
    assert len(cuad) == 60 and all(a.roles == {"evaluation"} for a in cuad)

    text = script.render(result)
    assert text.startswith(script.START) and text.endswith(script.END)
    assert text == script.render(script.audit(store)), "the audit is deterministic"
    assert "tested on" not in text
    assert "These numbers are not added together" in text


def test_without_a_store_only_the_manifests_are_audited() -> None:
    script = load_script()
    result = script.audit(Path("nowhere") / "workbench.db")
    assert result.store is None
    assert any("no store at" in note for note in result.notes)
    assert all(not a.readings for a in result.agreements.values())
    assert {what for what, _, _ in result.denominators} >= {"golden questions", "cuad-30.json contracts", "browser flows", "hand mutants"}
