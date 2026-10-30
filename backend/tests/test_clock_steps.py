"""A visit's life does not depend on the clock stepping (stress test, 2026-10-30, time 3 and time 4).

Two invariants, both about a public visitor's workspace:

- a session opens its workspace for the workspace's whole life: verify() refused a session whose issued-at time was more
  than 60 s ahead of the clock, so a step back of more than the session's age plus 60 s refused every open visit, and
  the page's reload swapped the cookie for an empty workspace (time 4);
- what a visit added is deleted 7 days after it began, plus the hourly pass: a visit made while the clock ran 30 days
  ahead kept its expiry 37 days out once the clock was corrected, so its rows lived to real day 37 (time 3).

The clock is wall time and it can step (Windows Secure Time Seeding is on on the live host). Nothing on the wall clock
alone can tell a visit made while the clock ran ahead from a clock that stepped back after a visit: both leave a visit
that began after now. The store's answer: such a visit is counted from now, its life kept whole and never cut (a step
back deletes nothing), so a visit lives at most its 7 days plus the time the clock ran ahead plus one pass.

The whole app's clock is moved here, as a step moves it: every utcnow (through app.models.datetime) and the token
check's time.time (through access.time). Nothing sleeps.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import db as db_module
from app import models
from app.api import access
from app.api.access import mint, verify
from app.application.retention import purge_expired_workspaces
from app.db import SessionLocal
from app.models import DocumentAccess, VisitorWorkspace
from tests.support import CONTRACT
from tests.test_access import SECRET
from tests.test_anonymous import Visitor, arrive

DAY = 86400.0


class Clock:
    """The app's wall clock, `offset` seconds from the real one."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.offset = 0.0
        real_time = time.time
        clock = self

        class Shifted(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
                return datetime.fromtimestamp(real_time() + clock.offset, tz)  # type: ignore[arg-type]

        monkeypatch.setattr(models, "datetime", Shifted)
        monkeypatch.setattr(access, "time", SimpleNamespace(time=lambda: real_time() + clock.offset, monotonic=time.monotonic))

    def step(self, seconds: float) -> None:
        self.offset += seconds


def _rows() -> tuple[int, int]:
    with SessionLocal() as session:
        return (
            session.scalar(select(func.count()).select_from(VisitorWorkspace)) or 0,
            session.scalar(select(func.count()).select_from(DocumentAccess)) or 0,
        )


def _visit_and_upload(public: TestClient) -> Visitor:
    visitor, _ = arrive(public)
    assert visitor.post("/api/documents", files={"file": ("a.txt", CONTRACT.encode(), "text/plain")}).status_code == 201
    return visitor


@pytest.mark.parametrize("back_s", [61, 300, 3600, DAY])
def test_a_step_back_keeps_an_open_workspace_open(public: TestClient, monkeypatch: pytest.MonkeyPatch, back_s: float) -> None:
    clock = Clock(monkeypatch)
    visitor = _visit_and_upload(public)
    clock.step(120)  # the visitor reads for two minutes
    clock.step(-back_s)
    listed = visitor.get("/api/documents")
    assert listed.status_code == 200 and len(listed.json()) == 1
    _, response = arrive(public, cookie=visitor.cookie)
    assert "set-cookie" not in response.headers, "the page's reload keeps the workspace it has"
    purge_expired_workspaces(db_module.engine, gap_s=0.0)
    assert _rows() == (1, 1), "a step back deletes nothing"
    assert visitor.get("/api/documents").status_code == 200


def test_a_visit_made_while_the_clock_ran_ahead_ends_its_seven_days_after_the_correction(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The finder's case: the clock 30 days ahead, a visit and an upload, the clock corrected an hour later."""
    clock = Clock(monkeypatch)
    clock.step(30 * DAY)
    visitor = _visit_and_upload(public)
    clock.step(-30 * DAY + 3600)  # corrected; an hour has passed
    assert visitor.get("/api/documents").status_code == 200, "the visitor's session still opens its workspace"
    purge_expired_workspaces(db_module.engine, gap_s=0.0)  # the first pass after the correction
    assert _rows() == (1, 1)
    clock.step(7 * DAY - 120)
    purge_expired_workspaces(db_module.engine, gap_s=0.0)
    assert _rows() == (1, 1), "control: not before its seven days"
    clock.step(3600)  # one pass later
    purge_expired_workspaces(db_module.engine, gap_s=0.0)
    assert _rows() == (0, 0), "seven days and a pass after the correction, not real day 37"


def test_a_small_step_back_just_after_a_visit_neither_deletes_nor_shortens_it(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 30 s NTP step 10 s after a visit: inside the tolerance the token check already gives, nothing moves."""
    clock = Clock(monkeypatch)
    visitor = _visit_and_upload(public)
    with SessionLocal() as session:
        before = session.scalars(select(VisitorWorkspace.expires_at)).one()
    clock.step(10 - 30)
    purge_expired_workspaces(db_module.engine, gap_s=0.0)
    with SessionLocal() as session:
        assert session.scalars(select(VisitorWorkspace.expires_at)).one() == before
    assert visitor.get("/api/documents").status_code == 200


def test_control_a_steady_clock_deletes_a_visit_on_its_seventh_day(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock(monkeypatch)
    _visit_and_upload(public)
    clock.step(7 * DAY - 60)
    purge_expired_workspaces(db_module.engine, gap_s=0.0)
    assert _rows() == (1, 1)
    clock.step(120)
    purge_expired_workspaces(db_module.engine, gap_s=0.0)
    assert _rows() == (0, 0)


# ---------------------------------------------------------------------------- the token check


@pytest.mark.parametrize("read_at", [-30 * DAY, -3600.0, -61.0, 0.0, 3599.0])
def test_property_a_session_is_good_until_it_expires_whatever_the_clock_read_when_it_was_made(read_at: float) -> None:
    """For a session the server minted at t0 with lifetime L, any reading c < t0 + L, far before t0 included, opens it:
    the MAC proves the server made it, and expiry and the workspace's row decide its life."""
    t0 = 1_800_000_000.0
    token = mint("anon-x", "verity-session", 3600, SECRET, now=t0)
    found = verify(token, "verity-session", SECRET, now=t0 + read_at)
    assert found is not None and found.subject == "anon-x"


def test_controls_an_expired_forged_or_misdirected_session_opens_nothing() -> None:
    t0 = 1_800_000_000.0
    token = mint("anon-x", "verity-session", 3600, SECRET, now=t0)
    body, mac = token.rsplit(".", 1)
    assert verify(token, "verity-session", SECRET, now=t0 + 3600) is None
    assert verify(f"{body}.{'0' * len(mac)}", "verity-session", SECRET, now=t0) is None
    assert verify(token, "verity-invite", SECRET, now=t0) is None


def test_an_invite_dated_ahead_of_the_clock_is_still_refused() -> None:
    """Kept for invites, which scripts/access.py mints outside this process: a not-before the minter wrote is honoured.
    The cost, recorded: after a step back, an invite minted on the same host in the last (step - 60 s) is refused until
    the clock catches up."""
    t0 = 1_800_000_000.0
    assert verify(mint("didier", "verity-invite", 3600, SECRET, now=t0 + 61), "verity-invite", SECRET, now=t0) is None
    assert verify(mint("didier", "verity-invite", 3600, SECRET, now=t0 + 59), "verity-invite", SECRET, now=t0) is not None


def test_the_shared_tolerance_is_one_definition() -> None:
    now = datetime(2026, 10, 30, 15, tzinfo=UTC)
    assert not models.issued_in_future(now + models.CLOCK_SKEW, now)
    assert models.issued_in_future(now + models.CLOCK_SKEW + timedelta(microseconds=1), now)
    assert models.CLOCK_SKEW.total_seconds() == access.CLOCK_SKEW_S
