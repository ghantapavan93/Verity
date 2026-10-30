"""Every daily quota opens again at the start of the next UTC day, and not before (stress test, 2026-10-30, mutation 6).

Three quotas count by day (application/quotas.py): uploads into every public workspace, one public workspace's
questions, and the readers' run ceiling. Each counts the rows made since day_start(), UTC midnight, and the refusals say
"try again tomorrow (UTC)" with a Retry-After to that moment. No test showed it: dropping any of the three day filters,
or moving the boundary to local midnight or a rolling 24 hours, passed every test that touches a quota. Shipped, such a
regression quietly ends the day's quota for good (thirty questions a workspace in all) while telling the reader to come
back tomorrow.

Finished runs are immutable, so the rows are made now and the quotas' clock is moved: to the last microsecond of
today, where a full quota still refuses (the control), then to the next midnight, where it must open.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import config
from app.application import quotas
from app.models import utcnow
from tests.support import upload_and_ask
from tests.test_quota_admission import _ask, _new_visitor, _upload_new, _with_document, windows_lifted

# What refuses a request here is the daily quota under test, not an hourly window.
pytestmark = pytest.mark.usefixtures(windows_lifted.__name__)


def _clock_at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(quotas, "utcnow", lambda: moment)


def _end_of_today() -> datetime:
    now = utcnow()
    return datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(days=1) - timedelta(microseconds=1)


def _next_midnight() -> datetime:
    return _end_of_today() + timedelta(microseconds=1)


def test_the_public_uploads_of_a_day_open_again_at_utc_midnight(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_max_uploads_per_day", 2)
    assert [_upload_new(_new_visitor(public)) for _ in range(2)] == [201, 201]
    _clock_at(monkeypatch, _end_of_today())
    assert _upload_new(_new_visitor(public)) == 429, "control: the day's uploads are spent until its end"
    _clock_at(monkeypatch, _next_midnight())
    assert _upload_new(_new_visitor(public)) == 201


def test_a_public_workspace_s_questions_of_a_day_open_again_at_utc_midnight(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_max_runs_per_day", 1)
    visitor, document_id = _with_document(public)
    assert _ask(visitor, document_id, "What notice applies?") == 202
    _clock_at(monkeypatch, _end_of_today())
    assert _ask(visitor, document_id, "Which law governs?") == 429, "control: the workspace's questions are spent until the day ends"
    _clock_at(monkeypatch, _next_midnight())
    assert _ask(visitor, document_id, "Which law governs?") == 202


def test_the_readers_run_ceiling_opens_again_at_utc_midnight(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    first = upload_and_ask(client, "What notice period applies to termination for convenience?", with_guidance=False)
    monkeypatch.setattr(config.settings, "max_runs_per_day", 1)
    ask = {"documentId": first["document"]["id"], "guidanceId": None, "question": "Which law governs?"}
    _clock_at(monkeypatch, _end_of_today())
    assert client.post("/api/runs", json=ask).status_code == 429, "control: the ceiling holds until the day ends"
    _clock_at(monkeypatch, _next_midnight())
    assert client.post("/api/runs", json=ask).status_code == 202


def test_the_ceiling_counts_every_visitor_by_the_same_day(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "max_runs_per_day", 1)
    first, first_document = _with_document(public)
    second, second_document = _with_document(public)
    assert _ask(first, first_document, "What notice applies?") == 202
    _clock_at(monkeypatch, _end_of_today())
    assert _ask(second, second_document, "What notice applies?") == 429
    _clock_at(monkeypatch, _next_midnight())
    assert _ask(second, second_document, "What notice applies?") == 202


@pytest.mark.parametrize("hour", [0, 1, 12, 23])
def test_the_day_starts_at_utc_midnight_and_retry_after_points_there(monkeypatch: pytest.MonkeyPatch, hour: int) -> None:
    # In UTC whatever the machine's zone, and the same calendar day, not the last 24 hours.
    _clock_at(monkeypatch, datetime(2026, 10, 30, hour, 0, 0, tzinfo=UTC))
    assert quotas.day_start() == datetime(2026, 10, 30, tzinfo=UTC)
    assert quotas.seconds_to_tomorrow() == (24 - hour) * 3600 + 1


# ---------------------------------------------------------------------------- the day's upload bytes
# Uploads were capped by count (300 a public day), not bytes: at 25 MB each the store could reach its 2 GiB floor in
# days, pausing every visitor's writes until retention (DECISIONS.md, 2026-10-30, open). Each document now records its
# size, and the day's new contracts in the public store together hold at most
# settings.anonymous_max_upload_bytes_per_day.


def _size(body: bytes) -> int:
    return len(body)


def test_the_public_day_takes_a_bounded_number_of_bytes_and_opens_again_at_midnight(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import Document
    from tests.test_quota_admission import _new_bytes, _upload

    bodies = [_new_bytes() for _ in range(3)]
    monkeypatch.setattr(config.settings, "anonymous_max_upload_bytes_per_day", _size(bodies[0]) + _size(bodies[1]) + _size(bodies[2]) // 2)
    assert [_upload(_new_visitor(public), body) for body in bodies[:2]] == [201, 201]
    with SessionLocal() as session:
        before = session.scalar(select(func.count()).select_from(Document))
    refused = _new_visitor(public).post("/api/documents", files={"file": ("contract.txt", bodies[2], "text/plain")})
    assert refused.status_code == 429 and "tomorrow" in refused.json()["detail"] and int(refused.headers["retry-after"]) > 0
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == before, "nothing was stored"
    assert _upload(_new_visitor(public), bodies[0]) in (200, 201), "control: bytes already held add none"
    _clock_at(monkeypatch, _next_midnight())
    assert _upload(_new_visitor(public), bodies[2]) == 201


def test_a_document_records_its_size(client: TestClient) -> None:
    from app.db import SessionLocal
    from app.models import Document

    body = b"SERVICES AGREEMENT\n\n1. Term\n\nThis Agreement runs for twelve months.\n"
    uploaded = client.post("/api/documents", files={"file": ("c.txt", body, "text/plain")}).json()
    with SessionLocal() as session:
        document = session.get(Document, uploaded["id"])
        assert document is not None and document.size_bytes == len(body)


def test_control_the_owner_store_takes_any_number_of_bytes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_quota_admission import _new_bytes

    monkeypatch.setattr(config.settings, "anonymous_max_upload_bytes_per_day", 1)
    codes = [client.post("/api/documents", files={"file": ("c.txt", _new_bytes(), "text/plain")}).status_code for _ in range(3)]
    assert codes == [201, 201, 201]
