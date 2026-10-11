"""The supervisor keeps the server up when it cannot write its own records (incident, 2026-10-11).

deploy/supervise.ps1 runs under $ErrorActionPreference = "Stop". Its log line was a bare Add-Content, so an IOException
ended the supervisor: at 05:44 a reader holding api.supervisor.log without write sharing (Git Bash's `tail -F`, opened
by an operator's watch) made the next line fail, the supervisor exited with code 1, and the API that had just stopped
accepting stayed down for 17 minutes with no one to restart it. Every write to the log or the pid file now goes through
Write-Record, which retries and then gives the record up. These tests run the script's own functions under the same
error preference against a file locked the same way, and keep a control that shows the lock really breaks a bare write.
"""

from __future__ import annotations

import ctypes
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

SUPERVISE = Path(__file__).resolve().parents[2] / "deploy" / "supervise.ps1"

pytestmark = pytest.mark.skipif(sys.platform != "win32" or shutil.which("powershell") is None, reason="the supervisor is a Windows PowerShell script")


def function_source(script: str, name: str) -> str:
    """The text of one `function <name>(...) { ... }` in the script, found by matching its braces."""
    start = re.search(rf"^function {re.escape(name)}\b", script, re.MULTILINE)
    assert start, f"{name} is not defined in supervise.ps1"
    depth, i = 0, script.index("{", start.start())
    for j in range(i, len(script)):
        depth += {"{": 1, "}": -1}.get(script[j], 0)
        if depth == 0:
            return script[start.start() : j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


@contextmanager
def held_without_write_sharing(path: Path) -> Iterator[None]:
    """Holds ``path`` open for reading and lets others only read it, as Git Bash's `tail -F` does."""
    generic_read, file_share_read, open_always, invalid = 0x80000000, 0x1, 4, ctypes.c_void_p(-1).value
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    handle = kernel32.CreateFileW(str(path), generic_read, file_share_read, None, open_always, 0, None)
    assert handle != invalid, ctypes.get_last_error()
    try:
        yield
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def run_powershell(body: str, log: Path) -> subprocess.CompletedProcess[str]:
    script = f"$ErrorActionPreference = 'Stop'\n$supervisorLog = '{log}'\n$pidFile = '{log.with_suffix('.pid')}'\n{body}\n'still supervising'"
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=60)


def record_functions() -> str:
    script = SUPERVISE.read_text(encoding="utf-8")
    return function_source(script, "Write-Record") + "\n" + function_source(script, "Write-Line")


def test_a_locked_log_does_not_end_the_supervisor(tmp_path: Path) -> None:
    log = tmp_path / "api.supervisor.log"
    with held_without_write_sharing(log):
        result = run_powershell(record_functions() + "\nWrite-Line 'did not answer (1 of 3)'", log)
    assert result.returncode == 0, result.stderr
    assert "still supervising" in result.stdout


def test_a_locked_pid_file_does_not_end_the_supervisor(tmp_path: Path) -> None:
    log = tmp_path / "api.supervisor.log"
    with held_without_write_sharing(log.with_suffix(".pid")):
        write_pid = "$ok = Write-Record { Set-Content -Path $pidFile -Value 4242 -Encoding ascii }"
        result = run_powershell(f'{record_functions()}\n{write_pid}\n"pid recorded: $ok"', log)
    assert result.returncode == 0, result.stderr
    assert "pid recorded: False" in result.stdout
    assert "still supervising" in result.stdout


def test_an_unlocked_log_gets_the_line(tmp_path: Path) -> None:
    log = tmp_path / "api.supervisor.log"
    result = run_powershell(record_functions() + "\nWrite-Line 'started api pid 1'", log)
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8-sig").rstrip().endswith("started api pid 1")


def test_control_the_lock_breaks_a_bare_add_content(tmp_path: Path) -> None:
    # The write the supervisor used before: without Write-Record the same lock ends the script.
    log = tmp_path / "api.supervisor.log"
    with held_without_write_sharing(log):
        result = run_powershell("Add-Content -Path $supervisorLog -Value 'x' -Encoding utf8", log)
    assert result.returncode != 0
    assert "still supervising" not in result.stdout


def test_every_record_write_goes_through_write_record() -> None:
    script = SUPERVISE.read_text(encoding="utf-8")
    inside = function_source(script, "Write-Record") + function_source(script, "Write-Line")
    code = [line.strip() for line in script.splitlines() if not line.strip().startswith("#")]
    writes = [line for line in code if re.search(r"\b(Add-Content|Set-Content|Out-File)\b", line)]
    unguarded = [line for line in writes if "Write-Record" not in line and line not in inside]
    assert unguarded == [], unguarded
