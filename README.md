# Contract Workbench

Review contracts against the guidance your team actually uses. Upload a contract and a
lawyer's instructions, ask a question or run a review, and get findings whose evidence opens
the exact clause. Runs locally at $0 with Qwen3 8B through Ollama; every citation is verified
by code before it is shown.

**Status: the vertical slice works end to end with the local model, and the three surfaces
exist.** Upload a contract (PDF, DOCX, TXT) → it is parsed into numbered sections → optionally
paste legal guidance → ask a question → the API retrieves candidate sections, asks Qwen3 8B for a
structured answer under a fixed JSON schema, verifies every quoted passage verbatim against the
stored text, decides the status in code, and streams the stages → click a citation to highlight
the exact passage → inspect the evidence → generate a review memo (HTML and DOCX). Nothing on
that path is mocked. **Findings** lists every verified finding and opens its document at the
passage. **Runs** shows each run's record (document and guidance hashes, prompt version and hash,
decoding options, tokens, latency, stage timeline, the sections handed to the model, how each
quote was located, the raw output), the **golden set** (forty-four fixed questions about the sample in
eleven categories, judged by code under every prompt version and model, with the comparison between
versions; the rule for keeping a prompt change is in `docs/GOLDENS.md`) and, beneath those, the three pre-registered
experiments that were killed before this product was built, read from the `ivo-experiments`
results file. DOCX files are read as Word shows them with all changes accepted: tracked
insertions kept, deletions and hidden text left out, and the document header says how many of
each the file carried. A person can confirm or dismiss any finding and the decision is kept as a
record; a finished run cannot be changed, and the database enforces it; every run has a
downloadable evidence pack that checks itself with nothing but Python. The same pipeline runs as
a batch over a corpus of twenty public contracts with its throughput and failure numbers
recorded, and a structural clustering of that corpus is measured against hand labels. Each of
these is described, with its measurement, under `docs/`.

```bash
# API (Python 3.13; Ollama running with qwen3:8b pulled)
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.lock -r requirements-dev.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8000
.venv/Scripts/python scripts/export_openapi.py   # after a schema change: writes openapi.json
.venv/Scripts/python scripts/run_goldens.py      # records the golden set against the live model (docs/GOLDENS.md)
# Optional: point Runs at the experiments record (defaults to ../ivo-experiments/docs/results.json)
# set WORKBENCH_EXPERIMENTS_RESULTS=C:\path\to\ivo-experiments\docs\results.json

# Interface
npm install
npm run dev -- -p 3900                     # http://localhost:3900
npm run api:types                          # regenerates src/lib/api.schema.ts from openapi.json
```

## Checks

The same commands are wired into `.github/workflows/checks.yml`, which also fails when
`openapi.json` or `src/lib/api.schema.ts` differ from what the API generates, so the interface
cannot drift from the backend. That workflow sits on branch `ci` and has not run yet: pushing it
needs the `workflow` scope on the GitHub token, which has not been granted. Until it lands, every
check below runs locally, by hand, before a push.

```bash
cd backend
.venv/Scripts/python -m ruff format --check . && .venv/Scripts/python -m ruff check .   # style and lint, pyproject.toml
.venv/Scripts/python -m mypy                                                            # strict, app + scripts + tests
.venv/Scripts/lint-imports                                                              # the three import contracts: verifier pure, providers blind, layers downward (.importlinter)
.venv/Scripts/python -m pytest -q                                                       # 277 tests, no model needed; seven Hypothesis properties of the verifier, one stateful property of the run record, one Schemathesis fuzz of every route (WORKBENCH_FUZZ_SCALE=20 for the deep pass)

npm run typecheck && npm run lint && npm run format:check   # tsc strict, eslint, prettier
npm test                                                    # Vitest: the run follower, the URL state and the explanation, 13 tests
npx playwright install chromium                             # once per machine: the browser the flows run in; the npm package alone does not bring it
npm run e2e                                                 # Playwright: twenty browser flows, real API, the model's recorded answers replayed, faults by marker
```

A fresh clone of `main` at `c4dd415` was set up from this file alone on 2026-09-30 and every command
above passed: the backend install and checks, 266 tests, the API on port 8000, the generated types with
no drift, the interface checks, 10 unit tests, 20 browser flows. One step failed once, and it is a note
about the environment, not a defect of the application: on Windows, `python -m venv .venv` failed at
`ensurepip` when the clone sat under a path with a short-name component (`C:\Users\NAME~1\AppData\…`);
the same clone under `C:\Temp` set up cleanly. Clone to a plain path.

The browser flows run the production build against the API, each on its own port and data
directory. The model's answers were recorded once from Qwen3 8B (`e2e/replay.json`, written by
`WORKBENCH_PROVIDER=record`) and are replayed byte for byte, so CI runs the same flows with no
GPU and no call to Ollama; a changed prompt or retrieval makes the replay refuse rather than
answer differently, and re-recording is one command. Traces and screenshots are kept for failures only.

The recordings that back the numbers in this file are made from the command line and read
back by the Runs surface:

```bash
cd backend
.venv/Scripts/python scripts/run_goldens.py --prompt answer-v1 --prompt answer-v2   # the golden set under each prompt (docs/GOLDENS.md)
.venv/Scripts/python scripts/run_goldens.py --report                                # improvements, regressions, unchanged, latency delta
.venv/Scripts/python scripts/reverify.py --withheld                                 # replay verification over recorded runs, no model call
.venv/Scripts/python scripts/run_batch.py --corpus <dir> --task core-fields         # field extraction over a corpus (docs/BATCH.md)
.venv/Scripts/python scripts/cluster_corpus.py --corpus <dir>                       # document families against the labels (docs/FAMILIES.md)
.venv/Scripts/python scripts/mutate_by_hand.py                                    # twenty-four hand mutants of the evidence boundary; each must be killed
.venv/Scripts/python scripts/data_audit.py --write                                # every agreement the repository touched, by sha256, with source, licence, role and the measurements on it (docs/DATA-EVIDENCE.md)
```

## How the code is organised

`ENGINEERING_CONSTITUTION.md` is the binding statement of where responsibility lives, with the
audit of what it found when it was adopted. In short: React renders what the API decided
(`src/components/workbench/{landing,workspace,assistant,shell,views,hooks}`, coordinated by
`Workbench.tsx`); a typed client (`src/lib/api.ts`) speaks to thin FastAPI routers
(`backend/app/api`); routes call use cases (`backend/app/application`); the run's stages live
in `backend/app/runs/service.py`; ingestion, retrieval, analysis, verification, memo and the
model provider are separate modules; identity is computed in one place (`backend/app/hashing.py`);
the golden set and its judge live in `backend/app/goldens`, model routing in `backend/app/routing`,
batch extraction in `backend/app/batch`, document families in `backend/app/families`; the
frontend's types are generated from the API's OpenAPI document. Runs are idempotent on their
inputs (document bytes, guidance, question, prompt hash, model and options) and immutable once
finished, enforced by the database.
The stage, status and reason vocabularies are declared once as types in `backend/app/models.py`
and used by the ORM, the API schema, the CHECK constraints and the run service.
Agents start at `AGENTS.md` and `CLAUDE.md`; library documentation reaches them through the Context7
MCP server declared in `.mcp.json`.

The bundled sample (`public/samples/cloud-service-agreement.docx`) is Common Paper's Cloud
Service Agreement, © Common Paper, CC BY 4.0, unmodified. It is a real standard agreement;
the interface says so when it is loaded.

## Plan

- `docs/DESIGN.md`: problem contract, domain model, invariants, architecture, the three
  surfaces, failure semantics, the first slice, what is not built.
- `docs/adr/`: local model behind a provider interface; citations verified by code; LangGraph
  only for the stateful flow; hybrid retrieval.
- `DECISIONS.md`: each decision as it was taken.

The three killed experiments that shaped this product live in the `ivo-experiments`
repository and appear under this product's Runs surface as records.

## Release checklist, as it stands

| Path | State |
|---|---|
| Upload DOCX | works (Common Paper sample: 11 pages, 123 sections); read as the accepted view, and the header says how many tracked changes and hidden runs were left out |
| Upload PDF | works as text; headings need numbering or capitals, otherwise the workspace says sections are approximate |
| Save guidance, ask, stream stages | work; stages carry the API's own counts and timing |
| Finding, citation verification, citation navigation | work; every shown quote was located by code, offsets stored |
| Evidence drawer, Findings → document, Runs, run record | work |
| Memo HTML and DOCX | work, from stored findings, no second model call; the Word file carries the run in its properties (core and custom), links each citation to a bookmarked sources table, and links each source back to the run and finding in the workbench; opens in Word without repair |
| Evidence pack | one zip per run: original bytes, canonical sections, the run record with hashes, every located span, and a dependency-free `verify.py` that re-checks all of it on any machine; a tampered pack fails |
| No matching evidence | `No supporting passage found`, with the sections searched |
| Invalid model output | `Analysis couldn't complete` with Try again; the run is `failed`, not a verdict |
| Citation mismatch | finding withheld; the run says so and keeps the raw output |
| Reload a completed run | works: the URL carries `document`, `run` and `view` |
| ~1280 px window | the design width |
| Narrow windows | lists work; the split workspace shows a plain note instead of cramping |
| Secrets | none in the tree; `.env*`, `data/` and `.venv/` are ignored |
| Sample licence | Common Paper CSA v2.1, CC BY 4.0; the bundled file's SHA-256 matches the corpus manifest |
| Repeated request | the same bytes are one document and a run has one memo, by unique index, whatever two concurrent first requests do; same inputs return the existing run (`reused: true`); a failed run is retryable; a run interrupted by a restart is failed with the reason; an open event stream to it ends within a heartbeat, whichever process ended it; a worker that finds its run already ended keeps that record and does not raise |
| Golden set | 44 questions on the sample in eleven categories (four with guidance and an expected status, two adversarial; the false-premise one fails today and says so in `docs/GOLDENS.md`); 37 of 44 under the current reader (Recording 5: answer-v3 at k = 6 also 37, one gain and one regression; answer-v2 at k = 10 38, three gains and two regressions with latency over the rule; neither adopted), judged by code under each prompt version and model; previous answer / new answer / what changed / better or worse on the Runs surface; `run_goldens.py --report`; the kill rule is `docs/GOLDENS.md` |
| Verifier | exact → normalized → casefold → typed tokens (v5: numbers as values with their precision, words at word boundaries, punctuation nothing; "$1,500" is never "$15.00"), the search bounded to the 5,000 characters the model was shown, each span carrying how many places its quote occurs; section-label stripping; no similarity ratio (a 0.994 match hid a changed digit); `scripts/reverify.py` replays verification over recorded runs without a model call; v4 (2026-09-29) never cuts a bare number off a quote and keeps decimal points, replayed over 847 recorded spans with nothing changed |
| Citation record | counted from every answered run, not sampled (`GET /api/engineering/citations`, shown under Runs); at 2026-09-28 across 243 runs: 425 of 469 quoted passages verified (343 exact, 46 normalized, 5 casefold, 6 letters-and-digits, 15 after label stripping, 10 relocated to another candidate section) and 42 of 384 findings withheld |
| Human review | a finding can be confirmed or dismissed by a named person, undone, and the state survives reload; append-only, idempotent; on the drawer and in the memo; Documents' "reviewed" comes from it |
| Reference check | a pass whose conclusion names a section the document does not have becomes needs review, by code, with the source shown; over the 398 recorded asserting findings it fires on 4, all wrong references, and never on the 25 that write a section's id as its number (`docs/GOLDENS.md`) |
| Status wording | a pass reads "Within guidance" only when the run had guidance, "Answered" otherwise, in the chip, the tables and the memo heading; the run and the findings list carry `hasGuidance` |
| Position check | the notice period is parsed by code from the verified quote and the requirement from the guidance (units, Decimal, "twenty-one (30) days" is ambiguous, a month is not thirty days); the model's numbers only choose among the quote's; a count it states that the evidence does not carry is needs review by code with the source shown, and a computed status carries its sentence; ceiling phrases ("no longer than", "up to", "not to exceed", …) and parenthesised or working-day counts parse; over 595 recorded findings none of the nine computed statuses disagreed with its quote |
| Model input | the exact system and user messages of any run are rebuilt from the record and hash to what the checking stage wrote (`scripts/reconstruct_inputs.py`: 458 of 458 runs since the message format was fixed; the 57 before it are reported, not repaired); prompt files are frozen by `prompts/manifest.json` |
| Why this answer | one read-only projection of the record (`GET /api/runs/{id}/explanation`), rendered in the evidence drawer per finding and on the Runs record: what was read (reader, coverage), what retrieval chose (rank, the ContextSlice of each candidate, the characters that never reached the model), what the model saw (the input rebuilt and hashed against the checking stage, or the reason it could not be), what the model proposed (its own words and hint, parsed from the stored output by ordinal, or "not reconstructable"), what code established (each SourceMatch: cited section, located section, method, occurrences, offsets, inside the model-visible slice or not) and the status as recorded with its source and sentence; the interface decides nothing; the Phase 1 run (`docs/DEMO-PROOF.md`) is the acceptance case, as a unit test against its recorded explanation |
| Stream and refresh | stage events carry ids and a reconnect is replayed from `Last-Event-ID`; the run id is in the URL as soon as the run exists, and the browser flow refreshes while the model is still answering and reattaches to the same run |
| Not read, said so | a DOCX reading records what it did with each of seventeen parts (headers, footers, footnotes, comments, content controls, fields, numbering, …); the paper says "Not read by this reading: …", the evidence pack carries it; census of the 36 licensed contracts: 32 footers and 12 headers with real text are not read today, and the parser tournament (`docs/PARSER-COMPARISON.md`) decides whether a reader that reads them earns its place: Docling did not (256 of 292 exact quotes kept against the reader's 292, thirty to four hundred times the time) |
| Admission to the model | calls in flight bounded per process, a person's questions served four to one over a corpus job, every call's queue wait on its stage row; measured against the live model: the person's waits halved (median 103 s to 46 s) for six percent on the batch's total (`docs/SCALE.md`) |
| Hostile files | an entity bomb and three-thousand-deep nesting are refused as unreadable packages in under a fiftieth of a second; twenty thousand members are read in half a second; an external relationship makes no network call; each reaches the API as a 422 with the reason (`tests/test_hostile_packages.py`, `docs/FAILURE-ENVELOPE.md`) |
| Memo revisions | a memo records the review state it describes; a later review earns a new memo, the earlier one is kept, and the Assistant says when a memo predates a review |
| Immutable records | the database refuses any update or delete on a finished run, its stages, findings and spans (SQLite triggers); reviews and memos are separate rows |
| Failure matrix | provider unavailable, transport failure retried once, malformed and empty files, oversized upload, a DOCX that unpacks past 256 MB and a PDF over 2,000 pages (both 413 before parsing), memo asked twice, prompt change, reader version: one test per row in `backend/tests/test_failure_matrix.py`; stale runs in `backend/tests/test_api_flow.py` |
| Stage record | every stage row has start, end, duration, status, attempt, input and output hashes and an error code; a run that has made no progress for four model timeouts plus a minute (the longest legitimate run: two validation rounds, each with one transport retry) is failed on the next read |
| Model routing | a run carries its task and why its model answered it; the policy is empty until a smaller model is measured on the golden set (`docs/ROUTING.md`) |
| Batch extraction | a field task over a corpus of 20 licensed public contracts, bounded concurrency, every value with its citation; first recording: 47 of 60 values answered with a verified citation in 57 min on one laptop GPU, 0 failures, 135 of 146 quotes verified (`docs/BATCH.md`) |
| Document families | structural fingerprints, exact Jaccard, single-linkage families, pairwise precision/recall/F1 against hand labels with the threshold sweep; finds the template family, not the suites (`docs/FAMILIES.md`) |
| Interface performance | 2,001 sections on screen 1.6 s after navigation in the production build, citation jumps within two frames; no virtualisation, and the number that would earn it is written down (`docs/PERFORMANCE.md`) |
| Lighthouse | landing 100/100/100/100 and workspace with a run 99/100/100/100 on the production build, LCP 0.7 s and 1.0 s; the one real finding, uncompressed API JSON, fixed with gzip and a test (`docs/PERFORMANCE.md`) |
| Dependencies | every pin moves through Dependabot, weekly, grouped per ecosystem (`.github/dependabot.yml`); CodeQL code scanning is on the CI branch, pending the workflow scope |
| SkillOpt | Microsoft's skill optimizer run against the production answer path, the seed prompt as the skill, CUAD contracts disjoint from CUAD-30 as data, the goldens as the untouched judge: six steps, twelve analyst calls, zero edits proposed, answer-v2 stands; why, and what would change it, in `docs/SKILLOPT.md` |
| Retrieval | BM25 scored against labels, 164 CUAD cases with experts' spans and 38 goldens: Recall@6 0.85 and 0.92; a hybrid with a local embedding model measured at 0.95 and 0.97 and built behind a setting; on the 44 goldens BM25 37, hybrid 40 with one regression, so BM25 stays the default by the rule (`docs/RETRIEVAL.md`) |
| Failure envelope | one table of cases, expected, observed and the test that holds each; writing it found two 422s that were a 500 and a wrong reason (`docs/FAILURE-ENVELOPE.md`) |
| Scale | what was measured and what each next step would have to earn; nothing says millions (`docs/SCALE.md`) |
| Data behind the claims | every agreement the repository has touched, by SHA-256, with its source, licence, role (evaluation, fixture, runtime) and the measurements made on it, and the denominator of each measured set kept apart; produced by `scripts/data_audit.py` from the manifests, the store and the records outside git, never by copying a result (`docs/DATA-EVIDENCE.md`) |
| Domain review | ten findings packed for a practising lawyer with five questions and room for disagreement, built from the record by document, model, prompt and retrieval (`backend/scripts/domain_review_pack.py`, `docs/DOMAIN-REVIEW.md`); not yet reviewed |
| Independent review | a read-only reviewer told to assume the tree was AI-generated and find where the story becomes fake: seven findings, all true, recorded as delivered before any fix, with what changed after (`docs/REVIEW-INDEPENDENT.md`) |
| Validation | what is proven, partial, missing and not justified, capability by capability, with the validator that holds each claim (`docs/VALIDATION.md`) |
| Browser flows | twenty Playwright flows against the production build and the real API: the seven happy paths (landing, sample, question to a verified citation whose highlight is the quote's own text, the withheld question, reload, Findings and Runs with the evidence pack, the memo) and ten reliability flows: a provider outage and non-schema output end as failed runs with the reason and never a verdict, a dropped event stream still finishes through polling, the same question twice returns the same run, the document travels gzipped, the memo names its run, a confirmed finding survives a reload, the URL alone restores a run, Escape closes the drawer, a narrow window gets the plain note, and axe finds no serious or critical WCAG 2.1 AA violation on the landing, the workspace or the open drawer; the model's answers recorded once and replayed, faults injected by markers the replay provider honours; and three flows the validation brief named: a review against guidance that ends in a finding with a status and the guidance in the drawer, a malformed upload refused with the reason and nothing opened, a refresh once the run is in the URL brings it back (the run id reaches the URL only when the run has finished, so this reloads after completion; a true mid-run refresh is unproven); traces kept on failure |
| Checks | backend 277 tests (eight Hypothesis properties, one Schemathesis fuzz), ruff, mypy strict, import-linter, twenty-four hand mutants killed; interface 13 unit tests and 20 browser flows, tsc, eslint, prettier, production build; results page 23; the CI workflow runs all of it and fails on generated-type drift, and waits on branch `ci` for the token's workflow scope |

## What is deliberately not here yet

SQLite and BM25 carry the slice. PostgreSQL, pgvector and LangGraph are named in the design
and the ADRs as the intended shape, and each is added when a measurement on real runs shows
the current choice failing (retrieval missing the governing clause; a flow that needs resume or
per-topic fan-out). Every quoted passage is still located by code, whatever the retrieval.
No frontier-model run (the $0 rule), no virtualised document view (measured:
not needed below about 5,000 sections), no MinHash (exact Jaccard is cheap at twenty
documents), no suite detection for contract families (structure does not carry it; publisher
metadata would), no routing policy until a smaller model is measured, and DOCX text hidden
through a character style (rather than directly on the run) is still read. Every one of these
has the measurement or the requirement that would change it written next to it.
