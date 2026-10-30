"""The API's log has a bound: per line, per flood and in total (stress test, 2026-10-30).

Any request without a session wrote its whole path into the log, up to 65 KB a line, and nothing capped or rotated the
one file a process wrote for its whole life: one client sending 404s in a loop added about 4 GB an hour to the disk the
store shares, and a full disk fails every SQLite write. The bounds are at the sink every logger shares (app/log_sink.py).
"""

from __future__ import annotations

import logging
import random
import shutil
from collections import namedtuple
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import log_sink
from app.log_sink import FORMAT, MESSAGE_CHARS, TRACE_CHARS, BoundedFormatter, FloodShaping, SegmentedFileHandler


def _record(message: str, *args: object, name: str = "app", shape: str | None = None, exc: bool = False) -> logging.LogRecord:
    record = logging.LogRecord(name, logging.INFO, __file__, 1, message, args or None, None)
    if exc:
        try:
            raise RuntimeError("x" * (TRACE_CHARS * 2))
        except RuntimeError:
            import sys

            record.exc_info = sys.exc_info()
    if shape is not None:
        record.shape = shape
    return record


def test_control_an_ordinary_line_is_written_exactly_as_before() -> None:
    record = _record("request_id=%s method=%s path=%s status=%d duration_ms=%.0f", "abc", "GET", "/api/runs", 200, 12.0)
    assert BoundedFormatter().format(record) == logging.Formatter(FORMAT).format(record)


def test_a_long_message_is_cut_and_keeps_its_length() -> None:
    path = "/api/x" + "A" * 64000
    line = BoundedFormatter().format(_record("refused path=%s status=%d", path, 404))
    assert len(line) < MESSAGE_CHARS + 200
    assert f"len={len('refused path=' + path + ' status=404')}" in line


def test_a_traceback_is_cut_too() -> None:
    line = BoundedFormatter().format(_record("failed", exc=True))
    assert len(line) < MESSAGE_CHARS + TRACE_CHARS + 200 and "[cut, len=" in line


def test_a_line_break_in_a_message_cannot_forge_a_line() -> None:
    line = BoundedFormatter().format(_record("path=%s status=%d", "/api/x\n2026-10-30 INFO app: request_id=forged", 404))
    assert "\n" not in line and "\\n2026-10-30" in line


def test_a_flood_of_one_kind_is_shaped_and_the_next_line_says_how_much_was_left_out() -> None:
    now = [0.0]
    shaping = FloodShaping(per_minute=3, clock=lambda: now[0])
    kept = [shaping.filter(_record("status=404 n=%d", n, shape="status 404")) for n in range(10)]
    assert kept == [True] * 3 + [False] * 7
    assert shaping.filter(_record("other", shape="status 401")), "another kind keeps its own count"
    assert shaping.filter(_record("a run's stage")), "a line with no kind is never shaped"
    now[0] = 61.0
    record = _record("status=404 n=%d", 10, shape="status 404")
    assert shaping.filter(record) and "[7 earlier line(s) like this left out]" in record.getMessage()


def _handler(folder: Path, segment: int = 50_000, keep: int = 150_000, floor: int = 0) -> SegmentedFileHandler:
    handler = SegmentedFileHandler(folder, "api", segment, keep, floor)
    handler.setFormatter(BoundedFormatter())
    return handler


def _total(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.glob("api.*.log"))


@pytest.mark.parametrize("seed", range(3))
def test_whatever_is_logged_the_segments_together_stay_within_their_bound(tmp_path: Path, capfd: pytest.CaptureFixture[str], seed: int) -> None:
    rng = random.Random(seed)
    handler = _handler(tmp_path)
    largest = 0
    held = None
    try:
        for n in range(600):
            path = "/api/" + "A" * rng.choice([1, 50, 1000, 16000, 65000])
            record = _record("request_id=%s path=%s status=%d", n, path, rng.choice([200, 401, 404, 405, 422, 500]), exc=rng.random() < 0.02)
            handler.handle(record)
            largest = max(largest, len(handler.format(record).encode()) + 1)
            if n == 300:
                # A reader holding the current segment open, as a person's tail does: Windows then refuses to rename it,
                # which a rotating handler needs, and to delete it.
                held = open(handler.segments()[-1], "rb")  # noqa: SIM115
            assert _total(tmp_path) <= handler.keep_bytes + handler.segment_bytes + largest
        assert handler.dropped == 0
    finally:
        if held is not None:
            held.close()
        handler.close()
    assert capfd.readouterr().err == "", "nothing of a record reached standard error"


def test_a_line_that_cannot_be_written_is_counted_and_the_next_one_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    handler = _handler(tmp_path, floor=10**6)
    usage = namedtuple("usage", "total used free")
    real = shutil.disk_usage
    monkeypatch.setattr(log_sink.shutil, "disk_usage", lambda path: usage(10**9, 10**9, 10))  # below the floor
    for n in range(5):
        handler.handle(_record("line %d", n))
    assert handler.dropped == 5 and _total(tmp_path) == 0
    monkeypatch.setattr(log_sink.shutil, "disk_usage", real)
    handler._space_checked = 0.0  # the next line looks at the disk again
    handler.handle(_record("back"))
    handler.close()
    written = "".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("api.*.log"))
    assert "back [5 earlier line(s) could not be written]" in written and handler.dropped == 0
    assert capfd.readouterr().err == ""


def test_a_folder_that_cannot_be_written_loses_lines_quietly(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    blocked = tmp_path / "not-a-folder"
    blocked.write_text("a file where the folder should be", encoding="utf-8")
    handler = _handler(blocked)
    handler.handle(_record("lost"))
    handler.close()
    assert handler.dropped == 1 and capfd.readouterr().err == ""


def test_the_requests_an_outsider_repeats_at_will_reach_the_log_cut_and_shaped(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Through the API: an unknown path of 16 KB, the most Cloudflare passes, sent in a loop.
    lines: list[str] = []

    class Kept(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    sink = Kept()
    sink.setFormatter(BoundedFormatter())
    sink.addFilter(FloodShaping(per_minute=5))
    logging.getLogger("app").addHandler(sink)
    try:
        for _ in range(20):
            assert client.get("/api/x" + "A" * 16000).status_code == 404
        assert client.get("/api/documents").status_code == 200
    finally:
        logging.getLogger("app").removeHandler(sink)
    requests = [line for line in lines if "path=/api/x" in line]
    assert len(requests) == 5 and all(len(line) < MESSAGE_CHARS + 200 for line in requests)
    assert any("path=/api/documents status=200" in line for line in lines), "an ordinary line is never shaped"


def test_uvicorn_writes_through_the_same_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("uvicorn", "uvicorn.error"):
        monkeypatch.setattr(logging.getLogger(name), "handlers", [logging.StreamHandler()])
        monkeypatch.setattr(logging.getLogger(name), "propagate", False)
    log_sink.configure(None, 1024, 4096, 0)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        assert logging.getLogger(name).handlers == [] and logging.getLogger(name).propagate
