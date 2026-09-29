"""Hand mutation run over the evidence boundary: change one decision line at a time, run the
suite, restore the file, report which test noticed.

This is the measurement that would earn a mutation-testing dependency, kept as a script until it
does (DECISIONS.md, 2026-09-28: nine mutants, one survivor, one test added). Every file is restored
from memory in a ``finally`` block and its bytes are compared afterwards; the script refuses to
report success if anything differs.

    .venv/Scripts/python scripts/mutate_by_hand.py          # all mutants
    .venv/Scripts/python scripts/mutate_by_hand.py M3 M7    # by name prefix
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SERVICE = BACKEND / "app" / "runs" / "service.py"
SPANS = BACKEND / "app" / "verify" / "spans.py"
DB = BACKEND / "app" / "db.py"
SUITE_TIMEOUT_S = 300


@dataclass(frozen=True)
class Mutant:
    name: str
    path: Path
    old: str
    new: str


MUTANTS: tuple[Mutant, ...] = (
    Mutant("M1 mismatch counts as verified", SERVICE, "verified = located is not None", "verified = True"),
    Mutant("M2 verified inverted", SERVICE, "verified = located is not None", "verified = located is None"),
    Mutant("M3 relocation to other candidates disabled", SERVICE, "for candidate in chosen:", "for candidate in []:"),
    Mutant(
        "M4 run complete even when nothing verified",
        SERVICE,
        'if verified_any:\n            _finish(session, run, "complete")',
        'if True:\n            _finish(session, run, "complete")',
    ),
    Mutant("M5 status decided as if all quotes verified", SERVICE, "guidance_text is not None, all_verified)", "guidance_text is not None, True)"),
    Mutant("M6 span offset drifts by one character", SERVICE, "start=located.start if located else -1,", "start=located.start + 1 if located else -1,"),
    Mutant("M7 digits ignored by the letters-and-digits tier", SPANS, "if ch.isalnum():", "if ch.isalpha():"),
    Mutant("M8 label-strip tier loses its name", SPANS, 'f"unprefixed:{found.method}"', 'f"{found.method}"'),
    Mutant("M9 immutability trigger never fires", DB, "WHEN {stage_of} IN {finished} ", "WHEN 0 "),
)


@dataclass(frozen=True)
class Outcome:
    mutant: Mutant
    verdict: str  # killed | SURVIVED | skipped
    detail: str


def run_suite() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=SUITE_TIMEOUT_S,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def first_failure(output: str) -> str:
    match = re.search(r"^(?:FAILED|ERROR) (\S+)", output, re.MULTILINE)
    return match.group(1) if match else "(no FAILED line in the output)"


def apply(mutant: Mutant, original: bytes) -> Outcome:
    text = original.decode("utf-8")
    if text.count(mutant.old) != 1:
        return Outcome(mutant, "skipped", f"anchor occurs {text.count(mutant.old)} times; the code moved")
    mutant.path.write_bytes(text.replace(mutant.old, mutant.new).encode("utf-8"))
    try:
        code, output = run_suite()
    finally:
        mutant.path.write_bytes(original)
    if code != 0:
        return Outcome(mutant, "killed", first_failure(output))
    return Outcome(mutant, "SURVIVED", "every test passed with the boundary broken")


def main(argv: list[str]) -> int:
    wanted = [m for m in MUTANTS if not argv or any(m.name.startswith(prefix) for prefix in argv)]
    originals = {path: path.read_bytes() for path in {m.path for m in wanted}}
    digests = {path: hashlib.sha256(data).hexdigest() for path, data in originals.items()}
    outcomes: list[Outcome] = []
    try:
        for mutant in wanted:
            outcomes.append(apply(mutant, originals[mutant.path]))
    finally:
        for path, data in originals.items():
            path.write_bytes(data)
    restored = all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in digests.items())

    width = max(len(o.mutant.name) for o in outcomes) if outcomes else 10
    for outcome in outcomes:
        print(f"{outcome.mutant.name:{width}}  {outcome.verdict:9} {outcome.detail}")
    killed = sum(o.verdict == "killed" for o in outcomes)
    survived = sum(o.verdict == "SURVIVED" for o in outcomes)
    print(f"\nkilled {killed}, survived {survived}, skipped {len(outcomes) - killed - survived}, of {len(outcomes)}")
    print(f"files restored byte for byte: {restored}")
    if not restored:
        print("STOP: a mutated file was not restored; check git or the backups before doing anything else")
        return 2
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
