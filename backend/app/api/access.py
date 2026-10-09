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
import secrets
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..application.workspace import PUBLIC_PREFIX, is_public
from ..config import settings
from ..db import SessionLocal, get_session
from ..errors import AccessRequired, Forbidden, InvalidInput, NotFound, Paused, TooManyRequests
from ..hashing import mac_sha256
from ..models import DocumentAccess, Run, VisitorWorkspace, as_utc, utcnow
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
# Public use: a new anonymous session costs nothing to ask for, so a per-session bound alone could be escaped by asking
# again. These hold per client address (the address Cloudflare saw), across every session from it. New sessions have no
# global ceiling on purpose: anyone could spend it and shut every new visitor out. What costs is bounded instead.
VISIT_LIMIT, ADDRESS_UPLOAD_LIMIT, ADDRESS_RUN_LIMIT, ADDRESS_WINDOW_S = 20, 30, 30, 3600
# Reviews, memos and guidance: every other write a visitor can make (one workspace wrote about 1.5 GB of memos an
# hour before these, audit 2026-10-09).
WORKSPACE_WRITE_LIMIT, ADDRESS_WRITE_LIMIT = 60, 120
ANONYMOUS_PREFIX = "anon-"


@dataclass(frozen=True)
class Session:
    subject: str
    expires_at: int


def enabled() -> bool:
    return bool(settings.access_secret)


def check_configuration() -> None:
    """A secret that is set must be one worth having, and a deployment that says the gate is required must have one.
    Called when the application is created, so a missing secret stops the process instead of opening the site."""
    if settings.access_secret and len(settings.access_secret) < MIN_SECRET_CHARS:
        raise RuntimeError(f"WORKBENCH_ACCESS_SECRET is shorter than {MIN_SECRET_CHARS} characters; make one with scripts/access.py secret")
    if settings.access_required and not settings.access_secret:
        raise RuntimeError("WORKBENCH_ACCESS_REQUIRED is set but WORKBENCH_ACCESS_SECRET is empty; the gate would be off. Refusing to start open.")


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


OPEN_WORKSPACE = "open"


def workspace_for(subject: str) -> str:
    """The workspace an invite subject works in: opaque, stable, derived from the verified subject and the secret, so it
    names no one in the record and cannot be chosen by a request. The typed reviewer name is never an identity."""
    prefix = PUBLIC_PREFIX if subject.startswith(ANONYMOUS_PREFIX) else "ws-"
    return prefix + mac_sha256(settings.access_secret, f"workspace:{subject}")[:16]


def require_access(request: Request) -> None:
    """Mounted on every router but this one and health. With the gate off it lets everything through, into one open
    workspace; with it on, the session's subject gives the request its workspace."""
    if not enabled():
        request.state.workspace = OPEN_WORKSPACE
        return
    session = current_session(request)
    if session is None or not _session_serves_here(session.subject):
        raise AccessRequired("This is a private preview. Open your invite link to enter.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin(request):
        raise Forbidden("This request did not come from the workbench.")
    request.state.subject = session.subject
    request.state.workspace = workspace_for(session.subject)


def current_workspace(request: Request) -> str:
    """The workspace of this request, set by require_access; the open workspace when the gate is off."""
    workspace: str | None = getattr(request.state, "workspace", None)
    if workspace is None:
        return OPEN_WORKSPACE if not enabled() else workspace_for(getattr(request.state, "subject", ""))
    return workspace


class SlidingWindow:
    """At most ``limit`` events per key in any ``window_s`` seconds. Returns the seconds to wait when refused."""

    def __init__(self, limit: int, window_s: int) -> None:
        self.limit, self.window_s = limit, window_s
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Forget every event: a new deployment, or a test that is its own reader."""
        with self._lock:
            self._events.clear()

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
visits = SlidingWindow(VISIT_LIMIT, ADDRESS_WINDOW_S)
address_uploads = SlidingWindow(ADDRESS_UPLOAD_LIMIT, ADDRESS_WINDOW_S)
address_runs = SlidingWindow(ADDRESS_RUN_LIMIT, ADDRESS_WINDOW_S)
workspace_writes = SlidingWindow(WORKSPACE_WRITE_LIMIT, ADDRESS_WINDOW_S)
address_writes = SlidingWindow(ADDRESS_WRITE_LIMIT, ADDRESS_WINDOW_S)


def client_address(request: Request) -> str:
    """The address Cloudflare saw, when the request came through the tunnel; the socket's otherwise."""
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")


def limit_run_starts(request: Request) -> None:
    """Mounted on the runs router: a reader may start so many runs in a while, and is told when to come back. With the
    gate on the reader is the invite's subject; with it off, the address. Until 2026-10-02 the limit applied only with
    the gate on, so an open site had none, and the deployed site was open."""
    if request.method != "POST":
        return
    refuse_if_paused()
    workspace = getattr(request.state, "workspace", "")
    if is_public_workspace(workspace):
        _take(address_runs, client_address(request), "questions were asked from your network")
        with SessionLocal() as session:
            today = session.scalar(select(func.count(Run.id)).where(Run.workspace_id == workspace, Run.created_at >= _day_start())) or 0
        if today >= settings.anonymous_max_runs_per_day:
            raise TooManyRequests(
                f"This demo workspace has asked {settings.anonymous_max_runs_per_day} questions today, its limit. Try again tomorrow (UTC).",
                retry_after=_seconds_to_tomorrow(),
            )
    wait = run_starts.take(getattr(request.state, "subject", None) or client_address(request))
    if wait is not None:
        raise TooManyRequests(
            f"Too many runs were started in the last {RUN_WINDOW_S // 60} minutes. Try again in {int(wait) + 1} seconds.", retry_after=int(wait) + 1
        )


router = APIRouter(prefix="/api/access", tags=["access"])


def _out(session: Session | None) -> AccessOut:
    if session is not None and not _session_serves_here(session.subject):
        session = None
    shown = session.subject if session is not None and not session.subject.startswith(ANONYMOUS_PREFIX) else None
    anonymous = enabled() and settings.anonymous_sessions
    return AccessOut(
        required=enabled(),
        entered=not enabled() or session is not None,
        subject=shown,
        anonymous=anonymous,
        retention_days=settings.anonymous_retention_days if anonymous else None,
    )


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
    if settings.anonymous_sessions:
        raise Forbidden("This demo opens without an invitation; an invite does not apply here.")
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


# ---------------------------------------------------------------------------- public use without an invite


def is_public_workspace(workspace: str | None) -> bool:
    """A workspace an anonymous visit made: it reads only its own records, never the curated ones
    (application/workspace.py), and it is bounded and deleted on schedule (application/retention.py)."""
    return is_public(workspace)


def _session_serves_here(subject: str) -> bool:
    """In public mode only an anonymous session opens anything: an invited session signed under the same secret would
    write a ws- workspace into the public store, past every bound, never purged, and the next start would refuse the
    store (audit 2026-10-09). Elsewhere, any valid session; an anonymous one while its workspace is open."""
    if settings.anonymous_sessions and not subject.startswith(ANONYMOUS_PREFIX):
        return False
    return _visitor_workspace_open(subject)


def _visitor_workspace_open(subject: str) -> bool:
    """An anonymous session opens its workspace only while the workspace is registered and has not ended. A session
    never outlives its workspace: once retention deletes the row, the cookie opens nothing, and the next visit makes a
    new subject, so a new workspace id. An invited reader's session is not affected."""
    if not subject.startswith(ANONYMOUS_PREFIX):
        return True
    with SessionLocal() as session:
        row = session.get(VisitorWorkspace, workspace_for(subject))
        return row is not None and as_utc(row.expires_at) > utcnow()


def _day_start() -> datetime:
    now = utcnow()
    return datetime(now.year, now.month, now.day, tzinfo=UTC)


def _seconds_to_tomorrow() -> int:
    return int((_day_start() + timedelta(days=1) - utcnow()).total_seconds()) + 1


def _take(window: SlidingWindow, key: str, what: str) -> None:
    wait = window.take(key)
    if wait is not None:
        raise TooManyRequests(f"Too many {what} in the last hour. Try again in {int(wait) // 60 + 1} minutes.", retry_after=int(wait) + 1)


def paused() -> bool:
    """The owner's switch: a file named public.paused in the data directory, read on every request, no restart."""
    return (settings.data_dir / "public.paused").exists()


def refuse_if_disk_low() -> None:
    """The public store keeps free space on its disk: daily caps count files, not bytes."""
    if shutil.disk_usage(settings.data_dir).free < settings.public_min_free_bytes:
        raise Paused("The demo's disk is nearly full, so new uploads and changes are paused. What you already added can still be read.")


def limit_public_writes(request: Request) -> None:
    """Mounted on the routers that write besides uploads and runs (reviews, memos, guidance, versions): a public
    workspace's writes share an hourly bound per workspace and per address, the owner's pause and the disk check."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    workspace = getattr(request.state, "workspace", None)
    if not is_public_workspace(workspace):
        return
    refuse_if_paused()
    refuse_if_disk_low()
    _take(workspace_writes, str(workspace), "changes from this demo workspace")
    _take(address_writes, client_address(request), "changes from your network")


def refuse_if_paused() -> None:
    if paused():
        raise Paused("New uploads and questions are paused on this demo for now. What you already added can still be read.")


def owner_only(request: Request) -> None:
    """Mounted on the corpus tools (goldens, families, batches): they read the store by content, across workspaces, and
    mean nothing to a visitor. A public workspace is told they do not exist."""
    if is_public_workspace(getattr(request.state, "workspace", None)):
        raise NotFound("route", request.url.path)


def admit_upload(request: Request, session: DbSession, workspace: str) -> None:
    """Called before an upload is read. Every workspace: the owner's pause. A public workspace: its own bound, its
    address's, and everyone's for the day."""
    refuse_if_paused()
    if not is_public_workspace(workspace):
        return
    refuse_if_disk_low()
    held = session.scalar(select(func.count()).select_from(DocumentAccess).where(DocumentAccess.workspace_id == workspace)) or 0
    if held >= settings.anonymous_max_documents:
        raise TooManyRequests(
            f"This demo workspace already holds {settings.anonymous_max_documents} contracts, its limit. Ask about one of them.", retry_after=3600
        )
    today = (
        session.scalar(
            select(func.count())
            .select_from(DocumentAccess)
            .where(DocumentAccess.workspace_id.like(f"{PUBLIC_PREFIX}%"), DocumentAccess.created_at >= _day_start())
        )
        or 0
    )
    if today >= settings.anonymous_max_uploads_per_day:
        raise TooManyRequests("The demo has taken all the uploads it takes in a day. Try again tomorrow (UTC).", retry_after=_seconds_to_tomorrow())
    _take(address_uploads, client_address(request), "uploads from your network")


@router.post("/visit", response_model=AccessOut)
def visit(request: Request, response: Response, session: DbSession = Depends(get_session)) -> AccessOut:
    """A browser with no session is handed one of its own: an unpredictable subject the server makes (the client never
    chooses it), signed like an invite's session, in a workspace no other session can read. A browser that already has
    a working session keeps it, unrenewed, so a refresh or a second tab stays in the same workspace and the session
    still ends with the workspace."""
    response.headers["Cache-Control"] = "no-store"
    if not enabled() or not settings.anonymous_sessions:
        raise Forbidden("This workbench opens by invitation.")
    if not _same_origin(request):
        raise Forbidden("This request did not come from the workbench.")
    existing = current_session(request)
    if existing is not None and _session_serves_here(existing.subject):
        return _out(existing)
    _take(visits, client_address(request), "new visits from your network")
    subject = ANONYMOUS_PREFIX + secrets.token_urlsafe(24)
    lifetime = settings.anonymous_retention_days * 86400
    now = utcnow()
    session.add(VisitorWorkspace(workspace_id=workspace_for(subject), created_at=now, expires_at=now + timedelta(seconds=lifetime)))
    session.commit()
    token = mint(subject, "verity-session", lifetime, settings.access_secret, now=now.timestamp())
    response.set_cookie(SESSION_COOKIE, token, max_age=lifetime, path="/", secure=True, httponly=True, samesite="strict")
    return AccessOut(required=True, entered=True, subject=None, anonymous=True, retention_days=settings.anonymous_retention_days)
