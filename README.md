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

The same commands run locally and in CI (`.github/workflows/checks.yml`). CI also fails when
`openapi.json` or `src/lib/api.schema.ts` differ from what the API generates, so the interface
cannot drift from the backend.

```bash
cd backend
.venv/Scripts/python -m ruff format --check . && .venv/Scripts/python -m ruff check .   # style and lint, pyproject.toml
.venv/Scripts/python -m mypy                                                            # strict, app + scripts + tests
.venv/Scripts/python -m pytest -q                                                       # 103 tests, no model needed; six are Hypothesis properties of the verifier

npm run typecheck && npm run lint && npm run format:check   # tsc strict, eslint, prettier
npm test                                                    # Vitest: the run follower and the URL state, 7 tests
npm run e2e                                                 # Playwright: seven browser flows, real API, the model's recorded answers replayed
```

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
.venv/Scripts/python scripts/mutate_by_hand.py                                    # nine hand mutants of the evidence boundary; each must be killed
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
| Repeated request | same inputs return the existing run (`reused: true`); a failed run is retryable; a run interrupted by a restart is failed with the reason |
| Golden set | 44 questions on the sample in eleven categories (four with guidance and an expected status, two adversarial; the false-premise one fails today and says so in `docs/GOLDENS.md`), judged by code under each prompt version and model; previous answer / new answer / what changed / better or worse on the Runs surface; `run_goldens.py --report`; the kill rule is `docs/GOLDENS.md` |
| Verifier | exact → normalized → casefold → letters-and-digits, plus section-label stripping, each tier named on the span; no similarity ratio (a 0.994 match hid a changed digit); `scripts/reverify.py` replays verification over recorded runs without a model call |
| Citation record | counted from every answered run, not sampled (`GET /api/engineering/citations`, shown under Runs); at 2026-09-28 across 243 runs: 425 of 469 quoted passages verified (343 exact, 46 normalized, 5 casefold, 6 letters-and-digits, 15 after label stripping, 10 relocated to another candidate section) and 42 of 384 findings withheld |
| Human review | a finding can be confirmed or dismissed by a named person, undone, and the state survives reload; append-only, idempotent; on the drawer and in the memo; Documents' "reviewed" comes from it |
| Immutable records | the database refuses any update or delete on a finished run, its stages, findings and spans (SQLite triggers); reviews and memos are separate rows |
| Failure matrix | provider unavailable, transport failure retried once, malformed and empty files, oversized upload, a DOCX that unpacks past 256 MB and a PDF over 2,000 pages (both 413 before parsing), memo asked twice, prompt change, reader version, stale runs: one test per row in `backend/tests/test_failure_matrix.py` |
| Stage record | every stage row has start, end, duration, status, attempt, input and output hashes and an error code; a run cannot stay in flight longer than the model timeout plus a minute |
| Model routing | a run carries its task and why its model answered it; the policy is empty until a smaller model is measured on the golden set (`docs/ROUTING.md`) |
| Batch extraction | a field task over a corpus of 20 licensed public contracts, bounded concurrency, every value with its citation; first recording: 47 of 60 values answered with a verified citation in 57 min on one laptop GPU, 0 failures, 135 of 146 quotes verified (`docs/BATCH.md`) |
| Document families | structural fingerprints, exact Jaccard, single-linkage families, pairwise precision/recall/F1 against hand labels with the threshold sweep; finds the template family, not the suites (`docs/FAMILIES.md`) |
| Interface performance | 2,001 sections on screen 1.6 s after navigation in the production build, citation jumps within two frames; no virtualisation, and the number that would earn it is written down (`docs/PERFORMANCE.md`) |
| Browser flows | seven Playwright flows against the production build and the real API: landing, sample to sections, question to a verified citation whose highlight is the quote's own text, the withheld question, reload from the URL, Findings and Runs with the evidence pack, the memo; the model's answers recorded once and replayed; traces kept on failure; a CI job |
| Checks | backend 103 tests (six Hypothesis properties), ruff, mypy strict; interface 7 unit tests and 7 browser flows, tsc, eslint, prettier, production build; results page 23; CI runs all of it and fails on generated-type drift |

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
