"""Hand mutation run over the evidence boundary: change one decision line at a time, run the
suite, restore the file, report which test noticed.

This is the measurement that would earn a mutation-testing dependency, kept as a script until it
does (DECISIONS.md, 2026-09-28: nine mutants, one survivor, one test added; sixteen since 2026-09-29, twenty-four since its evening). Every file is restored
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
TOKENS = BACKEND / "app" / "verify" / "tokens.py"
STATUS = BACKEND / "app" / "runs" / "status.py"
DB = BACKEND / "app" / "db.py"
MODELS = BACKEND / "app" / "models.py"
START_RUN = BACKEND / "app" / "application" / "start_run.py"
RECOVER = BACKEND / "app" / "application" / "recover_runs.py"
RUNS_API = BACKEND / "app" / "api" / "runs.py"
VERIFY_TEMPLATE = BACKEND / "app" / "application" / "verify_template.txt"
SUITE_TIMEOUT_S = 300


@dataclass(frozen=True)
class Mutant:
    name: str
    path: Path
    old: str
    new: str
    also: tuple[Path, str, str] | None = None  # a second edit, when two layers enforce the same invariant


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
    Mutant(
        "M5 status decided as if all quotes verified",
        SERVICE,
        "                all_verified,\n                quotes=[span.quote for span in spans if span.verified],\n",
        "                True,\n                quotes=[span.quote for span in spans if span.verified],\n",
    ),
    Mutant("M6 span offset drifts by one character", SERVICE, "start=located.start if located else -1,", "start=located.start + 1 if located else -1,"),
    Mutant(
        "M7 numbers lose their value in the typed tier",
        TOKENS,
        "            canonical = canonical_number(surface)\n        elif kind is Kind.CURRENCY:",
        '            canonical = "0"\n        elif kind is Kind.CURRENCY:',
    ),
    Mutant("M8 label-strip tier loses its name", SPANS, 'f"unprefixed:{found.method}"', 'f"{found.method}"'),
    Mutant("M9 immutability trigger never fires", DB, "WHEN {condition} ", "WHEN 0 "),
    Mutant(
        "M10 duplicate request creates a second run (lookup and unique index both off)",
        START_RUN,
        "    existing = active_run(session, key)\n    if existing is not None:\n        return StartedRun(existing, created=False)",
        "    existing = None\n    if existing is not None:\n        return StartedRun(existing, created=False)",
        also=(MODELS, 'Index("ux_runs_fingerprint_active", "fingerprint", unique=True,', 'Index("ux_runs_fingerprint_active", "fingerprint", unique=False,'),
    ),
    Mutant(
        "M11 provider failure leaves the run complete",
        SERVICE,
        '        _fail(session, run, str(error), "provider_error")\n',
        '        _finish(session, run, "complete", error=str(error), reason="provider_error")\n',
    ),
    Mutant("M12 evidence pack skips the document hash", VERIFY_TEMPLATE, 'report(sha256(HERE / document["file"]) == document["sha256"],', "report(True,"),
    Mutant(
        "M13 a match may start inside a word or a number",
        SPANS,
        "    if start > 0 and text[start - 1].isalnum() and text[start].isalnum():\n        return False\n",
        "    if False:\n        return False\n",
    ),
    Mutant(
        "M14 a match may end inside a word or a number",
        SPANS,
        "    return not (end < len(text) and text[end - 1].isalnum() and text[end].isalnum())\n",
        "    return True\n",
    ),
    Mutant(
        "M15 evidence pack skips the hash the run recorded",
        VERIFY_TEMPLATE,
        'report(hashlib.sha256(joined.encode("utf-8")).hexdigest() == recorded,',
        "report(True,",
    ),
    Mutant(
        "M16 section text of a finished run may change",
        DB,
        '"sections": f"EXISTS (SELECT 1 FROM runs WHERE runs.document_id = OLD.document_id AND runs.stage IN {finished})",',
        '"sections": "0",',
    ),
    Mutant(
        "M17 the event stream never re-reads the record",
        RUNS_API,
        "                    ended = _ended_in_the_record(run_id)\n",
        "                    ended = None\n",
    ),
    Mutant(
        "M18 staleness recovery tells no open stream",
        RECOVER,
        'bus.publish(StageEvent(run.id, "failed", message))',
        'bus.publish(StageEvent("nobody", "failed", message))',
    ),
    Mutant("M19 a failed worker writes into its broken session", SERVICE, "    session.rollback()\n    session.refresh(run)\n", ""),
    Mutant(
        "M20 two documents may share bytes and reader",
        MODELS,
        'Index("ux_documents_sha256_parser", "sha256", "parser_version", unique=True)',
        'Index("ux_documents_sha256_parser", "sha256", "parser_version", unique=False)',
    ),
    Mutant(
        "M21 a run may have two memos",
        MODELS,
        'Index("ux_memos_run_review", "run_id", "review_head", unique=True)',
        'Index("ux_memos_run_review", "run_id", "review_head", unique=False)',
    ),
    Mutant(
        "M22 the verifier searches beyond the slice the model saw",
        SERVICE,
        "    located = locate(quote, section.text[:window], _label(section)) if section is not None else None\n",
        "    located = locate(quote, section.text, _label(section)) if section is not None else None\n",
    ),
    Mutant(
        "M23 the status is computed from the model's numbers, not the quote's",
        STATUS,
        "    fact = next((f for f in (observed_fact(q, stated=observed) for q in quotes) if f is not None), None)\n",
        '    fact = observed_fact(observed or "") if observed else None\n',
    ),
    Mutant(
        "M24 a finished run may enter another stage", SERVICE, "    assert_transition(previous.stage if previous is not None else None, stage)\n", "    pass\n"
    ),
)


@dataclass(frozen=True)
class Outcome:
    mutant: Mutant
    verdict: str  # killed | SURVIVED | skipped
    detail: str


def run_suite() -> tuple[int, str]:
    proc = subprocess.run(
        # The fingerprint test fails on any edit to the files it names, so it would "kill" every mutant of them without
        # a single behaviour being tested. A mutant has to be killed by a test of what the code does.
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "--deselect", "tests/test_semantic_versions.py"],
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


def _edit(path: Path, original: bytes, old: str, new: str) -> str | None:
    """Write the mutated file; return a reason when the anchor is not exactly once in it."""
    text = original.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    old, new = old.replace("\n", newline), new.replace("\n", newline)
    if text.count(old) != 1:
        return f"anchor occurs {text.count(old)} times in {path.name}; the code moved"
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    return None


def apply(mutant: Mutant, originals: dict[Path, bytes]) -> Outcome:
    touched = [mutant.path] + ([mutant.also[0]] if mutant.also else [])
    try:
        problem = _edit(mutant.path, originals[mutant.path], mutant.old, mutant.new)
        if problem is None and mutant.also is not None:
            problem = _edit(mutant.also[0], originals[mutant.also[0]], mutant.also[1], mutant.also[2])
        if problem is not None:
            return Outcome(mutant, "skipped", problem)
        code, output = run_suite()
    finally:
        for path in touched:
            path.write_bytes(originals[path])
    if code != 0:
        return Outcome(mutant, "killed", first_failure(output))
    return Outcome(mutant, "SURVIVED", "every test passed with the boundary broken")


def main(argv: list[str]) -> int:
    wanted = [m for m in MUTANTS if not argv or any(m.name.startswith(prefix) for prefix in argv)]
    paths = {m.path for m in wanted} | {m.also[0] for m in wanted if m.also}
    originals = {path: path.read_bytes() for path in paths}
    digests = {path: hashlib.sha256(data).hexdigest() for path, data in originals.items()}
    outcomes: list[Outcome] = []
    try:
        for mutant in wanted:
            outcomes.append(apply(mutant, originals))
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
