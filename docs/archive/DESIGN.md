# Contract Workbench: design

Status: draft v0.1, 28 September 2026. Written before the implementation and updated when a
decision changes. The three killed experiments in `ivo-experiments` are the reliability layer
under this product, not its subject.

## 1. Problem contract

**Problem.** A reviewer has a contract and the guidance their team actually uses (a playbook,
a lawyer's note, a policy). They need answers about the contract that are grounded in its
exact text, judged against that guidance, with the derivation one click away and a usable
output at the end. Today that is a model reading a PDF and printing prose nobody can check.

**Primary users.** An in-house legal reviewer (asks and reviews); a legal engineer (judges
whether the system can be trusted); the engineers who read the code.

**Primary workflow.** Upload one or more contracts, optionally add guidance → open a
workspace with the document on the left and the Assistant on the right → ask a question or
run a review → receive structured findings whose citations open the exact contract text →
inspect the derivation → generate one review memo.

**Inputs.** Contracts as PDF, DOCX or TXT. Guidance as pasted text or an uploaded file.
Questions in plain language. **Outputs.** Findings (topic, status, conclusion, evidence
spans, suggested position), a review memo (HTML first, DOCX after), run records.

**Constraints.**

- Runs locally at $0: Qwen3 8B through Ollama by default; documents never leave the machine
  unless a remote provider is chosen explicitly.
- Deterministic code verifies every citation against the stored text before it is shown.
- Every run is reproducible from stored inputs: document hash, guidance hash, prompt version
  and hash, model tag, parameters.
- No confidence scores. Status is a closed set. "Insufficient evidence" is a first-class
  outcome, never a fabricated conclusion.
- Stage progress streams to the UI (reading, finding evidence, checking, complete); no
  chain-of-thought, no agent theatre.

**Non-goals.** Editing or redlining the document; a Word add-in; organisation management,
signup or password recovery; a generic chat page; agent visualisations; analytics
dashboards; resurrecting Surgicality or Field Plan as products; cloning Ivo.

## 2. Domain model

| Entity | Fields | Notes |
|---|---|---|
| `Document` | id, name, media type, sha256, page count, uploaded at, `sections[]` | Immutable once ingested |
| `Section` | id, document id, ordinal, number, heading, text, character offsets | The unit of citation and retrieval |
| `Guidance` | id, text, sha256, source (pasted or file) | Immutable; a new paste is a new record |
| `Request` | kind (`question` or `review`), text, scope (document ids, guidance id) | What the user asked |
| `Run` | id, created at, request, model tag, prompt version + hash, parameters, status, `stages[]`, raw output | Append-only; a re-run is a new run |
| `EvidenceSpan` | run id, document id, section id, start, end, quote, verified, method | `verified` is set by code, never by the model |
| `Finding` | run id, topic, status, conclusion, spans[], guidance reference, observed, required, suggested position | Shown only when every span verifies |
| `Memo` | run id, format, sha256, created at | Generated from findings, never from free text |

Run status: `created → reading → retrieving → analyzing → verifying → complete | unresolved | failed`.
Finding status: `pass | needs_review | missing | unresolved`.

## 3. Critical invariants

1. **A finding is shown only if every cited span verifies verbatim** (after whitespace and
   quote normalisation) against the stored section text. An unverifiable citation degrades
   the finding to `unresolved`; the model's text stays in the run record, behind a disclosure.
2. **Every run can be replayed** from what it stores. Nothing about a run is inferred later.
3. **The model never sets a status.** It proposes topic, conclusion, spans and position; code
   verifies spans, computes observed-versus-required where the guidance is numeric, and sets
   the status.
4. **No numbers pretend to be confidence.** Where the product quantifies, it counts things
   that exist: sections searched, spans verified, runs compared.
5. **Deterministic code owns** parsing, section identity, retrieval merging, span
   verification, IDs, hashes and persistence. The model owns analysis text, all of it
   validated before display.

Enforcement order: database constraints, then domain rules, then API validation, then UI.

## 4. Architecture

```
 Browser (Next.js 16, React 19, TypeScript, CSS Modules + tokens, Framer Motion for the morph)
   │  REST + SSE
 FastAPI (Python 3.13)
   ├─ ingest/      docx (accepted view of tracked changes; python-docx for structure, the XML for text), pdf (pypdf layout), txt → Document + Sections
   ├─ goldens/     fixed questions about the sample, judged by code per prompt version and model (docs/GOLDENS.md)
   ├─ routing/     which model answers which task, from golden measurements only (docs/ROUTING.md)
   ├─ batch/       the same run over a corpus with bounded concurrency; numbers from the records (docs/BATCH.md)
   ├─ families/    structural fingerprints → exact Jaccard → single-linkage families, measured against labels (docs/FAMILIES.md)
   ├─ retrieval/   BM25 (rank_bm25) ∪ pgvector (nomic-embed-text via Ollama) → fused candidates
   ├─ graph/       LangGraph state machine (below)
   ├─ verify/      span matcher: quote → (section, start, end) or nothing
   ├─ providers/   ModelProvider: Ollama (default) · Anthropic · OpenAI · Gemini
   ├─ memo/        findings → HTML → DOCX
   └─ runs/        persistence, stage events, replay
 PostgreSQL 16 + pgvector (Docker), SQLAlchemy 2, Alembic
```

**The graph.** LangGraph is used because the review flow has real state and real branches:

```
classify_request → identify_scope → retrieve_evidence → analyze → validate_citations
                                                                      ├─ verified   → compose_answer → END
                                                                      └─ unverified → request_more_context → END
review requests: identify_scope → extract_positions (from guidance) → per topic: retrieve → compare → generate_issue → validate
```

Business rules live in typed Python services, not in graph nodes; nodes call services.

**As built (2026-09-28).** The slice runs on SQLite (SQLAlchemy 2) and BM25 alone; there is no
Postgres, pgvector or LangGraph in the tree. Routes call use cases in `backend/app/application`
(ingest a document, start or reuse a run, project a memo, recover interrupted runs); the run is a
plain typed service (`backend/app/runs/service.py`) with the stages `reading → finding_evidence →
checking → verifying → complete | unresolved | failed`, persisted as rows and streamed over SSE.
Identity (document, guidance, prompt and memo hashes, run fingerprints) is computed in
`backend/app/hashing.py`. A run is idempotent on its inputs: the same document, guidance,
question, prompt hash and options return the existing running or completed run, enforced by a
partial unique index; failed runs are retryable. Each of the deferred pieces is added when a
measurement on real runs shows the current choice failing (ADR 0003, ADR 0004), not because this
diagram names it. `ENGINEERING_CONSTITUTION.md` holds the ownership map.

**Streaming.** `GET /api/runs/{id}/events` (SSE) emits stage transitions only:
`reading`, `finding_evidence`, `checking`, `verifying`, `complete`, `unresolved`, `failed`.

**API sketch.**

| Method and path | Purpose |
|---|---|
| `POST /api/documents` | upload; returns the document with sections |
| `POST /api/guidance` | store pasted or uploaded guidance |
| `POST /api/runs` | start a run for a request and scope; returns the run id |
| `GET /api/runs/{id}` · `GET /api/runs/{id}/events` | state with verified findings; stage stream |
| `GET /api/runs` · `GET /api/runs/{id}/detail` | run list; the full engineering record of one run |
| `GET /api/findings` | verified findings across runs (optional `documentId`) |
| `GET /api/documents` · `GET /api/documents/{id}` | uploaded documents; one document with sections |
| `POST /api/memos` · `GET /api/memos/{id}/html` · `/docx` | generate and fetch the memo for a run |
| `GET /api/engineering/experiments` | the killed experiments, from `ivo-experiments/docs/results.json` |

## 5. The three surfaces

1. **Workspace.** Document left (serif, sections addressable), Assistant right (scope chips,
   composer, results as objects with citations and actions), draggable divider, evidence drawer.
2. **Findings.** Verified findings across runs, grouped by document: topic, status,
   conclusion, question, citation count; opening one loads the document at the passage with the
   evidence drawer open.
3. **Runs.** Engineering history: model, prompt version and hash, decoding options, tokens,
   latency, stage timeline, the sections handed to the model, how each quote was located,
   the raw output, and the three killed experiments as records.

Navigation: Documents, Assistant (default), Findings, Runs. One seeded account. The three
non-Assistant destinations are views inside the same shell (rail on the left, one list per
screen), not separate pages.

## 6. Failure semantics

| Failure | Behaviour | `reason` on the run |
|---|---|---|
| Model output fails the schema | one retry with the validation error; then the run is `failed` ("Analysis couldn't complete", Try again) | `invalid_output` |
| A citation does not verify | the finding is withheld (`unresolved`); the raw output stays in the run ("Evidence could not be verified") | `citations_unverified` |
| The sections retrieved do not answer the question | the run is `unresolved` with the sections searched ("No supporting passage found") | `insufficient_evidence` |
| Something is absent from the sections read | a finding with status `missing`, worded as "not found in the sections reviewed", citing the closest provisions | none (complete) |
| Ollama unreachable | the run is `failed` with the exact reason; nothing is invented | `provider_error` |
| Unsupported or unreadable file | rejected at upload with the reason | n/a |
| A PDF whose text carries no numbering or capitals | read as flat text; the workspace says sections are approximate; quotes still verify against the text | n/a |

The stage list in the Assistant is the API's own progress: each stage row is written when
the stage starts and annotated when it finishes (`11 pages · 123 sections`, `6 candidate
sections`, `model answered in 48 s`, `3 of 3 quotes verified`). There is no chain-of-thought
to show, and none is requested from the model.

## 7. First vertical slice

Upload one real contract → paste one instruction → ask one question → retrieve the relevant
language → one structured finding → validate the citation → click the citation to highlight
the exact text → generate one memo. It must genuinely work with the local model before any
second feature is added. Nothing on this path is mocked.

## 8. What is not built

Another centred chat page; confidence scores; a floating AI orb; giant metric cards; fake
analytics; agents drawn as circles; animated graph nodes; "Agent 1 researching…"; a generic
dashboard; fake customer data; a direct Ivo clone; a fake Word plugin. The headline is the
job, not the stack.

## 9. Open questions

- Section detection on PDFs without structure: pypdf's layout mode keeps paragraphs, and
  headings are found by numbering or capitals only. Font-size heading detection was tried with
  pypdf's visitor API and it did not report per-run sizes on printed PDFs; a PDF library with
  character-level metrics would be the next step if PDFs matter. OCR is out of scope.
- Whether BM25 alone carries the slice; pgvector is added when a measurement shows it helps.
  The golden set is the measurement.
- DOCX text hidden through a character style: the reader drops runs marked hidden on the run
  itself (`w:vanish`) and resolves nothing from styles. Table-heavy paper (defined-term rows,
  schedules) parses as long unnumbered chunks; table-aware sectioning is the next ingestion job
  if such paper matters.
- Memo format: HTML first; DOCX when the HTML memo is right.
