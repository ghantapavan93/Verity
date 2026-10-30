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
import ipaddress
import json
import secrets
import shutil
import threading
import time
import weakref
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from typing import ClassVar, Literal

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as DbSession

from ..application.quotas import document_quotas, refuse_if_spent
from ..application.workspace import PUBLIC_PREFIX, is_public
from ..config import settings
from ..db import SessionLocal, get_session
from ..errors import AccessRequired, Conflict, Forbidden, InvalidInput, NotFound, Paused, TooManyRequests
from ..hashing import mac_sha256
from ..models import VisitorWorkspace, as_utc, utcnow
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
RUN_LIMIT, RUN_WINDOW_S = settings.run_start_limit, 600
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
    """At most ``limit`` events per key in any ``window_s`` seconds. Returns the seconds to wait when refused.

    A key whose newest event is older than the window is dropped once a window has passed since the last sweep, and at
    every retention pass (prune_windows): pruned only past 4,096 keys, a visitor's address or /64 was kept for the life
    of the process at demo traffic, the one place the API kept it (stress test, 2026-10-30, privacy 2)."""

    _every: ClassVar[weakref.WeakSet[SlidingWindow]] = weakref.WeakSet()

    def __init__(self, limit: int, window_s: int) -> None:
        self.limit, self.window_s = limit, window_s
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._swept = time.monotonic()
        SlidingWindow._every.add(self)

    def reset(self) -> None:
        """Forget every event: a new deployment, or a test that is its own reader."""
        with self._lock:
            self._events.clear()

    def _sweep(self, current: float) -> None:
        for stale in [k for k, v in self._events.items() if not v or v[-1] <= current - self.window_s]:
            del self._events[stale]
        self._swept = current

    def prune(self, now: float | None = None) -> None:
        with self._lock:
            self._sweep(time.monotonic() if now is None else now)

    def take(self, key: str, now: float | None = None) -> float | None:
        current = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= current - self.window_s:
                events.popleft()
            if len(events) >= self.limit:
                return events[0] + self.window_s - current
            events.append(current)
            # A flood of distinct keys does not grow this without bound, and no key outlives its window by more than one.
            if len(self._events) > 4096 or current - self._swept >= self.window_s:
                self._sweep(current)
            return None


def prune_windows(now: float | None = None) -> None:
    """Drop, from every window in this process, the keys past their window: at each retention pass (app.main)."""
    for window in list(SlidingWindow._every):
        window.prune(now)


exchanges = SlidingWindow(EXCHANGE_LIMIT, EXCHANGE_WINDOW_S)
run_starts = SlidingWindow(RUN_LIMIT, RUN_WINDOW_S)
visits = SlidingWindow(VISIT_LIMIT, ADDRESS_WINDOW_S)
address_uploads = SlidingWindow(ADDRESS_UPLOAD_LIMIT, ADDRESS_WINDOW_S)
address_runs = SlidingWindow(ADDRESS_RUN_LIMIT, ADDRESS_WINDOW_S)
workspace_writes = SlidingWindow(WORKSPACE_WRITE_LIMIT, ADDRESS_WINDOW_S)
address_writes = SlidingWindow(ADDRESS_WRITE_LIMIT, ADDRESS_WINDOW_S)
# Reads whose answer is large next to the request: a run's evidence pack carries the original file (up to 25 MB) and is
# zipped on every request, and a document comes back with its whole text. Nothing bounded them, so one visitor who
# uploaded once could ask for the same 26 MB pack in a loop, holding the upload link and the request threads the health
# probe also needs (security audit, 2026-10-30). A reader opens a contract a few times an hour and a pack rarely.
PACK_LIMIT, DOCUMENT_READ_LIMIT, PACKS_AT_ONCE = 30, 240, 2
address_packs = SlidingWindow(PACK_LIMIT, ADDRESS_WINDOW_S)
address_document_reads = SlidingWindow(DOCUMENT_READ_LIMIT, ADDRESS_WINDOW_S)
packs_building = threading.BoundedSemaphore(PACKS_AT_ONCE)
# A run's trust manifest locates every span in every section again, and its revision check scores every pair of loose
# sections of the two versions: seconds to minutes of CPU and up to gigabytes per GET, with no bound of any kind (stress
# test, 2026-10-30: GET /trust/diff on two 2,500-section versions took 15 s and 1.2 GB, and three at once three times
# that). Built two at a time in every store, since one process serves every reader; in the public store each counts as
# a contract view. What the diff costs itself is trust/diff.align's to bound.
TRUST_READS_AT_ONCE = 2
trust_reads_building = threading.BoundedSemaphore(TRUST_READS_AT_ONCE)


def _client_address(request: Request) -> str:
    """The address Cloudflare saw, when the request came through the tunnel; the socket's otherwise. Read by
    client_network alone: the wake-up share was keyed by it while every other window counted by network, and twelve
    addresses of one /64 spent the day's wake-ups (stress test, 2026-10-30), so no bound can be keyed by it."""
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")


def client_network(request: Request) -> str:
    """The network a request comes from, for the bounds on what one network has in flight at once (api/body_limit.py,
    api/documents.py): an IPv4 address itself, an IPv6 address's /64, the block one subscriber or one server is commonly
    given, so a host cannot multiply its share by using more of its own addresses. The hourly windows count by it too:
    by full address, a host with a /64 took a fresh address for every visit and no window filled (security audit,
    2026-10-30, reversing war room F-32 on the owner's instruction)."""
    address = _client_address(request)
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is None:
        # From the number, not the text: a scoped address ("fe80::1%eth0") does not parse back as a network.
        return str(ipaddress.IPv6Network((int(ip) >> 64 << 64, 64)))
    return str(ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) else ip)


def limit_run_starts(request: Request) -> None:
    """Mounted on the runs router: a reader may start so many runs in a while, and is told when to come back. With the
    gate on the reader is the invite's subject; with it off, the address. Until 2026-10-02 the limit applied only with
    the gate on, so an open site had none, and the deployed site was open. A public workspace's questions for the day
    are counted where the run is written (application/quotas.py), not here: counted here, every start of a burst passed."""
    if request.method != "POST":
        return
    refuse_if_paused()
    if is_public_workspace(getattr(request.state, "workspace", "")):
        _take(address_runs, client_network(request), "questions were asked from your network")
    wait = run_starts.take(getattr(request.state, "subject", None) or client_network(request))
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
def enter(body: InviteIn, request: Request, response: Response, replace: bool = False) -> AccessOut:
    """Exchange an invite for a session. The invite may be the bare token or the whole link it came in.

    A browser holding another reader's working session keeps it, 409 and no cookie, unless the request says the person
    chose to switch (``?replace=true``). An invite in the address silently replaced the session held, on arrival and on
    a change of the address, and what the reader added next went into the inviter's workspace (stress test, 2026-10-30,
    authz 1). A session of the same reader is renewed; an expired or revoked one is no session."""
    response.headers["Cache-Control"] = "no-store"
    if not enabled():
        return _out(None)
    if settings.anonymous_sessions:
        raise Forbidden("This demo opens without an invitation; an invite does not apply here.")
    wait = exchanges.take(client_network(request))
    if wait is not None:
        raise TooManyRequests(f"Too many attempts. Try again in {int(wait) + 1} seconds.", retry_after=int(wait) + 1)
    if not _same_origin(request):
        raise Forbidden("This request did not come from the workbench.")
    token = body.invite.strip().rpartition("invite=")[2].strip()
    invited = verify(token, "verity-invite", settings.access_secret)
    if invited is None:
        raise InvalidInput("That invite is not valid, or it has expired. Ask for a new link.")
    held = current_session(request)
    if held is not None and _session_serves_here(held.subject) and held.subject != invited.subject and not replace:
        raise Conflict(
            f"This browser is already inside as {held.subject}. The link is for {invited.subject}; nothing was changed. "
            "Switch only if you mean to work as that reader."
        )
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
    _take(address_writes, client_network(request), "changes from your network")


def limit_pack_downloads(request: Request) -> None:
    """A public workspace's network may download so many evidence packs an hour."""
    if is_public_workspace(getattr(request.state, "workspace", None)):
        _take(address_packs, client_network(request), "evidence packs downloaded from your network")


def limit_document_reads(request: Request) -> None:
    """A public workspace's network may open so many contracts an hour; each answer carries a whole contract."""
    if is_public_workspace(getattr(request.state, "workspace", None)):
        _take(address_document_reads, client_network(request), "contract views from your network")


def refuse_if_paused() -> None:
    if paused():
        raise Paused("New uploads and questions are paused on this demo for now. What you already added can still be read.")


def owner_only(request: Request) -> None:
    """Mounted on the corpus tools (goldens, families, batches): they read the store by content, across workspaces, and
    mean nothing to a visitor. A public workspace is told they do not exist."""
    if is_public_workspace(getattr(request.state, "workspace", None)):
        raise NotFound("route", request.url.path)


def refuse_upload_on_headers(request: Request) -> None:
    """What an upload is refused for on its headers alone, asked at the door (api/body_limit.py) before a byte of its
    body is read: the gate, the owner's pause, and a public store's disk. A paused demo still took a 20 MB body before
    saying so (war room W5 p4). admit_upload asks the last two again, with the bounds that need the store."""
    require_access(request)
    refuse_if_paused()
    if is_public_workspace(current_workspace(request)):
        refuse_if_disk_low()


def admit_upload(request: Request, session: DbSession, workspace: str) -> None:
    """Called before an upload is read. Every workspace: the owner's pause. A public workspace: the disk, its own bound
    and everyone's for the day as they stand now, and its address's. The bounds are counted here only to spare reading
    a file that would be refused; the count that decides is made again with the grant (application/quotas.py)."""
    refuse_if_paused()
    if not is_public_workspace(workspace):
        return
    refuse_if_disk_low()
    refuse_if_spent(session, document_quotas(workspace))
    _take(address_uploads, client_network(request), "uploads from your network")


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
    _take(visits, client_network(request), "new visits from your network")
    subject = ANONYMOUS_PREFIX + secrets.token_urlsafe(24)
    lifetime = settings.anonymous_retention_days * 86400
    now = utcnow()
    session.add(VisitorWorkspace(workspace_id=workspace_for(subject), created_at=now, expires_at=now + timedelta(seconds=lifetime)))
    session.commit()
    token = mint(subject, "verity-session", lifetime, settings.access_secret, now=now.timestamp())
    response.set_cookie(SESSION_COOKIE, token, max_age=lifetime, path="/", secure=True, httponly=True, samesite="strict")
    return AccessOut(required=True, entered=True, subject=None, anonymous=True, retention_days=settings.anonymous_retention_days)
