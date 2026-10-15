"""Every file is read where reading it can be stopped: a child process held to a memory and a time bound.

Reading is where untrusted bytes become trees, strings and page objects, and no bound written in terms of the bytes held
for long (2026-10-13): an 84 KB .docx of six million empty paragraphs took 848 MB and 35 s; a count of elements, added
for it, missed comments, processing instructions, attributes and text (a 529 KB file still took 2 GB) and made members
no part uses inflate (a 36 KB file, 862 MB); a byte budget for PDF content did not bound time, since pypdf's layout mode
slows with text positioning on one page (a 1.6 KB PDF read for 20 s). Each was one shape behind the next, so the bound
is now on what reading costs, measured while it runs: the child's memory is sampled and the child is ended past
READ_MEMORY_BYTES, and ended at READ_SECONDS whatever it is doing. No more than READINGS_AT_ONCE run at a time, however
they are asked for (an upload, or a document read again for a revision check). Within those bounds a reading comes back
exactly as it would from this process; a reader's own refusal comes back as it was raised, a file past a bound as
TooLargeToRead with the reason, and any other failure as an error, as it would be here.

The child is handed the file, and its name, by a path, never through the pipe that starts it: a write to that pipe past
what it holds waits for the child to read, and on Windows a child that died first left the parent blocked in start()
past every deadline (2 MB; 1 KB passed, war room W5 p10). A child that ends without answering is noticed when it ends, not at
the deadline.

This bounds resources, not trust: the child inherits the API's environment, and its answer is unpickled here.
"""

from __future__ import annotations

import contextlib
import ctypes
import functools
import logging
import multiprocessing
import os
import sys
import tempfile
import threading
import time
from multiprocessing import connection
from multiprocessing.connection import Connection
from pathlib import Path

from ..hashing import sha256_text
from . import Ingested, TooLargeToRead, UnsupportedFile, ingest

log = logging.getLogger(__name__)

# Real contracts read in under 10 s and 200 MB: over 40 of them read in a child on x86 (2026-10-13), the most memory
# any took was 194 MB and the longest any took was 9.2 s, two different files; on the Arm host the largest, 4.4 MB and
# 7,174 sections, was uploaded and read in process in 6.5 s (staging acceptance). The bounds are about three times
# that. Thirty seconds, not sixty: two hostile files held both reading slots for 60 s and a third reader waited past
# Cloudflare's 100 s (counter-review, 2026-10-13).
READ_SECONDS = 30.0
READ_MEMORY_BYTES = 768 * 1024 * 1024
READINGS_AT_ONCE = 2
# Off only in the backend test suite (conftest), whose tests change the reader in their own process; nothing in the
# deployment can turn the bounds off.
READ_IN_CHILD = True
# Where a reading's file waits for its child: the API sets its store's folder at start (handoff_folder, use_handoff_dir)
# and empties it then, and retention's sweep removes what is older than a reading lives, so a copy a killed process
# left is not kept. Loose in the system's temporary folder, nothing emptied it on Windows, and a force-stopped API left
# contracts there (Codex review, round 3, 2026-10-13). None, for scripts and tests: that temporary folder itself.
HANDOFF_DIR: Path | None = None
HANDOFF_PREFIX = "verity-reading-"
_SAMPLE_SECONDS = 0.05
_slots = threading.BoundedSemaphore(READINGS_AT_ONCE)

if sys.platform == "win32":
    from multiprocessing.context import SpawnContext

    @functools.cache
    def _process_context() -> SpawnContext:
        """Windows has no fork: each child starts a fresh interpreter."""
        return multiprocessing.get_context("spawn")

else:
    from multiprocessing.context import ForkServerContext

    @functools.cache
    def _process_context() -> ForkServerContext:
        """The API's process has threads, which a plain fork must not copy; a fork server, started once, does not, and
        it preloads the readers, so each child starts in milliseconds."""
        server = multiprocessing.get_context("forkserver")
        server.set_forkserver_preload(["app.ingest"])
        return server


class ReadingBusy(Exception):
    """No reading slot came free within the wait the caller allowed: the file was not read, and asked again it may be."""


def read_file(filename: str, data: bytes, *, wait: float | None = None) -> Ingested:
    """The one way the application reads a file: one of READINGS_AT_ONCE slots, then a bounded child. `wait` is the
    longest to wait for a slot (None: until one is free); past it, ReadingBusy."""
    if not _slots.acquire(timeout=wait):
        raise ReadingBusy(f"no reading slot came free in {wait:.0f} s")
    try:
        return ingest_bounded(filename, data) if READ_IN_CHILD else ingest(filename, data)
    finally:
        _slots.release()


def handoff_folder(store: Path) -> Path:
    """The folder a store's readings hand their files over in: inside the system's temporary folder, a tmpfs in the
    cloud container (deploy/cloud/compose.yml), so a contract on its way to a reading never reaches the store's
    persistent disk; named for the store, so two APIs on one machine never empty each other's."""
    name = sha256_text(str(store.resolve()))[:16]
    return Path(tempfile.gettempdir()) / f"verity-readings-{name}"


def use_handoff_dir(folder: Path) -> int:
    """Readings hand their files to their children in `folder` from now on. Files a stopped process left there are
    removed, and their number returned: one API process serves a store, so none of them is in use. The folder is this
    user's alone; a shared temporary folder where someone else made it first is refused."""
    global HANDOFF_DIR
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if hasattr(os, "getuid"):
        made = folder.stat()
        if made.st_uid != os.getuid() or made.st_mode & 0o077:
            raise RuntimeError(
                f"{folder} is not this user's own folder, readable by it alone, so readings will not hand contracts over in it: "
                "remove it, or point TMPDIR at a folder this user owns"
            )
    left = [path for path in folder.glob(f"{HANDOFF_PREFIX}*") if path.is_file()]
    for path in left:
        path.unlink(missing_ok=True)
    HANDOFF_DIR = folder
    return len(left)


def release_handoff_dir() -> None:
    """At a clean stop the folder goes, once nothing is left in it; a reading after this makes it again."""
    if HANDOFF_DIR is not None:
        with contextlib.suppress(OSError):  # not empty, or already gone: the next start empties it
            HANDOFF_DIR.rmdir()


def ingest_bounded(filename: str, data: bytes, *, seconds: float | None = None, memory: int | None = None) -> Ingested:
    """`ingest` in a child process, ended past `memory` bytes or `seconds` of time (by default the module's bounds, read
    when called). The time is counted from before the child starts."""
    seconds = READ_SECONDS if seconds is None else seconds
    memory = READ_MEMORY_BYTES if memory is None else memory
    deadline = time.monotonic() + seconds
    folder = HANDOFF_DIR
    if folder is not None:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)  # made again after a clean stop: this user's alone, as at start
    handle, path = tempfile.mkstemp(prefix=HANDOFF_PREFIX, dir=folder)  # readable by this user only
    try:
        with os.fdopen(handle, "wb") as file:
            name = filename.encode("utf-8", "surrogatepass")
            file.write(len(name).to_bytes(4, "big") + name)  # the name too: whatever its length, the start stays the same size
            file.write(data)
        return _read_child(path, deadline, seconds, memory)
    finally:
        try:
            os.unlink(path)
        except OSError as error:  # Windows: a child not yet gone still holds it
            log.warning("a reading's temporary file was not removed: %s", error)


def _read_child(path: str, deadline: float, seconds: float, memory: int) -> Ingested:
    context = _process_context()
    answers, answer = context.Pipe(duplex=False)
    child = context.Process(target=_read_in_child, args=(path, answer), daemon=True)
    try:
        child.start()  # carries a path and the pipe only: a few hundred bytes the start-up pipe holds whole
    except OSError as error:
        answers.close()
        answer.close()
        raise RuntimeError(f"a reading process could not be started: {error}") from error
    answer.close()
    failed = "reading the file failed in a way no contract causes"
    try:
        # Woken by an answer or by the child ending, whichever comes first.
        while not connection.wait([answers, child.sentinel], _SAMPLE_SECONDS):
            if _memory_bytes(child.pid) > memory:
                raise TooLargeToRead(f"reading the file took more than {memory // (1024 * 1024)} MB of memory; no contract needs that much")
            if time.monotonic() > deadline:
                raise TooLargeToRead(f"reading the file took longer than {seconds:.0f} s; no contract needs that long")
        if not answers.poll():
            # The child ended with nothing sent. Asked, not read: on Windows a child that died before taking its end of
            # the pipe leaves that end with this process, so the pipe never ends and a read would wait for ever.
            raise TooLargeToRead(failed)
        kind, value = answers.recv()
    except (EOFError, BrokenPipeError):
        # The child ended without an answer: killed by the kernel past the container's memory, or crashed, on this file.
        raise TooLargeToRead(failed) from None
    finally:
        answers.close()
        if child.is_alive():
            child.kill()
        child.join(5)
    return _outcome(kind, value)


def _outcome(kind: str, value: object) -> Ingested:
    """What the child's answer means here: the reading, or the refusal or error it would have been in this process."""
    if kind == "read":
        assert isinstance(value, Ingested)
        return value
    if kind == "too_large":
        raise TooLargeToRead(str(value))
    if kind == "unsupported":
        raise UnsupportedFile(str(value))
    # A bug in a reader is a server error here as it would be in this process, not a file "past its bounds".
    raise RuntimeError(f"reading the file failed in its child process: {value}")


def _read_in_child(path: str, answer: Connection) -> None:
    try:
        with open(path, "rb") as file:
            filename = file.read(int.from_bytes(file.read(4), "big")).decode("utf-8", "surrogatepass")
            data = file.read()
        answer.send(("read", ingest(filename, data)))
    except TooLargeToRead as error:
        answer.send(("too_large", str(error)))
    except UnsupportedFile as error:
        answer.send(("unsupported", str(error)))
    except MemoryError:
        answer.send(("too_large", "reading the file took more memory than any contract needs"))
    except Exception as error:  # noqa: BLE001 - every other failure goes back to the parent as the error it is
        answer.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        answer.close()


def _memory_bytes(pid: int | None) -> int:
    """The child's memory, as the operating system counts what it holds: resident pages on Linux, committed memory on
    Windows (its working set is trimmed under pressure); 0 when it cannot be read (the child has ended)."""
    if pid is None:
        return 0
    if sys.platform == "win32":
        return _windows_commit(pid)
    try:
        with open(f"/proc/{pid}/statm") as statm:
            return int(statm.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return 0


if sys.platform == "win32":

    class _MemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    def _windows_commit(pid: int) -> int:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MemoryCounters), ctypes.c_ulong]
        handle = kernel32.OpenProcess(0x0410, False, pid)  # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
        if not handle:
            return 0
        try:
            counters = _MemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            return int(counters.PagefileUsage) if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb) else 0
        finally:
            kernel32.CloseHandle(handle)
