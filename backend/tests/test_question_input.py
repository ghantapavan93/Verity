"""A question is what is left once invisible characters are removed (application.start_run).

Adversarial QA, 2026-10-15: a question of two zero-width spaces passed the length check, was stored empty and cost a
model call; the card showed an empty QUESTION heading over three answers to nothing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.support import FakeProvider

AGREEMENT = "SERVICES AGREEMENT\n\n1. PAYMENT\n\n1.1 Customer shall pay each invoice within thirty (30) days."


def _document(client: TestClient) -> str:
    return str(client.post("/api/documents", files={"file": ("services.txt", AGREEMENT.encode("utf-8"), "text/plain")}).json()["id"])


@pytest.mark.parametrize("question", ["​​", "​ ﻿ ⁠", "­"])
def test_a_question_with_no_visible_text_is_refused_and_asks_no_model(client: TestClient, question: str) -> None:
    provider = FakeProvider()
    client.app.state.provider = provider  # type: ignore[attr-defined]
    response = client.post("/api/runs", json={"documentId": _document(client), "guidanceId": None, "question": question})
    assert response.status_code == 422, response.text
    assert provider.calls == [] and client.get("/api/runs").json() == []


def test_control_a_question_with_invisible_characters_around_words_is_asked_without_them(client: TestClient) -> None:
    client.app.state.provider = FakeProvider()  # type: ignore[attr-defined]
    response = client.post("/api/runs", json={"documentId": _document(client), "guidanceId": None, "question": "​When is payment due?​"})
    assert response.status_code == 202, response.text
    assert client.get(f"/api/runs/{response.json()['id']}/detail").json()["question"] == "When is payment due?"
