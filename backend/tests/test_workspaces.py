"""Two reviewers, two workspaces, one store: A's work is A's, the curated record is everyone's, and B learns nothing
of A by knowing A's ids. The gate is on, as the deployment runs it; each workspace is a session cookie minted for its
own invite subject and sent on every request, so the two never share a cookie jar.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app import config
from app.api import access
from app.api.access import OPEN_WORKSPACE, SESSION_COOKIE, mint, workspace_for
from app.application.create_memo import create_memo as create_memo_for_run
from app.application.ingest_document import ingest_document, original_path
from app.application.review_finding import review_finding
from app.application.save_guidance import save_guidance
from app.application.start_run import start_run
from app.db import SessionLocal
from app.models import Document, Run
from app.runs.service import execute_run
from tests.support import CONTRACT, GUIDANCE
from tests.test_access import ORIGIN, SECRET

QUESTION = "How much notice does the customer need to give to terminate for convenience?"
SHA_LENGTH = 64


class Reviewer:
    """One workspace's view of the API: the same client, a different session cookie on every request."""

    def __init__(self, client: TestClient, subject: str) -> None:
        self.client = client
        self.subject = subject
        self.headers = {"Cookie": f"{SESSION_COOKIE}={mint(subject, 'verity-session', 3600, SECRET)}", "Origin": ORIGIN}

    def get(self, path: str) -> Response:
        response: Response = self.client.get(path, headers=self.headers)
        return response

    def post(self, path: str, json: dict[str, object] | None = None, files: dict[str, tuple[str, bytes, str]] | None = None) -> Response:
        response: Response = self.client.post(path, headers=self.headers, json=json, files=files)
        return response


@pytest.fixture
def two(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> tuple[Reviewer, Reviewer, TestClient]:
    monkeypatch.setattr(config.settings, "access_secret", SECRET)
    monkeypatch.setattr(config.settings, "app_url", ORIGIN)
    monkeypatch.setattr(config.settings, "access_revoked", [])
    client.base_url = ORIGIN
    return Reviewer(client, "reviewer-a"), Reviewer(client, "reviewer-b"), client


def work(a: Reviewer, question: str = QUESTION, contract: str = CONTRACT) -> dict[str, str]:
    """A uploads a contract, writes guidance, asks, reviews the finding, writes a memo and downloads the pack."""
    document = a.post("/api/documents", files={"file": ("agreement.txt", contract.encode("utf-8"), "text/plain")}).json()
    guidance = a.post("/api/guidance", json={"text": GUIDANCE}).json()
    started = a.post("/api/runs", json={"documentId": document["id"], "guidanceId": guidance["id"], "question": question})
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    detail = a.get(f"/api/runs/{run_id}/detail").json()
    finding_id = detail["findings"][0]["id"]
    review = a.post(f"/api/findings/{finding_id}/review", json={"verdict": "confirmed", "reviewer": "A", "note": None})
    assert review.status_code == 201, review.text
    memo = a.post("/api/memos", json={"runId": run_id})
    assert memo.status_code == 201, memo.text
    pack = a.get(f"/api/runs/{run_id}/evidence-pack")
    assert pack.status_code == 200
    return {"document": document["id"], "guidance": guidance["id"], "run": run_id, "finding": finding_id, "memo": memo.json()["id"]}


def make_curated(client: TestClient, question: str = QUESTION) -> dict[str, str]:
    """A curated record, made the way the project makes one: no workspace on the run or the guidance, no grant on the
    document, a review and a memo already on the record. The state of everything made before workspaces existed."""
    provider = client.provider
    with SessionLocal() as session:
        document = ingest_document(session, "hero.txt", CONTRACT.encode("utf-8"), workspace=None).document
        guidance = save_guidance(session, GUIDANCE, workspace=None).guidance
        run = start_run(session, document.id, guidance.id, question, provider, workspace=None).run
        run_id, document_id, guidance_id = run.id, document.id, guidance.id
    with SessionLocal() as session:
        execute_run(session, run_id, provider)
    with SessionLocal() as session:
        finished = session.get(Run, run_id)
        assert finished is not None and finished.stage == "complete" and finished.workspace_id is None
        finding = finished.findings[0]
        review_finding(session, finding.id, "confirmed", "Pavan", None)
        memo = create_memo_for_run(session, run_id).memo
        return {"document": document_id, "guidance": guidance_id, "run": run_id, "finding": finding.id, "memo": memo.id}


def test_a_workspace_is_opaque_stable_and_never_the_typed_name() -> None:
    config.settings.access_secret = SECRET
    try:
        first, again, other = workspace_for("min-kyu"), workspace_for("min-kyu"), workspace_for("didier")
    finally:
        config.settings.access_secret = ""
    assert first == again and first != other
    assert first.startswith("ws-") and len(first) == 19 and "min-kyu" not in first
    assert OPEN_WORKSPACE == "open"


def test_b_cannot_read_anything_of_a_by_its_ids_and_gets_no_existence_oracle(two: tuple[Reviewer, Reviewer, TestClient]) -> None:
    a, b, _ = two
    ids = work(a)
    missing = b.get("/api/runs/0000000000000000")
    assert missing.status_code == 404
    probes = {
        "document detail": b.get(f"/api/documents/{ids['document']}"),
        "run": b.get(f"/api/runs/{ids['run']}"),
        "run detail": b.get(f"/api/runs/{ids['run']}/detail"),
        "explanation": b.get(f"/api/runs/{ids['run']}/explanation"),
        "evidence pack": b.get(f"/api/runs/{ids['run']}/evidence-pack"),
        "events": b.get(f"/api/runs/{ids['run']}/events"),
        "review": b.post(f"/api/findings/{ids['finding']}/review", json={"verdict": "dismissed", "reviewer": "B", "note": None}),
        "memo as page": b.get(f"/api/memos/{ids['memo']}/html"),
        "memo as docx": b.get(f"/api/memos/{ids['memo']}/docx"),
        "memo for A's run": b.post("/api/memos", json={"runId": ids["run"]}),
        "guidance": b.get(f"/api/guidance/{ids['guidance']}"),
        "a run on A's document": b.post("/api/runs", json={"documentId": ids["document"], "guidanceId": None, "question": "x?"}),
        "a run with A's guidance": b.post("/api/runs", json={"documentId": ids["document"], "guidanceId": ids["guidance"], "question": "y?"}),
    }
    for name, response in probes.items():
        assert response.status_code == 404, (name, response.status_code, response.text[:120])
        # The same sentence a record that does not exist gets: the kind of thing and "not found", never the id, never a hint.
        detail = response.json()["detail"]
        assert detail.endswith("not found") and not any(value in detail for value in ids.values()), (name, detail)
        assert CONTRACT[:40] not in response.text and GUIDANCE[:30] not in response.text, name

    for path in ("/api/documents", "/api/runs", "/api/findings"):
        listed = b.get(path).json()
        assert not any(row["id"] in ids.values() or row.get("documentId") == ids["document"] or row.get("runId") == ids["run"] for row in listed), path
    assert b.get("/api/engineering/citations").json()["runs"] == 0, "B's census counts none of A's runs"


def test_run_reuse_never_crosses_workspaces(two: tuple[Reviewer, Reviewer, TestClient]) -> None:
    """A and B each upload the same bytes and ask the same question with the same guidance words."""
    a, b, _ = two
    first = work(a)
    document = b.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")})
    assert document.status_code == 201, "the same bytes are one stored reading, new to B"
    assert document.json()["id"] == first["document"], "deduplication by bytes and reader version is kept"
    guidance = b.post("/api/guidance", json={"text": GUIDANCE})
    assert guidance.status_code == 201 and guidance.json()["id"] != first["guidance"], "B's guidance is B's, whatever the words"
    started = b.post("/api/runs", json={"documentId": document.json()["id"], "guidanceId": guidance.json()["id"], "question": QUESTION})
    assert started.status_code == 202 and started.json()["id"] != first["run"], "B gets a run of its own, never A's"
    again = b.post("/api/runs", json={"documentId": document.json()["id"], "guidanceId": guidance.json()["id"], "question": QUESTION})
    assert again.status_code == 200 and again.json()["id"] == started.json()["id"], "B's own repeat is reused"
    with SessionLocal() as session:
        a_run, b_run = session.get(Run, first["run"]), session.get(Run, started.json()["id"])
        assert a_run is not None and b_run is not None
        assert a_run.workspace_id == workspace_for("reviewer-a") and b_run.workspace_id == workspace_for("reviewer-b")
        assert a_run.fingerprint != b_run.fingerprint


def test_the_curated_record_is_everyones_to_read_and_no_ones_to_change(two: tuple[Reviewer, Reviewer, TestClient]) -> None:
    a, b, client = two
    hero = make_curated(client)
    for reviewer in (a, b):
        run = reviewer.get(f"/api/runs/{hero['run']}")
        assert run.status_code == 200 and run.json()["shared"] is True
        assert reviewer.get(f"/api/runs/{hero['run']}/detail").status_code == 200
        assert reviewer.get(f"/api/documents/{hero['document']}").status_code == 200
        assert reviewer.get(f"/api/runs/{hero['run']}/evidence-pack").status_code == 200
        assert reviewer.get(f"/api/memos/{hero['memo']}/html").status_code == 200
        assert hero["run"] in {row["id"] for row in reviewer.get("/api/runs").json()}
        assert any(row["shared"] for row in reviewer.get("/api/findings").json())
        refused = reviewer.post(f"/api/findings/{hero['finding']}/review", json={"verdict": "dismissed", "reviewer": "X", "note": None})
        assert refused.status_code == 403 and "curated" in refused.json()["detail"], "no one changes the curated record"
    detail = a.get(f"/api/runs/{hero['run']}/detail").json()
    assert detail["findings"][0]["review"]["verdict"] == "confirmed", "the recorded review stands"


def test_both_workspaces_keep_working_beside_each_other(two: tuple[Reviewer, Reviewer, TestClient]) -> None:
    a, b, _ = two
    mine = work(a, "What is the notice period?")
    theirs = work(b, "What is the notice period?", CONTRACT + " 99. ADDENDUM. This copy differs by this clause.")
    assert mine["run"] != theirs["run"] and mine["document"] != theirs["document"]
    for reviewer, own, other in ((a, mine, theirs), (b, theirs, mine)):
        assert reviewer.get(f"/api/runs/{own['run']}").status_code == 200
        assert reviewer.get(f"/api/runs/{other['run']}").status_code == 404
        listed = {row["id"] for row in reviewer.get("/api/runs").json()}
        assert own["run"] in listed and other["run"] not in listed
        documents = {row["id"] for row in reviewer.get("/api/documents").json()}
        assert own["document"] in documents and other["document"] not in documents


def test_with_the_gate_off_everything_is_one_open_workspace(client: TestClient) -> None:
    document = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    run = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": "x?"}).json()
    with SessionLocal() as session:
        stored = session.get(Run, run["id"])
        assert stored is not None and stored.workspace_id == access.OPEN_WORKSPACE
    assert client.get(f"/api/runs/{run['id']}").json()["shared"] is False


def test_ordinary_logs_carry_ids_and_stages_never_the_words_or_the_tokens(two: tuple[Reviewer, Reviewer, TestClient], caplog: pytest.LogCaptureFixture) -> None:
    """The privacy truth: a run's whole life is logged by id, stage and duration. The contract, the guidance, the question,
    the invite and the session never appear; the original file lives under the data directory by its hash, nowhere a
    web route serves it from; the model is reached at a loopback address."""
    a, _, _ = two
    with caplog.at_level(logging.INFO):
        ids = work(a, "What notice ends this agreement for convenience?")
    text = caplog.text
    for secret in (CONTRACT[:60], GUIDANCE[:40], "What notice ends this agreement", a.headers["Cookie"].split("=", 1)[1], SECRET):
        assert secret not in text
    assert ids["run"] in text and "stage=" in text, "the run is in the log by its id and its stages"
    with SessionLocal() as session:
        document = session.get(Document, ids["document"])
        assert document is not None
        original = original_path(document)
    assert original.is_file() and config.settings.data_dir in original.parents, "the original is kept under the data directory by its hash"
    paths = set(a.client.app.openapi()["paths"])  # type: ignore[attr-defined]
    assert not any(path.startswith(("/files", "/data", "/static")) for path in paths), "no route serves files by path"
    assert all(path.startswith("/api/") for path in paths), paths
    assert config.settings.ollama_url.startswith(("http://localhost", "http://127.0.0.1")), "the model is local"
