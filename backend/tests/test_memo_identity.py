"""A memo handed back as the answer to a new request says what a memo written now would say (stress test, 2026-10-30).

A memo's identity was (run, review head), and the review head is the same function in every release: so no change to
the memo's wording, its flags or anything it projects (an account, a value check, a clause label) ever reached a memo
whose review state was unchanged. A store written under release-2026-10-12 was handed its old memo, "Issues requiring
review (0). None. Every finding was within guidance", for a finding the current account flags; curated runs refuse a
review, so theirs could never be replaced. A memo is now identified by what it says as well: asking again under the
same rules returns the same memo, and the first request after any rule that changes what it says writes a new one. A
memo already written is never rewritten: it is kept, and served by its own id, as it was.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.application.create_memo as create_memo_module
import app.memo.service as memo_service
from app import db as db_module
from app.application.create_memo import review_head
from app.db import SessionLocal, init_db
from app.models import Memo, Run
from app.runs.account import Account
from tests.support import upload_and_ask

QUESTION = "What notice is needed to terminate for convenience?"


def post(client: TestClient, run_id: str) -> tuple[int, str, str]:
    response = client.post("/api/memos", json={"runId": run_id})
    memo = response.json()
    return response.status_code, memo["id"], client.get(memo["htmlUrl"]).text


def test_a_change_to_the_memos_wording_reaches_the_next_request_and_the_old_memo_is_kept(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = upload_and_ask(client, QUESTION)["run_id"]
    status, first, html = post(client, run_id)
    assert status == 201 and "Flagged by automated checks" in html
    monkeypatch.setattr(memo_service, "FLAGS_HEAD", "Raised by the automated checks")
    status, second, html = post(client, run_id)
    assert status == 201 and second != first and "Raised by the automated checks" in html
    assert "Flagged by automated checks" in client.get(f"/api/memos/{first}/html").text, "the memo already written is as it was"
    assert post(client, run_id)[:2] == (200, second), "asked again under the same rules: the same memo"


def test_a_change_to_what_code_raises_reaches_the_next_request(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = upload_and_ask(client, QUESTION, with_guidance=False)["run_id"]
    status, first, html = post(client, run_id)
    assert status == 201 and "a concern a later rule raises" not in html
    real = create_memo_module.account_of

    def stricter(*args: object, **kwargs: object) -> Account:
        account = real(*args, **kwargs)  # type: ignore[arg-type]
        return replace(account, concerns=(*account.concerns, "a concern a later rule raises"))

    monkeypatch.setattr(create_memo_module, "account_of", stricter)
    status, second, html = post(client, run_id)
    assert status == 201 and second != first and "a concern a later rule raises" in html


def test_a_memo_written_under_earlier_rules_is_not_handed_back_as_current(client: TestClient) -> None:
    run_id = upload_and_ask(client, QUESTION)["run_id"]
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        assert run is not None
        # As a release before this one wrote it: the same run and review state, its own words, no content key.
        written = "<p>None. Every finding was within guidance.</p>"
        old = Memo(run_id=run_id, review_head=review_head(run), docx_path="memo-old.docx", docx_sha256="0" * 64, html=written)
        old.content_sha256 = None
        session.add(old)
        session.commit()
        old_id = old.id
    status, memo_id, html = post(client, run_id)
    assert status == 201 and memo_id != old_id and "Flagged by automated checks (1)" in html
    assert client.get(f"/api/memos/{old_id}/html").text == "<p>None. Every finding was within guidance.</p>"


def test_control_the_date_a_memo_is_asked_for_is_not_what_it_says(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = upload_and_ask(client, QUESTION)["run_id"]
    assert post(client, run_id)[0] == 201
    first = post(client, run_id)[1]

    class Tomorrow(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            return datetime(2031, 1, 2, 12, 0)

    monkeypatch.setattr(memo_service, "datetime", Tomorrow)
    assert post(client, run_id)[:2] == (200, first)


def test_a_store_kept_under_the_old_memo_index_takes_a_memo_under_new_rules(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = upload_and_ask(client, QUESTION)["run_id"]
    assert post(client, run_id)[0] == 201
    # The index a store made before this change keeps: one memo per (run, review head), whatever it says.
    with db_module.engine.begin() as connection:
        connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "ux_memos_run_review" ON memos (run_id, review_head)'))
    init_db(db_module.engine)  # what every start does to a store it opens
    monkeypatch.setattr(memo_service, "FLAGS_HEAD", "Raised by the automated checks")
    status, _, html = post(client, run_id)
    assert status == 201 and "Raised by the automated checks" in html
