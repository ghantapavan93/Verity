"""Build the record /break tells: one recorded failure, the fix that did not hold, and a rule's catch and false alarm.

Nothing on the page is typed by hand. Each run comes from a recorded store through the API's own projections (the run
detail and its explanation) and `reconstruct_input`, which rebuilds the exact model input from the record and checks it
against the hash the run recorded. The store is copied first, so the recording is never opened for writing. The cases,
their expected answers and the AI-assisted labels come from the evaluation files named on the command line (their
sha256 goes into the record); each contract's source (SEC EDGAR URL, hashes, conversion notes) from the corpus
manifest; the rejected party check's verdicts from a file its own code wrote at its own commit.

    python scripts/export_break_record.py --store v1=<store dir> --store v2=<store dir> --cases <party-cases-2.json>
        --labels <party2-labels.jsonl> --manifest <corpus manifest.json> --verdicts <party-verdicts.json>
        --diagnostic-cases <party-cases.json> --diagnostic-labels <party-labels.jsonl> --raw <corpus raw dir>
        [--mask-name "<a person the story does not need>" ...] [--out ../src/components/break/break-record.json]

The output is deterministic for the same inputs: no clock, no machine path. tests/test_break_record.py re-checks it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
DEFAULT_OUT = ROOT / "src" / "components" / "break" / "break-record.json"
SCHEMA = "break-record/1"
# The headline failure, then the policy rule's catch and its false alarm, all from the same unseen, pre-registered set.
HEADLINE = "Q-1"
CAUGHT = "Q-3"
FALSE_ALARM = "Q-2"
# The notice clause of a filed agreement lists people's email addresses. They are public in the filing and nothing on
# the page needs them, so they are masked wherever the record carries contract text. The input hash was checked against
# the unmasked record before masking (dump_store refuses a mismatch); the page says the addresses are masked.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_MASK = "[email address masked]"
# People the story does not need are masked the same way (release hygiene, 2026-10-11): the contacts a notice clause
# addresses ("Attention: …") and the people who signed ("/s/ …", "Name: …"), found by where a filing puts them, and
# anyone named with --mask-name (a person a case's question or label named). The headline keeps the stockholders'
# representative: its recorded question is about her role.
# A name is words on one line: a signature line followed by a "Name:" line must not read as one name that swallows "Name".
PERSON = r"[A-Z][a-z]+(?: [A-Z]\.)?(?: [A-Z][a-z'-]+){1,2}"
NAME_PLACES = [re.compile(rf"((?:Attention|Attn)[ ]*:?[ ]*\|?[ ]*){PERSON}"), re.compile(rf"(/s/[ ]*){PERSON}"), re.compile(rf"(Name:[ ]*\|?[ ]*){PERSON}")]
NAME_MASK = "[name masked]"


def masked(value: object, count: dict[str, int], names: list[str]) -> object:
    """``value`` with email addresses and people the story does not need replaced by their masks; ``count`` collects
    how many of each."""
    if isinstance(value, str):
        found = EMAIL.findall(value)
        count["emails"] += len(found)
        value = EMAIL.sub(EMAIL_MASK, value) if found else value
        for place in NAME_PLACES:
            value, n = place.subn(lambda m: m.group(1) + NAME_MASK, value)
            count["names"] += n
        for name in names:
            count["names"] += value.count(name)
            value = value.replace(name, NAME_MASK)
        return value
    if isinstance(value, list):
        return [masked(v, count, names) for v in value]
    if isinstance(value, dict):
        return {k: masked(v, count, names) for k, v in value.items()}
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finding_runs(store: Path, finding_ids: list[str]) -> dict[str, str]:
    db = sqlite3.connect(f"file:{(store / 'workbench.db').as_posix()}?mode=ro", uri=True)
    try:
        return dict(db.execute(f"SELECT id, run_id FROM findings WHERE id IN ({','.join('?' * len(finding_ids))})", finding_ids))
    finally:
        db.close()


def dump_store(run_ids: list[str]) -> dict[str, Any]:
    """In a child process whose WORKBENCH_DATA_DIR is a copy of one store: each run as the API projects it."""
    sys.path.insert(0, str(BACKEND))
    from fastapi.testclient import TestClient

    from app.application.reconstruct_input import reconstruct_input
    from app.db import SessionLocal
    from app.main import app
    from app.models import Section

    client = TestClient(app)
    runs = {}
    with SessionLocal() as session:
        for run_id in run_ids:
            detail = client.get(f"/api/runs/{run_id}/detail")
            explanation = client.get(f"/api/runs/{run_id}/explanation")
            if detail.status_code != 200 or explanation.status_code != 200:
                raise SystemExit(f"run {run_id}: detail {detail.status_code}, explanation {explanation.status_code}")
            rebuilt = reconstruct_input(session, run_id)
            if not rebuilt.matches:
                raise SystemExit(f"run {run_id}: the rebuilt input does not match the record ({rebuilt.problem})")
            body = detail.json()
            wanted = {c["sectionId"] for c in body["candidates"]} | {s["sectionId"] for f in body["findings"] for s in f["spans"] if s["sectionId"]}
            sections = {
                s.id: {"ordinal": s.ordinal, "number": s.number, "heading": s.heading, "text": s.text}
                for s in session.query(Section).filter(Section.id.in_(wanted))
            }
            runs[run_id] = {
                "detail": body,
                "explanation": explanation.json(),
                "input": {"system": rebuilt.system, "user": rebuilt.user, "sha256": rebuilt.input_sha256},
                "sections": sections,
            }
    return runs


def read_store(store: Path, run_ids: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "store"
        shutil.copytree(store, copy)
        env = {**os.environ, "WORKBENCH_DATA_DIR": str(copy), "WORKBENCH_PROVIDER": "replay", "WORKBENCH_LOG_LEVEL": "WARNING"}
        child = subprocess.run(
            [sys.executable, __file__, "--dump", ",".join(run_ids)], cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8", check=False
        )
        if child.returncode != 0:
            raise SystemExit(f"reading {store.name}: {child.stderr.strip()[-600:]}")
        runs: dict[str, Any] = json.loads(child.stdout)
        return runs


def filing_sha256(raw: Path) -> str:
    """The downloaded filing's bytes before the script tag SEC appends to every response. The tag carries a per-response
    token, so the whole download never hashes the same twice; the filing before it does, and anyone can check it."""
    text = raw.read_bytes().decode("utf-8")
    cut = text.rfind("<script")
    return hashlib.sha256((text[:cut] if cut >= 0 else text).encode("utf-8")).hexdigest()


def source_of(entry: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    return {
        "title": entry["title"],
        "company": entry["company_name"],
        "form": entry["filing_form"],
        "filingDate": entry["filing_date"],
        "accession": entry["filing_accession"],
        "exhibit": entry["exhibit_name"],
        "url": entry["source_url"],
        "sha256Original": entry["sha256_original"],
        "sha256Filing": filing_sha256(raw_dir / f"{entry['id']}.{entry['original_format']}"),
        "sha256Tested": entry["sha256_tested"],
        "conversion": {"tool": entry["conversion"]["tool"], "lost": entry["conversion"]["lost"]},
        "reuseNote": entry["reuse_note"],
    }


def session_view(session: str, run: dict[str, Any], finding_id: str, label: dict[str, Any]) -> dict[str, Any]:
    detail = run["detail"]
    finding = next(f for f in detail["findings"] if f["id"] == finding_id)
    explained = next(f for f in run["explanation"]["findings"] if f["id"] == finding_id)
    proposal = run["explanation"]["proposals"][explained["ordinal"]]
    return {
        "session": session,
        "runId": detail["id"],
        "createdAt": detail["createdAt"],
        "model": detail["model"],
        "provider": detail["provider"],
        "promptVersion": detail["promptVersion"],
        "promptHash": detail["promptHash"],
        "options": detail["options"],
        "latencyMs": round(detail["latencyMs"]),
        "inputTokens": detail["inputTokens"],
        "outputTokens": detail["outputTokens"],
        "documentSha256": detail["documentSha256"],
        "recordedInputSha256": run["explanation"]["reconstruction"]["recordedInputSha256"],
        "retrieval": run["explanation"]["retrieval"],
        "rawOutput": detail["rawOutput"],
        "proposal": proposal,
        "finding": {
            "id": finding["id"],
            "topic": finding["topic"],
            "conclusion": finding["conclusion"],
            "status": finding["status"],
            "statusSource": finding["statusSource"],
            "statusReason": finding["statusReason"],
            "spans": finding["spans"],
            "sourceMatches": explained["sourceMatches"],
            "policy": explained["recordedPolicyEvaluation"],
        },
        "adjudication": {"label": label["label"], "premiseAccepted": label.get("premise_accepted"), "note": label.get("note")},
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    stores = dict(item.split("=", 1) for item in args.store)
    cases_path, labels_path, manifest_path, verdicts_path = (Path(p) for p in (args.cases, args.labels, args.manifest, args.verdicts))
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in (cases["cases"] if isinstance(cases, dict) else cases)}
    diagnostic = json.loads(Path(args.diagnostic_cases).read_text(encoding="utf-8"))
    corpus_of = {c["id"]: c["corpus_id"] for c in [*cases.values(), *(diagnostic["cases"] if isinstance(diagnostic, dict) else diagnostic)]}
    labels = [json.loads(line) for line in labels_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    corpus = {e["id"]: e for e in (manifest if isinstance(manifest, list) else manifest["documents"])}
    verdicts = json.loads(verdicts_path.read_text(encoding="utf-8"))

    # The labelled findings of the three cases, by session: which store holds each comes from the verdict file.
    sessions_of = {(r["case"], r["session"]): r["finding"] for r in verdicts["rows"] if r["set"] == "unseen"}
    wanted = {case: {s: fid for (c, s), fid in sessions_of.items() if c == case} for case in (HEADLINE, CAUGHT, FALSE_ALARM)}
    runs_by_session: dict[str, dict[str, Any]] = {}
    finding_run: dict[str, str] = {}
    for session, store in stores.items():
        fids = [by_session[session] for by_session in wanted.values() if session in by_session]
        located = finding_runs(Path(store), fids)
        finding_run.update(located)
        runs_by_session[session] = read_store(Path(store), sorted(set(located.values())))
    label_of = {r["finding"]: r for r in labels}

    def case_view(case_id: str) -> dict[str, Any]:
        case = cases[case_id]
        sessions = []
        sections: dict[str, dict[str, Any]] = {}
        for session in sorted(wanted[case_id]):
            fid = wanted[case_id][session]
            run = runs_by_session[session][finding_run[fid]]
            sessions.append(session_view(session, run, fid, label_of[fid]))
            sections.update(run["sections"])
        first = runs_by_session[sorted(wanted[case_id])[0]][finding_run[wanted[case_id][sorted(wanted[case_id])[0]]]]
        return {
            "id": case_id,
            "family": case["family"],
            "question": case["question"],
            "expectedAnswer": case["expected_answer"],
            "requiredConditions": case["required_conditions"],
            "decisivePassages": [{"sectionId": p["section_id"], "heading": p["heading"], "quote": p["quote"]} for p in case["decisive_passages"]],
            "source": source_of(corpus[case["corpus_id"]], Path(args.raw)),
            "input": first["input"],
            "sessions": sessions,
            "sections": dict(sorted(sections.items())),
        }

    rows = []
    for r in verdicts["rows"]:
        rows.append({k: r[k] for k in ("set", "session", "case", "finding", "label", "flagged", "why", "parties", "actingInAnswer", "actingInQuote", "reason")})
        rows[-1]["source"] = corpus[corpus_of[r["case"]]]["source_url"]
        if r["label"] == "wrong_party":
            rows[-1].update({"question": r["question"], "conclusion": r["conclusion"], "quotes": r["quotes"], "labelNote": r["labelNote"]})
    return {
        "schema": SCHEMA,
        "evaluation": {
            "cases": {"file": cases_path.name, "sha256": sha256_file(cases_path)},
            "labels": {"file": labels_path.name, "sha256": sha256_file(labels_path)},
            "manifest": {"file": manifest_path.name, "sha256": sha256_file(manifest_path)},
            "verdicts": {"file": verdicts_path.name, "sha256": sha256_file(verdicts_path)},
            "diagnosticCases": {"file": Path(args.diagnostic_cases).name, "sha256": sha256_file(Path(args.diagnostic_cases))},
            "diagnosticLabels": {"file": Path(args.diagnostic_labels).name, "sha256": sha256_file(Path(args.diagnostic_labels))},
        },
        "headline": case_view(HEADLINE),
        "rejectedFix": {"commit": verdicts["commit"], "policy": verdicts["policy"], "function": verdicts["function"], "rows": rows},
        "counterexample": {"caught": case_view(CAUGHT), "falseAlarm": case_view(FALSE_ALARM)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump", help=argparse.SUPPRESS)
    parser.add_argument("--store", action="append", default=[], help="session=store directory (copied, never written)")
    parser.add_argument("--cases")
    parser.add_argument("--labels")
    parser.add_argument("--manifest")
    parser.add_argument("--verdicts")
    parser.add_argument("--diagnostic-cases")
    parser.add_argument("--diagnostic-labels")
    parser.add_argument("--raw", help="the corpus's downloaded filings, <id>.<format>")
    parser.add_argument("--mask-name", action="append", default=[], help="a person the story does not need, masked wherever named")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    if args.dump is not None:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        print(json.dumps(dump_store(args.dump.split(","))))
        return
    count = {"emails": 0, "names": 0}
    record = masked(build(args), count, args.mask_name)
    assert isinstance(record, dict)
    record["masking"] = {
        "inInput": record["headline"]["input"]["user"].count(EMAIL_MASK),
        "mask": EMAIL_MASK,
        "names": count["names"],
        "nameMask": NAME_MASK,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}: {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
