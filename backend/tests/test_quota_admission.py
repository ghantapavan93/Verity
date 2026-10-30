"""A quota is counted, and the row it limits is written, in one transaction no concurrent request can interleave.

War room F-13 / R10 (2026-10-13), confirmed by two independent reruns: every quota the store counts was check-then-insert.
`admit_upload` counted a workspace's documents before its upload was read and the grant was written after, so sixteen
uploads at once from one visitor were all held against a cap of ten; the daily run ceiling was counted before the run's
insert, and eight of ten starts released together got past a ceiling of three. In the cloud that ceiling (15 a day) is
the spend stop for a paid GPU.

The class is every quota counted in SQL before a write (application/quotas.py): the documents a public workspace holds,
the uploads every public workspace makes in a UTC day, the questions a public workspace asks in a day, and the new runs
every reader starts in a day. Each has a property test (N requests released together, over repeated trials: exactly the
cap accepted, the rest 429, never anything else) and a control (one at a time: exactly the cap, then 429). The original
reproductions are kept as they were found (ENG-01, ENG-01b, ENG-01c).
"""

from __future__ import annotations

import itertools
import sqlite3
import threading
import time
from collections.abc import Callable
from functools import partial

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config
from app import db as db_module
from app.api import access
from app.application import ingest_document as ingest_module
from app.application.workspace import PUBLIC_PREFIX
from app.db import SessionLocal
from app.ingest import Ingested
from app.ingest import ingest as read_contract
from app.models import DocumentAccess, Run
from tests.support import CONTRACT
from tests.test_anonymous import Visitor, arrive

QUESTION = "How much notice does the customer need to give to terminate for convenience?"
QUESTIONS = tuple(QUESTION if n == 0 else f"{QUESTION} ({n})" for n in range(6))  # six questions, each its own run
TRIALS = 4
_bytes_made = itertools.count()
_addresses_made = itertools.count(1)


@pytest.fixture(autouse=True)
def uploads_at_once_lifted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The door's cap on each network's uploads in flight (api/body_limit.py, tested in test_body_limit.py) is lifted:
    the bursts here come from one network and are larger than it, and what they test is the quota behind it."""
    from app.api import body_limit

    monkeypatch.setattr(body_limit, "UPLOADS_PER_NETWORK", 1000)


@pytest.fixture
def windows_lifted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-address and per-reader windows (api/access.py: in memory, checked and recorded under one lock, so not in
    this class) are lifted, so that what refuses a request here is the quota under test and nothing else."""
    for window in (access.visits, access.address_uploads, access.address_runs, access.run_starts):
        monkeypatch.setattr(window, "limit", 1_000_000)


def _new_visitor(client: TestClient) -> Visitor:
    """A browser from an address of its own (the visit window is per address)."""
    index = next(_addresses_made)
    visitor, _ = arrive(client, address=f"10.{index // 65536 % 256}.{index // 256 % 256}.{index % 256}")
    return visitor


def _new_bytes() -> bytes:
    """A contract no upload in this process has sent before, so every upload is a new document."""
    return f"{CONTRACT}\nVariant {next(_bytes_made)}.".encode()


def _upload(visitor: Visitor, body: bytes) -> int:
    return visitor.post("/api/documents", files={"file": ("contract.txt", body, "text/plain")}).status_code


def _upload_new(visitor: Visitor) -> int:
    return _upload(visitor, _new_bytes())


def _ask(visitor: Visitor, document_id: str, question: str) -> int:
    return visitor.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": question}).status_code


def _with_document(client: TestClient) -> tuple[Visitor, str]:
    visitor = _new_visitor(client)
    response = visitor.post("/api/documents", files={"file": ("contract.txt", _new_bytes(), "text/plain")})
    assert response.status_code == 201, response.text
    return visitor, str(response.json()["id"])


def _released_together(calls: list[Callable[[], int]]) -> list[int]:
    """Every call on its own thread, all released at once by a barrier; their status codes, sorted. An exception in a
    thread is reported as -1, so a failure is never lost."""
    go = threading.Barrier(len(calls))
    codes: list[int] = []
    guard = threading.Lock()

    def one(call: Callable[[], int]) -> None:
        go.wait()
        try:
            code = call()
        except Exception:  # noqa: BLE001 - reported as a code the assertions refuse
            code = -1
        with guard:
            codes.append(code)

    threads = [threading.Thread(target=one, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(codes)


def _grants(workspace_prefix: str | None = None, visitor: Visitor | None = None) -> int:
    with SessionLocal() as session:
        query = select(func.count()).select_from(DocumentAccess)
        if visitor is not None:
            query = query.where(DocumentAccess.workspace_id == access.workspace_for(visitor.subject))
        elif workspace_prefix is not None:
            query = query.where(DocumentAccess.workspace_id.like(f"{workspace_prefix}%"))
        return int(session.scalar(query) or 0)


def _runs(visitor: Visitor | None = None) -> int:
    with SessionLocal() as session:
        query = select(func.count(Run.id)).where(Run.workspace_id.isnot(None))
        if visitor is not None:
            query = query.where(Run.workspace_id == access.workspace_for(visitor.subject))
        return int(session.scalar(query) or 0)


def _slow_reading(monkeypatch: pytest.MonkeyPatch, seconds: float = 0.3) -> None:
    """A reading of a real contract takes seconds (docs/archive/PARSER-COMPARISON.md); this one takes a fraction, which is
    enough to hold every upload of a burst between its first count and its write."""

    def slow_ingest(name: str, data: bytes, *, wait: float | None = None) -> Ingested:
        time.sleep(seconds)
        return read_contract(name, data)

    monkeypatch.setattr(ingest_module, "read_file", slow_ingest)  # the one way the application reads (ingest/bounded.py)


# ---------------------------------------------------------------------------- documents a public workspace holds


@pytest.mark.usefixtures("windows_lifted")
def test_eng01_concurrent_uploads_from_one_visitor_hold_exactly_the_cap(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """ENG-01 as found: six uploads at once from one visitor against a cap of two were all held."""
    monkeypatch.setattr(config.settings, "anonymous_max_documents", 2)
    _slow_reading(monkeypatch)
    for trial in range(TRIALS):
        visitor = _new_visitor(public)
        codes = _released_together([partial(_upload_new, visitor) for _ in range(6)])
        held = len(visitor.get("/api/documents").json())
        assert codes == [201, 201, 429, 429, 429, 429] and held == 2, (trial, codes, held)


@pytest.mark.usefixtures("windows_lifted")
def test_eng01b_sixteen_uploads_at_once_are_held_to_the_default_cap(public: TestClient) -> None:
    """ENG-01b as found: the real reader, the default cap of ten, sixteen uploads at once from one browser: sixteen held."""
    cap = config.settings.anonymous_max_documents
    for trial in range(TRIALS):
        visitor = _new_visitor(public)
        codes = _released_together([partial(_upload_new, visitor) for _ in range(cap + 6)])
        held = _grants(visitor=visitor)
        assert codes == [201] * cap + [429] * 6 and held == cap, (trial, codes, held)


def test_control_uploads_one_at_a_time_stop_at_the_cap(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_max_documents", 2)
    visitor = _new_visitor(public)
    bodies = [_new_bytes() for _ in range(5)]
    assert [_upload(visitor, body) for body in bodies] == [201, 201, 429, 429, 429]
    assert _grants(visitor=visitor) == 2


def test_control_uploading_a_held_document_again_spends_nothing(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same bytes again are handed the stored reading (200) and add no grant: below the cap they are not refused."""
    monkeypatch.setattr(config.settings, "anonymous_max_documents", 3)
    visitor = _new_visitor(public)
    body = _new_bytes()
    assert [_upload(visitor, body) for _ in range(3)] == [201, 200, 200]
    assert _upload(visitor, _new_bytes()) == 201 and _upload(visitor, _new_bytes()) == 201
    assert _grants(visitor=visitor) == 3


# ---------------------------------------------------------------------------- uploads a day, every public workspace


@pytest.mark.usefixtures("windows_lifted")
def test_concurrent_uploads_from_many_visitors_stop_at_the_days_uploads(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _slow_reading(monkeypatch, 0.1)
    for trial in range(TRIALS):
        visitors = [_new_visitor(public) for _ in range(8)]
        cap = _grants(workspace_prefix=PUBLIC_PREFIX) + 3  # three more today, whatever earlier trials left
        monkeypatch.setattr(config.settings, "anonymous_max_uploads_per_day", cap)
        codes = _released_together([partial(_upload_new, visitor) for visitor in visitors])
        assert codes == [201] * 3 + [429] * 5 and _grants(workspace_prefix=PUBLIC_PREFIX) == cap, (trial, codes)


def test_control_uploads_from_many_visitors_one_at_a_time_stop_at_the_days_uploads(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_max_uploads_per_day", 2)
    assert [_upload(_new_visitor(public), _new_bytes()) for _ in range(4)] == [201, 201, 429, 429]
    assert _grants(workspace_prefix=PUBLIC_PREFIX) == 2


# ---------------------------------------------------------------------------- questions a public workspace asks in a day


@pytest.mark.usefixtures("windows_lifted")
def test_concurrent_questions_from_one_workspace_stop_at_its_days_questions(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "anonymous_max_runs_per_day", 2)
    monkeypatch.setattr(config.settings, "max_runs_per_day", 0)  # no global ceiling: the workspace's own bound is the one tested
    for trial in range(TRIALS):
        visitor, document_id = _with_document(public)
        codes = _released_together([partial(_ask, visitor, document_id, question) for question in QUESTIONS])
        assert codes == [202, 202, 429, 429, 429, 429] and _runs(visitor) == 2, (trial, codes)


def test_control_questions_one_at_a_time_stop_at_the_workspaces_day_and_a_repeat_is_handed_its_run(
    public: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly the cap, then 429; a question asked before creates no run and calls no model, so it is handed its run
    at the cap, as it already was at the global ceiling (test_daily_budget.py)."""
    monkeypatch.setattr(config.settings, "anonymous_max_runs_per_day", 2)
    monkeypatch.setattr(config.settings, "max_runs_per_day", 0)
    visitor, document_id = _with_document(public)
    assert [_ask(visitor, document_id, question) for question in QUESTIONS[:4]] == [202, 202, 429, 429]
    assert _ask(visitor, document_id, QUESTIONS[0]) == 200
    assert _runs(visitor) == 2


# ---------------------------------------------------------------------------- new runs a day, every reader


@pytest.mark.usefixtures("windows_lifted")
def test_eng01c_concurrent_starts_stop_at_the_global_daily_ceiling(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """ENG-01c as found: ten visitors released together against a ceiling of three; eight runs were started."""
    for trial in range(TRIALS):
        askers = [_with_document(public) for _ in range(10)]
        cap = _runs() + 3
        monkeypatch.setattr(config.settings, "max_runs_per_day", cap)
        codes = _released_together([partial(_ask, visitor, document_id, QUESTION) for visitor, document_id in askers])
        assert codes == [202] * 3 + [429] * 7 and _runs() == cap, (trial, codes)


def test_control_starts_one_at_a_time_stop_at_the_global_daily_ceiling(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "max_runs_per_day", 2)
    askers = [_with_document(public) for _ in range(4)]
    assert [_ask(visitor, document_id, QUESTION) for visitor, document_id in askers] == [202, 202, 429, 429]
    assert _runs() == 2


# ---------------------------------------------------------------------------- no new failure: a writer waits, it does not fail


def test_a_start_and_an_upload_wait_out_a_long_write_and_succeed(client: TestClient) -> None:
    """Another connection holds the store's write lock for two seconds, as a large ingest does: a question and an
    upload made meanwhile wait for it (the 30 s busy wait) and succeed. Nothing deadlocks; nothing answers 500."""
    document_id = client.post("/api/documents", files={"file": ("a.txt", _new_bytes(), "text/plain")}).json()["id"]
    path = db_module.engine.url.database
    assert path is not None
    holder = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    holder.execute("BEGIN IMMEDIATE")
    released = threading.Timer(2.0, lambda: holder.execute("COMMIT"))
    released.start()
    try:
        began = time.perf_counter()
        codes = _released_together(
            [
                lambda: client.post("/api/runs", json={"documentId": document_id, "guidanceId": None, "question": QUESTION}).status_code,
                lambda: client.post("/api/documents", files={"file": ("b.txt", _new_bytes(), "text/plain")}).status_code,
            ]
        )
        waited = time.perf_counter() - began
    finally:
        released.join()
        holder.close()
    assert codes == [201, 202] and waited >= 1.5, (codes, waited)
