"""Which process is running a stage, and whether it still exists.

Recovery of an interrupted run is by staleness, never by process, because the API, the golden runner and a
batch runner write into one database and a restart of one must not fail the others' live work. Staleness
alone, though, leaves a run whose process died in flight for the whole window (four model timeouts and a
minute), and every identical question asked in that window is handed the stuck run. A stage row therefore
records the identity of the process that opened it: host, pid, and the process's start time where the
platform gives one. A run whose latest stage was opened by a process on this host that no longer exists
can be recovered at once; a run owned by another host, or by a process that is still alive, waits for
staleness as before. Nothing here is a dependency: the start time comes from the operating system directly.
"""

from __future__ import annotations

import os
import socket
import sys
from dataclasses import dataclass
from functools import cache

SEPARATOR = ":"


@dataclass(frozen=True)
class ProcessIdentity:
    host: str
    pid: int
    started: str  # platform start token; "" when the platform gives none

    def render(self) -> str:
        return SEPARATOR.join((self.host, str(self.pid), self.started))

    @classmethod
    def parse(cls, text: str) -> ProcessIdentity | None:
        host, _, rest = text.partition(SEPARATOR)
        pid_text, _, started = rest.partition(SEPARATOR)
        if not host or not pid_text.isdigit():
            return None
        return cls(host, int(pid_text), started)


def _start_token(pid: int) -> str | None:
    """The process's start time as the platform reports it, or None when the process cannot be seen."""
    if sys.platform == "win32":
        return _start_token_windows(pid)
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            fields = handle.read().rpartition(")")[2].split()
        return fields[19]  # starttime, in clock ticks since boot
    except (OSError, IndexError):
        return "" if _alive_posix(pid) else None


def _alive_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _start_token_windows(pid: int) -> str | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    process_query_limited_information = 0x1000
    still_active = 259
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return None
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != still_active:
            return None
        creation, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            return ""
        return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


@cache
def this_process() -> ProcessIdentity:
    return ProcessIdentity(socket.gethostname(), os.getpid(), _start_token(os.getpid()) or "")


def owner_is_gone(owner: str | None) -> bool:
    """True only when the owner was a process on this host that provably no longer exists (or was replaced by a
    process with the same pid and a different start time). Unknown owners and other hosts are never "gone"."""
    if not owner:
        return False
    identity = ProcessIdentity.parse(owner)
    if identity is None or identity.host != this_process().host:
        return False
    if identity.pid == this_process().pid:
        return False
    token = _start_token(identity.pid)
    if token is None:
        return True
    return bool(identity.started) and bool(token) and token != identity.started
