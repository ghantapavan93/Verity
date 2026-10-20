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
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
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
    script = (
        f"$ErrorActionPreference = 'Stop'\n$supervisorLog = '{log}'\n$pidFile = '{log.with_suffix('.pid')}'\n$droppedLines = 0\n{body}\n'still supervising'"
    )
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


def test_lines_lost_to_a_lock_are_counted_on_the_next_line_written(tmp_path: Path) -> None:
    log = tmp_path / "api.supervisor.log"
    locked = "Write-Line 'did not answer (1 of 3)'\nWrite-Line 'did not answer (2 of 3)'"
    with held_without_write_sharing(log):
        first = run_powershell(f"{record_functions()}\n{locked}\n$droppedLines", log)
    assert first.returncode == 0, first.stderr
    assert first.stdout.splitlines()[0] == "2"
    after = run_powershell(f"{record_functions()}\n$droppedLines = 2\nWrite-Line 'started api pid 7'\n$droppedLines", log)
    assert after.stdout.splitlines()[0] == "0"
    assert log.read_text(encoding="utf-8-sig").rstrip().endswith("started api pid 7 (2 earlier line(s) could not be written)")


def test_control_the_lock_breaks_a_bare_add_content(tmp_path: Path) -> None:
    # The write the supervisor used before: without Write-Record the same lock ends the script.
    log = tmp_path / "api.supervisor.log"
    with held_without_write_sharing(log):
        result = run_powershell("Add-Content -Path $supervisorLog -Value 'x' -Encoding utf8", log)
    assert result.returncode != 0
    assert "still supervising" not in result.stdout


def test_every_record_write_goes_through_write_record() -> None:
    # Each write to a file, by cmdlet, .NET call or redirection, sits inside a Write-Record block on its own line.
    script = SUPERVISE.read_text(encoding="utf-8")
    code = [line.strip() for line in script.splitlines() if not line.strip().startswith("#")]
    write = re.compile(r"\b(Add-Content|Set-Content|Out-File|AppendAllText|WriteAllText|WriteAllLines)\b|\s>>?\s*[$\"'A-Za-z]")
    writes = [line for line in code if write.search(line)]
    assert len(writes) >= 2, writes
    unguarded = [line for line in writes if "Write-Record {" not in line]
    assert unguarded == [], unguarded


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for(predicate: Callable[[], bool], seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.25)
    return predicate()


def test_only_the_stop_file_ends_the_supervisor(tmp_path: Path) -> None:
    # The real script, run as deployed, where a pass fails twice over: an empty access.secret (its Trim() threw on
    # null) and no backend venv (Start-Process throws). Before m9 either ended the supervisor with code 1.
    (tmp_path / "deploy").mkdir()
    shutil.copy(SUPERVISE, tmp_path / "deploy" / "supervise.ps1")
    (tmp_path / "backend" / "data").mkdir(parents=True)
    (tmp_path / "backend" / "data" / "access.secret").write_text("", encoding="ascii")
    logs = tmp_path / "backend" / "data" / "logs" / "deploy"
    log = logs / "t.supervisor.log"
    command = ["powershell", "-NoProfile", "-NonInteractive", "-File", str(tmp_path / "deploy" / "supervise.ps1")]
    supervisor = subprocess.Popen([*command, "-Name", "api", "-Port", str(free_port()), "-Tag", "t"])
    try:
        assert wait_for(lambda: log.exists() and "supervisor pass failed" in log.read_text(encoding="utf-8-sig"), 30)
        text = log.read_text(encoding="utf-8-sig")
        assert "no access secret" in text
        assert supervisor.poll() is None, "the supervisor ended on a failed pass"
        (logs / "t.stop").write_text("stop", encoding="ascii")
        assert supervisor.wait(timeout=60) == 0
        assert "stop file present; supervisor exiting" in log.read_text(encoding="utf-8-sig")
    finally:
        if supervisor.poll() is None:
            supervisor.kill()


# What the supervisor writes about an end it did not see, an exit it did, and the files it keeps (ops audit, 2026-10-19).


def run_function(name: str, body: str, logs: Path, tag: str = "t") -> subprocess.CompletedProcess[str]:
    script = SUPERVISE.read_text(encoding="utf-8")
    prelude = f"$ErrorActionPreference = 'Stop'\n$logs = '{logs}'\n$Tag = '{tag}'\n$supervisorLog = '{logs / (tag + '.supervisor.log')}'\n$LOG_KEEP_DAYS = 14\n"
    command = prelude + function_source(script, name) + "\n" + body
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, timeout=60)


def aged(path: Path, days: float) -> Path:
    path.write_text("x", encoding="ascii")
    then = time.time() - days * 86400
    os.utime(path, (then, then))
    return path


def test_old_output_of_this_server_is_removed_and_nothing_else(tmp_path: Path) -> None:
    old = [aged(tmp_path / "t.20260901-000000.out.log", 15), aged(tmp_path / "t.20260901-000000.err.log", 15)]
    kept = [
        aged(tmp_path / "t.20261006-000000.out.log", 13),  # inside the fourteen days
        aged(tmp_path / "t.supervisor.log", 40),  # the supervisor's own record
        aged(tmp_path / "web.20260901-000000.out.log", 40),  # the other server's
        aged(tmp_path / "t.20260901-000000.out.log.bak", 40),  # not a stamped output file
    ]
    result = run_function("Remove-OldLogs", "Remove-OldLogs", tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2"
    assert not [path for path in old if path.exists()]
    assert all(path.exists() for path in kept)


def test_an_end_with_no_record_is_named_with_its_last_line(tmp_path: Path) -> None:
    (tmp_path / "t.supervisor.log").write_text("2026-10-18T22:00:00 started api pid 7 (output t.x.out.log)\n", encoding="utf-8")
    result = run_function("Get-UnrecordedEnd", "Get-UnrecordedEnd", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "ended without a record" in result.stdout and "Windows last started" in result.stdout
    assert result.stdout.rstrip().endswith("started api pid 7 (output t.x.out.log)")


RECORDED_ENDS = ["stop file present; supervisor exiting", "stop file present; not restarting", "supervisor not started: stop file present (x)"]


@pytest.mark.parametrize("last", [*RECORDED_ENDS, None])
def test_control_an_end_the_supervisor_recorded_is_not_named(tmp_path: Path, last: str | None) -> None:
    if last is not None:
        (tmp_path / "t.supervisor.log").write_text(f"2026-10-18T22:00:00 started api pid 7\n2026-10-18T23:00:00 {last}\n", encoding="utf-8")
    result = run_function("Get-UnrecordedEnd", '$end = Get-UnrecordedEnd\n"[$end]"', tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


@pytest.mark.parametrize(("code", "meaning"), [(1073807364, "0x40010004: ended by Windows"), (0, ""), (1, "")])
def test_an_exit_code_windows_chose_is_translated(tmp_path: Path, code: int, meaning: str) -> None:
    result = run_function("Get-ExitMeaning", f'"[$(Get-ExitMeaning {code})]"', tmp_path)
    assert result.returncode == 0, result.stderr
    said = result.stdout.strip()
    assert (meaning in said) if meaning else said == "[]"


def test_an_exit_carries_the_last_line_the_server_wrote(tmp_path: Path) -> None:
    err = tmp_path / "t.err.log"
    err.write_text("INFO started\nTraceback (most recent call last):\nRuntimeError: no access secret\n\n  \n", encoding="utf-8")
    long = tmp_path / "t.long.log"
    long.write_text("x" * 1000 + "\n", encoding="utf-8")
    body = f"\"[$(Get-LastLine '{err}')]\"\n\"[$(Get-LastLine '{long}')]\"\n\"[$(Get-LastLine '{tmp_path / 'missing.log'}')]\""
    result = run_function("Get-LastLine", body, tmp_path)
    assert result.returncode == 0, result.stderr
    named, cut, missing = result.stdout.splitlines()
    assert named == "[RuntimeError: no access secret]"
    assert cut == "[" + "x" * 300 + "...]"
    assert missing == "[]"
