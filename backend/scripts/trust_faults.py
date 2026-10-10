"""Fault matrix over the version-aware trust layer: put one fault at a time into `app/trust` (and the two application
modules it leans on), run `tests/test_trust.py`, restore the file, report whether the tests noticed.

Kept beside `mutate_by_hand.py` and run by the release gate (`scripts/release-gate.sh`). It exits non-zero when any
fault goes unnoticed or any file is not restored byte for byte, so a gate reads its status, not its output.

    .venv/Scripts/python scripts/trust_faults.py
"""

# ruff: noqa: E501  (each fault is one line as written in the source, so it can be found and put back exactly)
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TRUST = BACKEND / "app" / "trust"

# (what the fault breaks, file under app/trust, the line as written, the line with the fault)
FAULTS: tuple[tuple[str, str, str, str], ...] = (
    ("the recount ignores sections whose content is new", "diff.py", "        for section in fresh:\n            located = locate(evidence.quote", "        for section in []:\n            located = locate(evidence.quote"),
    ("a duplicated identical section counts once", "diff.py", "o.count * new_keys[o.section_key]", "o.count"),
    ("a quote that stands twice is unique", "compile.py", "    if places == 1:", "    if places >= 1:"),
    ("the place is read from the first of several matches", "diff.py", "text.count(evidence.before) == 1", "text.count(evidence.before) >= 1"),
    ("a different value is not a contradiction", "diff.py", "    if len(values) == 1:\n        return Standing.CONTRADICTED", "    if len(values) == 99:\n        return Standing.CONTRADICTED"),
    ("a finding with no quote is supported", "model.py", "    if not quotes or any(", "    if any("),
    ("any document may be diffed without a recorded version", "../application/trust_run.py", "if later.id != run.document_id and not is_later_version(", "if False and not is_later_version("),
    ("lineage is read without the workspace", "../application/versions.py", "filter_by(workspace_id=workspace, document_id=document_id).one_or_none()", "filter_by(document_id=document_id).first()"),
    ("sections align on wording at any overlap", "diff.py", "        if score < SAME_SECTION:", "        if score < 0.0:"),
    ("an old reader is always compatible", "compile.py", "    if reader_version == current_reader:", "    if True:"),
    ("an old reader is compatible though a quote is lost", "compile.py", "    lost = [item for item in located if not any(locate(item.quote, section.text, section.label) for section in current_reading)]", "    lost = []"),
    ("an unreadable document counts as compatible", "compile.py", "    if current_reading is None:", "    if False:"),
    ("carried-over sections contribute nothing", "diff.py", "for o in evidence.occurrences if new_keys[o.section_key]}", "for o in evidence.occurrences if False}"),
    ("a removed section keeps its occurrences", "diff.py", "carried = {o.section_key: o.count * new_keys[o.section_key] for o in evidence.occurrences if new_keys[o.section_key]}", "carried = {o.section_key: o.count * max(1, new_keys[o.section_key]) for o in evidence.occurrences}"),
    ("a section with new content is treated as carried over", "diff.py", "    fresh = [section for section in new if section.key not in old_keys]", "    fresh = [section for section in new if section.content_hash not in {o.content_hash for o in old}]"),
    ("earlier rules always lower trust", "compile.py", "    if not stale_rules:\n        return Obligation(obligation_id, Need.RULES_COMPATIBLE", "    if False:\n        return Obligation(obligation_id, Need.RULES_COMPATIBLE"),
    ("earlier rules are compatible though today's verifier finds nothing", "compile.py", "    lost = [item for item in located if not any(o.section_key == item.section_key for o in item.occurrences)]", "    lost = []"),
)  # fmt: skip


def main() -> int:
    caught = 0
    unrestored: list[str] = []
    for name, file, old, new in FAULTS:
        path = (TRUST / file).resolve()
        original = path.read_bytes()
        text = original.decode("utf-8")
        if text.count(old) != 1:
            print(f"STALE   {name} | the line is not in {file} exactly once: the fault no longer applies")
            return 2
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        try:
            run = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_trust.py", "-q", "-x", "-p", "no:cacheprovider"], cwd=BACKEND, capture_output=True, text=True
            )
        finally:
            path.write_bytes(original)
        if path.read_bytes() != original:
            unrestored.append(file)
        failed = [line for line in run.stdout.splitlines() if line.startswith("FAILED")]
        caught += run.returncode != 0
        print(("CAUGHT  " if run.returncode else "MISSED  ") + name + " | " + (failed[0][:100] if failed else ""))
    print(f"{caught} of {len(FAULTS)} faults caught")
    if unrestored:
        print(f"NOT RESTORED: {', '.join(unrestored)}")
    return 0 if caught == len(FAULTS) and not unrestored else 1


if __name__ == "__main__":
    sys.exit(main())
