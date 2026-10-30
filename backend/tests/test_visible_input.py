"""A name, a question and guidance are stored only when something in them can be seen (stress test, 2026-10-30,
journeys 3).

Each was tested for emptiness after visible_text(...).strip(), which removes format characters and spaces but keeps,
deliberately, characters text needs that render nothing on their own: joiners, direction marks, Hangul fillers,
variation selectors, a lone combining mark. A reviewer of only those was recorded ("Confirmed by ‍ on ..."), a
reviewer of only spaces or zero-width spaces was recorded with an empty name, and such a question started a run and
such guidance was saved, the empty-guidance failure of 2026-09-29 by another road. Now each is refused with 422 and
nothing is written, while real names and questions in any script pass unchanged.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.application.visible_input import has_visible_text
from app.db import SessionLocal
from app.models import FindingReview, Guidance, Run
from tests.support import upload_and_ask

INVISIBLE = [
    "   ",
    "​",
    "⁠ ⁠",
    "﻿­",
    "‍",
    "‌",
    "‎",
    "‏",
    "؜",
    "ㅤ",
    "ᅟ",
    "️",
    "͏",
    "⠀",
    "́",
    "‍ ‎",
    "　 ",
]
VISIBLE = ["Pat", "José", "José", "李雷", "محمد؜", "देव", "\U0001f469‍⚖️", "a"]


@pytest.mark.parametrize("text", INVISIBLE)
def test_text_that_renders_nothing_has_no_visible_text(text: str) -> None:
    assert not has_visible_text(text)


@pytest.mark.parametrize("text", VISIBLE)
def test_control_names_in_any_script_have_visible_text(text: str) -> None:
    assert has_visible_text(text)


def _count(model: type[FindingReview] | type[Run] | type[Guidance]) -> int:
    with SessionLocal() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.parametrize("text", INVISIBLE)
def test_a_reviewer_question_or_guidance_that_shows_nothing_is_refused_and_writes_nothing(client: TestClient, text: str) -> None:
    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    finding = result["run"]["findings"][0]["id"]
    reviews, runs, guidance = _count(FindingReview), _count(Run), _count(Guidance)
    decided = client.post(f"/api/findings/{finding}/review", json={"verdict": "confirmed", "reviewer": text, "note": None, "basedOn": 0})
    asked = client.post("/api/runs", json={"documentId": result["document"]["id"], "guidanceId": None, "question": text})
    saved = client.post("/api/guidance", json={"text": text})
    assert (decided.status_code, asked.status_code, saved.status_code) == (422, 422, 422)
    assert (_count(FindingReview), _count(Run), _count(Guidance)) == (reviews, runs, guidance)


def test_control_a_real_name_and_an_invisible_note_are_recorded(client: TestClient) -> None:
    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    finding = result["run"]["findings"][0]["id"]
    decided = client.post(f"/api/findings/{finding}/review", json={"verdict": "confirmed", "reviewer": "José", "note": "‍", "basedOn": 0})
    assert decided.status_code == 201
    review = decided.json()["review"]
    assert review["reviewer"] == "José" and review["note"] is None, "a note that shows nothing is no note"
