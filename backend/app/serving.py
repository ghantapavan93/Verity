"""The event loop the API is served on in the Windows deployment (deploy/supervise.ps1, deploy/up.ps1).

Windows' default server loop (the proactor) closes its listening socket when one accept fails, and a client that resets
its connection while the server accepts it fails that accept with ERROR_NETNAME_DELETED (WinError 64). The process stays
up and answers no one: the supervisor restarted a silent API 18 times between 2026-10-09 and 2026-10-11. The selector
loop does not have that failure but caps a process at 512 sockets, which one visitor holding progress streams open can
reach (release trust review, 2026-10-11). This loop is the proactor with one change: an accept that failed because of
the client is retried, and every other failure is handled as CPython handles it (asyncio.proactor_events, 3.13).

Those retries are logged as a count, not one line each: a client can reset thousands of connections, and CPython's own
accept task would add a traceback for every one ("Task exception was never retrieved").
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import sys
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

# Accept failures caused by the connecting client, not the listening socket: the client reset or abandoned it.
ERROR_NETNAME_DELETED = 64
ERROR_CONNECTION_ABORTED = 1236

# Retried accepts are reported at most this often, with the count since the last report.
REPORT_EVERY_SECONDS = 60.0


def client_caused(error: OSError) -> bool:
    return isinstance(error, ConnectionError) or getattr(error, "winerror", None) in (ERROR_NETNAME_DELETED, ERROR_CONNECTION_ABORTED)


if sys.platform == "win32":
    from asyncio import exceptions, trsock

    class ResilientProactorEventLoop(asyncio.ProactorEventLoop):
        _retried = 0
        _reported_at: float | None = None

        def _client_went_away(self, error: OSError) -> None:
            self._retried += 1
            now = time.monotonic()
            if self._reported_at is None or now - self._reported_at >= REPORT_EVERY_SECONDS:
                log.warning("%d accept(s) failed because the client went away (last: %s); accepting again", self._retried, error)
                self._retried, self._reported_at = 0, now

        def call_exception_handler(self, context: dict[str, Any]) -> None:
            # IocpProactor.accept wraps each accept in a task no one awaits; when the client went away its exception is
            # the one _start_serving already handled, and CPython would log it again with a traceback.
            task, error = context.get("future"), context.get("exception")
            if (
                isinstance(task, asyncio.Task)
                and isinstance(error, OSError)
                and client_caused(error)
                and task.get_coro().__qualname__ == "IocpProactor.accept.<locals>.accept_coro"  # type: ignore[union-attr]
            ):
                return
            super().call_exception_handler(context)

        def _start_serving(
            self,
            protocol_factory: Callable[[], asyncio.BaseProtocol],
            sock: socket.socket,
            sslcontext: ssl.SSLContext | None = None,
            server: asyncio.AbstractServer | None = None,
            backlog: int = 100,
            ssl_handshake_timeout: float | None = None,
            ssl_shutdown_timeout: float | None = None,
        ) -> None:
            # CPython 3.13's BaseProactorEventLoop._start_serving, with the client-caused accept failure retried.
            def loop(f: asyncio.Future[tuple[socket.socket, object]] | None = None) -> None:
                try:
                    if f is not None:
                        conn, addr = f.result()
                        protocol = protocol_factory()
                        if sslcontext is not None:
                            self._make_ssl_transport(  # type: ignore[attr-defined]
                                conn,
                                protocol,
                                sslcontext,
                                server_side=True,
                                extra={"peername": addr},
                                server=server,
                                ssl_handshake_timeout=ssl_handshake_timeout,
                                ssl_shutdown_timeout=ssl_shutdown_timeout,
                            )
                        else:
                            self._make_socket_transport(conn, protocol, extra={"peername": addr}, server=server)  # type: ignore[attr-defined]
                    if self.is_closed():
                        return
                    f = self._proactor.accept(sock)  # type: ignore[attr-defined]
                except OSError as exc:
                    if sock.fileno() != -1 and client_caused(exc):
                        self._client_went_away(exc)
                        self.call_soon(loop)
                    elif sock.fileno() != -1:
                        self.call_exception_handler({"message": "Accept failed on a socket", "exception": exc, "socket": trsock.TransportSocket(sock)})
                        sock.close()
                except exceptions.CancelledError:
                    sock.close()
                else:
                    self._accept_futures[sock.fileno()] = f  # type: ignore[attr-defined]
                    f.add_done_callback(loop)

            self.call_soon(loop)
