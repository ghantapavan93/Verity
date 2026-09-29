"""Identity is computed in one place; these pin its behaviour."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app import hashing

BACKEND = Path(__file__).resolve().parents[1]


def test_sha256_helpers_match_the_standard_library(tmp_path: Path) -> None:
    assert hashing.sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert hashing.sha256_text("abc") == hashing.sha256_bytes(b"abc")
    assert hashing.sha256_text("day’s") == hashlib.sha256("day’s".encode()).hexdigest()
    path = tmp_path / "f.bin"
    path.write_bytes(b"\x00\x01abc")
    assert hashing.sha256_file(path) == hashlib.sha256(b"\x00\x01abc").hexdigest()


def test_fingerprint_is_stable_and_unambiguous() -> None:
    a = hashing.fingerprint("run/v1", "doc", "guid", "question")
    assert a == hashing.fingerprint("run/v1", "doc", "guid", "question")
    assert re.fullmatch(r"[0-9a-f]{64}", a)
    # Boundaries between parts matter.
    assert hashing.fingerprint("t", "ab", "c") != hashing.fingerprint("t", "a", "bc")
    # None and "" are different inputs (no guidance versus empty guidance).
    assert hashing.fingerprint("t", None, "q") != hashing.fingerprint("t", "", "q")
    # The schema name is part of the identity.
    assert hashing.fingerprint("run/v1", "x") != hashing.fingerprint("run/v2", "x")
    # Order matters.
    assert hashing.fingerprint("t", "a", "b") != hashing.fingerprint("t", "b", "a")


def test_nothing_else_in_the_app_imports_hashlib() -> None:
    offenders = []
    for path in (BACKEND / "app").rglob("*.py"):
        if path.name == "hashing.py":
            continue
        if re.search(r"^\s*(import hashlib|from hashlib import)", path.read_text(encoding="utf-8"), re.MULTILINE):
            offenders.append(path.relative_to(BACKEND).as_posix())
    assert offenders == [], f"hash through app.hashing instead: {offenders}"
