"""A memo accounts for every proposal the run recorded (first-visitor acceptance test, 2026-10-14).

On an amended PDF uploaded by a fresh visitor, the model answered the renewal-window question from the superseded clause;
its quote was not found and code withheld the answer. The memo left withheld proposals out entirely and printed "No
automated check flagged a finding" over the one finding that remained (outside the
repository). The invariant: the memo says no automated check flagged anything only when nothing of the run, withheld
proposals included, is flagged; a withheld proposal is listed with code's reason and the model's sentence as the model's,
and its unfound quote is never printed.
"""

from __future__ import annotations

import io
import json
import re
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.memo.service import FLAGS_HEAD, NO_FLAGS, WITHHELD_HEAD
from app.providers.base import Generation
from tests.support import CONTRACT, GUIDANCE, FakeProvider

QUESTION = "How much notice does the customer need to give to terminate for convenience?"
UNFOUND = "Customer may renew for two years on notice given 210 days before the Expiry Date."
WITHHELD_SENTENCE = "The renewal window opens 210 days before the Expiry Date."


class WithheldProvider(FakeProvider):
    """The well-behaved answer, plus ``extra`` proposals whose quotes are not in the contract."""

    def __init__(self, extra: int = 1) -> None:
        super().__init__()
        self.extra = extra

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        payload = json.loads(super().generate_json(system, user, schema).text)
        for n in range(self.extra):
            payload["findings"].append(
                {
                    "topic": f"Renewal window {n + 1}",
                    "conclusion": WITHHELD_SENTENCE,
                    "status_hint": "pass",
                    "evidence": [{"section_id": "sec_1", "quote": UNFOUND}],
                    "guidance_reference": None,
                    "observed": "210 days",
                    "required": None,
                    "suggested_position": None,
                }
            )
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def _ask(client: TestClient, provider: FakeProvider, guidance: str | None) -> str:
    client.app.state.provider = provider  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    guidance_id = client.post("/api/guidance", json={"text": guidance}).json()["id"] if guidance else None
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": guidance_id, "question": QUESTION})
    assert started.status_code == 202, started.text
    return str(started.json()["id"])


def _memo(client: TestClient, run_id: str) -> tuple[str, str]:
    memo = client.post("/api/memos", json={"runId": run_id}).json()
    html = client.get(f"/api/memos/{memo['id']}/html").text.replace("&#x27;", "'")
    docx_bytes = client.get(f"/api/memos/{memo['id']}/docx").content
    words = "\n".join(p.text for p in Document(io.BytesIO(docx_bytes)).paragraphs)
    return html, words


def _texts(client: TestClient, run_id: str) -> tuple[str, str]:
    """The memo's words, both forms: the HTML without its tags, the DOCX's paragraphs."""
    html, words = _memo(client, run_id)
    return re.sub(r"<[^>]+>", "", html), words


def test_the_acceptance_case_a_withheld_answer_is_listed_flagged_and_never_quoted(client: TestClient) -> None:
    run_id = _ask(client, WithheldProvider(), guidance=None)  # the shown finding is a plain answer: nothing else flags
    detail = client.get(f"/api/runs/{run_id}/detail").json()
    assert detail["stage"] == "complete" and len(detail["withheld"]) == 1
    for text in _texts(client, run_id):
        assert NO_FLAGS.split(".")[0] not in text
        assert f"{FLAGS_HEAD} (1)" in text and "Renewal window 1 (withheld)" in text
        assert f"{WITHHELD_HEAD} (1)" in text and f"The model wrote, withheld: {WITHHELD_SENTENCE}" in text
        assert "Why withheld. no quote of it was found in the sections handed to the model" in text
        assert UNFOUND not in text  # every quote a memo prints was found in the document


@pytest.mark.parametrize(
    ("extra", "guidance"),
    [(0, None), (1, None), (2, None), (0, GUIDANCE), (1, GUIDANCE)],
)
def test_no_automated_flag_is_said_only_when_nothing_of_the_run_is_flagged(client: TestClient, extra: int, guidance: str | None) -> None:
    run_id = _ask(client, WithheldProvider(extra), guidance)
    detail = client.get(f"/api/runs/{run_id}/detail").json()
    flagged = [f for f in detail["findings"] if f["flagged"]]  # the API's findings carry the withheld proposals too
    for text in _texts(client, run_id):
        assert (NO_FLAGS.split(".")[0] in text) == (not flagged)
        assert f"{FLAGS_HEAD} ({len(flagged)})" in text


def test_control_the_pack_and_the_memo_flag_the_same_proposals(client: TestClient) -> None:
    import zipfile

    run_id = _ask(client, WithheldProvider(2), GUIDANCE)
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/evidence-pack").content)) as archive:
        packed = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith("findings.json"))))
    html, _ = _memo(client, run_id)
    for record in packed:
        title = f"{record['topic']} (withheld)" if record["decided_by"] == "withheld" else record["topic"]
        assert (f"<li>{title}" in html) == record["flagged"], record["topic"]


class NotFoundAndWithheld(WithheldProvider):
    """A not-found finding (whose own sentence the memo prints as "The model also wrote") beside a withheld proposal:
    the two must not be confused (a local of the memo once shared the withheld proposals' name)."""

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        payload = json.loads(super().generate_json(system, user, schema).text)
        quote = payload["findings"][0]["evidence"][0]
        payload["findings"].append(
            {
                "topic": "Most favoured nation",
                "conclusion": "The agreement contains no most favoured nation clause.",
                "status_hint": "missing",
                "evidence": [quote],
                "guidance_reference": None,
                "observed": None,
                "required": None,
                "suggested_position": None,
            }
        )
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def test_a_not_found_finding_and_a_withheld_proposal_are_each_said_as_what_they_are(client: TestClient) -> None:
    run_id = _ask(client, NotFoundAndWithheld(), guidance=None)
    detail = client.get(f"/api/runs/{run_id}/detail").json()
    assert {f["status"] for f in detail["findings"]} >= {"missing", "unresolved"}
    for text in _texts(client, run_id):
        assert f"{WITHHELD_HEAD} (1)" in text and f"The model wrote, withheld: {WITHHELD_SENTENCE}" in text
        assert "Most favoured nation" in text and "The model also wrote" in text and UNFOUND not in text


def test_the_runs_list_says_how_many_answers_were_withheld(client: TestClient) -> None:
    # The receipt names the withheld proposals; the list of runs counted only the shown findings, so a run with two
    # answers withheld read as a run of one (stress test, 2026-10-30, wave 2).
    run_id = _ask(client, WithheldProvider(extra=2), guidance=None)
    summary = next(r for r in client.get("/api/runs").json() if r["id"] == run_id)
    assert (summary["findings"], summary["withheld"]) == (1, 2)
    assert summary["withheld"] == len(client.get(f"/api/runs/{run_id}").json()["withheld"])


def test_control_a_run_with_nothing_withheld_says_none(client: TestClient) -> None:
    run_id = _ask(client, FakeProvider(), guidance=None)
    summary = next(r for r in client.get("/api/runs").json() if r["id"] == run_id)
    assert (summary["findings"], summary["withheld"]) == (1, 0)
