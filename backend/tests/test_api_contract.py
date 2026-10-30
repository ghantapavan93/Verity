"""The API contract describes what the API sends (stress test, 2026-10-30, tools 2 / K62).

openapi.json, from which the interface's types are generated, was faithful to the code and silent about most of what it
sends: no error status from errors.py on any operation (404, 409, 413, 429, 503), not the 200 of the six create-or-hold
routes, a 422 declared as a list where the API's own refusals send a string, and the evidence pack, the event stream,
the memo's Word file and the values CSV declared as JSON or plain text. A client generated from it mistyped every
error. Here a seeded store is walked through every operation, repeats and refusals included, and each answer's status,
media type and body are held to what the document declares for that operation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema_rs
import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app import db as db_module
from app.batch.service import run_batch
from tests.support import CONTRACT, GUIDANCE

REVISED = CONTRACT.replace("fifteen (15) days", "thirty (30) days")
QUESTION = "What notice period applies to termination for convenience?"


class Walk:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.document = client.app.openapi()  # type: ignore[attr-defined]
        self.checked: set[tuple[str, str, int]] = set()

    def call(self, method: str, template: str, path: str | None = None, **kwargs: Any) -> Response:  # noqa: ANN401
        answer = self.client.request(method.upper(), path or template, **kwargs)
        operation = self.document["paths"][template][method]
        declared = operation["responses"]
        assert str(answer.status_code) in declared, f"{method.upper()} {template} sent {answer.status_code}; declares {sorted(declared)}: {answer.text[:200]}"
        content = declared[str(answer.status_code)].get("content", {})
        sent = answer.headers.get("content-type", "").split(";")[0].strip()
        assert sent in content, f"{method.upper()} {template} {answer.status_code} sent {sent}; declares {sorted(content)}"
        schema = content[sent].get("schema")
        if sent == "application/json" and schema:
            validator = jsonschema_rs.validator_for({**schema, "components": self.document["components"]})
            errors = [str(error) for error in validator.iter_errors(answer.json())]
            assert errors == [], f"{method.upper()} {template} {answer.status_code}: {errors[:3]}"
        self.checked.add((method, template, answer.status_code))
        return answer


@pytest.fixture
def walk(client: TestClient) -> Walk:
    return Walk(client)


def _upload(walk: Walk, text: str, name: str = "agreement.txt") -> Response:
    return walk.call("post", "/api/documents", files={"file": (name, text.encode("utf-8"), "text/plain")})


def test_every_answer_of_a_seeded_store_is_as_the_contract_declares(walk: Walk, tmp_path: Path) -> None:
    document = _upload(walk, CONTRACT).json()
    assert _upload(walk, CONTRACT).status_code == 200  # the bytes already held
    later = _upload(walk, REVISED, "agreement-v2.txt").json()
    assert _upload(walk, "", "notes").status_code == 422  # the API's own refusal: a string
    walk.call("get", "/api/documents")
    walk.call("get", "/api/documents/{document_id}", f"/api/documents/{document['id']}")
    walk.call("get", "/api/documents/{document_id}", "/api/documents/no-such-document")

    guidance = walk.call("post", "/api/guidance", json={"text": GUIDANCE}).json()
    assert walk.call("post", "/api/guidance", json={"text": GUIDANCE}).status_code == 200
    walk.call("post", "/api/guidance", json={"text": "   "})
    walk.call("get", "/api/guidance/{guidance_id}", f"/api/guidance/{guidance['id']}")
    walk.call("get", "/api/guidance/{guidance_id}", "/api/guidance/no-such-guidance")

    ask = {"documentId": document["id"], "guidanceId": guidance["id"], "question": QUESTION}
    run = walk.call("post", "/api/runs", json=ask).json()
    assert walk.call("post", "/api/runs", json=ask).status_code == 200  # the same question: the run held
    walk.call("post", "/api/runs", json={**ask, "documentId": "no-such-document"})
    walk.call("post", "/api/runs", json={**ask, "question": 5})  # FastAPI's own refusal: a list
    for template in ("/api/runs/{run_id}", "/api/runs/{run_id}/detail", "/api/runs/{run_id}/explanation", "/api/runs/{run_id}/trust"):
        walk.call("get", template, template.replace("{run_id}", run["id"]))
        walk.call("get", template, template.replace("{run_id}", "no-such-run"))
    walk.call("get", "/api/runs")
    walk.call("get", "/api/runs/{run_id}/evidence-pack", f"/api/runs/{run['id']}/evidence-pack")
    walk.call("get", "/api/runs/{run_id}/events", f"/api/runs/{run['id']}/events")

    finding = walk.call("get", "/api/findings").json()[0]
    decide = {"verdict": "confirmed", "reviewer": "A. Reviewer", "note": None, "basedOn": 0}
    walk.call("post", "/api/findings/{finding_id}/review", f"/api/findings/{finding['id']}/review", json=decide)
    assert walk.call("post", "/api/findings/{finding_id}/review", f"/api/findings/{finding['id']}/review", json=decide).status_code == 200
    walk.call("post", "/api/findings/{finding_id}/review", f"/api/findings/{finding['id']}/review", json={**decide, "verdict": "dismissed", "basedOn": 0})
    walk.call("post", "/api/findings/{finding_id}/review", f"/api/findings/{finding['id']}/review", json={**decide, "verdict": "maybe"})

    memo = walk.call("post", "/api/memos", json={"runId": run["id"]}).json()
    assert walk.call("post", "/api/memos", json={"runId": run["id"]}).status_code == 200
    walk.call("get", "/api/memos/{memo_id}/html", f"/api/memos/{memo['id']}/html")
    walk.call("get", "/api/memos/{memo_id}/docx", f"/api/memos/{memo['id']}/docx")
    walk.call("get", "/api/memos/{memo_id}/docx", "/api/memos/no-such-memo/docx")

    walk.call("get", "/api/runs/{run_id}/trust/diff", f"/api/runs/{run['id']}/trust/diff?documentId={later['id']}")  # not a version yet: 409
    said = {"previousDocumentId": document["id"]}
    walk.call("post", "/api/documents/{document_id}/supersedes", f"/api/documents/{later['id']}/supersedes", json=said)
    assert walk.call("post", "/api/documents/{document_id}/supersedes", f"/api/documents/{later['id']}/supersedes", json=said).status_code == 200
    walk.call("post", "/api/documents/{document_id}/supersedes", f"/api/documents/{document['id']}/supersedes", json={"previousDocumentId": document["id"]})
    walk.call("get", "/api/runs/{run_id}/trust/diff", f"/api/runs/{run['id']}/trust/diff?documentId={later['id']}")
    walk.call("get", "/api/documents/{document_id}/versions", f"/api/documents/{later['id']}/versions")

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "alpha.txt").write_text(CONTRACT, encoding="utf-8")
    batch_id = run_batch(db_module.SessionLocal, walk.client.provider, [corpus], "core-fields", concurrency=1)  # type: ignore[attr-defined]
    walk.call("get", "/api/batches")
    walk.call("get", "/api/batches/{batch_id}", f"/api/batches/{batch_id}")
    walk.call("get", "/api/batches/{batch_id}/values.csv", f"/api/batches/{batch_id}/values.csv")
    walk.call("get", "/api/batches/{batch_id}", "/api/batches/no-such-batch")
    walk.call("post", "/api/model/wake")
    walk.call("get", "/api/health")


def test_the_contract_declares_the_media_types_the_api_sends(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]

    def media(template: str, method: str = "get") -> set[str]:
        return set(paths[template][method]["responses"]["200"]["content"])

    assert media("/api/runs/{run_id}/evidence-pack") == {"application/zip"}
    assert media("/api/runs/{run_id}/events") == {"text/event-stream"}
    assert media("/api/memos/{memo_id}/docx") == {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    assert media("/api/batches/{batch_id}/values.csv") == {"text/csv"}


def test_every_error_the_api_raises_is_declared_by_its_class(client: TestClient) -> None:
    # The error statuses are generated from errors.py, so a class added there is declared wherever it can be raised.
    from app.api.contract import error_responses
    from app.errors import Busy, NotFound, Paused

    declared = error_responses(NotFound, Busy, Paused)
    assert set(declared) == {404, 503}
    assert "store is busy" in declared[503]["description"].lower() or "paused" in declared[503]["description"].lower()
    schemas = client.app.openapi()["components"]["schemas"]  # type: ignore[attr-defined]
    assert schemas["ErrorOut"]["properties"]["detail"]["anyOf"], "a refusal sends a sentence, FastAPI's own a list"


def test_the_committed_contract_is_the_code_s(client: TestClient) -> None:
    committed = json.loads((Path(__file__).resolve().parents[2] / "openapi.json").read_text(encoding="utf-8"))
    from app.main import create_app

    assert committed == create_app().openapi()
