"""The event loop the API is served on in the Windows deployment (deploy/supervise.ps1, deploy/up.ps1).

Windows' default server loop (the proactor) closes its listening socket when one accept fails, and a client that resets
its connection while the server accepts it fails that accept with ERROR_NETNAME_DELETED (WinError 64). The process stays
up and answers no one: the supervisor restarted a silent API 18 times between 2026-10-09 and 2026-10-11. The selector
loop does not have that failure but caps a process at 512 sockets, which one visitor holding progress streams open can
reach (release trust review, 2026-10-11). This loop is the proactor with one change: an accept that failed because of
the client is retried, and every other failure is handled as CPython handles it (asyncio.proactor_events, 3.13).

Those retries are logged as a count, not one line each: a client can reset thousands of connections, and CPython's own
accept task would add a traceback for every one ("Task exception was never retrieved").

The same reset can also arrive after the accept, while the server closes the connection: CPython's shutdown() then
raises ConnectionResetError between the shutdown and the close, so the socket was left to the finaliser, the server kept
the connection until the transport was collected, and the error was logged with a traceback (seen as a flaky test, m9
gate, 2026-10-11). The plain connections this loop makes finish that close; any other failure there still propagates as
in CPython. TLS connections, which CPython's _make_ssl_transport builds itself, keep its behaviour; the deployment
serves plain HTTP on loopback behind the tunnel.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import sys
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

# Accept failures caused by the connecting client, not the listening socket: the client reset or abandoned it.
ERROR_NETNAME_DELETED = 64
ERROR_CONNECTION_ABORTED = 1236

# The first retried accept is logged at once; any that follow within this window are logged together when it closes.
REPORT_EVERY_SECONDS = 60.0
# An accept that fails before it is even started is retried after this pause, so a failure that repeats cannot spin.
RETRY_PAUSE_SECONDS = 0.5


def client_caused(error: OSError) -> bool:
    return isinstance(error, ConnectionError) or getattr(error, "winerror", None) in (ERROR_NETNAME_DELETED, ERROR_CONNECTION_ABORTED)


if sys.platform == "win32":
    from asyncio import exceptions, proactor_events, trsock

    class ResilientSocketTransport(proactor_events._ProactorSocketTransport):
        def _call_connection_lost(self, exc: BaseException | None) -> None:
            # CPython 3.13's _ProactorBasePipeTransport._call_connection_lost, with a client-caused shutdown failure
            # allowed: the client already reset the connection, and the close and the server's bookkeeping still run.
            t: Any = self  # the base class's private attributes, as CPython uses them
            if t._called_connection_lost:
                return
            try:
                t._protocol.connection_lost(exc)
            finally:
                if hasattr(t._sock, "shutdown") and t._sock.fileno() != -1:
                    try:
                        t._sock.shutdown(socket.SHUT_RDWR)
                    except OSError as error:
                        if not client_caused(error):
                            raise
                t._sock.close()
                t._sock = None
                server = t._server
                if server is not None:
                    server._detach(t)
                    t._server = None
                t._called_connection_lost = True

    class ResilientProactorEventLoop(asyncio.ProactorEventLoop):
        _retried = 0
        _window: asyncio.TimerHandle | None = None

        def _make_socket_transport(
            self,
            sock: socket.socket,
            protocol: asyncio.BaseProtocol,
            waiter: asyncio.Future[Any] | None = None,
            extra: dict[str, Any] | None = None,
            server: asyncio.AbstractServer | None = None,
        ) -> ResilientSocketTransport:
            return ResilientSocketTransport(self, sock, protocol, waiter, extra, server)  # type: ignore[arg-type]

        def _client_went_away(self, error: OSError) -> None:
            if self._window is None:
                log.warning("1 accept(s) failed because the client went away (%s); accepting again", error)
                self._window = self.call_later(REPORT_EVERY_SECONDS, self._report_retried)
            else:
                self._retried += 1

        def _report_retried(self) -> None:
            if self._retried == 0:
                self._window = None
                return
            log.warning("%d more accept(s) failed because the client went away in %gs; accepting again", self._retried, REPORT_EVERY_SECONDS)
            self._retried = 0
            self._window = self.call_later(REPORT_EVERY_SECONDS, self._report_retried)

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
                accepting = False
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
                            self._make_socket_transport(conn, protocol, extra={"peername": addr}, server=server)
                    if self.is_closed():
                        return
                    accepting = True
                    f = self._proactor.accept(sock)  # type: ignore[attr-defined]
                except OSError as exc:
                    if sock.fileno() != -1 and client_caused(exc):
                        self._client_went_away(exc)
                        # A completed accept that failed waits for the next client; one that failed to start would not.
                        if accepting:
                            self.call_later(RETRY_PAUSE_SECONDS, loop)
                        else:
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
