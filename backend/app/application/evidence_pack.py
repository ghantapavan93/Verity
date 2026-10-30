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
import re
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ..analysis.service import window_of
from ..config import settings
from ..document_names import run_document_name
from ..errors import NotFound
from ..hashing import sha256_bytes
from ..ingest import base_name
from ..models import Run, iso, utcnow
from ..runs.account import account_of
from ..runs.relations import load
from ..runs.status import basis
from ..verify import spans as verifier
from ..verify import tokens
from .clause_location import ClauseLocator
from .create_memo import review_head
from .ingest_document import coverage_of, document_suffix, original_path
from .reconstruct_input import reconstruct_input

# The normalisation table, embedded in verify.py: v10's, from which the pack builds v11's with IGNORABLE_RANGES.
QUOTE_MAP = {chr(k): v for k, v in verifier._QUOTE_MAP_V10.items()}

# The standalone checker shipped in every pack. It lives in a text file so that the rule
# 'only app/hashing.py imports hashlib' stays enforceable by a grep over the code.
VERIFY_PY = (Path(__file__).with_name("verify_template.txt")).read_text(encoding="utf-8")


def render_verify_py() -> str:
    """The checker as a pack carries it: the workbench's normalisation table, its typed-token pattern (v7 on), the
    reading of a written number of verifier v8 to v11 (their patterns, v9's amount word, v10's labelled word, signs and
    digit marks), and v11's joiners and sentence ends, copied in, so the two cannot read a text differently: a pack
    checks each run as its verifier read it.
    Each is a JSON string literal inside a JSON string literal: valid Python, decoded by json.loads in the checker."""
    embedded = {
        "__QUOTE_MAP__": json.dumps(QUOTE_MAP, ensure_ascii=True),
        "__TOKEN__": json.dumps(tokens._TOKEN.pattern, ensure_ascii=True),
        "__WRITTEN__": json.dumps(tokens._WRITTEN_V8.pattern, ensure_ascii=True),
        "__WRITTEN_V9__": json.dumps(tokens._WRITTEN_V9.pattern, ensure_ascii=True),
        "__WRITTEN_V10__": json.dumps(tokens._WRITTEN_V10.pattern, ensure_ascii=True),
        "__WRITTEN_V11__": json.dumps(tokens._WRITTEN.pattern, ensure_ascii=True),
        "__LABELLED_WORD__": json.dumps(tokens._LABELLED_WORD.pattern, ensure_ascii=True),
        "__AMOUNT_WORD__": json.dumps(tokens._AMOUNT_WORD.pattern, ensure_ascii=True),
        "__MINUS_SIGNS__": json.dumps(sorted(tokens._MINUS_SIGNS), ensure_ascii=True),
        "__DIGIT_MARKS__": json.dumps(sorted(tokens._DIGIT_MARKS), ensure_ascii=True),
        "__ATTACHED__": json.dumps(sorted(tokens._ATTACHED_V8), ensure_ascii=True),
        "__ATTACHED_V9__": json.dumps(sorted(tokens._ATTACHED), ensure_ascii=True),
        "__SIGN_OPENERS__": json.dumps(sorted(tokens.SIGN_OPENERS), ensure_ascii=True),
        "__DIGIT_MARKS_V11__": json.dumps(sorted(tokens._DIGIT_MARKS_V11), ensure_ascii=True),
        "__SIGN_OPENERS_V11__": json.dumps(sorted(tokens.SIGN_OPENERS_V11), ensure_ascii=True),
        "__JOINERS__": json.dumps(sorted(tokens._JOINERS), ensure_ascii=True),
        "__SENTENCE_END__": json.dumps(tokens._SENTENCE_END.pattern, ensure_ascii=True),
        "__CLAUSE_LETTER__": json.dumps(tokens._CLAUSE_LETTER.pattern, ensure_ascii=True),
        "__IGNORABLE_RANGES__": json.dumps(verifier.IGNORABLE_RANGES),
        "__JOINED__": json.dumps(sorted(tokens._JOINED), ensure_ascii=True),
        "__ATTACHED_V11__": json.dumps(sorted(tokens._ATTACHED_V11), ensure_ascii=True),
        "__LABEL_ENDS__": json.dumps(verifier._LABEL_ENDS, ensure_ascii=True),
    }
    text = VERIFY_PY
    for name, value in embedded.items():
        text = text.replace(name, json.dumps(value))
    return text


README_TXT = """Evidence pack for one Verity run.

  run.json        the run: question, stage, hashes of the document, sections, prompt and options, model
  sections.json   the canonical sections the run read, exactly as stored (offsets index into these texts)
  findings.json   every finding the model proposed with its status and every quoted span, located or withheld;
                  `conclusion` is the model's own sentence as recorded, its section handles written as the sections'
                  labels (one that names no section it was given as "[unidentified section]"; model_output.txt
                  keeps the handles), `shown_conclusion` what the workbench shows
                  (for a point the model reported as not found, only that it was not found in the sections given).
                  Who said what, per finding:
                    status, status_source, status_reason  the status and what set it; a status_source of model_hint
                                    is the model's own call, any other is a check code ran
                    decided_by      "code", "model", or "withheld" (no quote found in the sections handed over)
                    concerns        every sentence code wrote against the status or could not establish
                    flagged         a status other than a pass, or a pass with a concern
                    model           the model's own words: its reading (observed, required), its reference to the
                                    guidance, its suggested position; none of them checked by code
                    review          a person's decision, when one was recorded; nothing else is a person's
                    relations       what the contract's own replacement and precedence statements mean for it, in
                                    code's words, by index into relations.json: "replaced" (quotes text the
                                    contract replaced in full, not the replacement; code set the status);
                                    "old_value" (quotes the replacement, states only replaced values; since
                                    policy-v16 code lowers a pass for it, else a concern); "scoped", "precedence" or "dated" (the
                                    question names a time): a concern code cannot resolve; "context"
  relations.json  the replacement and precedence statements the run located (policy-v11), each end with its offsets
                  into sections.json; verify.py checks every one. A located statement is a fact about the text, not
                  a ruling on its legal effect. Absent for a run recorded before policy-v11
  model_output.txt  the model's structured output exactly as the run recorded it, in the model's own words; verify.py
                  checks it against the hash the run recorded when the model answered
  document/       the original uploaded bytes, when they were kept
  model_input/    the exact system and user messages behind the answer this pack records, rebuilt from the
                  record when it allows it (for a run without an answer, the messages of its first call); run.json
                  carries the hash the run recorded when it made the call. When the first answer failed
                  validation, the recorded answer was given those messages plus a note on why it was rejected,
                  which the run did not keep: no model input is packed then, and run.json's model_input says why
  guidance.txt    the legal guidance the run was given, when any
  verify.py       a dependency-free check: python3 verify.py

The pack asserts nothing a machine cannot re-check. Run verify.py; every PASS line is a claim you
have now checked yourself. A PASS on a span says its quote was found where the run recorded it; it says
nothing about whether the finding's answer is right. The pack is not signed: it shows that its files agree with each other and
with the hashes the run recorded, not that nobody changed them together.
"""


@dataclass(frozen=True)
class EvidencePack:
    filename: str
    data: bytes


# Characters a file name may not carry on Windows, and the device names it reserves. A document is stored under the name
# a person gave it; inside the pack its file must be one every system can create. A document named "<img onerror=…>.txt"
# made a pack that could not be unpacked on Windows at all (hostile content, 2026-10-02).
_UNPORTABLE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$", re.IGNORECASE)


def pack_name(name: str) -> str:
    """The document's file name inside the pack. run.json keeps the name as given (the workspace's, document_names)."""
    safe = _UNPORTABLE.sub("_", base_name(name)).rstrip(" .") or "document"
    return f"_{safe}" if _RESERVED.match(safe) else safe


def build_evidence_pack(session: Session, run_id: str) -> EvidencePack:
    run = session.get(Run, run_id)
    if run is None:
        raise NotFound("run", run_id)
    document = run.document
    sections = [{"id": s.id, "ordinal": s.ordinal, "number": s.number, "heading": s.heading, "text": s.text} for s in document.sections]
    sections_json = json.dumps(sections, ensure_ascii=False, indent=1)
    locator = ClauseLocator(document.sections)
    accounts = {f.id: account_of(f, locator.clause_numbers if f.status != "missing" else frozenset()) for f in run.findings}
    recorded = load(run.relations_json)
    findings = [
        {
            "id": f.id,
            "ordinal": f.ordinal,
            "topic": f.topic,
            "status": f.status,
            "status_source": f.status_source,
            "status_reason": f.status_reason,
            # What the status rests on (runs.status.basis): whether code compared a period, and the sections the quote's
            # sentence points at that the model was not handed, as code recorded them.
            "code_compared": basis(f.status_source, f.status_reason).code_compared,
            "unseen_reason": basis(f.status_source, f.status_reason).unseen,
            "conclusion": f.conclusion,
            "shown_conclusion": f.shown_conclusion,
            # Who set the status and what code raised about it, as the workbench and the memo read it (runs.account).
            "decided_by": (account := accounts[f.id]).decided_by,
            "flagged": account.flagged,
            "concerns": list(account.concerns),
            # The model's own words beside the finding: none of them is checked by code.
            "model": {
                "observed": f.observed,
                "required": f.required,
                "guidance_reference": f.guidance_reference,
                "suggested_position": f.suggested_position,
            },
            "review": (
                {"verdict": f.review.verdict, "reviewer": f.review.reviewer, "note": f.review.note, "at": iso(f.review.created_at)} if f.review else None
            ),
            # What the contract's replacement and precedence statements mean for it, as recorded (relations.json indices).
            "relations": [{"relation": n.relation, "effect": n.effect, "sentence": n.sentence} for n in recorded.notes.get(f.ordinal, ())],
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
                    "clause_label": locator.label(s),
                }
                for s in f.spans
            ],
        }
        for f in run.findings
    ]
    original = original_path(document)
    original_bytes = original.read_bytes() if original.exists() else None
    rebuilt = reconstruct_input(session, run.id)
    options = json.loads(run.options_json or "{}")
    # The input of the answer this pack's findings come from, or why it is not here (reconstruct_input.answered).
    model_input = {
        "input_sha256_recorded": rebuilt.recorded_input_sha256,
        "reconstructable": rebuilt.answered,
        "problem": rebuilt.answered_problem,
        "system_file": "model_input/system.txt" if rebuilt.answered else None,
        "user_file": "model_input/user.txt" if rebuilt.answered else None,
        "prompt_window_chars": window_of(json.loads(run.options_json or "{}")),
        "model_calls": rebuilt.calls,  # a transport retry included
        "validation_rounds": rebuilt.rounds,  # null when the record cannot tell
    }
    context_slices = [
        {"label": s.label, "section_id": s.section_id, "rank": s.rank, "start": s.start, "end": s.end, "truncated": s.truncated, "sha256": s.content_sha256}
        for s in rebuilt.slices
    ]
    # The name as the run's workspace knows it (document_names), with the type's extension, as reading_name gives it.
    shown_name = run_document_name(run)
    suffix = document_suffix(document)
    shown_file = shown_name if shown_name.lower().endswith(suffix) else f"{shown_name}{suffix}"
    record = {
        "run_id": run.id,
        "fingerprint": run.fingerprint,
        "question": run.question,
        "stage": run.stage,
        "reason": run.reason,
        "task": run.task,
        "document": {
            "id": document.id,
            "name": shown_name,
            "sha256": document.sha256,
            "parser_version": document.parser_version,
            "parse_coverage": coverage_of(document),
            "file": f"document/{pack_name(shown_file)}" if original_bytes is not None else None,
        },
        "sections_sha256": sha256_bytes(sections_json.encode("utf-8")),
        # What the run itself recorded when it read the document (the reading stage's output hash), so the pack
        # can be checked against the record and not only against itself.
        "sections_text_sha256_recorded": next((s.output_hash for s in run.stages if s.stage == "reading"), None),
        "guidance_sha256": run.guidance_sha256,
        "guidance_file": "guidance.txt" if run.guidance else None,
        "review_head": review_head(run),
        "model_input": model_input,
        # The model's own words, exactly as recorded: findings.json gives its sentences with the run's section handles
        # replaced (runs.prose), so a handle it was not given shows here as it wrote it. The checking stage recorded the
        # hash of this text when the model answered; a run recorded before stages kept hashes has none to check against.
        "model_output": {
            "file": "model_output.txt" if run.raw_output is not None else None,
            "sha256_recorded": next((s.output_hash for s in run.stages if s.stage == "checking"), None),
        },
        "context_slices": context_slices,
        # How the sections handed to the model were chosen. `mode` is null on a run recorded before it was a field.
        "retrieval": {"mode": run.retrieval_mode, "requested_k": options.get("retrieval_k"), "returned": len(context_slices) if rebuilt.slices else None},
        "provider": run.provider,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "prompt_hash": run.prompt_hash,
        "options": json.loads(run.options_json or "{}"),
        "created_at": iso(run.created_at),
        "finished_at": iso(run.finished_at),
        "packed_at": iso(utcnow()),
        # The verifier of the build that wrote this pack. A run made under an earlier verifier keeps what that one
        # recorded: each span in findings.json carries the tier that matched it (`method`), and that is the record.
        "verifier": {
            "describes": "the verifier of the build that wrote this pack; each span's own `method` is what verified it",
            "version": verifier.VERIFIER_VERSION,
            "ladder": ["exact", "normalized", "casefold", "typed"],
            "label_stripping": True,
            "boundary": "no edge splits a run of letters and digits; a typed match is whole tokens, words compared whole",
            "window_chars": window_of(json.loads(run.options_json or "{}")),
            # A character Unicode assigned after the checker's own database reads as unassigned there (stress test,
            # 2026-10-30): verify.py names the version it was built with and refuses to judge what it cannot read.
            "unicode": unicodedata.unidata_version,
        },
        "workbench_link": f"{settings.app_url}/?document={document.id}&run={run.id}",
        # The contract's replacement and precedence statements the run recorded (runs.relations, policy-v11).
        "relations_file": "relations.json" if run.relations_json else None,
        "relations_note": None if run.relations_json else "the run was recorded before relations were (policy-v11); none are shown, none re-derived",
    }
    verify_py = render_verify_py()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.writestr("README.txt", README_TXT)
        pack.writestr("run.json", json.dumps(record, ensure_ascii=False, indent=1))
        pack.writestr("sections.json", sections_json)
        pack.writestr("findings.json", json.dumps(findings, ensure_ascii=False, indent=1))
        if run.relations_json:
            pack.writestr("relations.json", json.dumps([asdict(r) for r in recorded.relations], ensure_ascii=False, indent=1))
        pack.writestr("verify.py", verify_py)
        if run.raw_output is not None:
            pack.writestr("model_output.txt", run.raw_output)
        if original_bytes is not None:
            pack.writestr(f"document/{pack_name(shown_file)}", original_bytes)
        if rebuilt.answered and rebuilt.system is not None and rebuilt.user is not None:
            pack.writestr("model_input/system.txt", rebuilt.system)
            pack.writestr("model_input/user.txt", rebuilt.user)
        if run.guidance:
            pack.writestr("guidance.txt", run.guidance.text)
    return EvidencePack(filename=f"evidence-{run.id}.zip", data=buffer.getvalue())
