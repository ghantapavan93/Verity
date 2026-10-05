"""Record what Verity does when a reviewed agreement is revised, and export the record as an evidence bundle.

    cd backend && .venv/Scripts/python scripts/export_review_evidence.py --out <folder>

The product is run for real, in process, against a scratch database: the first version of a fixture agreement is
uploaded and reviewed by the configured model; the second version is uploaded and declared to supersede the first;
the run's trust manifest and its trust diff against the second version are read from the same HTTP interface the
workbench uses. What comes back is written down unchanged, together with two things counted here: how many model
calls had been made before the revision and how many after it, and the hash of the run's record before and after
the diff was asked for.

Nothing is rewritten on the way out. The record is the API's own JSON. The export is a folder in the Evidence Bundle
format, version 1: ``bundle.json``, the record under ``records/`` and the two fixture documents under ``sources/``.
The format's specification and the code that checks a bundle live in the public research repository; this script
shares no code with it and imports nothing from it.

The two documents are fixtures written for this recording (``scripts/revision_evidence/``). They differ in one
phrase. The findings are whatever the model proposed and the verifier established on the day of the recording.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from httpx import Response

    from app.providers.admission import AdmissionController, Workload
    from app.providers.base import Generation, ModelProvider

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SOURCE_HOME = "backend/scripts/revision_evidence"  # where the fixtures are in this repository, and so under sources/ in the bundle
FIXTURES = BACKEND.parent / SOURCE_HOME
QUESTION = "What is the term of this Agreement, which law governs it, and may Customer terminate for convenience?"
GUIDANCE = "We can accept termination for convenience at 30 days' notice or more. Anything below 30 days requires review."
SCHEMA, RECORD_SCHEMA = "evidence-bundle/1", "verity-review-snapshot/1"
GENERATOR = ("backend/scripts/export_review_evidence.py",)
WAIT_SECONDS = 900
PRODUCER = "verity product evidence export"
# What a bundle says of itself when it was exported before its exporter or its documents were committed: the commit
# it names does not hold them, so it is a build for review and not a release.
REVIEW_BUILD = "verity product evidence export, review build: the exporter and the fixture documents were not yet in the commit named"


def canonical(value: object, sort_keys: bool = False) -> bytes:
    """The one way a bundle writes JSON: two-space indent, no ASCII escaping, a final newline, ``\\n`` line ends."""
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=sort_keys) + "\n").encode("utf-8")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ModelCalls:
    """How many model calls were made while this is open. A call is counted where it cannot be missed: the configured
    provider is admitted through one shared controller, so admissions there are its calls; a provider handed in (the
    tests hand one in) is counted at its own ``generate_json``. Nothing about a call is changed, and both are put
    back as they were on the way out."""

    def __init__(self, controller: AdmissionController, provider: ModelProvider | None) -> None:
        self.count = 0
        self._controller, self._provider = controller, provider
        self._admit = controller.acquire
        self._generate = provider.generate_json if provider is not None else None

    def __enter__(self) -> Self:
        admit, generate = self._admit, self._generate

        def admitted(workload: Workload) -> tuple[float, int]:
            self.count += 1
            return admit(workload)

        def generated(system: str, user: str, schema: dict[str, Any]) -> Generation:
            self.count += 1
            assert generate is not None
            return generate(system, user, schema)

        if self._provider is None:
            self._controller.acquire = admitted  # type: ignore[method-assign]
        else:
            self._provider.generate_json = generated  # type: ignore[method-assign]
        return self

    def __exit__(self, *exc: object) -> None:
        if self._provider is None:
            self._controller.acquire = self._admit  # type: ignore[method-assign]
        else:
            self._provider.generate_json = self._generate  # type: ignore[method-assign, assignment]


def record(scratch: Path, provider: ModelProvider | None = None) -> dict[str, Any]:
    """Run the product on the two fixture versions and return what its interface said, unchanged. The model is the
    configured one unless a provider is handed in, which the tests do. The process is pointed at a scratch database
    and data folder for the recording and pointed back afterwards, whatever happens."""
    from app import config
    from app import db as db_module
    from app.providers import admission

    before = (db_module.engine, config.settings.data_dir, config.settings.access_secret, config.settings.access_required)
    engine = db_module.make_engine(f"sqlite:///{(scratch / 'recording.db').as_posix()}")
    try:
        db_module.engine = engine
        db_module.SessionLocal.configure(bind=engine)
        config.settings.data_dir = scratch
        config.settings.access_secret = ""
        config.settings.access_required = False
        with ModelCalls(admission, provider) as calls:
            return recorded(calls, provider)
    finally:
        db_module.engine, config.settings.data_dir, config.settings.access_secret, config.settings.access_required = before
        db_module.SessionLocal.configure(bind=before[0])
        engine.dispose()


def recorded(calls: ModelCalls, provider: ModelProvider | None) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.main import create_app

    def must(response: Response, *codes: int) -> dict[str, Any]:
        if response.status_code not in codes:
            raise SystemExit(f"{response.request.method} {response.request.url.path} answered {response.status_code}: {response.text[:300]}")
        answer: dict[str, Any] = response.json()
        return answer

    with TestClient(create_app(provider=provider)) as client:
        texts = {name: (FIXTURES / f"agreement-{name}.txt").read_bytes() for name in ("v1", "v2")}
        first = must(client.post("/api/documents", files={"file": ("agreement-v1.txt", texts["v1"], "text/plain")}), 200, 201)
        guidance = must(client.post("/api/guidance", json={"text": GUIDANCE}), 200, 201)
        started = must(client.post("/api/runs", json={"documentId": first["id"], "guidanceId": guidance["id"], "question": QUESTION}), 202)
        deadline = time.monotonic() + WAIT_SECONDS
        run = must(client.get(f"/api/runs/{started['id']}"), 200)
        while run["stage"] not in ("complete", "failed") and time.monotonic() < deadline:
            time.sleep(2)
            run = must(client.get(f"/api/runs/{started['id']}"), 200)
        if run["stage"] != "complete":
            raise SystemExit(f"the run did not complete: stage {run['stage']}, reason {run.get('reason')}, error {run.get('error')}")
        calls_before = calls.count
        trust = must(client.get(f"/api/runs/{run['id']}/trust"), 200)

        second = must(client.post("/api/documents", files={"file": ("agreement-v2.txt", texts["v2"], "text/plain")}), 200, 201)
        version = must(client.post(f"/api/documents/{second['id']}/supersedes", json={"previousDocumentId": first["id"]}), 200, 201)
        listed = client.get(f"/api/documents/{second['id']}/versions")
        if listed.status_code != 200:
            raise SystemExit(f"the versions of the second document could not be read: {listed.status_code}")
        versions: list[dict[str, Any]] = listed.json()
        diff = must(client.get(f"/api/runs/{run['id']}/trust/diff", params={"documentId": second["id"]}), 200)
        run_after = must(client.get(f"/api/runs/{run['id']}"), 200)
        trust_after = must(client.get(f"/api/runs/{run['id']}/trust"), 200)

    return {
        "schema": RECORD_SCHEMA,
        "what_this_is": "A recording of Verity, the product, run on two fixture versions of one agreement. "
        "Not a benchmark and not a measurement of legal judgment.",
        "question": QUESTION,
        "guidance": GUIDANCE,
        "documents": {
            "v1": {"file": f"sources/{SOURCE_HOME}/agreement-v1.txt", "sha256": digest(texts["v1"]), "document": first},
            "v2": {"file": f"sources/{SOURCE_HOME}/agreement-v2.txt", "sha256": digest(texts["v2"]), "document": second},
        },
        "run": run,
        "trust": trust,
        "supersedes": version,
        "versions": versions,
        "diff": diff,
        "model_calls": {"before_the_revision": calls_before, "after_the_revision": calls.count - calls_before},
        "run_record_sha256": {"before_the_diff": digest(canonical(run, sort_keys=True)), "after_the_diff": digest(canonical(run_after, sort_keys=True))},
        "trust_manifest_id": {"before_the_diff": trust["manifestId"], "after_the_diff": trust_after["manifestId"]},
    }


def bundle(snapshot: dict[str, Any], commit: str, generator: dict[str, bytes], sources: dict[str, bytes], producer: str = PRODUCER) -> dict[str, bytes]:
    """The bundle's files, by their path in it. ``sources`` are the fixture files by their path in this repository;
    each keeps that path under ``sources/``. Pure: the same record, commit and sources give the same bytes."""
    record_path = "records/review-snapshot.json"
    files = {record_path: canonical(snapshot), **{f"sources/{path}": content for path, content in sources.items()}}
    listed: list[dict[str, Any]] = [
        {
            "path": record_path,
            "role": "record",
            "record_schema": RECORD_SCHEMA,
            "sha256": digest(files[record_path]),
            "bytes": len(files[record_path]),
            "parents": [f"sources/{path}" for path in sorted(sources)],
        }
    ]
    listed += [
        {
            "path": f"sources/{path}",
            "role": "source",
            "sha256": digest(sources[path]),
            "bytes": len(sources[path]),
            "source_path": path,
            "source_sha256": digest(sources[path]),
        }
        for path in sorted(sources)
    ]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA,
        "producer": producer,
        "source_repository": "verity",
        "source_commit": commit,
        "generated_by": GENERATOR[0],
        "generated_version": "1",
        "generator": [{"path": path, "sha256": digest(content)} for path, content in generator.items()],
        "parents": [],
        "scene_grammar": 1,
        "files": listed,
    }
    manifest["artifact_id"] = "sha256:" + digest(canonical(manifest, sort_keys=True))
    files["bundle.json"] = canonical(manifest, sort_keys=True)
    return files


# What a string that names a machine looks like, whichever machine: a drive, a home or temporary folder, a
# backslash path, a loopback or any numeric address.
MACHINE = re.compile(
    r"[A-Za-z]:[\\/]|\\\\|(?:^|[\s\"'(=])/(?:home|Users|tmp|var|private|mnt)/|\blocalhost\b|\[::1\]|\b\d{1,3}(?:\.\d{1,3}){3}\b", re.IGNORECASE
)


def leaks(snapshot: object) -> list[str]:
    """Every string in the record that names a machine or the person at it. A record that holds one is not exported.
    The strings are looked at as they are, not as JSON would escape them, so no form of a path is missed for the
    way it happens to be written; and this machine's own names are looked for whatever else a string looks like."""
    own = {name.lower() for name in (Path.home().name, getpass.getuser(), socket.gethostname()) if len(name) > 2}
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(key)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and (MACHINE.search(node) or any(name in node.lower() for name in own)):
            found.append(node[:80])

    walk(snapshot)
    return found


def committed(path: str, repository: Path) -> bool:
    """Whether ``path`` is in the current commit and the file on disk is that commit's, byte for byte."""
    blob = subprocess.run(["git", "cat-file", "blob", f"HEAD:{path}"], cwd=repository, capture_output=True, check=False)
    return blob.returncode == 0 and blob.stdout == (repository / path).read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="the folder to write the bundle to; replaced if it exists")
    parser.add_argument(
        "--review-build", action="store_true", help="export although the exporter or the fixtures are not committed; the bundle says so of itself"
    )
    args = parser.parse_args()
    repository = BACKEND.parent
    sources = {f"{SOURCE_HOME}/{path.name}": path.read_bytes() for path in sorted(FIXTURES.glob("agreement-*.txt"))}
    loose = [path for path in (*GENERATOR, *sources) if not committed(path, repository)]
    if loose and not args.review_build:
        raise SystemExit(
            f"not in the current commit, or changed since: {loose}. A bundle names one commit and stands on that commit's files; "
            "commit them, or pass --review-build"
        )
    # The commit the bundle names is the last one that changed the exporter or a fixture: the commit that holds what
    # the record was made from. A review build, whose files are not committed, can only name the checkout's commit.
    asked = ["git", "rev-parse", "HEAD"] if loose else ["git", "log", "-1", "--format=%H", "--", *GENERATOR, *sources]
    commit = subprocess.run(asked, cwd=repository, capture_output=True, check=True).stdout.decode().strip()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        snapshot = record(Path(scratch))
    found = leaks(snapshot)
    if found:
        raise SystemExit(f"the record names a machine ({found}); nothing is exported")
    files = bundle(snapshot, commit, {path: (repository / path).read_bytes() for path in GENERATOR}, sources, REVIEW_BUILD if loose else PRODUCER)
    if args.out.exists():
        shutil.rmtree(args.out)
    for name, content in files.items():
        (args.out / name).parent.mkdir(parents=True, exist_ok=True)
        (args.out / name).write_bytes(content)
    changes = snapshot["diff"].get("findings", [])
    calls = snapshot["model_calls"]
    print(
        f"wrote {len(files)} files to {args.out}{' (a review build)' if loose else ''}: {len(snapshot['run']['findings'])} findings, "
        f"{len(changes)} accounted for in the diff, model calls before the revision {calls['before_the_revision']}, after {calls['after_the_revision']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
