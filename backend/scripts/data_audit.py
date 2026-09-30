"""The data audit behind docs/DATA-EVIDENCE.md: every agreement this repository has touched, by SHA-256.

For each distinct document it answers where the bytes came from, under which licence, what role they played
(runtime: uploaded through the API by a person; evaluation: a corpus, a label set or the golden document;
fixture: a test or browser-flow input), which measurements touched them, and where the same bytes appear more
than once. It then states the denominator of every measured set separately, and the strongest claim those
denominators allow. It never adds sets together: the sample is CP01, the CUAD sets are text files, and
"tested on N contracts" is not a sentence this repository makes.

Deterministic: it reads the manifests in the tree, the store when there is one, and the gitignored measurement
records when they exist; it prints Markdown; it writes nothing but, with --write, the block between the markers
in docs/DATA-EVIDENCE.md.

    cd backend && .venv/Scripts/python scripts/data_audit.py            # print the audit
    cd backend && .venv/Scripts/python scripts/data_audit.py --write    # refresh the block in docs/DATA-EVIDENCE.md
"""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.hashing import sha256_bytes, sha256_text  # noqa: E402

START = "<!-- data-audit:start -->"
END = "<!-- data-audit:end -->"

ROLE_ORDER = ("evaluation", "fixture", "runtime")


@dataclass
class Agreement:
    sha256: str
    names: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    licences: set[str] = field(default_factory=set)
    roles: set[str] = field(default_factory=set)
    measurements: set[str] = field(default_factory=set)
    readings: list[str] = field(default_factory=list)  # parser versions of the store's rows for these bytes
    runs: int = 0

    @property
    def licence(self) -> str:
        return ", ".join(sorted(self.licences)) if self.licences else "not recorded"


@dataclass
class Audit:
    agreements: dict[str, Agreement]
    denominators: list[tuple[str, str, str]]  # (what, number, where it is counted from)
    notes: list[str]
    store: str | None  # where the store was read from, or None when there is none
    prefixes: dict[str, str]  # sha256 prefix → full sha256, for manifests that identify by prefix

    def by_role(self, role: str) -> list[Agreement]:
        return sorted((a for a in self.agreements.values() if role in a.roles), key=lambda a: (min(a.names) if a.names else "", a.sha256))


def _agreement(audit: dict[str, Agreement], sha256: str) -> Agreement:
    return audit.setdefault(sha256, Agreement(sha256=sha256))


def _resolve(audit: dict[str, Agreement], prefix: str) -> str:
    """A manifest that names bytes by a sha256 prefix is resolved against everything already known; an unknown
    prefix stays a prefix, so the report shows it was never seen in full."""
    for sha in audit:
        if sha.startswith(prefix):
            return sha
    return prefix


def provenance_rows() -> tuple[list[dict[str, str]], str | None]:
    """The public corpus's provenance file (ivo-experiments), by env or by the sibling checkout; absent on a bare clone."""
    candidate = os.environ.get("WORKBENCH_CORPUS_SOURCES") or str(ROOT.parent / "ivo-experiments" / "experiments" / "b1-word-structure" / "corpus_sources.csv")
    path = Path(candidate)
    if not path.exists():
        return [], None
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    shown = str(path.relative_to(ROOT.parent)) if path.is_relative_to(ROOT.parent) else "corpus_sources.csv (WORKBENCH_CORPUS_SOURCES)"
    return rows, shown


def audit(store_path: Path | None = None) -> Audit:
    agreements: dict[str, Agreement] = {}
    notes: list[str] = []
    denominators: list[tuple[str, str, str]] = []

    # --- the sample and the golden document
    sample = ROOT / "public" / "samples" / "cloud-service-agreement.docx"
    sample_sha = sha256_bytes(sample.read_bytes())
    a = _agreement(agreements, sample_sha)
    a.names.add(sample.name)
    a.sources.add("bundled sample (Common Paper Cloud Service Agreement v2.1)")
    a.licences.add("CC BY 4.0")
    a.roles.update({"evaluation", "fixture"})
    a.measurements.update({"golden set", "browser flows (replayed answers)", "load envelope", "interface performance"})

    goldens = json.loads((BACKEND / "app" / "goldens" / "set.json").read_text(encoding="utf-8"))
    golden_prefix = goldens["document"]["sha256"]
    if not sample_sha.startswith(golden_prefix):
        notes.append(f"the golden set names document {golden_prefix}… and the bundled sample hashes to {sample_sha[:16]}…: they differ")
    denominators.append(("golden questions", str(len(goldens["goldens"])), "app/goldens/set.json, on one document (the sample)"))

    # --- the public corpus (provenance in ivo-experiments)
    rows, provenance_path = provenance_rows()
    if provenance_path:
        for row in rows:
            a = _agreement(agreements, row["sha256"])
            a.names.add(f"{row['id']}.docx")
            a.sources.add(f"{row['publisher']} ({row['id']})")
            a.licences.add(row["licence"])
            a.roles.add("evaluation")
            a.measurements.add("public corpus (batch, families, parser tournament)")
        denominators.append(("public corpus agreements with provenance", str(len(rows)), provenance_path))
    else:
        notes.append("the public corpus's provenance file (ivo-experiments corpus_sources.csv) was not found; its licences are not checked here")

    # --- CUAD sets (text files; the archive's licence is in data/cuad/SOURCE.txt)
    cuad_licence = "CC BY 4.0 (CUAD v1, The Atticus Project)"
    for manifest, measurement in (("cuad-30.json", "CUAD-30 clause measurement"), ("cuad-skillopt.json", "SkillOpt (disjoint CUAD contracts)")):
        data = json.loads((BACKEND / "app" / "batch" / "corpora" / manifest).read_text(encoding="utf-8"))
        for contract in data["contracts"]:
            a = _agreement(agreements, contract["sha256"])
            a.names.add(contract["file"])
            a.sources.add("CUAD v1 (SEC exhibit)")
            a.licences.add(cuad_licence)
            a.roles.add("evaluation")
            a.measurements.add(measurement)
        denominators.append((f"{manifest} contracts", str(len(data["contracts"])), f"app/batch/corpora/{manifest}"))
    task = json.loads((BACKEND / "app" / "batch" / "tasks" / "cuad-clauses.json").read_text(encoding="utf-8"))
    denominators.append(("CUAD-30 questions (one per category)", str(len(task["fields"])), "app/batch/tasks/cuad-clauses.json"))
    core = json.loads((BACKEND / "app" / "batch" / "tasks" / "core-fields.json").read_text(encoding="utf-8"))
    denominators.append(("batch fields over the public corpus", str(len(core["fields"])), "app/batch/tasks/core-fields.json"))

    # --- family labels (by sha256 prefix)
    labels = json.loads((BACKEND / "app" / "families" / "labels.json").read_text(encoding="utf-8"))
    for name, prefix in labels["documents"].items():  # name → the first sixteen hex digits of the sha256
        sha = _resolve(agreements, prefix)
        a = _agreement(agreements, sha)
        a.names.add(name)
        a.roles.add("evaluation")
        a.measurements.add("document families (hand labels)")
    denominators.append(("hand-labelled documents for families", str(len(labels["documents"])), "app/families/labels.json"))

    # --- fixtures
    pdf = BACKEND / "tests" / "fixtures" / "services-agreement.pdf"
    a = _agreement(agreements, sha256_bytes(pdf.read_bytes()))
    a.names.add(pdf.name)
    a.sources.add("test fixture (printed from Chrome)")
    a.licences.add("the repository's own")
    a.roles.add("fixture")
    a.measurements.add("backend tests")
    support = (BACKEND / "tests" / "support.py").read_text(encoding="utf-8")
    contract_match = re.search(r'^CONTRACT = """(.*?)"""', support, re.S | re.M)
    if contract_match:
        a = _agreement(agreements, sha256_text(contract_match.group(1)))
        a.names.add("agreement.txt (tests.support.CONTRACT)")
        a.sources.add("synthetic test contract")
        a.licences.add("the repository's own")
        a.roles.add("fixture")
        a.measurements.add("backend tests")
    demo = BACKEND / "experiments" / "demo_proof" / "make_fixture.py"
    if demo.exists():
        notes.append(
            "the Phase 1 fixture (docs/DEMO-PROOF.md) is a CUAD contract rendered as a DOCX by experiments/demo_proof/make_fixture.py; "
            "its bytes are in the store only where the proof was run"
        )

    replay = ROOT / "e2e" / "replay.json"
    if replay.exists():
        recorded = json.loads(replay.read_text(encoding="utf-8"))
        denominators.append(("recorded model answers replayed by the browser flows", str(len(recorded)), "e2e/replay.json, all on the sample"))
    flows = sum(len(re.findall(r"^\s*test\(", p.read_text(encoding="utf-8"), re.M)) for p in sorted((ROOT / "e2e").glob("*.spec.ts")))
    denominators.append(("browser flows", str(flows), "e2e/*.spec.ts"))
    mutants = (BACKEND / "scripts" / "mutate_by_hand.py").read_text(encoding="utf-8")
    denominators.append(("hand mutants", str(len(set(re.findall(r'"(M\d+) ', mutants)))), "scripts/mutate_by_hand.py"))

    # --- the store: what was uploaded, read and run
    path = store_path or settings.data_dir / "workbench.db"
    store = None
    if path.exists():
        store = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            for sha, name, parser in db.execute("SELECT sha256, name, parser_version FROM documents ORDER BY created_at, id"):
                a = _agreement(agreements, sha)
                a.names.add(name)
                a.readings.append(parser or "unversioned")
            for sha, count in db.execute("SELECT d.sha256, COUNT(*) FROM runs r JOIN documents d ON d.id = r.document_id GROUP BY d.sha256"):
                agreements[sha].runs += count
            batch_sets = defaultdict(set)
            for corpus, sha in db.execute(
                "SELECT b.corpus, d.sha256 FROM batch_items i JOIN batches b ON b.id = i.batch_id "
                "JOIN runs r ON r.id = i.run_id JOIN documents d ON d.id = r.document_id"
            ):
                batch_sets[corpus].add(sha)
                agreements[sha].measurements.add(f"batch '{corpus}'")
                agreements[sha].roles.add("evaluation")
            for corpus, shas in sorted(batch_sets.items()):
                denominators.append((f"distinct agreements in batch '{corpus}'", str(len(shas)), "the store's batch_items"))
            spans, verified = db.execute("SELECT COUNT(*), COALESCE(SUM(verified), 0) FROM evidence_spans").fetchone()
            denominators.append(
                (
                    "evidence spans in the store (a verifier replay's population)",
                    f"{spans} ({verified} verified)",
                    "the store's evidence_spans, at the time of the audit",
                )
            )
            runs = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            denominators.append(("runs in the store", str(runs), "the store's runs, at the time of the audit"))
        finally:
            db.close()
        for a in agreements.values():
            if a.readings and not a.roles:
                a.roles.add("runtime")  # in the store and in no manifest: a person put it there through the API
                a.sources.add("uploaded through the API")
    else:
        notes.append(f"no store at {path}: only the manifests in the tree are audited (a fresh clone has no uploads, runs or batches)")

    # --- measurement records outside git
    tournament = settings.data_dir / "tournament" / "current.json"
    if tournament.exists():
        records = json.loads(tournament.read_text(encoding="utf-8"))
        names = sorted({r["document"] for r in records})
        for a in agreements.values():
            if a.names & set(names):
                a.measurements.add("parser tournament")
        denominators.append(("documents in the parser tournament's baseline record", str(len(names)), "data/tournament/current.json (not in git)"))
    else:
        notes.append("the parser tournament's record (data/tournament/current.json) is not present; its documents are not counted")
    logs = settings.data_dir / "logs"
    for pattern, what in (("admission-*.json", "admission measurement"), ("load-envelope-*.json", "load envelope")):
        found = sorted(logs.glob(pattern)) if logs.exists() else []
        if found:
            denominators.append((f"{what} records", str(len(found)), f"data/logs/{pattern} (not in git)"))
        else:
            notes.append(f"no {what} record under data/logs; that measurement is documented in prose only on this machine")

    prefixes = {p: _resolve(agreements, p) for p in labels["documents"].values()}
    prefixes[golden_prefix] = _resolve(agreements, golden_prefix)
    return Audit(agreements=agreements, denominators=denominators, notes=notes, store=store, prefixes=prefixes)


def duplicates(a: Audit) -> list[str]:
    lines: list[str] = []
    reread = [ag for ag in a.agreements.values() if len(ag.readings) > 1]
    if reread:
        versions = sorted({r for ag in reread for r in ag.readings})
        lines.append(
            f"{len(reread)} agreements are stored as more than one reading ({', '.join(versions)}): one set of bytes, one row per reader version, "
            "kept because finished runs read each of them"
        )
    for agreement in sorted(a.agreements.values(), key=lambda x: x.sha256):
        if len(agreement.names) > 1:
            lines.append(f"`{agreement.sha256[:16]}…` is known under {len(agreement.names)} names: {', '.join(sorted(agreement.names))}")
    by_name: dict[str, set[str]] = defaultdict(set)
    for agreement in a.agreements.values():
        for name in agreement.names:
            by_name[name].add(agreement.sha256)
    for name, shas in sorted(by_name.items()):
        if len(shas) > 1:
            lines.append(f"the name {name} covers {len(shas)} different sets of bytes ({', '.join(s[:12] + '…' for s in sorted(shas))})")
    return lines


def render(a: Audit) -> str:
    out: list[str] = [START, "", f"Store audited: `{a.store}`" if a.store else "Store audited: none (manifests only)", ""]
    total = len(a.agreements)
    partial = sum(1 for sha in a.agreements if len(sha) < 64)
    out.append(
        f"Distinct agreements known to this repository, by SHA-256: **{total}**"
        + (f" ({partial} known only by a prefix from a label file)" if partial else "")
        + "."
    )
    out.append("")
    for role in ROLE_ORDER:
        items = a.by_role(role)
        out.append(f"### {role} ({len(items)})")
        out.append("")
        out.append("| sha256 | names | source | licence | readings | runs | measurements |")
        out.append("|---|---|---|---|---|---|---|")
        for ag in items:
            names = ", ".join(sorted(ag.names)) or "—"
            sources = "; ".join(sorted(ag.sources)) or "not recorded"
            readings = ", ".join(ag.readings) if ag.readings else "not in the store"
            measurements = "; ".join(sorted(ag.measurements)) or "none"
            out.append(f"| `{ag.sha256[:16]}…` | {names} | {sources} | {ag.licence} | {readings} | {ag.runs} | {measurements} |")
        out.append("")
    out.append("### Denominators, each its own")
    out.append("")
    out.append("| What | Number | Counted from |")
    out.append("|---|---|---|")
    for what, number, where in a.denominators:
        out.append(f"| {what} | {number} | {where} |")
    out.append("")
    dupes = duplicates(a)
    out.append("### The same bytes, more than once")
    out.append("")
    out.extend(f"- {line}" for line in dupes) if dupes else out.append("- none")
    out.append("")
    if a.notes:
        out.append("### Not audited here")
        out.append("")
        out.extend(f"- {note}" for note in a.notes)
        out.append("")
    out.append("### The strongest claim these records allow")
    out.append("")
    evaluation = a.by_role("evaluation")
    runtime = [ag for ag in a.by_role("runtime") if "evaluation" not in ag.roles]
    licensed = [ag for ag in evaluation if ag.licences]
    out.append(
        f"Every measurement in this repository was made on one of {len(evaluation)} evaluation agreements, {len(licensed)} of them under a recorded "
        "licence (CC BY 4.0 or OGL v3.0), and each measurement has its own denominator in the table above: the golden set is questions about one "
        "contract, CUAD-30 is thirty text files against experts' spans, the batch and the families are the twenty-document public corpus, and the "
        "verifier replay is a count of spans, not of contracts. These numbers are not added together, because the sets overlap (the bundled sample "
        "is CP01 of the corpus) and because a span, a question and a contract are not the same unit. "
        f"{len(runtime)} further agreement{'s' if len(runtime) != 1 else ''} in the store {'were' if len(runtime) != 1 else 'was'} uploaded through "
        "the API by a person and measured nothing; they are listed so that no count above quietly includes them."
    )
    out.append("")
    out.append(END)
    return "\n".join(out)


def main() -> None:
    text = render(audit())
    if "--write" in sys.argv:
        target = ROOT / "docs" / "DATA-EVIDENCE.md"
        current = target.read_text(encoding="utf-8")
        start, end = current.index(START), current.index(END) + len(END)
        target.write_text(current[:start] + text + current[end:], encoding="utf-8", newline="\n")
        print(f"wrote the audit block into {target}")
    else:
        print(text)


if __name__ == "__main__":
    main()
