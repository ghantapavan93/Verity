"""Where the API's log lines go, and what bounds them (stress test, 2026-10-30).

Every logger wrote to one unbounded stream: the supervisor redirects the API's standard error to a file per start
(deploy/supervise.ps1), and nothing capped a line or the file. Any request without a session wrote its whole path, up
to 65 KB a line at the API and 16 KB through Cloudflare, so one client sending 401s and 404s in a loop added about
4 GB an hour to the disk the store, the model and the system share: the public store pauses writes at 2 GiB free, and
a full disk fails every SQLite write, runs in flight included. The bounds are at the sink, for every logger:

- each record is cut: its message at MESSAGE_CHARS, a traceback at TRACE_CHARS, keeping the head and the length it had,
  and a line break in a message is written as an escape, so a path cannot forge a line;
- lines a flood repeats (a request line with a 4xx status, a refusal of one kind) are kept at SHAPED_PER_MINUTE a minute
  for each kind; the next kept line of that kind says how many were left out, so a flood cannot evict the record;
- with WORKBENCH_LOG_DIR set (the supervisor sets it), lines go to segments of settings.log_segment_bytes in that
  folder, and the oldest are deleted while all of them together pass settings.log_keep_bytes. A segment is never
  renamed: Windows refuses a rename while any reader holds the file, and the rotating handler then printed every record
  and its traceback to standard error instead (reproduced, WinError 32). A line that cannot be written (the folder is
  gone, the disk is below its floor) is dropped and counted, never printed elsewhere, and the next line written says how
  many were lost. Unset, lines go to standard error, as in tests and on a laptop, and a container's log driver bounds it.

uvicorn's own loggers are sent through the same handler, so no logger writes past these bounds.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MESSAGE_CHARS = 2000
TRACE_CHARS = 16000
SHAPED_PER_MINUTE = 60
_ESCAPED = str.maketrans({"\r": "\\r", "\n": "\\n"})


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}...[cut, len={len(text)}]"


class BoundedFormatter(logging.Formatter):
    """The deployment's format, with every part of a record cut to its bound. An ordinary line is exactly what the
    plain formatter writes."""

    def __init__(self) -> None:
        super().__init__(FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        record.message = _cut(record.getMessage().translate(_ESCAPED), MESSAGE_CHARS)
        record.asctime = self.formatTime(record, self.datefmt)
        line = self.formatMessage(record)
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line = f"{line}\n{_cut(record.exc_text, TRACE_CHARS)}"
        if record.stack_info:
            line = f"{line}\n{_cut(self.formatStack(record.stack_info), TRACE_CHARS)}"
        return line


class FloodShaping(logging.Filter):
    """At most ``per_minute`` lines a minute of each kind a record names in its ``shape`` attribute (the request line of
    a 4xx, a refusal); the first kept line after a gap says how many of its kind were left out. A record with no shape
    is always kept: a run's stages, a failure, a start."""

    def __init__(self, per_minute: int = SHAPED_PER_MINUTE, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__()
        self.per_minute = per_minute
        self._clock = clock
        self._lock = threading.Lock()
        self._minute: dict[str, tuple[float, int, int]] = {}  # kind -> (window start, kept, left out)

    def filter(self, record: logging.LogRecord) -> bool:
        kind = getattr(record, "shape", None)
        if not kind:
            return True
        now = self._clock()
        with self._lock:
            started, kept, left_out = self._minute.get(kind, (now, 0, 0))
            if now - started >= 60:
                started, kept = now, 0
            if kept >= self.per_minute:
                self._minute[kind] = (started, kept, left_out + 1)
                return False
            self._minute[kind] = (started, kept + 1, 0)
            if len(self._minute) > 1024:  # kinds come from status codes and refusal names, but bound them anyway
                for stale in [k for k, (s, _, lost) in self._minute.items() if now - s >= 60 and not lost]:
                    del self._minute[stale]
        if left_out:
            record.msg = f"{record.getMessage()} [{left_out} earlier line(s) like this left out]"
            record.args = None
        return True


class SegmentedFileHandler(logging.Handler):
    """Lines appended to segments of at most ``segment_bytes`` in ``folder``, the oldest deleted while every segment of
    ``name`` together holds more than ``keep_bytes``. Never renames, never prints a record anywhere else."""

    def __init__(self, folder: Path, name: str, segment_bytes: int, keep_bytes: int, floor_bytes: int) -> None:
        super().__init__()
        self.folder, self.name = folder, name
        self.segment_bytes, self.keep_bytes, self.floor_bytes = segment_bytes, keep_bytes, floor_bytes
        self.dropped = 0
        self._stream: IO[bytes] | None = None
        self._written = 0
        self._sequence = 0
        self._stamp = time.strftime("%Y%m%d-%H%M%S")
        self._space_checked = 0.0
        self._space_ok = True

    def segments(self) -> list[Path]:
        return sorted(self.folder.glob(f"{self.name}.*.log"), key=lambda p: p.name)

    def _room(self) -> bool:
        now = time.monotonic()
        if now - self._space_checked >= 1.0:
            self._space_checked = now
            try:
                self._space_ok = shutil.disk_usage(self.folder).free >= self.floor_bytes
            except OSError:
                self._space_ok = False
        return self._space_ok

    def _close(self) -> None:
        if self._stream is not None:
            with contextlib.suppress(OSError):
                self._stream.close()
        self._stream = None

    def _next_segment(self) -> IO[bytes]:
        self._close()
        self.folder.mkdir(parents=True, exist_ok=True)
        self._sequence += 1
        path = self.folder / f"{self.name}.{self._stamp}.{os.getpid()}.{self._sequence:05d}.log"
        stream = open(path, "ab")  # noqa: SIM115 - held open across records; closed on the next segment or at close
        self._stream, self._written = stream, 0
        held = [(p, p.stat().st_size) for p in self.segments() if p.exists()]
        total = sum(size for _, size in held)
        for old, size in held:
            if total <= self.keep_bytes or old == path:
                break
            try:
                old.unlink()
                total -= size
            except OSError:
                continue  # a reader holds it: it goes at a later segment
        return stream

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            if self.dropped:
                line = f"{line} [{self.dropped} earlier line(s) could not be written]"
            data = (line + "\n").encode("utf-8", "backslashreplace")
            if not self._room():
                raise OSError("the log's disk is below its floor")
            stream = self._stream
            if stream is None or self._written + len(data) > self.segment_bytes:
                stream = self._next_segment()
            stream.write(data)
            stream.flush()
            self._written += len(data)
            self.dropped = 0
        except Exception:  # noqa: BLE001 - a line that cannot be written is counted, never raised or printed
            self.handleError(record)

    def handleError(self, record: logging.LogRecord) -> None:
        # The default prints the record and a traceback to standard error: the unbounded stream this replaces.
        self.dropped += 1
        self._close()

    def close(self) -> None:
        self.acquire()
        try:
            self._close()
        finally:
            self.release()
        super().close()


def make_handler(log_dir: Path | None, segment_bytes: int, keep_bytes: int, floor_bytes: int) -> logging.Handler:
    handler: logging.Handler = (
        logging.StreamHandler(sys.stderr) if log_dir is None else SegmentedFileHandler(log_dir, "api", segment_bytes, keep_bytes, floor_bytes)
    )
    handler.setFormatter(BoundedFormatter())
    handler.addFilter(FloodShaping())
    return handler


def configure(log_dir: Path | None, segment_bytes: int, keep_bytes: int, floor_bytes: int) -> None:
    """The one logging setup of the API process: every logger, uvicorn's included, through one bounded handler. Like
    logging.basicConfig, it leaves a root logger that already has a handler alone (a test runner's)."""
    logging.basicConfig(level=logging.INFO, handlers=[make_handler(log_dir, segment_bytes, keep_bytes, floor_bytes)])
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        own = logging.getLogger(name)
        own.handlers.clear()
        own.propagate = True
