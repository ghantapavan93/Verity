"""Who may reach the workbench: a signed invite, exchanged for a signed session cookie.

The workbench is published for a few named readers. Until 2026-10-02 the gate was Cloudflare Access in front of the
tunnel (an email, then a one-time code): real, and too much to ask of someone following a link. This is the gate
inside the application instead, so the tunnel can publish the host without it and the store is still not public.

    invite link   https://<host>/<any page>#invite=<token>     made by scripts/access.py, one per reader
    exchange      POST /api/access/session {"invite": token}   the interface does this on arrival and strips the link
    session       Set-Cookie: __Host-verity_session=<token>    Secure, HttpOnly, SameSite=Strict, seven days
    every route   Depends(require_access)                      attached where the routers are mounted (app.main)

The invite rides in the URL fragment, which a browser never sends: it reaches no server log, no proxy and no Referer
header, and a link scanner that fetches the URL exchanges nothing. It is not single-use, deliberately: mail and chat
clients fetch links before a person does, and a reader who opens the link on a second device should get in. It
expires, it names one reader, and that reader can be revoked (`WORKBENCH_ACCESS_REVOKED`); changing the secret ends
every invite and every session at once.

Both tokens are `v1.<claims>.<mac>`: the claims as base64url JSON (subject, audience, issued, expires) and an
HMAC-SHA256 over them under `WORKBENCH_ACCESS_SECRET`. Nothing is stored: a token is valid when its MAC is, its
audience is the one asked for, its time has come and not passed, and its subject is not revoked. There is no
password, so there is nothing to hash, guess or forget; no account, no signup, no reset.

With no secret configured the gate is off and every request is let through, which is how a laptop, the tests and
the browser flows run. `/api/health` says which it is.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Request, Response

from ..config import settings
from ..errors import AccessRequired, Forbidden, InvalidInput, TooManyRequests
from ..hashing import mac_sha256
from ..schemas import AccessOut, InviteIn

SESSION_COOKIE = "__Host-verity_session"
TOKEN_VERSION = "v1"
Audience = Literal["verity-invite", "verity-session"]
MIN_SECRET_CHARS = 32
MAX_TOKEN_CHARS = 1024
CLOCK_SKEW_S = 60

# The two operations worth a limit once the host is reachable without Cloudflare Access: guessing at the exchange,
# and starting model runs, each of which holds the one GPU for half a minute or more. Per client address for the
# first (nobody is known yet), per reader for the second. In memory, in this process: one API process serves the
# preview, and a limit that forgets on restart is still a limit.
EXCHANGE_LIMIT, EXCHANGE_WINDOW_S = 10, 600
RUN_LIMIT, RUN_WINDOW_S = 20, 600


@dataclass(frozen=True)
class Session:
    subject: str
    expires_at: int


def enabled() -> bool:
    return bool(settings.access_secret)


def check_configuration() -> None:
    """A secret that is set must be one worth having. Called when the application is created."""
    if settings.access_secret and len(settings.access_secret) < MIN_SECRET_CHARS:
        raise RuntimeError(f"WORKBENCH_ACCESS_SECRET is shorter than {MIN_SECRET_CHARS} characters; make one with scripts/access.py secret")


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint(subject: str, audience: Audience, lifetime_s: int, secret: str, now: float | None = None) -> str:
    issued = int(time.time() if now is None else now)
    claims = {"sub": subject, "aud": audience, "iat": issued, "exp": issued + lifetime_s}
    body = f"{TOKEN_VERSION}.{_encode(json.dumps(claims, sort_keys=True, separators=(',', ':')).encode('utf-8'))}"
    return f"{body}.{mac_sha256(secret, body)}"


def verify(token: str | None, audience: Audience, secret: str, now: float | None = None) -> Session | None:
    """The session a token stands for, or None: malformed, signed by another secret, for another audience, not yet
    valid, expired or revoked are all the same answer, and none of them is told apart to the caller."""
    if not token or not secret or len(token) > MAX_TOKEN_CHARS:
        return None
    body, _, mac = token.rpartition(".")
    version, _, encoded = body.partition(".")
    if version != TOKEN_VERSION or not encoded or not mac:
        return None
    if not hmac.compare_digest(mac.encode("ascii", "replace"), mac_sha256(secret, body).encode("ascii")):
        return None
    try:
        claims = json.loads(_decode(encoded))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
    if not isinstance(claims, dict):
        return None
    subject, issued, expires = claims.get("sub"), claims.get("iat"), claims.get("exp")
    if not isinstance(subject, str) or not subject or type(issued) is not int or type(expires) is not int or claims.get("aud") != audience:
        return None
    current = time.time() if now is None else now
    if issued > current + CLOCK_SKEW_S or expires <= current or subject in settings.access_revoked:
        return None
    return Session(subject, expires)


def current_session(request: Request) -> Session | None:
    return verify(request.cookies.get(SESSION_COOKIE), "verity-session", settings.access_secret)


def _same_origin(request: Request) -> bool:
    """A request that changes something must come from the workbench's own pages. The cookie is SameSite=Strict, so a
    browser does not send it from elsewhere at all; this is the second lock, for a client that is not a browser."""
    origin = request.headers.get("origin")
    return origin is None or origin.rstrip("/") in {settings.app_url, *settings.cors_origins}


def require_access(request: Request) -> None:
    """Mounted on every router but this one and health. With the gate off it lets everything through."""
    if not enabled():
        return
    session = current_session(request)
    if session is None:
        raise AccessRequired("This is a private preview. Open your invite link to enter.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin(request):
        raise Forbidden("This request did not come from the workbench.")
    request.state.subject = session.subject


class SlidingWindow:
    """At most ``limit`` events per key in any ``window_s`` seconds. Returns the seconds to wait when refused."""

    def __init__(self, limit: int, window_s: int) -> None:
        self.limit, self.window_s = limit, window_s
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def take(self, key: str, now: float | None = None) -> float | None:
        current = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= current - self.window_s:
                events.popleft()
            if len(events) >= self.limit:
                return events[0] + self.window_s - current
            events.append(current)
            if len(self._events) > 4096:  # a flood of distinct keys does not grow this without bound
                for stale in [k for k, v in self._events.items() if not v or v[-1] <= current - self.window_s]:
                    del self._events[stale]
            return None


exchanges = SlidingWindow(EXCHANGE_LIMIT, EXCHANGE_WINDOW_S)
run_starts = SlidingWindow(RUN_LIMIT, RUN_WINDOW_S)


def client_address(request: Request) -> str:
    """The address Cloudflare saw, when the request came through the tunnel; the socket's otherwise."""
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")


def limit_run_starts(request: Request) -> None:
    """Mounted on the runs router: a reader may start so many runs in a while, and is told when to come back."""
    if not enabled() or request.method != "POST":
        return
    wait = run_starts.take(getattr(request.state, "subject", client_address(request)))
    if wait is not None:
        raise TooManyRequests(
            f"Too many runs were started in the last {RUN_WINDOW_S // 60} minutes. Try again in {int(wait) + 1} seconds.", retry_after=int(wait) + 1
        )


router = APIRouter(prefix="/api/access", tags=["access"])


def _out(session: Session | None) -> AccessOut:
    return AccessOut(required=enabled(), entered=not enabled() or session is not None, subject=session.subject if session else None)


@router.get("", response_model=AccessOut)
def access(request: Request, response: Response) -> AccessOut:
    """Whether the gate is on and whether this browser is through it. Open to everyone: it is how the page knows
    to ask for an invite, and it says nothing else."""
    response.headers["Cache-Control"] = "no-store"
    return _out(current_session(request) if enabled() else None)


@router.post("/session", response_model=AccessOut)
def enter(body: InviteIn, request: Request, response: Response) -> AccessOut:
    """Exchange an invite for a session. The invite may be the bare token or the whole link it came in."""
    response.headers["Cache-Control"] = "no-store"
    if not enabled():
        return _out(None)
    wait = exchanges.take(client_address(request))
    if wait is not None:
        raise TooManyRequests(f"Too many attempts. Try again in {int(wait) + 1} seconds.", retry_after=int(wait) + 1)
    if not _same_origin(request):
        raise Forbidden("This request did not come from the workbench.")
    token = body.invite.strip().rpartition("invite=")[2].strip()
    invited = verify(token, "verity-invite", settings.access_secret)
    if invited is None:
        raise InvalidInput("That invite is not valid, or it has expired. Ask for a new link.")
    lifetime = settings.access_session_days * 86400
    response.set_cookie(
        SESSION_COOKIE,
        mint(invited.subject, "verity-session", lifetime, settings.access_secret),
        max_age=lifetime,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return AccessOut(required=True, entered=True, subject=invited.subject)
