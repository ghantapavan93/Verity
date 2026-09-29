"""Build docs/DOMAIN-REVIEW.md from the record, selecting runs by document, model, prompt and
retrieval rather than by question text.

    cd backend && .venv/Scripts/python scripts/domain_review_pack.py > ../docs/DOMAIN-REVIEW.md

For each golden in the pack, the latest complete run on the bundled sample (found by the file's
sha256, so a re-upload under another name is the same document) with the default model, the
current prompt version and BM25 retrieval. A golden with no such run gets a row that says so.
The independent review of 2026-09-29 found the previous pack assembled by question text, which
let runs on another document and on a rejected model into a document meant for a reviewer
outside the loop; this script exists so that cannot happen again.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run from backend/ without an install, like the other scripts

from app.config import settings
from app.hashing import sha256_file
from app.ingest import PARSER_VERSION

BACKEND = Path(__file__).resolve().parents[1]
SAMPLE = BACKEND.parent / "public" / "samples" / "cloud-service-agreement.docx"
GOLDENS = BACKEND / "app" / "goldens" / "set.json"
PACK = ["g02", "g03", "g04", "g08", "g09", "g10", "g12", "g19", "g20", "g29"]
MODEL = "qwen3:8b"
PROMPT = "answer-v2"
QUOTE_LIMIT = 350

QUESTIONS = (
    "Questions: (1) Is the conclusion correct? (2) Is the quoted evidence sufficient for it? (3) What legal "
    "nuance is missing? (4) Is the status appropriate? (5) Would you act on this finding as written?"
)


def cell(text: str | None, limit: int | None = None) -> str:
    flat = re.sub(r"\s+", " ", (text or "").strip()).replace("|", "\\|")
    if limit is not None and len(flat) > limit:
        flat = flat[:limit].rstrip() + " […]"
    return flat


def latest_run(connection: sqlite3.Connection, document_id: str, question: str, guidance: str | None) -> sqlite3.Row | None:
    guidance_clause = "AND runs.guidance_id IS NULL" if guidance is None else "AND guidance.text = :guidance"
    row: sqlite3.Row | None = connection.execute(
        f"""
        SELECT runs.id, runs.created_at, runs.options_json
        FROM runs LEFT JOIN guidance ON guidance.id = runs.guidance_id
        WHERE runs.document_id = :document AND runs.question = :question AND runs.model = :model
          AND runs.prompt_version = :prompt AND runs.stage = 'complete'
          AND runs.options_json NOT LIKE '%hybrid%' {guidance_clause}
        ORDER BY runs.created_at DESC LIMIT 1
        """,
        {"document": document_id, "question": question, "model": MODEL, "prompt": PROMPT, "guidance": guidance},
    ).fetchone()
    return row


def finding_and_quote(connection: sqlite3.Connection, run_id: str) -> tuple[str, str]:
    finding = connection.execute("SELECT id, topic, status, conclusion FROM findings WHERE run_id = ? ORDER BY ordinal LIMIT 1", (run_id,)).fetchone()
    if finding is None:
        return "no finding recorded", "-"
    spans = connection.execute(
        """
        SELECT spans.quote, spans.verified, spans.method, spans.cited_section_label, sections.number, sections.heading
        FROM evidence_spans spans LEFT JOIN sections ON sections.id = spans.section_id
        WHERE spans.finding_id = ? ORDER BY spans.ordinal
        """,
        (finding["id"],),
    ).fetchall()
    finding_cell = f"**{cell(finding['topic'])}** ({finding['status']}): {cell(finding['conclusion'])}"
    verified = [s for s in spans if s["verified"]]
    if verified:
        span = verified[0]
        label = span["number"] or span["cited_section_label"] or span["heading"] or "?"
        quote_cell = f'"{cell(span["quote"], QUOTE_LIMIT)}" (§{cell(label)}, {span["method"]})'
        if len(verified) > 1:
            quote_cell += f" and {len(verified) - 1} more verified"
        return finding_cell, quote_cell
    if finding["status"] == "missing":
        return finding_cell, "none: the model said the contract does not address it"
    return finding_cell, f"none: {len(spans)} quote(s) withheld, not found in the document"


def main() -> int:
    goldens = {g["id"]: g for g in json.loads(GOLDENS.read_text(encoding="utf-8"))["goldens"]}
    sample_sha = sha256_file(SAMPLE)
    connection = sqlite3.connect(settings.data_dir / "workbench.db")
    connection.row_factory = sqlite3.Row
    # The same bytes are one document row per reader version; the pack is built on the current reader's parse.
    document = connection.execute(
        "SELECT id, name, parser_version FROM documents WHERE sha256 = ? AND parser_version = ? ORDER BY created_at LIMIT 1",
        (sample_sha, PARSER_VERSION),
    ).fetchone()
    if document is None:
        print(f"the sample ({sample_sha[:16]}) has no row under reader {PARSER_VERSION} in {settings.data_dir}", file=sys.stderr)
        return 1

    rows: list[str] = []
    for index, golden_id in enumerate(PACK, start=1):
        golden = goldens[golden_id]
        run = latest_run(connection, document["id"], golden["question"], golden.get("guidance"))
        if run is None:
            rows.append(
                f"| {index} | {golden_id} | {cell(golden['question'])} | no complete run with this model, prompt and retrieval in the record | - | - | |"
            )
            continue
        finding_cell, quote_cell = finding_and_quote(connection, run["id"])
        rows.append(f"| {index} | {golden_id} | {cell(golden['question'])} | {finding_cell} | {quote_cell} | `{run['id']}` {run['created_at'][:10]} | |")

    print("# Domain review pack: ten findings for a practising lawyer or legal-ops reviewer")
    print()
    print(
        "Every finding below was produced by the workbench on the bundled sample, the Common Paper Cloud Service "
        f"Agreement (CC BY 4.0), sha256 `{sample_sha[:16]}…`, read by reader {document['parser_version']}; model `{MODEL}`, "
        f"prompt `{PROMPT}`, BM25 retrieval; for each question the latest complete run in the record, selected by those "
        "fields and not by hand. Every quote shown was verified by code against the document text, and the verifier "
        "tier is given next to the section. Quotes longer than "
        f"{QUOTE_LIMIT} characters are cut with […]; the evidence pack of the run (Runs → the run → evidence pack) has the whole quote. "
        "The engineering has been measured; the legal judgment has not."
    )
    print()
    print(QUESTIONS)
    print()
    print("| # | Golden | Question asked | Finding (status) | Verified quote (section, tier) | Run | Your answers to 1 to 5 |")
    print("|---|---|---|---|---|---|---|")
    print("\n".join(rows))
    print()
    print(f"Built by `backend/scripts/domain_review_pack.py` on {date.today().isoformat()} from the record in `backend/data`.")
    print()
    print("Reviewer: ____________________  Date: __________  Time spent: ______")
    return 0


if __name__ == "__main__":
    sys.exit(main())
