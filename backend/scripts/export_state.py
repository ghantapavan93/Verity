"""Build the public artifact: /state as a static site that needs no server, API, store, model or lab checkout to run.

The page's one request, the contract-state record, becomes a file beside it, written by the loader the API itself uses
(app.api.engineering.load_contract_state), so no number on the page is typed by hand. The export refuses unless the
record file's bytes hash to the pinned frozen record and the record's own body hash verifies. A manifest beside the
page names both hashes, the record's source commit and the Verity commit the page was built from.

    cd backend && .venv/Scripts/python scripts/export_state.py --build              # npm build into ../out-state, then the record
    cd backend && .venv/Scripts/python scripts/export_state.py --out ../out-state   # the record into an existing build

The record path defaults to the API's (the lab's committed results/contract-state.json); --record names another copy.

With --workbench-url the build also carries /break, the recorded failure, which needs no API either: its workbench
links lead to the live workbench at that address, and --hosting says where that workbench runs (/break tells its
readers). Without it the artifact is /state alone, as before.

    cd backend && .venv/Scripts/python scripts/export_state.py --build --workbench-url https://ivo.pavankg.dev
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.api.engineering import DEFAULT_CONTRACT_STATE, load_contract_state  # noqa: E402

# The frozen record (contract-state experiment, lab commit 822f107; FROZEN 2026-10-07). A different file is a different
# record and is not published under this page.
PINNED_RECORD_SHA256 = "cff26179f199d6d58768df968fbf4af5fda3e446e6fbe04844bf73c057290f1d"
RECORD_FILE = "contract-state.json"
MANIFEST_FILE = "evidence-manifest.json"


class ExportError(RuntimeError):
    """The artifact would not show the frozen record; nothing is written."""


def verity_commit() -> str | None:
    try:
        found = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return found.stdout.decode().strip() or None


def workbench_address(url: str) -> str:
    """The live workbench's origin, as /break links to it: https, a host, and nothing after it."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ExportError(f"the workbench address must be an https origin, like https://verity.example.com, not {url!r}")
    return f"https://{parts.netloc}"


def build(out: Path, workbench_url: str | None = None, hosting: str = "workstation") -> None:
    """`next build` in export mode; Next writes the static site into its distDir, ../out-state.

    With a workbench address the site carries /break as well (src/app/break/page.tsx), linking to that workbench."""
    npm = shutil.which("npm")
    if npm is None:
        raise ExportError("npm is not on PATH")
    environment = {**os.environ, "NEXT_PUBLIC_EXPORT": "state"}
    environment.pop("NEXT_PUBLIC_API_URL", None)  # the artifact has no API, and names none
    # Only what this call says: a value left in the shell would put /break, or a cloud, in an artifact that did not ask.
    environment.pop("NEXT_PUBLIC_WORKBENCH_URL", None)
    environment.pop("NEXT_PUBLIC_HOSTING", None)
    if workbench_url is not None:
        environment["NEXT_PUBLIC_WORKBENCH_URL"] = workbench_address(workbench_url)
        if hosting == "cloud":
            environment["NEXT_PUBLIC_HOSTING"] = "cloud"
    commit = verity_commit()
    if commit:
        environment["NEXT_PUBLIC_BUILD_SHA"] = commit
    subprocess.run([npm, "run", "build"], cwd=ROOT, env=environment, check=True)
    if not (out / "index.html").is_file():
        raise ExportError(f"the build left no index.html in {out.name}")


def export(record: Path, out: Path, pinned: str = PINNED_RECORD_SHA256) -> dict[str, object]:
    """Write the record and its manifest into the built site at ``out``; refuse anything but the pinned record."""
    if not (out / "index.html").is_file():
        raise ExportError(f"{out.name} holds no built page; build it first (--build)")
    if not record.is_file():
        raise ExportError(f"no record at {record.name}")
    file_sha256 = hashlib.sha256(record.read_bytes()).hexdigest()
    if file_sha256 != pinned:
        raise ExportError(f"{record.name} is not the frozen record: its bytes hash to {file_sha256[:12]}, not {pinned[:12]}")
    loaded = load_contract_state(record)
    if not loaded.available or not loaded.sha256_verified:
        raise ExportError(f"the record does not verify: {loaded.detail or 'its body hash does not match'}")
    body = loaded.model_dump(mode="json", by_alias=True)  # the shape GET /api/engineering/contract-state answers with
    (out / RECORD_FILE).write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    manifest: dict[str, object] = {
        "schema": "verity-public-state/1",
        "record_file": RECORD_FILE,
        "record_file_sha256": file_sha256,
        "record_body_sha256": loaded.sha256,
        "record_body_sha256_verified": loaded.sha256_verified,
        "record_source_commit": loaded.source_commit,
        "record_generated_at": loaded.generated_at,
        "served_file_sha256": hashlib.sha256((out / RECORD_FILE).read_bytes()).hexdigest(),
        "verity_commit": verity_commit(),
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (out / MANIFEST_FILE).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--record", type=Path, default=DEFAULT_CONTRACT_STATE)
    parser.add_argument("--out", type=Path, default=ROOT / "out-state")
    parser.add_argument("--build", action="store_true", help="run the export build first")
    parser.add_argument("--workbench-url", help="with --build: also carry /break, linking to the live workbench here")
    parser.add_argument("--hosting", choices=("workstation", "cloud"), default="workstation", help="where that workbench runs")
    args = parser.parse_args(argv)
    if args.workbench_url is not None and not args.build:
        parser.error("--workbench-url changes what is built; it needs --build")
    try:
        if args.build:
            build(args.out, args.workbench_url, args.hosting)
        manifest = export(args.record, args.out)
    except (ExportError, subprocess.CalledProcessError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(f"exported: record {str(manifest['record_file_sha256'])[:12]} (body verified), verity {str(manifest['verity_commit'])[:7]}, into {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
