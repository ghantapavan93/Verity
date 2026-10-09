"""A workspace sees the name it gave a file, never the name another workspace gave the same bytes.

Documents stay deduplicated by bytes and reader version (one stored reading), so a second workspace uploading bytes
someone else already stored is granted that reading. The bytes tell it nothing new; the name and the upload date are
not in the bytes. Found on the deployed site (2026-10-09): every invited reader who loaded the sample saw it under the
file name a test reader had given the same bytes the day before. The name a workspace gave is kept on its grant, and
everything shown to that workspace, and the model's input for its runs, uses it.
"""

from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.api.access import workspace_for
from app.db import SessionLocal
from app.document_names import UNNAMED
from app.models import DocumentAccess
from tests.support import CONTRACT
from tests.test_workspaces import QUESTION, Reviewer, two  # noqa: F401  (the fixture)


def upload(reviewer: Reviewer, name: str) -> dict[str, object]:
    response = reviewer.post("/api/documents", files={"file": (name, CONTRACT.encode("utf-8"), "text/plain")})
    assert response.status_code in (200, 201), response.text
    body: dict[str, object] = response.json()
    return body


def ask(reviewer: Reviewer, document_id: str) -> str:
    started = reviewer.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": QUESTION})
    assert started.status_code == 202, started.text
    return str(started.json()["id"])


def pack_of(reviewer: Reviewer, run_id: str) -> tuple[dict[str, object], str]:
    pack = reviewer.get(f"/api/runs/{run_id}/evidence-pack")
    assert pack.status_code == 200
    with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
        record = json.loads(archive.read("run.json"))
        user = archive.read("model_input/user.txt").decode("utf-8") if "model_input/user.txt" in archive.namelist() else ""
    return record, user


def names_seen(reviewer: Reviewer, document_id: str, run_id: str) -> dict[str, str]:
    return {
        "list": next(d["name"] for d in reviewer.get("/api/documents").json() if d["id"] == document_id),
        "document": reviewer.get(f"/api/documents/{document_id}").json()["name"],
        "runs": next(r["documentName"] for r in reviewer.get("/api/runs").json() if r["id"] == run_id),
        "run detail": reviewer.get(f"/api/runs/{run_id}/detail").json()["documentName"],
        "explanation": reviewer.get(f"/api/runs/{run_id}/explanation").json()["reading"]["documentName"],
    }


def test_each_workspace_sees_its_own_name_for_the_same_bytes(two: tuple[Reviewer, Reviewer, TestClient]) -> None:  # noqa: F811
    a, b, _ = two
    first = upload(a, "acme-master-agreement.txt")
    second = upload(b, "my-copy.txt")
    assert first["id"] == second["id"], "one stored reading: the bytes are deduplicated as before"
    assert second["name"] == "my-copy.txt", "the upload answers with the name this workspace gave"
    document_id = str(first["id"])
    run_a, run_b = ask(a, document_id), ask(b, document_id)

    seen_by_b = names_seen(b, document_id, run_b)
    assert set(seen_by_b.values()) == {"my-copy.txt"}, seen_by_b
    record_b, user_b = pack_of(b, run_b)
    assert record_b["document"]["name"] == "my-copy.txt"  # type: ignore[index]
    assert record_b["model_input"]["reconstructable"] is True, "B's run rebuilds to what it was given"  # type: ignore[index]
    assert "my-copy.txt" in user_b and "acme-master-agreement.txt" not in user_b, "the model was never told A's name"
    memo = b.post("/api/memos", json={"runId": run_b}).json()
    html = b.get(f"/api/memos/{memo['id']}/html").text
    assert "my-copy.txt" in html and "acme-master-agreement" not in html

    # Control: A sees A's name everywhere, and A's run rebuilds.
    assert set(names_seen(a, document_id, run_a).values()) == {"acme-master-agreement.txt"}
    record_a, user_a = pack_of(a, run_a)
    assert record_a["model_input"]["reconstructable"] is True and "acme-master-agreement.txt" in user_a  # type: ignore[index]
    # And B never sees A's upload date: B's document is dated by B's grant.
    with SessionLocal() as session:
        grant_b = session.get(DocumentAccess, (workspace_for("reviewer-b"), document_id))
        assert grant_b is not None
    assert b.get(f"/api/documents/{document_id}").json()["createdAt"][:19] == grant_b.created_at.isoformat()[:19]


def test_a_workspace_keeps_the_first_name_it_gave(two: tuple[Reviewer, Reviewer, TestClient]) -> None:  # noqa: F811
    a, _, _ = two
    first = upload(a, "first-name.txt")
    again = upload(a, "second-name.txt")
    assert again["id"] == first["id"] and again["name"] == "first-name.txt", "a name its runs were given never changes"


def test_a_grant_made_before_names_were_kept_shows_no_one_elses_name(two: tuple[Reviewer, Reviewer, TestClient]) -> None:  # noqa: F811
    """Grants from before 2026-10-09 have no name. The first workspace on a document gave the stored name and still sees
    it; a later one sees a neutral label. Each run's input still rebuilds: it was given the stored name, and still is."""
    a, b, _ = two
    document_id = str(upload(a, "original-name.txt")["id"])
    upload(b, "b-name.txt")
    with SessionLocal() as session:
        for subject in ("reviewer-a", "reviewer-b"):
            grant = session.get(DocumentAccess, (workspace_for(subject), document_id))
            assert grant is not None
            grant.name = None
        session.commit()
    run_b = ask(b, document_id)
    assert b.get(f"/api/documents/{document_id}").json()["name"] == UNNAMED
    assert a.get(f"/api/documents/{document_id}").json()["name"] == "original-name.txt"
    record_b, _ = pack_of(b, run_b)
    assert record_b["model_input"]["reconstructable"] is True  # type: ignore[index]


def test_a_curated_document_keeps_its_name_for_everyone(two: tuple[Reviewer, Reviewer, TestClient]) -> None:  # noqa: F811
    from tests.test_workspaces import make_curated

    _, b, client = two
    curated = make_curated(client)
    names = {d["id"]: d["name"] for d in b.get("/api/documents").json()}
    assert names[curated["document"]] != UNNAMED
