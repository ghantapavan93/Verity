"""Back up a Verity data directory, and restore one, so a deployment can be rolled back.

A code rollback cannot undo what a newer reader wrote: documents read under reader v10 stay in the store and finished
runs are immutable. The backup is the rollback. It holds a consistent copy of the database (SQLite's online backup API,
consistent under WAL while the API keeps writing), the original uploaded bytes, the finished memos and a manifest that
names every file by its sha256. Secrets (access.secret, invite lists) are not copied: they are configuration, kept and
restored by whoever holds them.

    python scripts/backup.py create --data-dir /data --out /backups/verity-20261009
    python scripts/backup.py verify /backups/verity-20261009
    python scripts/backup.py restore /backups/verity-20261009 --to /data-restored

A restore goes only into an empty or new directory, checks every hash first, and runs PRAGMA integrity_check.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.ingest import PARSER_VERSION  # noqa: E402

SCHEMA = "verity-backup/1"
DATABASE = "workbench.db"
# The durable files beside the database. memos/pending holds documents being written; they are not a record yet.
DIRECTORIES = ("documents", "memos")
SKIPPED = ("pending",)
COUNTED = ("documents", "sections", "runs", "findings", "finding_reviews", "memos")


class BackupError(RuntimeError):
    """The backup or the restore cannot be trusted; nothing that depends on it should go ahead."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def counts(database: Path) -> dict[str, int]:
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        present = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in COUNTED if table in present}


def integrity(database: Path) -> str:
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def triggers(database: Path) -> list[str]:
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        return sorted(row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'"))


def source_commit() -> str | None:
    try:
        found = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BACKEND, capture_output=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return found.stdout.decode().strip() or None


def _empty_target(target: Path) -> None:
    if target.exists() and any(target.iterdir()):
        raise BackupError(f"{target.name} is not empty; a backup or a restore goes only into an empty or new directory")
    target.mkdir(parents=True, exist_ok=True)


def create(data_dir: Path, out: Path, database: str = DATABASE) -> dict[str, object]:
    """A consistent copy of ``data_dir`` in ``out`` with its manifest. The source is only read."""
    source_db = data_dir / database
    if not source_db.is_file():
        raise BackupError(f"no {database} in the data directory")
    _empty_target(out)
    with sqlite3.connect(f"file:{source_db.as_posix()}?mode=ro", uri=True) as source, sqlite3.connect(out / database) as copy:
        source.backup(copy)
        # The copy is one self-contained file: in WAL mode (inherited from the source) every later read would leave -wal and
        # -shm files beside it. The API puts a restored store back into WAL when it connects.
        copy.execute("PRAGMA journal_mode=DELETE")
    checked = integrity(out / database)
    if checked != "ok":
        raise BackupError(f"the copied database fails integrity_check: {checked}")
    files: dict[str, dict[str, object]] = {database: {"sha256": sha256_file(out / database), "bytes": (out / database).stat().st_size}}
    for name in DIRECTORIES:
        folder = data_dir / name
        if not folder.is_dir():
            continue
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            relative = path.relative_to(data_dir)
            if (relative.parts[1:2] and relative.parts[1] in SKIPPED) or path.name.endswith(".part"):
                continue
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            files[relative.as_posix()] = {"sha256": sha256_file(target), "bytes": target.stat().st_size}
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "database": database,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_commit": source_commit(),
        "parser_version": PARSER_VERSION,
        "integrity_check": checked,
        "counts": counts(out / database),
        "triggers": triggers(out / database),
        "files": files,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest


def verify(backup: Path) -> dict[str, object]:
    """The manifest, once every file it names is present with its recorded hash and nothing else is in the backup."""
    manifest_path = backup / "manifest.json"
    if not manifest_path.is_file():
        raise BackupError("no manifest.json: not a Verity backup")
    manifest: dict[str, object] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise BackupError(f"the manifest is not a {SCHEMA} manifest")
    files = manifest["files"]
    assert isinstance(files, dict)
    for relative, recorded in files.items():
        path = backup / relative
        if not path.is_file():
            raise BackupError(f"{relative} is named in the manifest and missing")
        if sha256_file(path) != recorded["sha256"]:
            raise BackupError(f"{relative} does not match its recorded sha256")
    present = {p.relative_to(backup).as_posix() for p in backup.rglob("*") if p.is_file()} - {"manifest.json"}
    extra = sorted(present - set(files))
    if extra:
        raise BackupError(f"files not in the manifest: {extra[:5]}")
    return manifest


def restore(backup: Path, target: Path) -> dict[str, object]:
    """The backup, verified, copied into an empty ``target``; the restored database passes integrity_check and holds the
    counts and triggers the manifest recorded."""
    manifest = verify(backup)
    _empty_target(target)
    files = manifest["files"]
    assert isinstance(files, dict)
    for relative in files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / relative, destination)
        if sha256_file(destination) != files[relative]["sha256"]:
            raise BackupError(f"{relative} changed while it was copied")
    database = target / str(manifest["database"])
    if integrity(database) != "ok":
        raise BackupError("the restored database fails integrity_check")
    if counts(database) != manifest["counts"] or triggers(database) != manifest["triggers"]:
        raise BackupError("the restored database does not hold what the manifest recorded")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    made = commands.add_parser("create")
    made.add_argument("--data-dir", type=Path, required=True)
    made.add_argument("--out", type=Path, required=True)
    checked = commands.add_parser("verify")
    checked.add_argument("backup", type=Path)
    restored = commands.add_parser("restore")
    restored.add_argument("backup", type=Path)
    restored.add_argument("--to", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            manifest = create(args.data_dir, args.out)
        elif args.command == "verify":
            manifest = verify(args.backup)
        else:
            manifest = restore(args.backup, args.to)
    except BackupError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    files = manifest["files"]
    assert isinstance(files, dict)
    print(f"{args.command}: {len(files)} files, counts {manifest['counts']}, parser {manifest['parser_version']}, integrity {manifest['integrity_check']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
