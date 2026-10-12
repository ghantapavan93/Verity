"""The interface's lock file installs on every platform a release is built on: the workstation (Windows) and the cloud
image (Linux, deploy/cloud/Dockerfile.web runs `npm ci`).

npm writes the lock on the machine that ran it, and a lock written on Windows has twice lost optional packages only a
Linux install resolves (@emnapi/core and @emnapi/runtime, needed by @img/sharp-wasm32): `npm ci` on Linux then refused
the lock as out of sync and no cloud image could be built (fixed in f8a2f92, 2026-10-08; lost again with 960dcfd, found
by the cloud readiness review, 2026-10-12). npm's own check is to resolve every dependency of every package in the lock
the way Node resolves it; a dependency with no entry on that path is what it refuses.
"""

from __future__ import annotations

import json
from pathlib import Path

LOCK = Path(__file__).resolve().parents[2] / "package-lock.json"


def resolves(packages: dict[str, object], holder: str, name: str) -> bool:
    """Whether ``name``, required by the package at ``holder``, has an entry where Node looks: the holder's own
    node_modules, then each enclosing node_modules up to the root."""
    base = holder
    while True:
        if (f"{base}/node_modules/{name}" if base else f"node_modules/{name}") in packages:
            return True
        if not base:
            return False
        cut = base.rfind("node_modules/")
        base = base[:cut].rstrip("/") if cut > 0 else ""


def unresolved(lock: dict[str, object]) -> list[str]:
    packages = lock["packages"]
    assert isinstance(packages, dict)
    missing = []
    for holder, entry in packages.items():
        for field in ("dependencies", "optionalDependencies"):
            for name in entry.get(field, {}):
                if not resolves(packages, holder, name):
                    missing.append(f"{holder or '(root)'} needs {name}")
    return missing


def test_every_dependency_in_the_lock_has_an_entry_on_its_resolution_path() -> None:
    assert unresolved(json.loads(LOCK.read_text(encoding="utf-8"))) == []


def test_the_check_finds_the_entry_a_windows_lock_lost() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    del lock["packages"]["node_modules/@emnapi/runtime"]
    assert "node_modules/@img/sharp-wasm32 needs @emnapi/runtime" in unresolved(lock)
