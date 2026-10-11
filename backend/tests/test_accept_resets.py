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
import hashlib
import inspect
import logging
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SUPERVISE = BACKEND.parent / "deploy" / "supervise.ps1"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the proactor accept failure is a Windows behaviour")


def deployed_loop(script: Path = SUPERVISE) -> str | None:
    """The --loop a deploy script gives uvicorn, or None when it gives none (uvicorn's default)."""
    line = next(line for line in script.read_text(encoding="utf-8").splitlines() if '"uvicorn"' in line)
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
    assert deployed_loop(SUPERVISE.with_name("up.ps1")) == deployed_loop()  # the manual start runs the same loop
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


def test_every_retried_accept_is_counted_in_the_log(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    # Review of 39ade6e: a burst shorter than the report window was logged as "1 accept(s)" and the rest never reported.
    # The first failure is logged at once; those that follow are reported when the window closes, so the counts add up.
    from app import serving

    monkeypatch.setattr(serving, "REPORT_EVERY_SECONDS", 0.05)
    loop = serving.ResilientProactorEventLoop()
    reset = OSError(22, "The specified network name is no longer available", None, 64)
    try:
        with caplog.at_level(logging.WARNING, logger="app.serving"):
            for _ in range(37):
                loop._client_went_away(reset)
            loop.run_until_complete(asyncio.sleep(0.2))
            for _ in range(5):  # a second burst, after a quiet window
                loop._client_went_away(reset)
            loop.run_until_complete(asyncio.sleep(0.2))
    finally:
        loop.close()
    counts = [int(m) for m in re.findall(r"(\d+) (?:more )?accept\(s\) failed", caplog.text)]
    assert sum(counts) == 42
    assert len(counts) == 4  # each burst: the first at once, the rest together


def test_an_accept_that_fails_to_start_is_retried_after_a_pause_not_in_a_spin() -> None:
    # Review of 39ade6e: an accept failing as it starts, rather than when a client arrives, has nothing to wait for; an
    # immediate retry would spin a core while the throttled log showed one line a minute.
    from app.serving import RETRY_PAUSE_SECONDS, ResilientProactorEventLoop

    loop = ResilientProactorEventLoop()
    listener = socket.create_server(("127.0.0.1", 0))
    attempts = 0

    def refuse(_sock: socket.socket) -> None:
        nonlocal attempts
        attempts += 1
        raise ConnectionResetError(10054, "reset as the accept started")

    try:
        loop._proactor.accept = refuse  # type: ignore[attr-defined]
        loop._start_serving(asyncio.Protocol, listener)
        loop.run_until_complete(asyncio.sleep(1.0))
        assert 1 < attempts <= 1.0 / RETRY_PAUSE_SECONDS + 1  # retried, and paced
        assert listener.fileno() != -1  # still listening
    finally:
        listener.close()
        loop.close()


def test_the_cpython_code_the_loop_copies_is_the_code_it_was_written_against() -> None:
    # app.serving copies BaseProactorEventLoop._start_serving and relies on IocpProactor.accept's task name and private
    # attributes (CPython 3.13.2). A Python upgrade that changes either fails here, to be compared before it ships.
    import asyncio.proactor_events
    import asyncio.windows_events

    def digest(function: object) -> str:
        return hashlib.sha256(inspect.getsource(function).encode()).hexdigest()  # type: ignore[arg-type]

    assert digest(asyncio.proactor_events.BaseProactorEventLoop._start_serving) == "7b6bcf24da6fafb38c63e276e1de553706da3f0d0bbc7300b521cb4599145afe"  # type: ignore[attr-defined]
    assert digest(asyncio.windows_events.IocpProactor.accept) == "66c5aee644d5fafa38425393e30a71bf12b57b1f4fafd4340126ce6869956185"
    # ResilientSocketTransport copies _call_connection_lost and the loop replaces _make_socket_transport (m9).
    lost = asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost  # type: ignore[attr-defined]
    make = asyncio.proactor_events.BaseProactorEventLoop._make_socket_transport  # type: ignore[attr-defined]
    assert digest(lost) == "21755f1f4d9172c66ccb8ff6787e522916a0375b1e47222cb5f74916f30fa5ef"
    assert digest(make) == "1811908cb3d4c5d7302c2f554515621e8df19f71edd7c5e1985e6736a297b256"


class ClosingSocket:
    """A connected socket whose shutdown fails the way a reset one does on Windows, recording what was done to it."""

    def __init__(self, error: OSError) -> None:
        self.error, self.closed = error, False

    def fileno(self) -> int:
        return -1 if self.closed else 5

    def shutdown(self, how: int) -> None:
        raise self.error

    def close(self) -> None:
        self.closed = True


def closing_transport(error: OSError) -> SimpleNamespace:
    """The state _call_connection_lost reads and writes, without a live connection behind it."""
    server = SimpleNamespace(detached=[])
    server._detach = server.detached.append
    protocol = SimpleNamespace(lost=[])
    protocol.connection_lost = protocol.lost.append
    return SimpleNamespace(_called_connection_lost=False, _protocol=protocol, _sock=ClosingSocket(error), _server=server)


@pytest.mark.parametrize(
    "error",
    [ConnectionResetError(10054, "reset by peer"), ConnectionAbortedError(10053, "aborted"), OSError(22, "gone", None, 64)],
    ids=["reset", "aborted", "netname-deleted"],
)
def test_a_connection_the_client_reset_is_closed_and_released(error: OSError) -> None:
    # CPython 3.13.2 let this error escape after protocol.connection_lost: no close, the server still counting the
    # connection, and a traceback in the log (the flaky m9 gate). The transport the loop makes finishes all three.
    from app.serving import ResilientSocketTransport

    t = closing_transport(error)
    sock, server = t._sock, t._server
    ResilientSocketTransport._call_connection_lost(t, None)  # type: ignore[arg-type]
    assert t._protocol.lost == [None]
    assert sock.closed and t._sock is None
    assert server.detached == [t] and t._server is None
    assert t._called_connection_lost
    ResilientSocketTransport._call_connection_lost(t, None)  # type: ignore[arg-type]  # a second call is a no-op
    assert t._protocol.lost == [None]


def test_control_a_shutdown_failure_the_client_did_not_cause_still_propagates() -> None:
    from app.serving import ResilientSocketTransport

    t = closing_transport(OSError(9, "bad file descriptor"))
    with pytest.raises(OSError, match="bad file descriptor"):
        ResilientSocketTransport._call_connection_lost(t, None)  # type: ignore[arg-type]
    assert not t._called_connection_lost


def test_the_loop_serves_every_connection_on_that_transport() -> None:
    from app.serving import ResilientProactorEventLoop, ResilientSocketTransport

    seen: list[object] = []

    async def scenario() -> None:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            seen.append(writer.transport)
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        _, writer = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.2)
        writer.close()
        server.close()
        await server.wait_closed()

    loop = ResilientProactorEventLoop()
    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()
    assert [type(t) for t in seen] == [ResilientSocketTransport]
