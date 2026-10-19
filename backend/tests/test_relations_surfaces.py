"""One recorded account of the contract's own statements, read alike by every surface (policy-v11).

A question about the agreement as it stands, answered from a clause the amendment replaced in full: the API says code set
needs review and why, with both ends of the relation; the findings list flags it with the same words; the memo prints
them under "Why flagged."; the evidence pack carries the relation and its verify.py checks every end offline. Asked
about the original agreement, the same quote raises nothing and the memo says what the contract did later. A run
recorded before policy-v11 shows no relations and is not re-derived.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.memo.service import RELATED_HEAD
from app.models import Run
from tests.test_relations_oracle import OracleModel

AGREEMENT = "\n\n".join(
    [
        "DISTRIBUTION AGREEMENT",
        "1. TERM",
        "1.1 This Agreement runs for three (3) years from 1 March 2025.",
        "1.2 Distributor may renew this Agreement by notice given not earlier than two hundred ten (210) days and not later than one hundred "
        "fifty (150) days before expiry.",
        "AMENDMENT NO. 1",
        'This Amendment No. 1 is dated September 18, 2025 (the "Amendment Date").',
        "1. With effect from the Amendment Date, clause 1.2 of the Agreement is deleted in its entirety and replaced with the following: "
        '"1.2 Distributor may renew this Agreement by notice given not earlier than one hundred twenty (120) days and not later than '
        'forty-five (45) days before expiry."',
    ]
)
OLD = (
    "Distributor may renew this Agreement by notice given not earlier than two hundred ten (210) days and not later than one hundred fifty "
    "(150) days before expiry."
)


NEW = (
    "Distributor may renew this Agreement by notice given not earlier than one hundred twenty (120) days and not later than forty-five (45) days before expiry."
)


def _ask(client: TestClient, question: str, monkeypatch: pytest.MonkeyPatch, quotes: tuple[str, ...] = (OLD,), agreement: str = AGREEMENT) -> dict[str, Any]:
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = OracleModel(  # type: ignore[attr-defined]
        {
            "topic": "Renewal notice",
            "conclusion": "Notice of renewal is due 210 to 150 days before expiry.",
            "observed": "210 to 150 days",
            "quotes": list(quotes),
        }
    )
    document = client.post("/api/documents", files={"file": ("distribution.txt", agreement.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": question})
    assert started.status_code == 202, started.text
    return client.get(f"/api/runs/{started.json()['id']}/detail").json()


def _memo(client: TestClient, run_id: str) -> tuple[str, str]:
    memo = client.post("/api/memos", json={"runId": run_id}).json()
    html = re.sub(r"<[^>]+>", "", client.get(f"/api/memos/{memo['id']}/html").text).replace("&#x27;", "'").replace("&quot;", '"')
    words = "\n".join(p.text for p in Document(io.BytesIO(client.get(f"/api/memos/{memo['id']}/docx").content)).paragraphs)
    return html, words


def test_every_surface_reads_one_account_of_a_replaced_clause(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    detail = _ask(client, "When must the distributor give notice to renew?", monkeypatch)
    finding = detail["findings"][0]
    (note,) = finding["relations"]
    assert (finding["status"], finding["statusSource"], finding["decidedBy"], note["effect"]) == ("needs_review", "position_check", "code", "replaced")
    assert finding["spans"][0]["verified"] is True  # the quote is still where it was found
    assert finding["statusReason"] == note["sentence"] and "does not say it asks about the original agreement" in note["sentence"]
    relation = note["relation"]
    assert relation["replaced"]["text"].startswith("1.2 Distributor") and "(210)" in relation["replaced"]["text"]
    assert relation["replacement"]["text"].startswith("1.2 Distributor") and "(120)" in relation["replacement"]["text"]
    assert relation["effective"] == "2025-09-18, the Amendment Date"
    assert detail["relations"] and detail["relations"][0]["statement"] == relation["statement"]

    listed = next(f for f in client.get("/api/findings").json() if f["id"] == finding["id"])
    assert listed["flagged"] is True and f"code: {note['sentence']}" in listed["concerns"]

    for text in _memo(client, detail["id"]):
        assert "Why flagged." in text and note["sentence"] in text
        assert "No automated check flagged" not in text

    pack = client.get(f"/api/runs/{detail['id']}/evidence-pack")
    with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
        archive.extractall(tmp_path)
    packed = json.loads((tmp_path / "findings.json").read_text(encoding="utf-8"))[0]
    relations = json.loads((tmp_path / "relations.json").read_text(encoding="utf-8"))
    assert packed["relations"] == [{"relation": 0, "effect": "replaced", "sentence": note["sentence"]}]
    assert relations[0]["replaced"]["text"] == relation["replaced"]["text"]
    # The labels print "§": -X utf8 keeps the pipe UTF-8 under -I, which ignores PYTHONIOENCODING.
    checked = subprocess.run([sys.executable, "-I", "-X", "utf8", str(tmp_path / "verify.py")], capture_output=True, text=True, encoding="utf-8")
    assert checked.returncode == 0, checked.stdout
    assert checked.stdout.count("PASS relation 1 (replaces)") == 3  # statement, original clause, replacement


def test_control_asked_about_the_original_agreement_the_same_quote_raises_nothing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    detail = _ask(client, "What notice did the agreement originally require for renewal?", monkeypatch)
    finding = detail["findings"][0]
    assert [n["effect"] for n in finding["relations"]] == ["context"]
    # Nothing from the relation: the status is the model's, and no concern names the amendment (another check may still
    # say the passage offers two periods, which is not this one's business).
    assert finding["status"] == "pass" and not [c for c in finding["concerns"] if "replace" in c]
    for text in _memo(client, detail["id"]):
        assert RELATED_HEAD in text and "the question asks about the original agreement" in text


@pytest.mark.parametrize(
    ("question", "quotes", "effect", "says"),
    [
        # The run's date is not the time a question names: the same quote of the replaced clause, asked about June 2025.
        ("What notice did renewal need in June 2025?", (OLD,), "dated", "the question names a time (“June 2025”)"),
    ],
)
def test_a_concern_code_cannot_resolve_is_one_account_on_every_surface_and_never_codes_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, question: str, quotes: tuple[str, ...], effect: str, says: str
) -> None:
    detail = _ask(client, question, monkeypatch, quotes)
    finding = detail["findings"][0]
    (note,) = finding["relations"]
    assert note["effect"] == effect and says in note["sentence"] and "is not decided by code" in note["sentence"]
    assert finding["statusReason"] != note["sentence"]  # a concern beside the status, never the reason code set it
    assert all(span["verified"] for span in finding["spans"])
    listed = next(f for f in client.get("/api/findings").json() if f["id"] == finding["id"])
    assert listed["flagged"] is True and f"code: {note['sentence']}" in listed["concerns"]
    for text in _memo(client, detail["id"]):
        assert "Why flagged." in text and note["sentence"] in text
    pack = client.get(f"/api/runs/{detail['id']}/evidence-pack")
    with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
        archive.extractall(tmp_path)
    packed = json.loads((tmp_path / "findings.json").read_text(encoding="utf-8"))[0]
    assert packed["relations"] == [{"relation": 0, "effect": effect, "sentence": note["sentence"]}]
    assert f"code: {note['sentence']}" in packed["concerns"]


def test_quoting_the_replacement_with_only_the_replaced_values_is_code_status_on_every_surface(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Policy-v16 (the owner's decision on the amendment challenge, 2026-10-17): quoting the replacement is not following
    it. An answer that quotes both and states only the replaced periods is needs review set by code, with code's sentence
    as the reason on every surface and once among the concerns; until v16 it was a concern beside the model's pass."""
    detail = _ask(client, "When must the distributor give notice to renew?", monkeypatch, (OLD, NEW))
    finding = detail["findings"][0]
    (note,) = finding["relations"]
    assert note["effect"] == "old_value" and "one only the replaced wording states" in note["sentence"]
    assert (finding["status"], finding["statusSource"], finding["decidedBy"], finding["statusReason"]) == (
        "needs_review",
        "position_check",
        "code",
        note["sentence"],
    )
    assert all(span["verified"] for span in finding["spans"])
    listed = next(f for f in client.get("/api/findings").json() if f["id"] == finding["id"])
    assert listed["flagged"] is True and listed["concerns"].count(f"code: {note['sentence']}") == 1
    for text in _memo(client, detail["id"]):
        assert "Why flagged." in text and note["sentence"] in text and "No automated check flagged" not in text
    pack = client.get(f"/api/runs/{detail['id']}/evidence-pack")
    with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
        archive.extractall(tmp_path)
    packed = json.loads((tmp_path / "findings.json").read_text(encoding="utf-8"))[0]
    assert packed["relations"] == [{"relation": 0, "effect": "old_value", "sentence": note["sentence"]}]
    assert packed["concerns"].count(f"code: {note['sentence']}") == 1


@pytest.mark.parametrize(("start", "effective"), [("March 2025", "2025-03-01, March 2025"), ("September 18, 2025", "2025-09-18, September 18, 2025")])
def test_a_start_written_as_a_month_or_with_a_comma_is_read_and_the_run_completes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, start: str, effective: str
) -> None:
    """Until 2026-10-14 "With effect from March 2025" raised ValueError in the run's relation step, before the model was
    asked: the run failed with "The server failed while answering this question", and asking again failed the same way."""
    detail = _ask(client, "When must the distributor give notice to renew?", monkeypatch, agreement=AGREEMENT.replace("the Amendment Date,", f"{start},"))
    assert (detail["stage"], detail["reason"]) == ("complete", None), detail["error"]
    (note,) = detail["findings"][0]["relations"]
    assert note["effect"] == "replaced" and note["relation"]["effective"] == effective and note["relation"]["scope"] is None


def test_the_relations_a_finished_run_recorded_cannot_be_rewritten(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A run recorded before policy-v11 keeps its NULL (shown as no relations, never re-derived), and one recorded after
    keeps what it recorded: the store refuses to change either once the run has finished."""
    from sqlalchemy.exc import DatabaseError

    from app.db import SessionLocal

    detail = _ask(client, "When must the distributor give notice to renew?", monkeypatch)
    with SessionLocal() as session, pytest.raises(DatabaseError, match="immutable"):
        session.execute(Run.__table__.update().where(Run.id == detail["id"]).values(relations_json=None))
    assert client.get(f"/api/runs/{detail['id']}/detail").json()["relations"] == detail["relations"]
