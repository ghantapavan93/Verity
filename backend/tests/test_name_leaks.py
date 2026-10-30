"""No workspace is shown, or has the model given, the name another workspace chose for the same bytes (stress test,
2026-10-30, authz 2 and journeys 2).

One stored reading per set of bytes, and in an invited store the shared row took the first uploader's file name. Two
paths gave it to others: a later workspace whose grant had no name (grants before 2026-10-09) had every new run given
the first uploader's name in its CONTRACT line, and so in its pack and in any answer that repeated it; and a curated
run (a batch, the goldens) over bytes a workspace uploaded first showed that workspace's name to every other one, on
the run, its findings, its explanation, its pack and its memo, and was itself prompted with it. Now a new shared row is
named by its type in every store, a stored name that is a workspace's own is shown and given only to that workspace,
and a run recorded before is rebuilt with the name it was actually given.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db as db_module
from app.application.reconstruct_input import reconstruct_input
from app.batch.service import report, run_batch
from app.db import SessionLocal
from app.document_names import UNNAMED
from app.models import Document
from tests.support import CONTRACT
from tests.test_workspaces import QUESTION, Reviewer, two  # noqa: F401  (the fixture)

SECRET_NAME = "Project Falcon - Globex acquisition MSA (A only).txt"


def _upload(reviewer: Reviewer, name: str, body: str = CONTRACT) -> str:
    answer = reviewer.post("/api/documents", files={"file": (name, body.encode("utf-8"), "text/plain")})
    assert answer.status_code in (200, 201), answer.text
    return str(answer.json()["id"])


def _ask(reviewer: Reviewer, document_id: str, question: str = QUESTION) -> str:
    started = reviewer.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": question})
    assert started.status_code == 202, started.text
    return str(started.json()["id"])


def test_a_new_shared_row_is_named_by_its_type_and_each_workspace_sees_its_own_name(two: tuple[Reviewer, Reviewer, TestClient]) -> None:  # noqa: F811
    a, b, _ = two
    document_id = _upload(a, SECRET_NAME)
    assert _upload(b, "b-own.txt") == document_id
    with SessionLocal() as session:
        stored = session.get(Document, document_id)
        assert stored is not None and stored.name == "document.txt"
    assert a.get(f"/api/documents/{document_id}").json()["name"] == SECRET_NAME  # control: the uploader's own
    assert b.get(f"/api/documents/{document_id}").json()["name"] == "b-own.txt"


def _legacy_grants(document_id: str, stored_name: str) -> None:
    """The state of an invited store from before 2026-10-09: the shared row carries the first uploader's name, and the
    grants carry none."""
    with db_module.engine.begin() as connection:
        connection.execute(text("UPDATE document_access SET name = NULL WHERE document_id = :d"), {"d": document_id})
        connection.execute(text("UPDATE documents SET name = :n WHERE id = :d"), {"n": stored_name, "d": document_id})


def test_a_new_run_on_an_unnamed_grant_is_given_the_label_its_workspace_is_shown(two: tuple[Reviewer, Reviewer, TestClient]) -> None:  # noqa: F811
    a, b, client = two
    document_id = _upload(a, SECRET_NAME)
    _upload(b, "b-own.txt")
    _legacy_grants(document_id, SECRET_NAME)
    run_b = _ask(b, document_id)
    assert SECRET_NAME not in client.provider.calls[-1] and f"CONTRACT: {UNNAMED}" in client.provider.calls[-1]  # type: ignore[attr-defined]
    assert b.get(f"/api/runs/{run_b}/detail").json()["documentName"] == UNNAMED
    run_a = _ask(a, document_id, "Which law governs this agreement?")
    assert f"CONTRACT: {SECRET_NAME}" in client.provider.calls[-1], "control: the first uploader is given its own name"  # type: ignore[attr-defined]
    with SessionLocal() as session:
        for run_id in (run_a, run_b):
            rebuilt = reconstruct_input(session, run_id)
            assert rebuilt.problem is None and rebuilt.input_sha256 == rebuilt.recorded_input_sha256


def test_a_run_given_the_old_name_still_rebuilds_with_it(two: tuple[Reviewer, Reviewer, TestClient]) -> None:  # noqa: F811
    import pytest

    from app import document_names

    a, b, client = two
    document_id = _upload(a, SECRET_NAME)
    _upload(b, "b-own.txt")
    _legacy_grants(document_id, SECRET_NAME)
    with pytest.MonkeyPatch.context() as patched:  # the rule a run recorded before was made under
        patched.setattr(document_names, "prompt_name", document_names.legacy_prompt_name)
        run_b = _ask(b, document_id)
    assert f"CONTRACT: {SECRET_NAME}" in client.provider.calls[-1]  # type: ignore[attr-defined]
    with SessionLocal() as session:
        rebuilt = reconstruct_input(session, run_b)
    assert rebuilt.problem is None and rebuilt.input_sha256 == rebuilt.recorded_input_sha256
    assert f"CONTRACT: {SECRET_NAME}" in rebuilt.user, "rebuilt with the name it was given, as recorded"


def _corpus(directory: Path) -> Path:
    directory.mkdir()
    (directory / "cuad-0001.txt").write_text(CONTRACT, encoding="utf-8")
    (directory / "cuad-0002.txt").write_text(CONTRACT.replace("State of Delaware", "State of New York"), encoding="utf-8")
    return directory


def test_a_curated_run_on_bytes_a_workspace_uploaded_first_never_shows_its_name(two: tuple[Reviewer, Reviewer, TestClient], tmp_path: Path) -> None:  # noqa: F811
    a, b, client = two
    document_id = _upload(a, SECRET_NAME)
    with db_module.engine.begin() as connection:  # an invited store's row from before rows were named by type
        connection.execute(text("UPDATE documents SET name = :n WHERE id = :d"), {"n": SECRET_NAME, "d": document_id})
    batch_id = run_batch(SessionLocal, client.provider, [_corpus(tmp_path / "corpus")], "core-fields", concurrency=1)  # type: ignore[attr-defined]
    prompts = " ".join(client.provider.calls)  # type: ignore[attr-defined]
    assert SECRET_NAME not in prompts, "the project's own run was not prompted with a workspace's name"
    runs = b.get("/api/runs").json()
    shown = " ".join(
        [r["documentName"] for r in runs]
        + [b.get(f"/api/runs/{r['id']}/detail").text + b.get(f"/api/runs/{r['id']}/explanation").text for r in runs]
        + [b.get("/api/findings").text]
    )
    assert SECRET_NAME not in shown
    assert "cuad-0002.txt" in [r["documentName"] for r in runs], "control: a curated document no workspace holds keeps its name"
    with SessionLocal() as session:
        rows = report(session, batch_id).rows
    assert SECRET_NAME not in [row.document_name for row in rows] and "cuad-0002.txt" in [row.document_name for row in rows]
