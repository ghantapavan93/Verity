# Engineering Constitution

Adopted 28 September 2026. Binding for every change in this repository. AI-assisted
implementation is allowed and encouraged; architectural ownership stays explicit. The test of
this document is not whether the code looks sophisticated but whether another engineer can
say, for any behaviour, which layer owns it, what invariant it enforces, what happens when it
fails, and why the structure is the way it is.

## The rule under everything

A finding shown to the user may originate from a language model. A claim that its evidence
is verified may only originate from deterministic code.

**The second rule (2026-09-28).** Every sophisticated component must earn its existence with
either a measured failure it fixes or an explicit requirement from the product. Find the hardest
failure, build the smallest serious solution, measure it, move on. A component that cannot point
at its measurement or its requirement is removed.

## Ownership map

| Layer | Owns | Must not own | In this tree |
|---|---|---|---|
| React and Next.js | presentation, interaction, ephemeral UI state, navigation | legal or domain decisions, citation verification, persistence rules, model behaviour | `src/app`, `src/components/workbench/{landing,workspace,assistant,shell,views,hooks}` |
| Typed API client | the frontend/backend contract, error text for the interface | business rules, retries that change meaning | `src/lib/api.ts`, `src/lib/types.ts` (derived from `src/lib/api.schema.ts`, generated from `openapi.json`) |
| FastAPI routers | transport: runtime validation, request and response mapping, status codes, streaming | the workflow itself | `backend/app/api/*`, `backend/app/schemas.py`, `backend/app/errors.py` |
| Application services | use cases: ingest a document, start or reuse a run, project a memo, recover after a restart | HTTP, model calls | `backend/app/application/*`, `backend/app/runs/service.py` (the run's stages) |
| Domain vocabulary and invariants | Document, Section, Guidance, Run, Finding, EvidenceSpan, Memo; stage, status and reason vocabularies; the status decision | rendering, transport | `backend/app/models.py`, `backend/app/runs/status.py` |
| Ingestion | PDF, DOCX (the accepted view: tracked insertions kept, deletions and hidden text left out and counted) and TXT to canonical sections | model calls, persistence | `backend/app/ingest/*` |
| Retrieval | candidate sections for a question | deciding truth | `backend/app/retrieval/*` |
| Analysis and prompts | building the message, calling the provider, validating the shape of what comes back | deciding whether a quote exists, deciding status | `backend/app/analysis/*`, versioned prompt files under `analysis/prompts/` |
| Model provider | communication with one model runtime behind `ModelProvider` | database access, business rules | `backend/app/providers/*` |
| Verification | locating a quoted passage in the stored text, or refusing | interpretation | `backend/app/verify/spans.py` |
| Identity | every hash and fingerprint | anything else | `backend/app/hashing.py` |
| Persistence | tables, columns, indexes, constraints, additive migration | model calls | `backend/app/models.py`, `backend/app/db.py` |
| Memo | a projection of a complete run's verified findings, HTML and a Word document whose properties, bookmarks and links carry the run | a second model call | `backend/app/memo/*`, `backend/app/application/create_memo.py` |
| Evidence pack | the run's record, bytes, sections and spans in one zip with a dependency-free checker | asserting anything the checker cannot re-check | `backend/app/application/evidence_pack.py`, `verify_template.txt` |
| Golden set | the fixed questions, the verdict rule, the comparison between prompt versions and models | model calls (the runner goes through `start_run`), the runtime path | `backend/app/goldens/*`, `backend/scripts/run_goldens.py`, `docs/GOLDENS.md` |
| Human review | a person's decision on a finding, appended and reversible | changing the finding or its run | `backend/app/models.py` (`FindingReview`), `backend/app/application/review_finding.py` |
| Model routing | which model answers which task, from a policy justified by golden measurements | guessing at difficulty | `backend/app/routing/*`, `docs/ROUTING.md` |
| Batch extraction | the same run over a corpus with bounded concurrency, and the numbers computed from the records | a second way of deciding a value | `backend/app/batch/*`, `backend/scripts/run_batch.py`, `docs/BATCH.md` |
| Document families | structural fingerprints, similarity, clustering and their evaluation against labels | model calls, claims beyond the measured corpus | `backend/app/families/*`, `backend/scripts/cluster_corpus.py`, `docs/FAMILIES.md` |
| Replay | verifying a recorded run again with the current verifier, without a model call | changing the run | `backend/app/application/reverify_run.py`, `backend/scripts/reverify.py` |
| Engineering records | the golden set's verdicts and the pre-registered experiments that preceded the product | the production workflow | `backend/app/api/engineering.py`, reading the run records and `ivo-experiments/docs/results.json` |

## Rules

1. Before adding code, name the layer that owns the behaviour. If two layers could own it,
   pick the one that can be tested without the others.
2. The frontend renders truth; it does not invent it. `span.verified`, offsets, statuses and
   reasons arrive from the API. No component decides whether evidence is valid, whether a
   finding is supported, which retrieval to use, or whether a result should be persisted.
3. Routes stay thin: validate, call one application service, map the result. A route that
   parses, retrieves, prompts, verifies and writes is the prototype shape this document exists
   to prevent.
4. Probabilistic models propose: interpretations, candidate findings, candidate passages,
   explanations. Deterministic code owns identity, source verification, hashes, permissions,
   state transitions, persistence and reproducibility.
5. Model output is untrusted input until runtime validation and evidence verification succeed.
   A quote the verifier cannot locate is never shown as evidence; the finding is withheld and
   the run says so.
6. Never encode a software invariant only as a prompt instruction when code can enforce it.
   Prompts carry what genuinely needs interpretation. The JSON schema and the verifier carry
   the rest.
7. One canonical implementation each for hashing, text normalisation, citation location and
   status decisions. No `utils`, `helpers` or `misc` modules.
8. The primary runtime path never falls back to mock data. Fixtures and fake providers live in
   tests and are unmistakably test-only. When the API or the model is unavailable, the
   interface says so.
9. Failures are typed by owner: unsupported file, not found, conflict, provider error,
   invalid structured output, unverified citations, insufficient evidence, interrupted run.
   Each has one response shape and one wording on screen.
10. Every run persists what reproducing it needs: document identity and hash, guidance hash,
    provider, model, decoding options, prompt version and hash, the sections handed to the
    model, the raw structured output, each quote's location method and offsets, stage
    timestamps, the outcome and its reason.
11. Completed runs are immutable history. A changed prompt, model or document creates a new
    run. Historical runs keep their own prompt version and hash.
12. Repeating a request must not repeat a model call. Identical inputs return the existing
    running or completed run; the database enforces this with a unique index over non-failed
    runs; failed runs stay retryable.
13. The database holds the invariants it can: foreign keys, CHECK constraints on stage, status
    and reason vocabularies, the fingerprint index. Where SQLite cannot add a constraint to an
    existing file without rebuilding it, the constraint applies to new files and the same
    vocabulary is enforced in code, and this document says so.
14. Every public API boundary uses runtime validation and typed contracts. The backend schema is
    the source of truth; the frontend's types are generated from it, never retyped.
15. Dependencies are earned by a demonstrated requirement. Postgres, pgvector, LangGraph,
    queues, caches, agents and observability stacks are not added for résumé value. Structured
    request and stage logs with ids and durations are enough until they are not.
16. Tests target boundaries, not only helpers: the verifier refusing a fabricated quote, the
    route contract on bad input, the full path with a fake provider, idempotent creation,
    recovery after a restart. Domain behaviour is testable without rendering the interface.
17. Visual sophistication never justifies coupling. Motion, glass and interaction stay in
    presentation code. The visual system is frozen; there is no theme switching.

## Before every meaningful change

1. Which layer owns this?
2. What invariant does it enforce?
3. What happens when it fails?
4. Can it be tested without the interface, the model or the database where appropriate?
5. Is this abstraction required by the problem, or does it merely look sophisticated?

If the answer to the fifth is the latter, do not add it.

## Adopted with known violations

The audit below was written before the cleanup that removed the violations, and is kept as
written. Credibility comes from the record, not from a pristine document.

| Rule | State at adoption | Removed by |
|---|---|---|
| Frontend renders truth | held | — |
| Model output untrusted until verified; fabricated quotes withheld | held; test existed | — |
| No mocks on the runtime path | held since the sample data was deleted | — |
| One normaliser, one status decision | held | — |
| Prompts carry interpretation only | held | — |
| Runs immutable and reproducible | held | — |
| Earned dependencies | held | — |
| Composition-only workbench component | **violated**: one 1,300-line component owned upload, SSE following, URL state, guidance, run state, drawer and memo | split into `landing/`, `workspace/`, `assistant/`, `shell/` and `hooks/`; the coordinator is 450 lines of state and layout |
| Thin routes | **violated**: memo projection, upload persistence and run creation lived in routes | `application/ingest_document.py`, `application/start_run.py`, `application/create_memo.py`; typed errors mapped in one handler |
| One hashing implementation | **violated**: four `hashlib` call sites | `app/hashing.py`; a test fails if any other module imports hashlib |
| Idempotent run creation | **missing**: two identical requests made two model runs | run fingerprint over document, guidance, question, prompt hash and options; partial unique index over non-failed runs; `reused` on the response |
| Database-held vocabularies | **partial**: foreign keys only | CHECK constraints on stage, status and reason for new files; vocabularies shared by models, schema and code, with a test that they agree |
| Interrupted runs | **missing**: a run in flight at restart stayed "checking" forever and blocked its fingerprint | `application/recover_runs.py` at startup marks them failed with the reason |
| Structured logging | **missing** | request id, method, path, status and duration per request; run id, document id, stage and duration per stage |
| Generated API types | **missing**: frontend types were retyped by hand | `openapi.json` exported from the app, `src/lib/api.schema.ts` generated, `types.ts` derives from it; Literal unions on the schema |

A second audit followed the external review of 2026-09-28 (`ivo-research/KIMI-WORKBENCH-REVIEW-STATUS.md`):

| Rule | State at the second audit | Removed by |
|---|---|---|
| Ingestion reads what the reader sees | **violated**: python-docx `paragraph.text` walks only a paragraph's direct runs, so a tracked insertion and its deletion both vanished ("continues for  months.") and hidden text was read | `ingest/readers.py` reads the accepted view at the XML level; `parser_version`, `tracked_changes` and `hidden_runs` are recorded per document and the header says what was left out |
| Vocabularies typed once | **partial**: Literal types lived in the API schema, the ORM columns were `str`, and every mapping cast implicitly | `RunStageName`, `FindingStatusName`, `RunReasonName` declared in `models.py`; ORM, schema, run service and status decision share them; a test asserts the schema carries the same types |
| Static checks on the backend | **missing**: no linter, no type checker | `pyproject.toml`: ruff (style, imports, annotations, bugbear, pytest style) and mypy `--strict` over app, scripts and tests, all clean |
| Frontend tests | **missing** | Vitest with Testing Library: the run follower and the URL state, the two behaviours no backend test can see; then seven Playwright flows against the production build with the model's answers replayed (`e2e/`, 2026-09-28) |
| Continuous checks | **missing**: the type contract held only when someone remembered two commands | `.github/workflows/checks.yml`: backend, interface, and a job that regenerates `openapi.json` and `api.schema.ts` and fails on any difference |
| Measured prompt changes | **missing**: `answer-v2` replaced `answer-v1` on judgement | the golden set: twelve questions judged by code per prompt version, a comparison on the Runs surface, and the kill rule in `docs/GOLDENS.md` |

A third audit followed the role-specific review of 2026-09-28 (`DECISIONS.md`, P0 to P6). Each
row names the measurement or requirement that earned the component, as the second rule demands:

| Component | Earned by | State |
|---|---|---|
| Verifier tiers (alnum, label stripping) | a census of withheld quotes: most were text in the document missed by strictness; replay showed 5 gained, 0 lost | kept; no ratio tier because 0.994 hid a changed digit |
| Human review | the product requirement that a person adjudicates what the model proposed and code verified | kept; append-only, reversible |
| Immutability triggers | the requirement that a finished run is a record; found a real defect (startup recovery swept another process's live run) | kept; recovery is now by staleness |
| Stage records with hashes and attempts | the requirement that failures be inspectable without inference | kept |
| Provider retry, malformed-file refusals, memo idempotency | the failure matrix, one test per row | kept |
| Golden set of 44 in eleven categories, regression report | the A1 lesson: a prompt change is judged on held-out questions or not at all | kept |
| Model in the run's identity, router with an empty policy | the requirement to compare models like prompts; the policy waits for a measurement | kept, policy empty |
| Batch extraction | the requirement to show the pipeline over a corpus, with numbers | kept; twenty documents, stated as twenty |
| Document families | measured on twenty labeled documents: template families found, suites not; the next signal was tested in the text and rejected | kept as measured; suite detection not built |
| Virtualised document view | measured on 2,001 sections: not needed | not built; threshold recorded |

Commit hashes for the removals are recorded by the person who commits; nothing in this
repository is committed by the assistant.

## Deliberately not done

- No repository pattern, no `domain/` and `persistence/` folder taxonomy: the modules already
  have one owner each, and renaming them would be churn.
- No LangGraph: the run is a typed service with persisted stages. It is added when the flow
  needs resume or per-topic fan-out, not before.
- No Postgres or pgvector: SQLite and BM25 carry the slice; a measurement on real questions
  decides otherwise.
- No CHECK constraints retrofitted onto existing SQLite files: that needs a table rebuild for
  appearance's sake. New files get them; code enforces the same lists everywhere.
- No font-size heading detection for PDFs: pypdf's visitor did not report sizes on printed
  files; a character-metrics library would be a new dependency for one feature.
- Browser tests came on an explicit requirement, not a broken release (the second way under
  rule 2): seven Playwright flows in `e2e/`, with the model's answers recorded once and replayed
  so they run in CI without a GPU.
- No pyright alongside mypy: one type checker, and mypy needs no Node in the backend job.
- No guidance goldens yet: the status decision with guidance rests on day-count parsing the set
  does not exercise; goldens with guidance are added when a change to that decision needs
  measuring.
- No style-resolved hidden text: the reader drops runs marked hidden directly; a character style
  that hides text is not resolved. Recorded as an open question in `docs/DESIGN.md`.
- No virtualised document view: measured on 2,001 sections, not needed; the threshold that would
  earn it is in `docs/PERFORMANCE.md`.
- No MinHash for document families: exact Jaccard over twenty documents is cheap and exact; the
  sketch is the step for a corpus whose shingle sets do not fit.
- No suite detection for document families: structure does not carry it (measured), and the
  next signal was tested in the text and rejected; publisher metadata would be next.
- No routing policy until a smaller model is measured on the golden set per task; the router
  exists so that the measurement has somewhere to land, and says so in every run's record.
- No frontier-model run: the $0 rule; the router and the golden set are how one would be
  compared if it were ever made.
