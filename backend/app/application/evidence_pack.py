"""Use case: a self-verifying evidence pack for a run.

One zip holds the original document bytes, the canonical sections the run read, the run record
with its hashes, every finding with its located spans, and a dependency-free `verify.py` that
re-hashes the document and the sections and re-locates every quote at its stored offsets under
the same normalisation the workbench used. Anyone with Python can check the evidence on their
own machine without this service. Nothing in the pack is computed by a model.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ..analysis.service import MAX_SECTION_CHARS_IN_PROMPT
from ..config import settings
from ..errors import NotFound
from ..hashing import sha256_bytes
from ..models import Run, iso, utcnow
from ..verify import spans as verifier
from .create_memo import review_head
from .ingest_document import coverage_of, original_path
from .reconstruct_input import reconstruct_input

QUOTE_MAP = {chr(k): v for k, v in verifier._QUOTE_MAP.items()}  # the one normalisation table, embedded in verify.py

# The standalone checker shipped in every pack. It lives in a text file so that the rule
# 'only app/hashing.py imports hashlib' stays enforceable by a grep over the code.
VERIFY_PY = (Path(__file__).with_name("verify_template.txt")).read_text(encoding="utf-8")

README_TXT = """Evidence pack for one Contract Workbench run.

  run.json        the run: question, stage, hashes of the document, sections, prompt and options, model
  sections.json   the canonical sections the run read, exactly as stored (offsets index into these texts)
  findings.json   every finding the model proposed with its status and every quoted span, located or withheld
  document/       the original uploaded bytes, when they were kept
  model_input/    the exact system and user messages the model was given, rebuilt from the record (when the
                  record still allows it); run.json carries the hash the run recorded when it made the call
  guidance.txt    the legal guidance the run was given, when any
  verify.py       a dependency-free check: python3 verify.py

The pack asserts nothing a machine cannot re-check. Run verify.py; every PASS line is a claim you
have now checked yourself.
"""


@dataclass(frozen=True)
class EvidencePack:
    filename: str
    data: bytes


def build_evidence_pack(session: Session, run_id: str) -> EvidencePack:
    run = session.get(Run, run_id)
    if run is None:
        raise NotFound("run", run_id)
    document = run.document
    sections = [{"id": s.id, "ordinal": s.ordinal, "number": s.number, "heading": s.heading, "text": s.text} for s in document.sections]
    sections_json = json.dumps(sections, ensure_ascii=False, indent=1)
    findings = [
        {
            "id": f.id,
            "ordinal": f.ordinal,
            "topic": f.topic,
            "status": f.status,
            "status_source": f.status_source,
            "conclusion": f.conclusion,
            "review": (
                {"verdict": f.review.verdict, "reviewer": f.review.reviewer, "note": f.review.note, "at": iso(f.review.created_at)} if f.review else None
            ),
            "spans": [
                {
                    "ordinal": s.ordinal,
                    "section_id": s.section_id,
                    "cited_label": s.cited_section_label,
                    "start": s.start,
                    "end": s.end,
                    "quote": s.quote,
                    "verified": s.verified,
                    "method": s.method,
                    "match_count": s.match_count,
                }
                for s in f.spans
            ],
        }
        for f in run.findings
    ]
    original = original_path(document)
    original_bytes = original.read_bytes() if original.exists() else None
    rebuilt = reconstruct_input(session, run.id)
    model_input = {
        "input_sha256_recorded": rebuilt.recorded_input_sha256,
        "reconstructable": rebuilt.matches,
        "problem": rebuilt.problem,
        "system_file": "model_input/system.txt" if rebuilt.matches else None,
        "user_file": "model_input/user.txt" if rebuilt.matches else None,
        "prompt_window_chars": 5000,
    }
    context_slices = [
        {"label": s.label, "section_id": s.section_id, "rank": s.rank, "start": s.start, "end": s.end, "truncated": s.truncated, "sha256": s.content_sha256}
        for s in rebuilt.slices
    ]
    record = {
        "run_id": run.id,
        "fingerprint": run.fingerprint,
        "question": run.question,
        "stage": run.stage,
        "reason": run.reason,
        "task": run.task,
        "document": {
            "id": document.id,
            "name": document.name,
            "sha256": document.sha256,
            "parser_version": document.parser_version,
            "parse_coverage": coverage_of(document),
            "file": f"document/{document.name}" if original_bytes is not None else None,
        },
        "sections_sha256": sha256_bytes(sections_json.encode("utf-8")),
        # What the run itself recorded when it read the document (the reading stage's output hash), so the pack
        # can be checked against the record and not only against itself.
        "sections_text_sha256_recorded": next((s.output_hash for s in run.stages if s.stage == "reading"), None),
        "guidance_sha256": run.guidance_sha256,
        "guidance_file": "guidance.txt" if run.guidance else None,
        "review_head": review_head(run),
        "model_input": model_input,
        "context_slices": context_slices,
        "provider": run.provider,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "prompt_hash": run.prompt_hash,
        "options": json.loads(run.options_json or "{}"),
        "created_at": iso(run.created_at),
        "finished_at": iso(run.finished_at),
        "packed_at": iso(utcnow()),
        "verifier": {
            "version": verifier.VERIFIER_VERSION,
            "ladder": ["exact", "normalized", "casefold", "typed"],
            "label_stripping": True,
            "boundary": "no edge splits a run of letters and digits; a typed match is whole tokens",
            "window_chars": MAX_SECTION_CHARS_IN_PROMPT,
        },
        "workbench_link": f"{settings.app_url}/?document={document.id}&run={run.id}",
    }
    verify_py = VERIFY_PY.replace("__QUOTE_MAP__", json.dumps(json.dumps(QUOTE_MAP, ensure_ascii=True)))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.writestr("README.txt", README_TXT)
        pack.writestr("run.json", json.dumps(record, ensure_ascii=False, indent=1))
        pack.writestr("sections.json", sections_json)
        pack.writestr("findings.json", json.dumps(findings, ensure_ascii=False, indent=1))
        pack.writestr("verify.py", verify_py)
        if original_bytes is not None:
            pack.writestr(f"document/{document.name}", original_bytes)
        if rebuilt.matches and rebuilt.system is not None and rebuilt.user is not None:
            pack.writestr("model_input/system.txt", rebuilt.system)
            pack.writestr("model_input/user.txt", rebuilt.user)
        if run.guidance:
            pack.writestr("guidance.txt", run.guidance.text)
    return EvidencePack(filename=f"evidence-{run.id}.zip", data=buffer.getvalue())
