"""The product evidence export: what Verity writes down when a reviewed agreement is revised, and the bundle it leaves in.

The seams are the script's two functions: ``record`` (the product run in process on the two fixture versions; the
interface's own answers come back unchanged) and ``bundle`` (a record, a commit and the fixture bytes in; the bundle's
files out). The model here is a scripted one that quotes the Term clause verbatim, so what is tested is the product
around the model: verification, the trust manifest, lineage, the diff, and that a revision costs no model call.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app import config
from app import db as db_module
from app.api import access
from app.providers.base import Generation

BACKEND = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("export_review_evidence", BACKEND / "scripts" / "export_review_evidence.py")
assert spec is not None and spec.loader is not None
export = importlib.util.module_from_spec(spec)
sys.modules["export_review_evidence"] = export
spec.loader.exec_module(export)

TERM = "This Agreement commences on January 31, 2027 and continues for twelve (12) months."
LAW = "This Agreement is governed by the laws of the State of Delaware."


class Scripted:
    """A model that proposes two findings and quotes each verbatim from the section it was handed."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self) -> None:
        self.calls = 0

    def healthy(self) -> tuple[bool, str]:
        return True, "scripted"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        self.calls += 1
        findings = []
        for topic, quote in (("Term", TERM), ("Governing law", LAW)):
            label = re.search(r"\[(sec_\d+)\][^\[]*" + re.escape(quote), user, re.S)
            assert label, f"the section holding {quote!r} was not handed to the model"
            findings.append(
                {
                    "topic": topic,
                    "conclusion": f"{quote} [{label.group(1)}]",
                    "status_hint": "pass",
                    "evidence": [{"section_id": label.group(1), "quote": quote}],
                    "guidance_reference": None,
                    "observed": None,
                    "required": None,
                    "suggested_position": None,
                }
            )
        payload = {"findings": findings, "insufficient_evidence": False, "note": None}
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=1.0, model=self.model)


@pytest.fixture
def recorded(tmp_path: Path) -> tuple[dict[str, Any], Scripted]:
    # the run-start limit is per process; this test is its own reader
    access.run_starts.reset()
    access.exchanges.reset()
    provider = Scripted()
    return export.record(tmp_path, provider=provider), provider


def test_recording_leaves_the_process_as_it_found_it(tmp_path: Path) -> None:
    """The recording points the process at a scratch database and counts model calls at two seams. Afterwards the
    database, the data folder, the access settings, the shared admission controller and the provider handed in are
    what they were: a recording made in a process that goes on to serve would otherwise leave the gate off."""
    from app.providers import admission

    access.run_starts.reset()
    access.exchanges.reset()
    provider = Scripted()
    before = (
        db_module.engine,
        config.settings.data_dir,
        config.settings.access_secret,
        config.settings.access_required,
        admission.acquire,
        provider.generate_json,
    )
    snapshot = export.record(tmp_path, provider=provider)
    after = (
        db_module.engine,
        config.settings.data_dir,
        config.settings.access_secret,
        config.settings.access_required,
        admission.acquire,
        provider.generate_json,
    )
    assert after == before and db_module.SessionLocal.kw["bind"] is before[0]
    assert snapshot["model_calls"] == {"before_the_revision": 1, "after_the_revision": 0} and provider.calls == 1, (
        "the count in the record is the count of calls made"
    )

    class Refusing(Scripted):
        def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
            raise RuntimeError("the model is away")

    access.run_starts.reset()
    (tmp_path / "second").mkdir()
    with pytest.raises(SystemExit):
        export.record(tmp_path / "second", provider=Refusing())
    assert (db_module.engine, config.settings.data_dir, config.settings.access_secret, config.settings.access_required, admission.acquire) == before[:5], (
        "and when the recording fails, too"
    )


def test_a_revision_is_accounted_for_without_asking_the_model_again(recorded: tuple[dict[str, Any], Scripted]) -> None:
    snapshot, provider = recorded
    assert provider.calls == 1, "one review, one model call; the second version, its lineage and the diff cost none"
    assert snapshot["model_calls"]["before_the_revision"] == 1, "and the record's own count saw that call"
    assert snapshot["model_calls"]["after_the_revision"] == 0
    assert [finding["topic"] for finding in snapshot["run"]["findings"]] == ["Term", "Governing law"]
    assert snapshot["trust"]["counts"] == {"supported": 2, "needs_review": 0, "unsupported": 0}
    diff = snapshot["diff"]
    assert diff["counts"] == {"unchanged": 1, "revalidated": 0, "stale": 1}
    by_topic = {change["topic"]: change for change in diff["findings"]}
    assert (by_topic["Term"]["before"], by_topic["Term"]["after"], by_topic["Term"]["verdict"]) == ("supported", "unsupported", "stale")
    assert any("12 months → 57 months" in why for why in by_topic["Term"]["why"]), "the reason is the typed fact that changed"
    assert (by_topic["Governing law"]["before"], by_topic["Governing law"]["after"], by_topic["Governing law"]["verdict"]) == (
        "supported",
        "supported",
        "unchanged",
    )
    assert diff["sectionsSearched"] + diff["sectionsReused"] == diff["sectionsTotal"] and diff["sectionsSearched"] == 1


def test_asking_what_a_revision_does_changes_nothing_about_the_run(recorded: tuple[dict[str, Any], Scripted]) -> None:
    snapshot, _ = recorded
    assert snapshot["run_record_sha256"]["before_the_diff"] == snapshot["run_record_sha256"]["after_the_diff"]
    assert snapshot["trust_manifest_id"]["before_the_diff"] == snapshot["trust_manifest_id"]["after_the_diff"]
    assert snapshot["supersedes"]["supersedesDocumentId"] == snapshot["documents"]["v1"]["document"]["id"]
    assert [version["documentId"] for version in snapshot["versions"]] == [snapshot["documents"][name]["document"]["id"] for name in ("v1", "v2")]
    for name in ("v1", "v2"):
        assert snapshot["documents"][name]["sha256"] == hashlib.sha256((export.FIXTURES / f"agreement-{name}.txt").read_bytes()).hexdigest()


def test_the_record_names_nothing_on_the_machine_that_made_it(recorded: tuple[dict[str, Any], Scripted], tmp_path: Path) -> None:
    snapshot, _ = recorded
    assert export.leaks(snapshot) == []
    planted = [
        str(tmp_path),  # a temporary folder, with backslashes on Windows
        tmp_path.as_posix(),  # the same with forward slashes
        str(Path.home()),
        "C:/Users/SOMEON~1/AppData/Local/Temp/tmpab12/recording.db",  # a short name no home folder matches
        "/home/someone/verity/backend/data",
        "/tmp/recording.db",
        "\\\\fileserver\\share\\contract.docx",
        "http://localhost:11434",
        "http://127.0.0.1:8000/api",
        "http://192.168.1.20:8000",
        "0.0.0.0",
        "[::1]:8000",
        f"made on {export.socket.gethostname()}",
        f"by {export.getpass.getuser()}",
    ]
    for value in planted:
        assert export.leaks({**snapshot, "note": value}), f"{value!r} would have been caught"
        assert export.leaks({**snapshot, "nested": [{"deep": {value: 1}}]}), f"{value!r} as a key, three levels down, would have been caught"
    for harmless in ("1.5% per month", "USD 250,000 per year", "sec_1", "policy-v3", "2026-10-05T06:30:50+00:00", "qwen3:8b", "§1 Term"):
        assert export.leaks({"note": harmless}) == [], f"{harmless!r} is not a machine's name"


def test_only_a_committed_file_counts_as_committed(tmp_path: Path) -> None:
    def git(*arguments: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.autocrlf=false", *arguments],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

    git("init", "-q")
    (tmp_path / "kept.txt").write_bytes(b"one\n")
    git("add", "kept.txt")
    git("commit", "-q", "-m", "kept")
    (tmp_path / "loose.txt").write_bytes(b"two\n")
    assert export.committed("kept.txt", tmp_path) and not export.committed("loose.txt", tmp_path)
    (tmp_path / "kept.txt").write_bytes(b"one\r\n")
    assert not export.committed("kept.txt", tmp_path), "a file changed since its commit, even in line endings alone, is not that commit's"
    record = {"schema": export.RECORD_SCHEMA}
    said = [json.loads(export.bundle(record, "0" * 40, {}, {}, producer)["bundle.json"])["producer"] for producer in (export.PRODUCER, export.REVIEW_BUILD)]
    assert said == [export.PRODUCER, export.REVIEW_BUILD] and "not yet in the commit named" in said[1], (
        "a bundle exported ahead of its commit says so of itself"
    )


def test_the_bundle_is_the_record_and_the_two_documents_and_is_the_same_bytes_every_time() -> None:
    snapshot = {"schema": export.RECORD_SCHEMA, "run": {"findings": []}, "diff": {"findings": []}}
    sources = {f"{export.SOURCE_HOME}/{path.name}": path.read_bytes() for path in sorted(export.FIXTURES.glob("agreement-*.txt"))}
    v1, v2 = (f"{export.SOURCE_HOME}/agreement-{name}.txt" for name in ("v1", "v2"))
    generator = {"backend/scripts/export_review_evidence.py": b"the script"}
    commit = "0123456789abcdef0123456789abcdef01234567"
    files = export.bundle(snapshot, commit, generator, sources)
    assert files == export.bundle(json.loads(json.dumps(snapshot)), commit, dict(generator), dict(sources))
    assert set(files) == {"bundle.json", "records/review-snapshot.json", f"sources/{v1}", f"sources/{v2}"}
    manifest = json.loads(files["bundle.json"])
    assert manifest["schema_version"] == "evidence-bundle/1" and manifest["source_repository"] == "verity" and manifest["source_commit"] == commit
    assert {entry["path"]: (entry["sha256"], entry["bytes"]) for entry in manifest["files"]} == {
        name: (hashlib.sha256(content).hexdigest(), len(content)) for name, content in files.items() if name != "bundle.json"
    }
    record = next(entry for entry in manifest["files"] if entry["role"] == "record")
    assert record["record_schema"] == export.RECORD_SCHEMA and record["parents"] == [f"sources/{v1}", f"sources/{v2}"]
    body = {key: value for key, value in manifest.items() if key != "artifact_id"}
    assert manifest["artifact_id"] == "sha256:" + hashlib.sha256(export.canonical(body, sort_keys=True)).hexdigest()
    assert json.loads(export.bundle(snapshot, commit[::-1], generator, sources)["bundle.json"])["artifact_id"] != manifest["artifact_id"]
    assert sources[v1].count(b"twelve (12) months") == 1 and sources[v2].count(b"fifty-seven (57) months") == 1
    assert sources[v1].replace(b"twelve (12) months", b"fifty-seven (57) months") == sources[v2], "the two versions differ in one phrase"
