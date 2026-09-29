# System map

Verified against commit `43a67f3` (2026-09-29). An index, not documentation: each row names the
owner, the file, the principal function or class, what goes in and what comes out. When a subsystem
changes, update its row and the commit above. Never rewrite broadly because a row is stale.

## Roots and locations

| What | Where |
|---|---|
| Frontend root | `src/` (Next.js 16, App Router). Entry `src/app/page.tsx` → `src/components/workbench/Workbench.tsx` |
| Backend root | `backend/app/` (FastAPI, SQLAlchemy 2, SQLite). Entry `backend/app/main.py`; `uvicorn app.main:app` from `backend/` |
| Database | SQLite in WAL mode at `{WORKBENCH_DATA_DIR or backend/data}/workbench.db` (`backend/app/config.py`). Schema owner `backend/app/models.py`. Additive column/index migration and immutability triggers: `backend/app/db.py` `init_db` → `ensure_columns`, `ensure_immutability` |
| Data directory | `documents/{sha256}{ext}` (original upload, written after the commit), `memos/memo-{run_id}.docx`, `logs/`; all of `backend/data/` is gitignored |
| Bundled sample | `public/samples/cloud-service-agreement.docx`, sha256 `cb72dad74b3af676…`: Common Paper Cloud Service Agreement v2.1, CC BY 4.0, unmodified (stated in `README.md` and the `document` block of `backend/app/goldens/set.json`). Under reader v4: 11 pages, 123 sections |
| Evaluation data (never read by the API; see `docs/SYSTEM_TRUTH.md` E) | goldens `backend/app/goldens/set.json` (44); CUAD manifest and expert labels `backend/app/batch/corpora/{cuad-30.json, cuad-30-labels.json, cuad-skillopt.json}`; CUAD archive and texts `backend/data/cuad/` (gitignored; provenance in `SOURCE.txt`); public 20-contract corpus `../ivo-experiments/experiments/{b1-word-structure, pilot-redline-integrity}/corpus` (licences in `corpus_sources.csv`, `sources.csv`); family labels `backend/app/families/labels.json`; test fixtures `backend/tests/support.py`, `backend/tests/fixtures/services-agreement.pdf`; recorded model answers `e2e/replay.json` |
| Prompts | `backend/app/analysis/prompts/answer-v1.md`, `answer-v2.md` (default: `settings.prompt_version`), `answer-v3.md` (pre-registered candidate, not default) |
| Model provider | Ollama at `WORKBENCH_OLLAMA_URL` (default `http://localhost:11434`), model `qwen3:8b`. Provider by `WORKBENCH_PROVIDER`: `ollama` (default), `replay`, `record` |
| API contract | `openapi.json` written by `backend/scripts/export_openapi.py` → `src/lib/api.schema.ts` by `npm run api:types` |
| Settings | `backend/app/config.py` `Settings`: env `WORKBENCH_DATA_DIR`, `_DATABASE_URL`, `_PROVIDER`, `_MODEL`, `_OLLAMA_URL`, `_RETRIEVAL` (bm25 / hybrid), `_RETRIEVAL_K` (6), `_EMBED_MODEL`, `_PROMPT_VERSION`, `_ROUTING_POLICY` (`{}`), `_REPLAY_FILE`, `_CORS_ORIGINS`, `_APP_URL`; fixed: temperature 0, seed 42, num_ctx 16384, model_timeout_s 600 |

## Backend

| Responsibility | Files | Principal function / class | Input → output |
|---|---|---|---|
| HTTP error mapping | `backend/app/errors.py`, handler in `main.py` | `WorkbenchError` 500, `NotFound` 404, `Conflict` 409, `InvalidInput` 422, `TooLarge` 413 | exception → `{"detail": text}` |
| Identity | `backend/app/hashing.py` | `sha256_bytes`, `sha256_text`, `sha256_file`, `fingerprint(kind, *parts)` (length-prefixed, 0x1F-joined) | bytes or text → hex. The only `app/` module that imports hashlib |
| Ingestion | `backend/app/ingest/__init__.py`, `readers.py`, `sections.py`; `backend/app/application/ingest_document.py` | `ingest(name, data)` (`PARSER_VERSION = "v4"`); `readers.py` dispatch by extension, `read_docx`, `read_pdf`, txt reader; `sections.py` heading levels, numbers, lead-in rule, 6,000-character split; `ingest_document(session, name, data)` | file bytes → `Document` + `Section` rows and the stored file. Reuse when sha256 and parser version match (200, `reused`). Caps: 25 MB upload, 256 MB declared unpack, 2,000 PDF pages |
| Documents API | `backend/app/api/documents.py` | `POST /api/documents`, `GET /api/documents`, `GET /api/documents/{id}` | multipart file → `DocumentOut` (201 / 200) / `DocumentSummary[]` |
| Guidance | `backend/app/application/save_guidance.py`, `backend/app/api/guidance.py` | `save_guidance` (strip, sha256, oldest row wins); `POST /api/guidance`, `GET /api/guidance/{id}` | text 1–20,000 chars → `GuidanceOut` (201 / 200). No update, delete or list |
| Run identity and start | `backend/app/application/start_run.py` | `start_run`, `run_options`, `compute_fingerprint` (`run/v1`: document id, guidance id, question, prompt sha256, options JSON), `active_run`; index `ux_runs_fingerprint_active` in `models.py` | `RunIn` → `StartedRun(run, created)`. Running, complete and unresolved runs are reused; only failed runs are retried |
| Run execution | `backend/app/runs/service.py`; worker `_worker` in `backend/app/api/runs.py` (own session; `create_run` commits before returning) | `execute_run`: reading → finding_evidence (`_retrieve`) → checking (`analyze`) → verifying (`verify_evidence`, `decide`, `check_references`) → complete / unresolved (`insufficient_evidence`, `citations_unverified`) / failed (`invalid_output`, `provider_error`, `internal_error`); `_set_stage`, `_note_stage` | run id → `run_stages`, `findings`, `evidence_spans`, `raw_output`, `candidates_json` |
| Retrieval | `backend/app/retrieval/lexical.py`, `hybrid.py` | `LexicalIndex` (BM25Okapi defaults, heading ×3, 39 stopwords, numbers kept, no stemming), `HybridIndex` (`ollama_embed`, RRF k = 60), `fuse` | (heading, text) per section + query (question + guidance) → top k; fallback: first k sections. Labels `sec_<ordinal>` |
| Analysis: the one model call | `backend/app/analysis/service.py`, `schema.py` | `load_prompt`, `build_user_message` (QUESTION / LEGAL GUIDANCE / CONTRACT / SECTIONS; `MAX_SECTION_CHARS_IN_PROMPT` 5,000), `analyze` (2 validation rounds × 1 transport retry: 1–4 calls); `ANALYSIS_SCHEMA`, `AnalysisOut` (≤5 findings, 1–3 evidence each, `status_hint` pass / needs_review / missing) | prompt + message → `AnalysisResult(proposal, generation, validation_error, attempts)` |
| Providers | `backend/app/providers/base.py`, `ollama.py`, `replay.py`, `__init__.py` | `OllamaProvider.generate_json` (`/api/chat`, `format` = schema, `think` false, 600 s), `healthy` (`/api/tags`); `ReplayProvider`, `RecordingProvider` (key sha256(system + "\n␞\n" + user); markers `[[fault:provider]]`, `[[fault:garbage]]`); `make_provider` | (system, user, schema) → `Generation(text, tokens, latency, model)` |
| Routing | `backend/app/routing/router.py` | `route`: explicit model → `policy[task]` → default; tasks `clause_lookup`, `guidance_comparison` | task → model + reason. Policy is `{}` by default |
| Verifier | `backend/app/verify/spans.py`; `verify_evidence` in `backend/app/runs/service.py`; `backend/app/application/reverify_run.py` | `locate(quote, text, label)` → `Located(start, end, method)`: exact → normalized → casefold → alnum, `bounded()` at every tier, `strip_label` → `unprefixed:<tier>`; `verify_evidence`: cited section first, then the other candidates → `relocated:<tier>`; `reverify_run` replays without writing | model quote → offsets into the stored section text, or `None` |
| Status | `backend/app/runs/status.py` | `decide(status_hint, observed, required, guidance_present, all_verified)` → `Decision(status, source)` with sources `no_evidence`, `computed_days`, `model_hint`; `check_references` → `reference_check` | model fields → finding status |
| Prose | `backend/app/runs/prose.py` | `label_handles` | `sec_N` handles in model prose → `§number` or heading |
| Persistence | `backend/app/models.py`; `backend/app/db.py` | tables documents, sections, guidance, runs, run_stages, findings, evidence_spans, finding_reviews, batches, batch_items, memos; triggers: runs / run_stages / findings / evidence_spans immutable once the run is terminal, sections / documents once any terminal run read them | ORM rows ↔ SQLite |
| Staleness recovery | `backend/app/application/recover_runs.py` | `recover_interrupted_runs`; `stale_after_seconds()` = 4 × 600 + 60 s; runs at startup and on every run read | stuck runs → failed / `internal_error` ("Interrupted…") |
| Runs API and events | `backend/app/api/runs.py` | `create_run` (202 / 200), `get_run`, `get_detail`, `events` (SSE: stored stage rows, then live bus, keep-alive 15 s), `evidence_pack` | `RunIn` → `RunOut` / `RunDetail` / stream / zip |
| Human review | `backend/app/application/review_finding.py`, `backend/app/api/findings.py` | `review_finding` (append-only `finding_reviews`; 409 for withheld or incomplete; repeat 200; `cleared` = undo); `GET /api/findings` (complete runs, not unresolved, ≤ 500) | `ReviewIn` → `FindingReviewOut`; `FindingRecord[]` |
| Memo | `backend/app/application/create_memo.py`, `backend/app/memo/service.py`, `backend/app/api/memos.py` | `create_memo` (409 unless complete; one memo per run, 200 on repeat); DOCX with bookmarks, internal and external links, `docProps/custom.xml` (run id, fingerprint, hashes, model, prompt) plus stored HTML | run id → `MemoOut` (docx / html URLs). No model call |
| Evidence pack | `backend/app/application/evidence_pack.py`, `verify_template.txt` | zip: `README.txt`, `run.json` (ids, hashes, the reading stage's recorded hash, verifier description), `sections.json`, `findings.json`, `verify.py` (stdlib only), `document/{name}` | run id → zip, rebuilt per request. No model call |
| Batch | `backend/app/batch/service.py`, `tasks/*.json`, `cuad_match.py`; `backend/scripts/run_batch.py`; `backend/app/api/batches.py` (read-only) | each (document, field) → ordinary `start_run` / `execute_run`; `value_for` → answered / not_found / withheld / failed; `report`, `list_batches`, CSV | corpus + task → `batches`, `batch_items`, runs |
| Families | `backend/app/families/fingerprint.py`, `service.py`; `labels.json` | headings, defined terms and word 5-gram shingles, Jaccard 0.25 / 0.25 / 0.5, single linkage at 0.15; precision, recall, F1 against labels | stored documents → `FamiliesOut`. No model |
| Goldens | `backend/app/goldens/service.py`; `backend/scripts/run_goldens.py` | `load_set`, `golden_document` (sample by sha prefix under the current reader), `run_for` (by fingerprint), `judge`, `compare`, `report` | recorded runs → verdict per golden, per prompt version |
| Engineering API | `backend/app/api/engineering.py`; `backend/app/application/citation_record.py` | `/api/engineering/experiments` (reads `../ivo-experiments/docs/results.json`), `/citations` (spans by method over answered runs), `/families`, `/goldens` | DB and files → `*Out` |
| Health | `backend/app/api/health.py` | provider `healthy()` | → `HealthOut` (always 200; `ok` carries the state) |

## Frontend

| Responsibility | Files | Principal function / component | Input → output |
|---|---|---|---|
| Shell and state | `src/components/workbench/Workbench.tsx`; `landing/Landing.tsx` | `loadFile`, `loadSample` (the one direct `fetch`, for the static sample), `openDocument`, `ask`, `openRun`, `jumpTo`, `openEvidence`, `navigate` | user actions → API calls, React state, URL |
| API client | `src/lib/api.ts` | `request` (error = API `detail` or "The workbench API at … is not reachable."), `uploadDocument`, `createGuidance`, `createRun`, `followRun` (SSE `/events`; on stream error, poll `/detail` every 3 s), `getRun`, `getRunDetail`, `listFindings`, `reviewFinding`, `createMemo`, `health`, `listDocuments`. ESLint bans `fetch`, `EventSource` and `api.schema` imports outside this file (`eslint.config.mjs`) | typed calls → typed responses |
| Hooks | `src/components/workbench/hooks/useRunFollower.ts`, `useUrlState.ts`, `useGuidance.ts`, `useMemoAction.ts`, `useDropZone.ts`, `useDocWidth.ts` | placeholder run → stages → finished record; `view` / `document` / `run` (written only once finished) in the URL, `finding` read only; guidance POST on "Use", removal browser-only | events → state |
| Types and labels | `src/lib/api.schema.ts` (generated), `src/lib/types.ts` | `STAGE_LABELS`, `REASON_TITLES`, `STATUS_LABELS` (pass → "Within guidance"), `STATUS_SOURCE_LABELS`, `isLocated`, `citationLabel` | schema → display strings |
| Surfaces | `workspace/DocumentPane.tsx`; `assistant/{AssistantPanel, FindingCard, RunOutcome, StageList, EvidenceDrawer}.tsx`; `GuidanceScope.tsx`; `views/FindingsView.tsx`; `views/RunsView.tsx`; `shell/Rail.tsx`, `shell/primitives.tsx` | document with `<mark>` from stored offsets (verified spans only); findings, withheld list, failure states; evidence drawer; review (reviewer name in localStorage); run record with timeline, candidates, raw output, evidence-pack link, batches, families, goldens, citations | persisted run → screen |

## Tests, scripts, browser flows

| Kind | Where | What each holds |
|---|---|---|
| Backend tests | `backend/tests/` (`conftest.py`: temp DB and `FakeProvider` per test; `support.py`: `CONTRACT`, `GUIDANCE`, `FakeProvider` knobs, `FUZZ_SCALE`) | `test_api_flow` full path, paraphrase → unresolved, garbage → failed, SSE, reuse and retry, stale run, review; `test_failure_matrix` provider down and retry, 413 / 422 cases, triggers, prompt change, zip-slip, reference check; `test_api_fuzz` Schemathesis, no 5xx; `test_run_invariants_stateful` Hypothesis machine; `test_spans`, `test_spans_properties`, `test_verify_evidence` verifier; `test_retrieval_and_status`; `test_evidence_pack`; `test_memo_docx`; `test_ingest`, `test_pdf_ingest`, `test_sections`; `test_hashing`; `test_db_columns`; `test_batch`; `test_families`; `test_goldens`; `test_prose`; `test_replay_provider` |
| Scripts | `backend/scripts/` | `run_goldens.py`, `run_batch.py`, `reverify.py`, `eval_retrieval.py` (`--mode`, `--k`, `--ranks`), `load_envelope.py`, `mutate_by_hand.py` (16 mutants), `domain_review_pack.py`, `score_cuad.py`, `cuad_corpus.py`, `cluster_corpus.py`, `export_openapi.py` |
| Browser and unit | `playwright.config.ts` (API 8001 in replay from `e2e/replay.json`, production web build on 3901, data `backend/data/e2e`; `E2E_PROVIDER=record` re-records); `e2e/workbench.spec.ts` (7), `e2e/reliability.spec.ts` (10), `e2e/critical.spec.ts` (3); Vitest `src/**/*.test.tsx` (`useRunFollower`, `useUrlState`) | flows against the real API; hooks |
| Static checks | `backend/.importlinter` (verifier pure, providers blind, layers downward), `eslint.config.mjs`, ruff, mypy strict, prettier, tsc; `.github/dependabot.yml`; the CI workflow lives on branch `ci`, not on `main` | |

## Documents

| File | Records |
|---|---|
| `README.md` | status, commands, release checklist with measured rows, sample attribution, what is not built |
| `DECISIONS.md` | dated decision log |
| `ENGINEERING_CONSTITUTION.md` | ownership map, binding rules, pre-change questions, audits |
| `CLAUDE.md`, `AGENTS.md` | working rules; Next.js docs authority and the Next / FastAPI ownership table |
| `docs/SYSTEM_TRUTH.md` | the system comprehension pass: workflow trace, upload capabilities, garbage matrix, provenance, model versus code, guidance, verification guarantees, scale, the Ivo comparison, adversarial questions, one-page truth |
| `docs/DESIGN.md`, `docs/adr/0001-0004` | problem contract, domain model, invariants; local model behind a provider, citations verified by code, LangGraph only for stateful flow (not implemented), hybrid retrieval |
| `docs/GOLDENS.md`, `docs/RETRIEVAL.md`, `docs/ROUTING.md`, `docs/SKILLOPT.md` | the golden set and recordings; retrieval measured against labels; model routing; prompt optimisation |
| `docs/BATCH.md`, `docs/CUAD.md`, `docs/FAMILIES.md`, `docs/DOMAIN-REVIEW.md` | batch recording; CUAD-30 pre-registration; families against labels; the lawyer pack |
| `docs/FAILURE-ENVELOPE.md`, `docs/SCALE.md`, `docs/PERFORMANCE.md` | cases and the test that holds each; the measured envelope and what each next step must earn; interface measurements |
| `docs/VALIDATION.md`, `docs/REVIEW-INDEPENDENT.md`, `docs/DEMO.md` | the validation audit; the independent review and its fixes; the walkthrough |
