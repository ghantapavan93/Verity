"""Every field an evidence pack shows is checked, or verify.py says it is not (stress test, 2026-10-30: K42, K43).

findings.json and run.json were bound to nothing. Twenty-two one-file edits of a real pack exited 0 with no FAIL: a
status turned to pass, an invented review, a span moved to another passage, the conclusion and the question rewritten,
the verifier version lowered, a forged relation. Nulling a pointer turned its check into a NOTE that said "older
record", which was untrue. The run had recorded three stage hashes that would have caught most of it, and the pack
carried none of them.

The invariant: every PASS line is a check that could have failed, and every field the pack shows is either checked or
labelled unchecked. So each of these tests edits one file of a real pack, built through the API, and asks for a FAIL,
or an UNCHECKED line that names the edited field; the control is that the untouched pack exits 0. The matrix walks
every field of every JSON file, not a list of edits someone thought of. The pack is not signed, and nothing here claims
that an edit of several files together is caught: only that no single file can change unseen.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import types
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app import db as db_module
from app.application.evidence_pack import render_verify_py
from app.db import SessionLocal
from app.models import Run
from app.runs import prose
from app.runs.service import finished_record
from tests.support import FUZZ_SCALE, upload_and_ask

QUESTION = "How much notice does the customer need to give to terminate for convenience?"

# ------------------------------------------------------------------------------------------------- the packs


def _zip(client: TestClient, run_id: str) -> bytes:
    response = client.get(f"/api/runs/{run_id}/evidence-pack")
    assert response.status_code == 200, response.text
    return response.content


def _verified(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    return str(upload_and_ask(client, QUESTION)["run_id"])


def _withheld(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    client.provider.paraphrase = True  # type: ignore[attr-defined]
    return str(upload_and_ask(client, "Can the customer terminate for convenience?")["run_id"])


def _related(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    from tests.test_relations_surfaces import _ask

    return str(_ask(client, "When must the distributor give notice to renew?", monkeypatch)["id"])


def _reviewed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    run_id = _verified(client, monkeypatch)
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    reviewed = client.post(f"/api/findings/{finding['id']}/review", json={"verdict": "confirmed", "reviewer": "A. Reviewer", "note": "checked"})
    assert reviewed.status_code == 201, reviewed.text
    return run_id


KINDS: dict[str, Callable[[TestClient, pytest.MonkeyPatch], str]] = {
    "verified": _verified,  # a verified quote, guidance, the model input packed
    "withheld": _withheld,  # the model's quote is not in the contract: the finding is withheld
    "relations": _related,  # a clause the amendment replaced: relations.json and a note on the finding
    "reviewed": _reviewed,  # a person's review recorded after the run
}
_BUILT: dict[str, bytes] = {}


def pack(kind: str, client: TestClient, monkeypatch: pytest.MonkeyPatch, folder: Path) -> Path:
    """A real pack of this kind, unpacked into `folder`; built once per kind and reused, since a pack holds its whole run."""
    if kind not in _BUILT:
        _BUILT[kind] = _zip(client, KINDS[kind](client, monkeypatch))
    with zipfile.ZipFile(io.BytesIO(_BUILT[kind])) as archive:
        archive.extractall(folder)
    return folder


# ------------------------------------------------------------------------------------------------- the checker

_CODE = compile(render_verify_py(), "verify.py", "exec")


def _module() -> types.ModuleType:
    module = types.ModuleType("pack_verify")
    module.__dict__["__file__"] = str(Path("verify.py").resolve())
    exec(_CODE, module.__dict__)
    return module


CHECKER = _module()


def check(folder: Path) -> tuple[int, list[str]]:
    """verify.py's exit code and lines for a folder, run in this process: the matrix runs it a few thousand times."""
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="utf-8")
    with contextlib.redirect_stdout(stream):
        code = CHECKER.main(folder)
    stream.flush()
    return code, buffer.getvalue().decode("utf-8").splitlines()


def run_verify(folder: Path) -> subprocess.CompletedProcess[str]:
    """verify.py as a recipient runs it: its own process, isolated, nothing of this repository on its path."""
    return subprocess.run([sys.executable, "-I", "-X", "utf8", "verify.py"], cwd=folder, capture_output=True, text=True, encoding="utf-8", check=False)


def names(line: str, file: str, field: str) -> bool:
    """Whether an UNCHECKED line names the field: `UNCHECKED <file> <field>, <field>; <file> <field>: why`, a field
    named with its parents joined by dots and its list positions left out ("spans.clause_label")."""
    head = line.removeprefix("UNCHECKED ").split(": ", 1)[0]
    for group in head.split("; "):
        named_file, _, fields = group.partition(" ")
        if named_file != file:
            continue
        for named in fields.split(", "):
            if named == "every field" or field == named or field.startswith(f"{named}."):
                return True
    return False


def answered(code: int, lines: list[str], file: str, field: str) -> bool:
    """A FAIL line, an UNCHECKED line naming the field, or a run the checker refuses to judge (NOT CHECKED, exit 2)."""
    if code == 1 and any(line.startswith("FAIL ") for line in lines):
        return True
    if code == 2 and any(line.startswith("NOT CHECKED ") for line in lines) and not any(line.startswith(("PASS ", "FAIL ")) for line in lines):
        return True
    return any(line.startswith("UNCHECKED ") and names(line, file, field) for line in lines)


# ------------------------------------------------------------------------------------------------- one edit per field

Path_ = tuple[str | int, ...]


def _nodes(value: object, at: Path_ = ()) -> Iterator[tuple[Path_, object]]:
    yield at, value
    if isinstance(value, dict):
        for key, inner in value.items():
            yield from _nodes(inner, (*at, key))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from _nodes(inner, (*at, index))


def field_name(at: Path_) -> str:
    return ".".join(str(part) for part in at if not isinstance(part, int))


def _changed(value: object) -> object:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, str):
        return value + "x"
    return "x"  # a null given a value


def edits(document: object) -> Iterator[tuple[str, Path_, Callable[[object], None]]]:
    """Every one-field edit of a JSON document: each value changed, each value nulled, each key removed, each list
    emptied. Yields (what, where, edit), the edit applied in place to a copy."""

    def parent(root: Any, at: Path_) -> Any:  # noqa: ANN401 - a JSON document, indexed by its own paths
        for part in at[:-1]:
            root = root[part]
        return root

    for at, value in _nodes(document):
        if not at:
            continue
        if not isinstance(value, (dict, list)):
            yield "changed", at, lambda root, at=at, value=value: parent(root, at).__setitem__(at[-1], _changed(value))
        if value is not None:
            yield "nulled", at, lambda root, at=at: parent(root, at).__setitem__(at[-1], None)
        if isinstance(at[-1], str):
            yield "removed", at, lambda root, at=at: parent(root, at).pop(at[-1])
        if isinstance(value, list) and value:
            yield "emptied", at, lambda root, at=at: parent(root, at).__setitem__(at[-1], [])


def _write_json(path: Path, data: object) -> None:
    path.write_bytes(json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


@pytest.mark.parametrize("kind", list(KINDS))
def test_control_an_untouched_pack_exits_0_and_checks_every_stage(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str) -> None:
    folder = pack(kind, client, monkeypatch, tmp_path / kind)
    done = run_verify(folder)
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert not [line for line in lines if line.startswith(("FAIL ", "NOT CHECKED "))], done.stdout
    for claim in (
        "PASS stage rows: reading > finding_evidence > checking > verifying > ",
        "PASS reading: the document run.json names is the one the run read",
        "PASS sections are what the run read",
        "PASS question and guidance: what the run was asked with",
        "PASS candidates: the sections handed to the model, in order, are the ones the run chose",
        "PASS model output: the recorded answer hashes to what the run recorded",
        "PASS located spans: every span's section, offsets, verified flag and tier are what the run recorded",
        "PASS the record the run finished on",
        "PASS finding 1: its words are the model's answer in model_output.txt",
        "PASS README.txt",
    ):
        assert any(line.startswith(claim) for line in lines), (claim, done.stdout)
    # The re-written JSON of the matrix below is byte-for-byte the pack's own: an edit that changes nothing fails nothing.
    for name in ("run.json", "findings.json", "relations.json", "sections.json"):
        _write_json(folder / name, json.loads((folder / name).read_bytes()))
    assert check(folder)[0] == 0


# What a pack of a run finished from 2026-10-30 on leaves unchecked, and says so; anything else it shows is checked.
# Changing this list changes what the pack claims: README.txt says the same.
ALWAYS_UNCHECKED = {
    "run.json": {
        "created_at",
        "finished_at",
        "packed_at",
        "document.name",
        "document.parser_version",
        "document.parse_coverage",
        "workbench_link",
        "verifier.describes",
        "verifier.version",
        "verifier.ladder",
        "verifier.label_stripping",
        "verifier.boundary",
        "verifier.unicode",
        "relations_note",
        "model_input.problem",
        "model_input.model_calls",
        "model_input.validation_rounds",
        "stages.attempt",
        "stages.rounds",
    },
    "findings.json": {"decided_by", "flagged", "concerns", "code_compared", "unseen_reason", "spans.clause_label"},
}


def _unchecked_fields(lines: list[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for line in lines:
        if line.startswith("UNCHECKED "):
            for group in line.removeprefix("UNCHECKED ").split(": ", 1)[0].split("; "):
                file, _, fields = group.partition(" ")
                found.setdefault(file, set()).update(fields.split(", "))
    return found


@pytest.mark.parametrize("kind", ["verified", "withheld", "relations"])
def test_a_new_pack_leaves_unchecked_only_what_it_cannot_bind(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str) -> None:
    code, lines = check(pack(kind, client, monkeypatch, tmp_path / kind))
    assert code == 0, lines
    assert _unchecked_fields(lines) == ALWAYS_UNCHECKED, lines


def test_a_reviewed_pack_says_its_review_is_unchecked(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    code, lines = check(pack("reviewed", client, monkeypatch, tmp_path / "reviewed"))
    assert code == 0, lines
    found = _unchecked_fields(lines)
    assert found["findings.json"] == ALWAYS_UNCHECKED["findings.json"] | {"review"}, lines
    assert found["run.json"] == ALWAYS_UNCHECKED["run.json"] | {"review_head"}, lines


MATRIX = [(kind, file) for kind in KINDS for file in ("run.json", "findings.json", "relations.json", "sections.json")]


@pytest.mark.parametrize(("kind", "file"), MATRIX, ids=[f"{kind}-{file}" for kind, file in MATRIX])
def test_every_field_edited_alone_fails_or_is_named_unchecked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str, file: str
) -> None:
    folder = pack(kind, client, monkeypatch, tmp_path / kind)
    target = folder / file
    original = target.read_bytes()
    document = json.loads(original)
    misses = []
    tried = 0
    for what, at, edit in edits(document):
        edited = json.loads(original)
        edit(edited)
        _write_json(target, edited)
        code, lines = check(folder)
        tried += 1
        if not answered(code, lines, file, field_name(at)):
            misses.append(f"{what} {file} {'/'.join(map(str, at))}: exit {code}")
    target.write_bytes(original)
    assert check(folder)[0] == 0, "the control: the restored pack passes"
    assert tried or file == "relations.json"
    assert not misses, "\n".join(misses)


FILES = ["README.txt", "model_output.txt", "model_input/system.txt", "model_input/user.txt", "guidance.txt", "document/agreement.txt"]


@pytest.mark.parametrize("name", FILES)
def test_every_other_file_edited_alone_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str) -> None:
    folder = pack("verified", client, monkeypatch, tmp_path / "verified")
    target = folder / name
    target.write_bytes(target.read_bytes() + b" ")
    code, lines = check(folder)
    assert code == 1 and any(line.startswith("FAIL ") for line in lines), lines


# ------------------------------------------------------------------------------------------------- the stress test's own edits


def _findings(folder: Path) -> list[dict[str, Any]]:
    return json.loads((folder / "findings.json").read_bytes())  # type: ignore[no-any-return]


def _run(folder: Path) -> dict[str, Any]:
    return json.loads((folder / "run.json").read_bytes())  # type: ignore[no-any-return]


def _text(folder: Path, section_id: str) -> str:
    return next(s["text"] for s in json.loads((folder / "sections.json").read_bytes()) if s["id"] == section_id)


def status_to_model_pass(folder: Path) -> None:
    findings = _findings(folder)
    findings[0].update(status="pass", status_source="model_hint", status_reason=None, decided_by="model", flagged=False, concerns=[], code_compared=False)
    _write_json(folder / "findings.json", findings)


def invent_review(folder: Path) -> None:
    findings = _findings(folder)
    findings[0]["review"] = {"verdict": "confirmed", "reviewer": "General Counsel", "note": "approved", "at": "2026-10-30T00:00:00+00:00"}
    _write_json(folder / "findings.json", findings)


def relocate_span(folder: Path) -> None:
    findings = _findings(folder)
    span = findings[0]["spans"][0]
    quote = "On termination, Customer pays all Fees accrued."
    span["start"] = _text(folder, span["section_id"]).index(quote)
    span.update(end=span["start"] + len(quote), quote=quote)
    _write_json(folder / "findings.json", findings)


def unverify_span(folder: Path) -> None:
    findings = _findings(folder)
    findings[0]["spans"][0]["verified"] = False
    _write_json(folder / "findings.json", findings)


def rewrite_conclusion(folder: Path) -> None:
    findings = _findings(folder)
    findings[0]["conclusion"] = findings[0]["shown_conclusion"] = "Customer may terminate on 30 days' notice; within guidance."
    _write_json(folder / "findings.json", findings)


def run_edit(change: Callable[[dict[str, Any]], None]) -> Callable[[Path], None]:
    def edit(folder: Path) -> None:
        record = _run(folder)
        change(record)
        _write_json(folder / "run.json", record)

    edit.__name__ = change.__name__
    return edit


def question(record: dict[str, Any]) -> None:
    record["question"] = "Is the customer bound for twelve months with no exit?"


def verifier_v7(record: dict[str, Any]) -> None:
    record["options"]["verifier_version"] = "v7"


def verifier_removed(record: dict[str, Any]) -> None:
    record["options"].pop("verifier_version")


def window_50(record: dict[str, Any]) -> None:
    record["verifier"]["window_chars"] = 50


def stage_failed_model_renamed(record: dict[str, Any]) -> None:
    record.update(stage="failed", model="gpt-5", provider="openai")


def fingerprint_zeroed(record: dict[str, Any]) -> None:
    record["fingerprint"] = "0" * 64


def null_reading_hash(record: dict[str, Any]) -> None:
    record["sections_text_sha256_recorded"] = None


def null_guidance_file(record: dict[str, Any]) -> None:
    record["guidance_file"] = None


def null_model_input(record: dict[str, Any]) -> None:
    record["model_input"]["user_file"] = None


def null_model_output_file(record: dict[str, Any]) -> None:
    record["model_output"]["file"] = None


def null_model_output_hash(record: dict[str, Any]) -> None:
    record["model_output"]["sha256_recorded"] = None


def empty_context_slices(record: dict[str, Any]) -> None:
    record["context_slices"] = []


def null_a_stage_hash(record: dict[str, Any]) -> None:
    next(row for row in record["stages"] if row["stage"] == "verifying")["output_hash"] = None


def drop_the_stage_rows(record: dict[str, Any]) -> None:
    record.pop("stages")


def forge_relation(folder: Path) -> None:
    sections = json.loads((folder / "sections.json").read_bytes())
    section = next(s for s in sections if s["number"] == "2")
    phrase = "On termination, Customer pays all Fees accrued."
    start = section["text"].index(phrase)
    passage = {"section_id": section["id"], "label": "§2", "start": start, "end": start + len(phrase), "text": phrase}
    _write_json(folder / "relations.json", [{"kind": "supersedes", "statement": passage, "replaced": None, "replacement": None}])


def rewrite_readme(folder: Path) -> None:
    (folder / "README.txt").write_bytes(b"Evidence pack. Everything in it was checked by a lawyer.\n")


STRESS_EDITS = [
    status_to_model_pass,
    invent_review,
    relocate_span,
    unverify_span,
    rewrite_conclusion,
    run_edit(question),
    run_edit(verifier_v7),
    run_edit(verifier_removed),
    run_edit(window_50),
    run_edit(stage_failed_model_renamed),
    run_edit(fingerprint_zeroed),
    run_edit(null_reading_hash),
    run_edit(null_guidance_file),
    run_edit(null_model_input),
    run_edit(null_model_output_file),
    run_edit(null_model_output_hash),
    run_edit(empty_context_slices),
    run_edit(null_a_stage_hash),
    run_edit(drop_the_stage_rows),
    forge_relation,
    rewrite_readme,
]


@pytest.mark.parametrize("edit", STRESS_EDITS, ids=[edit.__name__ for edit in STRESS_EDITS])
def test_each_edit_the_stress_test_made_now_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, edit: Callable[[Path], None]) -> None:
    """The edits that exited 0: each now fails outright, and no line calls the record older than it is. A nulled pointer
    beside a hash the run recorded is a FAIL, never a NOTE."""
    folder = pack("verified", client, monkeypatch, tmp_path / "verified")
    edit(folder)
    done = run_verify(folder)
    assert done.returncode == 1 and "\nFAIL " in f"\n{done.stdout}", done.stdout + done.stderr
    assert "older record" not in done.stdout


def test_a_withheld_finding_made_a_verified_pass_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The skeptic's stronger form: in a withheld pack, findings.json alone turned the model's invented quote into a real
    sentence, verified, with status pass, and verify.py printed PASS for it."""
    folder = pack("withheld", client, monkeypatch, tmp_path / "withheld")
    findings = _findings(folder)
    span = findings[0]["spans"][0]
    section_id = span["section_id"] or _run(folder)["context_slices"][0]["section_id"]
    quote = _text(folder, section_id)[: _text(folder, section_id).index(".") + 1]
    span.update(section_id=section_id, start=0, end=len(quote), quote=quote, verified=True, method="exact", match_count=1)
    findings[0].update(status="pass", status_source="model_hint", decided_by="model", flagged=False, concerns=[])
    _write_json(folder / "findings.json", findings)
    code, lines = check(folder)
    assert code == 1 and "FAIL located spans: every span's section, offsets, verified flag and tier are what the run recorded" in "\n".join(lines), lines


def test_a_missing_document_file_is_named_unchecked_never_called_older(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The original bytes may truly be absent (a store copied without them), so their absence is UNCHECKED, not FAIL:
    the line says what is not checked and claims nothing about the record's age."""
    folder = pack("verified", client, monkeypatch, tmp_path / "verified")
    run_edit(lambda record: record["document"].__setitem__("file", None))(folder)
    code, lines = check(folder)
    assert code == 0 and any(line.startswith("UNCHECKED ") and names(line, "run.json", "document.file") for line in lines), lines
    assert not any("older record" in line for line in lines)


# ------------------------------------------------------------------------------------------------- versions and older runs


@pytest.mark.parametrize("recorded", ["v99", "v11b", "eleven"])
def test_a_run_verified_under_a_verifier_the_checker_does_not_know_is_not_checked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, recorded: str
) -> None:
    """A newer verifier's rules are not this checker's: it judged a "v99" run by its own and printed PASS (stress test,
    2026-10-30, STO-3). It now judges nothing: NOT CHECKED, exit 2, no PASS and no FAIL."""
    folder = pack("verified", client, monkeypatch, tmp_path / "verified")
    run_edit(lambda record: record["options"].__setitem__("verifier_version", recorded))(folder)
    done = run_verify(folder)
    assert done.returncode == 2, done.stdout
    lines = done.stdout.splitlines()
    assert lines[0].startswith("NOT CHECKED ") and not [line for line in lines if line.startswith(("PASS ", "FAIL ", "NOTE "))], done.stdout


def test_control_the_checkers_own_verifier_is_checked(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.verify.spans import VERIFIER_VERSION

    folder = pack("verified", client, monkeypatch, tmp_path / "verified")
    assert _run(folder)["options"]["verifier_version"] == VERIFIER_VERSION
    assert int(VERIFIER_VERSION.removeprefix("v")) == CHECKER.KNOWN_VERIFIER


def _as_finished_before_the_record_hash(run_id: str) -> None:
    """A run as every run finished before 2026-10-30 recorded it: no hash on its last stage. Made by hand, the triggers
    forbid it; they are put back."""
    with db_module.engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER trg_run_stages_no_update_when_finished")
        connection.exec_driver_sql("UPDATE run_stages SET input_hash = NULL WHERE run_id = ? AND stage IN ('complete', 'unresolved')", (run_id,))
    db_module.ensure_immutability(db_module.engine)


def test_an_older_runs_pack_says_what_it_cannot_bind(client: TestClient, tmp_path: Path) -> None:
    """A run finished before the record hash existed: its pack still passes, names every field the missing hash would
    have bound as UNCHECKED, and an edited status is then unchecked, never passed as checked."""
    run_id = str(upload_and_ask(client, QUESTION)["run_id"])
    _as_finished_before_the_record_hash(run_id)
    folder = tmp_path / "older"
    with zipfile.ZipFile(io.BytesIO(_zip(client, run_id))) as archive:
        archive.extractall(folder)
    code, lines = check(folder)
    assert code == 0, lines
    for file, field in (("findings.json", "status"), ("findings.json", "status_source"), ("run.json", "options"), ("relations.json", "kind")):
        assert any(line.startswith("UNCHECKED ") and names(line, file, field) for line in lines), (file, field, lines)
    assert not any("PASS the record the run finished on" in line for line in lines)
    status_to_model_pass(folder)
    code, lines = check(folder)
    assert code == 0 and any(line.startswith("UNCHECKED ") and names(line, "findings.json", "status") for line in lines), lines


def test_the_pack_carries_the_runs_stage_rows_as_recorded(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """run.json's stage rows are the workbench's own, so a recipient can compare the two; the record hash verify.py
    recomputes from the pack is the one the workbench computes from the database."""
    for kind in ("verified", "withheld", "relations"):
        run_id = KINDS[kind](client, monkeypatch)
        folder = tmp_path / kind
        with zipfile.ZipFile(io.BytesIO(_zip(client, run_id))) as archive:
            archive.extractall(folder)
        stages = client.get(f"/api/runs/{run_id}/detail").json()["stages"]
        packed = _run(folder)["stages"]
        assert [(s["stage"], s["input_hash"], s["output_hash"]) for s in packed] == [(s["stage"], s["inputHash"], s["outputHash"]) for s in stages]
        with SessionLocal() as session:
            run = session.get(Run, run_id)
            assert run is not None
            assert packed[-1]["input_hash"] == finished_record(run, run.stage)
        record = CHECKER.record_of(_run(folder), _findings(folder), json.loads((folder / "relations.json").read_bytes()))
        assert record == packed[-1]["input_hash"], kind


# ------------------------------------------------------------------------------------------------- the model's words

HANDLES = st.text(alphabet="sec_0123456789 .,()[]-–abiv§", min_size=0, max_size=30)


@settings(max_examples=300 * FUZZ_SCALE, deadline=None)
@given(text=HANDLES, data=st.data())
def test_the_pack_writes_handles_as_labels_as_the_workbench_does(text: str, data: st.DataObject) -> None:
    """findings.json's sentences are the model's with each handle written as its section's label (runs.prose); the
    pack's checker writes them the same way, so a conclusion edited in findings.json fails against model_output.txt."""
    labels = data.draw(st.dictionaries(st.sampled_from([f"sec_{n}" for n in range(4)]), st.sampled_from(["§1", "§2.1", "Fees", ""]), max_size=4))
    assert CHECKER.label_handles(text, labels) == prose.label_handles(text, labels), (text, labels)
