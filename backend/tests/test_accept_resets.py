"""The API keeps accepting connections after clients reset theirs (release trust review, 2026-10-11).

On Windows asyncio's default server loop (the proactor) closes its listening socket when an accept fails with WinError 64
("the specified network name is no longer available"), which a client resetting its connection mid-handshake causes.
The process stays up and never accepts again. On the public demo the supervisor restarted a silent API 18 times between
2026-10-09 23:40 and 2026-10-11 02:48 (deploy/supervise.ps1 logs), about a minute of failed requests each. The selector
loop re-arms its listener after such an error. The deployment's launch line names the loop; this test runs the API the
way that line does and resets connections at it, and shows the default loop failing the same way, so it can tell.
"""

from __future__ import annotations

import contextlib
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SUPERVISE = BACKEND.parent / "deploy" / "supervise.ps1"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the proactor accept failure is a Windows behaviour")


def deployed_loop() -> str | None:
    """The --loop the supervisor gives uvicorn, or None when it gives none (uvicorn's default)."""
    line = next(line for line in SUPERVISE.read_text(encoding="utf-8").splitlines() if '"uvicorn"' in line)
    found = re.search(r'"--loop",\s*"([^"]+)"', line)
    return found.group(1) if found else None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            return bool(response.status == 200)
    except OSError:
        return False


def survives_resets(loop: str | None, tmp_path: Path, resets: int = 600) -> bool:
    port = free_port()
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    if loop:
        command += ["--loop", loop]
    env = {**os.environ, "WORKBENCH_DATA_DIR": str(tmp_path / f"store-{port}"), "WORKBENCH_PROVIDER": "replay"}
    server = subprocess.Popen(command, cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while not healthy(port):
            assert time.monotonic() < deadline, "the API did not start"
            time.sleep(0.3)
        for i in range(resets):
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            client.setblocking(False)
            with contextlib.suppress(OSError):
                client.connect(("127.0.0.1", port))
            client.close()
            if i % 200 == 199:
                time.sleep(0.5)
                if not healthy(port):
                    return False
        return healthy(port)
    finally:
        server.kill()
        server.wait(timeout=10)


def test_the_deployed_api_keeps_accepting_after_connection_resets(tmp_path: Path) -> None:
    assert deployed_loop() == "asyncio:SelectorEventLoop"
    assert survives_resets(deployed_loop(), tmp_path)


def test_control_the_default_loop_stops_accepting_under_the_same_resets(tmp_path: Path) -> None:
    assert not survives_resets(None, tmp_path)
