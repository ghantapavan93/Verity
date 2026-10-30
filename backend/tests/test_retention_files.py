"""One file a pass cannot remove never stops the pass, and a file in use is judged by what this process saw, not by a
clock that can step (stress test, 2026-10-30, time 6).

Every per-file step in the purge and the sweep went through a stat and an unlink that caught only FileNotFoundError.
Windows refuses to delete a file another handle holds (a pack being read, a trust re-read, an antivirus scan): the
PermissionError ended the pass, and every file after it in documents/, the memos, the pending drafts and the handoff
files stayed for the hour; after a purge's commit it skipped the memo deletions and the checkpoint the secure delete
depends on. A file renamed between the folder listing and its stat aborted 6 of 1,102 passes against a busy writer.

And the sweep's grace was a file's mtime against the wall clock: after a forward step of more than an hour, a partial
upload being written looked abandoned. A file is now abandoned when it has been seen unchanged for the grace by this
process's monotonic clock, or, while the wall clock has not stepped since the process started, when its mtime is past
the grace.

Faults are injected at the file calls, so the tests say the same on every platform; the monotonic clock is set, not
waited for.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app import db as db_module
from app.application import retention
from app.application.retention import purge_expired_workspaces, sweep_orphaned_files
from app.models import utcnow
from tests.support import CONTRACT
from tests.test_anonymous import arrive
from tests.test_retention import end


def _old(path: Path, data: bytes = b"left behind") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    then = time.time() - 2 * 3600
    os.utime(path, (then, then))
    return path


def _refuse(monkeypatch: pytest.MonkeyPatch, held: set[Path], call: str = "unlink", error: type[OSError] = PermissionError) -> None:
    """``call`` on any path in ``held`` fails as Windows fails it for a file another handle holds."""
    real = getattr(Path, call)

    def guarded(self: Path, *args: object, **kwargs: object) -> object:
        if self in held:
            raise error(13, "The process cannot access the file because it is being used by another process", str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, call, guarded)


@pytest.fixture
def leftovers(public: TestClient) -> dict[str, Path]:
    data = config.settings.data_dir
    from app.ingest import bounded

    return {
        "first": _old(data / "documents" / ("0" * 64 + ".txt")),
        "held": _old(data / "documents" / ("8" * 64 + ".txt")),
        "last": _old(data / "documents" / ("f" * 64 + ".txt")),
        "memo": _old(data / "memos" / "memo-left.docx"),
        "draft": _old(data / "memos" / "pending" / ("a" * 32) / "memo-run.docx"),
        "handoff": _old(bounded.handoff_folder(data) / f"{bounded.HANDOFF_PREFIX}left"),
    }


def _age_folder(path: Path) -> None:
    then = time.time() - 2 * 3600
    os.utime(path, (then, then))


def _there(path: Path) -> bool:
    return os.path.exists(path)  # not Path.exists, which goes through the Path.stat a test refuses


def test_a_file_the_system_will_not_delete_is_kept_and_the_pass_goes_on(leftovers: dict[str, Path]) -> None:
    _age_folder(leftovers["draft"].parent)
    with pytest.MonkeyPatch.context() as faults:
        _refuse(faults, {leftovers["held"]})
        removed = sweep_orphaned_files(db_module.engine)
    assert removed == 5
    assert _there(leftovers["held"])
    assert not any(_there(leftovers[name]) for name in ("first", "last", "memo", "draft", "handoff"))
    assert sweep_orphaned_files(db_module.engine) == 1, "released, it goes at the next pass"


def test_a_file_that_vanishes_between_the_listing_and_its_stat_does_not_end_the_pass(leftovers: dict[str, Path]) -> None:
    with pytest.MonkeyPatch.context() as faults:
        _refuse(faults, {leftovers["first"]}, call="stat", error=FileNotFoundError)
        sweep_orphaned_files(db_module.engine)
    assert not _there(leftovers["last"]) and not _there(leftovers["memo"]) and not _there(leftovers["handoff"])


def test_any_error_on_one_file_keeps_that_file_only(leftovers: dict[str, Path]) -> None:
    with pytest.MonkeyPatch.context() as faults:
        _refuse(faults, {leftovers["memo"]}, call="stat", error=OSError)
        sweep_orphaned_files(db_module.engine)
    assert _there(leftovers["memo"]) and not _there(leftovers["last"]) and not _there(leftovers["handoff"])


def test_a_purge_whose_file_is_held_deletes_its_rows_checkpoints_and_leaves_the_file_to_the_sweep(public: TestClient) -> None:
    visitor, _ = arrive(public)
    assert visitor.post("/api/documents", files={"file": ("a.txt", CONTRACT.encode(), "text/plain")}).status_code == 201
    original = next((config.settings.data_dir / "documents").glob("*.txt"))
    end(visitor)
    with pytest.MonkeyPatch.context() as faults:
        _refuse(faults, {original})
        report = purge_expired_workspaces(db_module.engine, gap_s=0.0)
    assert report.workspaces and report.documents == 1 and report.files == 0
    assert report.checkpointed and report.kept == 1, "the checkpoint ran; the held file is counted, not raised"
    assert _there(original)
    _age_folder(original)
    assert sweep_orphaned_files(db_module.engine) == 1 and not original.exists()


def test_a_failed_purge_does_not_skip_the_hour_s_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    swept: list[object] = []

    def purge_fails(_engine: object) -> None:
        raise PermissionError(13, "in use")

    async def one_pass(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(main, "purge_expired_workspaces", purge_fails)
    monkeypatch.setattr(main, "sweep_orphaned_files", swept.append)
    monkeypatch.setattr(asyncio, "sleep", one_pass)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._retain_hourly())
    assert swept, "the sweep ran although the purge failed"


# ---------------------------------------------------------------------------- in flight, whatever the wall clock did


class Clocks:
    """The wall clock `step` off the real one, and time passing on it and on the process's monotonic clock together."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, step: timedelta) -> None:
        self.wall, self.passed = utcnow() + step, 0.0
        start = time.monotonic()
        monkeypatch.setattr(retention, "_monotonic", lambda: start + self.passed)

    def advance(self, seconds: float) -> None:
        self.passed += seconds

    def now(self) -> datetime:
        return self.wall + timedelta(seconds=self.passed)


GRACE = retention.SWEEP_GRACE.total_seconds()


def test_after_a_forward_step_a_file_being_written_is_not_taken_for_abandoned(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The finder's case: a partial upload written a moment ago, and the wall clock now an hour and a minute ahead."""
    clocks = Clocks(monkeypatch, timedelta(minutes=61))
    documents = config.settings.data_dir / "documents"
    documents.mkdir(parents=True, exist_ok=True)
    partial = documents / ("e" * 64 + ".txt.1a2b3c4d.part")
    partial.write_bytes(b"an upload being written")
    assert sweep_orphaned_files(db_module.engine, now=clocks.now()) == 0
    assert partial.exists()
    clocks.advance(GRACE - 1)
    assert sweep_orphaned_files(db_module.engine, now=clocks.now()) == 0, "control: not before this process has seen it a whole grace"
    clocks.advance(2)
    assert sweep_orphaned_files(db_module.engine, now=clocks.now()) == 1, "seen unchanged for the grace: abandoned"
    assert not partial.exists()


def test_after_a_step_back_an_abandoned_file_still_goes_once_seen_for_the_grace(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    clocks = Clocks(monkeypatch, -timedelta(hours=3))  # the orphan's mtime now reads an hour "in the future"
    orphan = _old(config.settings.data_dir / "documents" / ("d" * 64 + ".txt"))
    assert sweep_orphaned_files(db_module.engine, now=clocks.now()) == 0
    clocks.advance(GRACE + 1)
    assert sweep_orphaned_files(db_module.engine, now=clocks.now()) == 1 and not orphan.exists()


def test_a_file_that_changes_is_seen_afresh(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    clocks = Clocks(monkeypatch, timedelta(hours=2))
    documents = config.settings.data_dir / "documents"
    documents.mkdir(parents=True, exist_ok=True)
    partial = documents / ("c" * 64 + ".txt.0f0f0f0f.part")
    partial.write_bytes(b"first bytes")
    sweep_orphaned_files(db_module.engine, now=clocks.now())
    clocks.advance(GRACE + 1)
    partial.write_bytes(b"first bytes and more")  # still being written
    assert sweep_orphaned_files(db_module.engine, now=clocks.now()) == 0 and partial.exists()


def test_control_with_the_wall_clock_where_it_was_a_file_past_the_grace_goes_in_one_pass(public: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    Clocks(monkeypatch, timedelta(0))
    orphan = _old(config.settings.data_dir / "documents" / ("b" * 64 + ".txt"))
    young = config.settings.data_dir / "documents" / ("a" * 64 + ".txt")
    young.write_bytes(b"just written")
    assert sweep_orphaned_files(db_module.engine) == 1 and not orphan.exists() and young.exists()
