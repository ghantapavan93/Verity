"""Make the secret the gate signs with, and the invite links that open it (app/api/access.py).

    .venv/Scripts/python scripts/access.py secret                       # once: writes backend/data/access.secret (never printed)
    .venv/Scripts/python scripts/access.py invite min-kyu               # a link for one reader, good for 14 days
    .venv/Scripts/python scripts/access.py invite didier --days 7 --path "/?document=<id>&run=<id>"
    .venv/Scripts/python scripts/access.py check "<link or token>"      # who an invite is for and when it ends

The secret lives in a file under backend/data, which the repository ignores; the deployment reads it into
WORKBENCH_ACCESS_SECRET when it starts the API (deploy/supervise.ps1, deploy/up.ps1). It is never an argument, so it
is never in a shell history, and this script never prints it. An invite is printed, because sending it is the point:
it is a credential for one reader until it expires, so send it to that reader only. To take one reader's access
away, add the name to WORKBENCH_ACCESS_REVOKED and restart the API; to take everyone's, make a new secret.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.api.access import MIN_SECRET_CHARS, mint, verify  # noqa: E402
from app.config import settings  # noqa: E402

SECRET_FILE = settings.data_dir / "access.secret"


def read_secret() -> str:
    secret = os.environ.get("WORKBENCH_ACCESS_SECRET", "").strip() or (SECRET_FILE.read_text(encoding="utf-8").strip() if SECRET_FILE.exists() else "")
    if len(secret) < MIN_SECRET_CHARS:
        raise SystemExit(f"no secret: run `scripts/access.py secret` first (looked in WORKBENCH_ACCESS_SECRET and {SECRET_FILE})")
    return secret


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("secret", help="write a new signing secret to backend/data/access.secret")
    make.add_argument("--replace", action="store_true", help="overwrite an existing secret: every invite and session made under it stops working")
    invite = commands.add_parser("invite", help="print an invite link for one reader")
    invite.add_argument("subject", help="who the link is for; recorded in the token, shown nowhere public")
    invite.add_argument("--days", type=int, default=14, help="how long the link opens the workbench (default 14)")
    invite.add_argument("--path", default="/", help='where the link lands, for example "/?document=<id>&run=<id>" (default "/")')
    invite.add_argument("--origin", default=settings.app_url, help=f"the public origin (default WORKBENCH_APP_URL, now {settings.app_url})")
    check = commands.add_parser("check", help="say who an invite is for and whether it is still good")
    check.add_argument("invite")
    args = parser.parse_args(argv)

    if args.command == "secret":
        if SECRET_FILE.exists() and not args.replace:
            raise SystemExit(f"{SECRET_FILE} exists. Replacing it ends every invite and session; pass --replace to do that.")
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_text(secrets.token_urlsafe(48) + "\n", encoding="utf-8")
        print(f"wrote {SECRET_FILE} (not shown). Restart the API through deploy/ to turn the gate on; /api/health then reports access.")
        return 0
    if args.command == "invite":
        if not args.path.startswith("/") or args.path.startswith("//") or "#" in args.path:
            raise SystemExit('--path must be a path on the workbench, starting with one "/" and carrying no "#"')
        token = mint(args.subject, "verity-invite", args.days * 86400, read_secret())
        print(f"{args.origin.rstrip('/')}{args.path}#invite={token}")
        print(f"for {args.subject}, good for {args.days} days. It is a credential: send it to that reader only.", file=sys.stderr)
        return 0
    session = verify(args.invite.strip().rpartition("invite=")[2], "verity-invite", read_secret())
    if session is None:
        print("not valid under the current secret: expired, revoked, or not an invite this secret signed")
        return 1
    days = (session.expires_at - time.time()) / 86400
    print(f"an invite for {session.subject}, good for another {days:.1f} days")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
