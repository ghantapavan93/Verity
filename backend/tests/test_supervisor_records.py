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
    prelude = (
        f"$ErrorActionPreference = 'Stop'\n$logs = '{logs}'\n$Tag = '{tag}'\n$supervisorLog = '{logs / (tag + '.supervisor.log')}'\n"
        "$LOG_KEEP_DAYS = 14\n$LOG_KEEP_BYTES = 200MB\n"
    )
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


def sized(path: Path, size: int, days: float) -> Path:
    path.write_bytes(b"x" * size)
    then = time.time() - days * 86400
    os.utime(path, (then, then))
    return path


def test_output_past_its_byte_budget_is_removed_oldest_first(tmp_path: Path) -> None:
    # By age alone, a server that wrote fast or restarted in a loop kept every byte for two weeks (stress test, 2026-10-30).
    oldest = [sized(tmp_path / f"t.2026102{n}-000000.err.log", 400, 5 - n) for n in range(3)]  # 1,200 bytes, oldest first
    newest = sized(tmp_path / "t.20261029-000000.err.log", 400, 1)
    others = [sized(tmp_path / "web.20261020-000000.err.log", 5000, 5), sized(tmp_path / "t.supervisor.log", 5000, 5)]
    result = run_function("Remove-OldLogs", "$LOG_KEEP_BYTES = 900\nRemove-OldLogs", tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2"
    assert [path.exists() for path in oldest] == [False, False, True] and newest.exists()
    assert all(path.exists() for path in others), "only this server's stamped output counts"


def test_control_output_inside_its_byte_budget_is_kept(tmp_path: Path) -> None:
    files = [sized(tmp_path / f"t.2026102{n}-000000.out.log", 400, 5 - n) for n in range(3)]
    result = run_function("Remove-OldLogs", "$LOG_KEEP_BYTES = 1200\nRemove-OldLogs", tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0" and all(path.exists() for path in files)


def test_an_api_exit_reads_its_last_line_from_its_own_log_when_its_error_output_is_empty(tmp_path: Path) -> None:
    # The API writes its log to segments of its own (backend/app/log_sink.py); its standard error is then usually empty.
    script = SUPERVISE.read_text(encoding="utf-8")
    segments = tmp_path / "t"
    segments.mkdir()
    (segments / "api.20261030-000000.100.00001.log").write_text("INFO older segment\n", encoding="utf-8")
    (segments / "api.20261030-000000.100.00002.log").write_text("ERROR app: Application startup failed\n", encoding="utf-8")
    (tmp_path / "empty.err.log").write_text("", encoding="utf-8")
    (tmp_path / "said.err.log").write_text("RuntimeError: refusing to start\n", encoding="utf-8")
    prelude = f"$ErrorActionPreference = 'Stop'\n$Name = 'api'\n$apiLogs = '{segments}'\n"
    functions = function_source(script, "Get-LastLine") + "\n" + function_source(script, "Get-LastServerLine")
    body = f"\"[$(Get-LastServerLine '{tmp_path / 'empty.err.log'}')]\"\n\"[$(Get-LastServerLine '{tmp_path / 'said.err.log'}')]\""
    command = prelude + functions + "\n" + body
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["[ERROR app: Application startup failed]", "[RuntimeError: refusing to start]"]


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


# ---------------------------------------------------------------------------- what down.ps1 stops
# down.ps1 stopped whatever process held the pid a record named, with its whole tree, and never removed the record:
# after an end the supervisor did not see, Windows gave that pid to an unrelated process and down.ps1 killed it
# (stress test, 2026-10-30, ops 6). A process is now the one recorded only when its start time matches too.

DOWN = SUPERVISE.with_name("down.ps1")


@contextmanager
def a_live_process() -> Iterator[subprocess.Popen[bytes]]:
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        yield sleeper
    finally:
        if sleeper.poll() is None:
            sleeper.kill()
        sleeper.wait(10)


def start_token(pid: int) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", f"(Get-Process -Id {pid}).StartTime.ToFileTimeUtc()"], capture_output=True, text=True
    )
    return result.stdout.strip()


def run_down(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    (tmp_path / "deploy").mkdir(exist_ok=True)
    shutil.copy(DOWN, tmp_path / "deploy" / "down.ps1")
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-File", str(tmp_path / "deploy" / "down.ps1")], capture_output=True, text=True, timeout=60
    )


def _logs(tmp_path: Path) -> Path:
    logs = tmp_path / "backend" / "data" / "logs" / "deploy"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


@pytest.mark.parametrize("record", ["another start", "no start time"])
def test_a_record_naming_another_process_stops_nothing_and_is_removed(tmp_path: Path, record: str) -> None:
    logs = _logs(tmp_path)
    with a_live_process() as other:
        token = "" if record == "no start time" else str(int(start_token(other.pid)) - 10_000_000)  # a second earlier
        (logs / "api.pid").write_text(f"{other.pid} {token}".strip(), encoding="ascii")
        result = run_down(tmp_path)
        assert result.returncode == 0, result.stderr
        assert other.poll() is None, "the unrelated process is alive"
        assert "stale" in result.stdout
    assert not (logs / "api.pid").exists(), "the stale record is gone"


def test_control_the_recorded_server_is_stopped_and_its_record_removed(tmp_path: Path) -> None:
    logs = _logs(tmp_path)
    with a_live_process() as server:
        (logs / "web.pid").write_text(f"{server.pid} {start_token(server.pid)}", encoding="ascii")
        result = run_down(tmp_path)
        assert result.returncode == 0, result.stderr
        assert server.wait(10) is not None and "stopped supervised web" in result.stdout
    assert not (logs / "web.pid").exists()


def test_the_unsupervised_record_is_held_to_the_same_rule(tmp_path: Path) -> None:
    import json

    logs = _logs(tmp_path)
    with a_live_process() as ours, a_live_process() as other:
        record = {"api": {"pid": ours.pid, "started": start_token(ours.pid)}, "web": {"pid": other.pid, "started": "1"}, "tunnel": other.pid}
        (logs / "pids.json").write_text(json.dumps(record), encoding="utf-8")
        result = run_down(tmp_path)
        assert result.returncode == 0, result.stderr
        assert ours.wait(10) is not None, "the recorded api is stopped"
        assert other.poll() is None, "a pid another process holds now, with or without a start time, is left alone"
    assert not (logs / "pids.json").exists()


# Elapsed time in the deploy scripts is the monotonic clock's (stress test, 2026-10-30, time 5). The supervisor measured
# the watchdog's grace and a server's run with local Get-Date; .NET subtracts local times tick by tick, so across the
# fall-back (2026-11-01, 02:00 CDT) a server restarted in the hour before read -2,400 s old, the watchdog skipped a hung
# API for up to an hour, and the exit line said "after -3269 s" and doubled the backoff. A clock step of S did the same
# for S. The watchdog is run here against a process that never answers, under a Get-Date stepped back an hour after its
# first reading.

STEPPED_GET_DATE = """
$script:readings = 0
function Get-Date { $script:readings++; $now = [DateTime]::Now; if ($script:readings -gt 1) { $now = $now.AddSeconds(-3600) }; return $now }
"""


def run_watchdog(tmp_path: Path, clock: str) -> tuple[subprocess.CompletedProcess[str], str]:
    script = SUPERVISE.read_text(encoding="utf-8")
    log = tmp_path / "t.supervisor.log"
    body = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$supervisorLog = '{log}'",
            f"$stopFile = '{tmp_path / 't.stop'}'",
            "$droppedLines = 0",
            "$Name = 'api'",
            "$HEALTH_EVERY_SECONDS = 1; $HEALTH_GRACE_SECONDS = 1; $HEALTH_MISSES = 2",
            clock,
            function_source(script, "Write-Record"),
            function_source(script, "Write-Line"),
            function_source(script, "Watch-Server"),
            "$server = Start-Process -FilePath powershell -ArgumentList '-NoProfile','-Command','Start-Sleep 20' -WindowStyle Hidden -PassThru",
            "$null = $server.Handle",
            f"$ran = Watch-Server $server 'http://127.0.0.1:{free_port()}/api/health'",
            "if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }",
            "'ran ' + $ran",
        ]
    )
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", body], capture_output=True, text=True, timeout=90)
    return result, log.read_text(encoding="utf-8-sig") if log.exists() else ""


@pytest.mark.parametrize("clock", [STEPPED_GET_DATE, ""], ids=["stepped-back-an-hour", "control-steady"])
def test_a_silent_server_is_stopped_after_its_misses_whatever_the_clock_does(tmp_path: Path, clock: str) -> None:
    result, log = run_watchdog(tmp_path, clock)
    assert result.returncode == 0, result.stderr
    assert "(2 of 2)" in log and "is running but not answering: stopping it" in log
    ran = int(re.findall(r"ran (-?\d+)", result.stdout)[-1])
    assert 0 <= ran < 15, f"the server ran {ran} s by the monotonic clock: stopped after its grace and two misses"


DEPLOY = SUPERVISE.parent


def test_no_deploy_script_measures_a_duration_or_a_deadline_with_the_wall_clock() -> None:
    """A static guard over every script in deploy/: no Get-Date subtraction, no Get-Date deadline in seconds or minutes,
    no comparison against one. A calendar cutoff for file times (Remove-OldLogs' 14 days, AddDays) is not a duration."""
    banned = [
        r"\(Get-Date\)\s*-\s*\$",  # (Get-Date) - $began
        r"\(Get-Date\)\s*-(lt|le|gt|ge)\b",  # (Get-Date) -lt $deadline
        r"\(Get-Date\)\.Add(Seconds|Minutes|Milliseconds|Hours|Ticks)\(",  # a deadline in time units
        r"=\s*Get-Date\s*$",  # $began = Get-Date
    ]
    found = [
        f"{path.name}:{number}: {line.strip()}"
        for path in sorted(DEPLOY.glob("*.ps1"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if any(re.search(pattern, line) for pattern in banned)
    ]
    assert not found, "measure elapsed time with [Diagnostics.Stopwatch]:\n" + "\n".join(found)
