"""The API keeps accepting connections after clients reset theirs (release trust review, 2026-10-11).

On Windows asyncio's default server loop (the proactor) closes its listening socket when an accept fails with WinError 64
("the specified network name is no longer available"), which a client resetting its connection mid-handshake causes.
The process stays up and never accepts again. On the public demo the supervisor restarted a silent API 18 times between
2026-10-09 23:40 and 2026-10-11 02:48 (deploy/supervise.ps1 logs), about a minute of failed requests each. The deployment
runs app.serving's loop, which retries an accept the client caused to fail. These tests run the API the way the launch
line does, reset connections at it and hold many open, and show the default and selector loops failing, so they can tell.
"""

from __future__ import annotations

import asyncio
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


def survives_resets(loop: str | None, tmp_path: Path, resets: int = 600, log: Path | None = None) -> bool:
    """Resets ``resets`` connections at the API, then asks health; the API's stderr goes to ``log`` when given."""
    port = free_port()
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    if loop:
        command += ["--loop", loop]
    env = {**os.environ, "WORKBENCH_DATA_DIR": str(tmp_path / f"store-{port}"), "WORKBENCH_PROVIDER": "replay"}
    stderr = log.open("wb") if log else subprocess.DEVNULL
    server = subprocess.Popen(command, cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=stderr)
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
        if log:
            stderr.close()  # type: ignore[union-attr]


def holds_connections(loop: str | None, tmp_path: Path, held: int = 600) -> bool:
    """Opens ``held`` connections and keeps them open (as visitors holding progress streams would), then asks health."""
    port = free_port()
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    if loop:
        command += ["--loop", loop]
    env = {**os.environ, "WORKBENCH_DATA_DIR": str(tmp_path / f"store-{port}"), "WORKBENCH_PROVIDER": "replay"}
    server = subprocess.Popen(command, cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sockets: list[socket.socket] = []
    try:
        deadline = time.monotonic() + 30
        while not healthy(port):
            assert time.monotonic() < deadline, "the API did not start"
            time.sleep(0.3)
        for _ in range(held):
            client = socket.create_connection(("127.0.0.1", port), timeout=5)
            sockets.append(client)
        time.sleep(1)
        return healthy(port)
    finally:
        for client in sockets:
            client.close()
        server.kill()
        server.wait(timeout=10)


def test_the_deployed_api_keeps_accepting_after_connection_resets(tmp_path: Path) -> None:
    assert deployed_loop() == "app.serving:ResilientProactorEventLoop"
    assert survives_resets(deployed_loop(), tmp_path)


def test_client_resets_do_not_flood_the_log(tmp_path: Path) -> None:
    # One traceback and one warning per reset (2,661 tracebacks in a 3 MB log after 3,000 local resets) would let any
    # client fill the supervisor's log; what an operator needs is that resets happened, and how many.
    log = tmp_path / "api.log"
    assert survives_resets(deployed_loop(), tmp_path, log=log)
    text = log.read_text(encoding="utf-8", errors="replace")
    assert "accepting again" in text
    assert "Traceback" not in text
    assert text.count("accepting again") <= 3


def test_control_the_default_loop_stops_accepting_under_the_same_resets(tmp_path: Path) -> None:
    assert not survives_resets(None, tmp_path)


def test_the_deployed_api_holds_more_connections_than_select_allows(tmp_path: Path) -> None:
    # The selector loop, the first fix tried, has no WinError 64 failure but caps a process at 512 sockets (review of
    # 311e30c): one visitor holding progress streams open could silence it.
    assert holds_connections(deployed_loop(), tmp_path)


def test_control_the_selector_loop_falls_silent_past_its_socket_limit(tmp_path: Path) -> None:
    assert not holds_connections("asyncio:SelectorEventLoop", tmp_path)


def test_control_other_unretrieved_errors_are_still_reported() -> None:
    # The log filter drops only CPython's accept task failing because the client went away; the same error from any
    # other task, and any other error, still reaches the exception handler.
    from app.serving import ResilientProactorEventLoop

    async def accept_coro() -> None:
        pass

    async def other() -> None:
        pass

    accept_coro.__qualname__ = "IocpProactor.accept.<locals>.accept_coro"
    loop = ResilientProactorEventLoop()
    reported: list[dict[str, object]] = []
    loop.set_exception_handler(lambda _loop, context: reported.append(context))
    reset = OSError(22, "The specified network name is no longer available", None, 64)
    try:
        tasks = {name: loop.create_task(coro()) for name, coro in (("accept", accept_coro), ("other", other))}
        loop.run_until_complete(asyncio.gather(*tasks.values()))
        loop.call_exception_handler({"message": "Task exception was never retrieved", "exception": reset, "future": tasks["accept"]})
        assert reported == []
        loop.call_exception_handler({"message": "Task exception was never retrieved", "exception": reset, "future": tasks["other"]})
        loop.call_exception_handler({"message": "x", "exception": OSError(22, "refused", None, 10013), "future": tasks["accept"]})
        assert len(reported) == 2
    finally:
        loop.close()
