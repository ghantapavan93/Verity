# Validation, 2026-09-29

A phase with no product work: what the repository claims, which validator holds each claim, what
is only partly held, what is missing, and what is deliberately not built. The validators ran in a
fixed order, findings were recorded before anything was fixed, and the only code changes of the
phase are fixes to defects the validators found.

Marks: **proven** means a deterministic check in the tree holds the claim and ran today;
**partial** means part of the claim is held and the rest is named; **missing** means the claim
is made or wanted and nothing holds it yet; **not justified** means the component is absent on
purpose, with the measurement that would earn it written down.

## Audit

| Capability | Mark | Held by | What is not held |
|---|---|---|---|
| Reading DOCX, PDF and text into numbered sections | proven | the reader tests; the failure matrix (malformed, empty, oversized, a DOCX declaring more than 256 MB, a PDF over 2,000 pages, an encrypted PDF), Schemathesis on the upload route | hidden text set by a character style, and PDF headings by font size, are open questions in `docs/DESIGN.md` |
| Retrieval within a document | proven, with a measured blind spot | `scripts/eval_retrieval.py`: Recall@6 0.85 on 164 CUAD cases with experts' spans, 0.92 on 38 goldens; uncapped-liability questions 0.44 | hybrid retrieval measured 0.95 and 0.97 and is available behind `WORKBENCH_RETRIEVAL=hybrid`, not default, after one golden regressed (`docs/RETRIEVAL.md`) |
| Answering in the schema, Qwen3 8B, prompt v2 | proven on the golden set | `scripts/run_goldens.py`: 37 of 44 under BM25 (g08 g11 g12 g26 g35 g42 g44 fail), 40 of 44 under hybrid | one model measured; the 4B was rejected on the set (`docs/ROUTING.md`); SkillOpt proposed no edit to the prompt (`docs/SKILLOPT.md`) |
| A quote is shown only when code finds it in the text | proven | `tests/test_spans.py`; seven Hypothesis properties; a replay of the verifier over 611 recorded spans; sixteen hand mutants of the evidence boundary, all killed | the verifier gained a boundary rule today (v3) after the independent review found "5 days" inside "fifteen (15) days"; there is still no similarity tier, by census |
| Status decision under guidance | partial | the status tests; golden g29 | day-count parsing is exercised by one golden; more are added when a change to that decision needs measuring |
| The run record: stages, hashes, immutability | proven | SQLite triggers on runs, stages, findings, spans and, since today, the sections and documents a finished run read; the stateful property that finished runs never change and verified spans read back as their quotes; `test_failure_matrix` | |
| The same question is one run | proven | fingerprint lookup plus a partial unique index; the stateful property; mutant M10 (lookup and index both off) killed; the browser flow that asks twice | |
| A dead run is failed, a live one is not | proven after a fix | `test_api_flow` stale run; measured at twenty concurrent questions | the window was one model timeout plus a minute and failed six live runs under load; it is four timeouts plus a minute now |
| The API contract | proven | `openapi.json` drift test; the generated client; Schemathesis over every operation except the event stream, twelve examples each, no 5xx (`tests/test_api_fuzz.py`) | |
| An evidence pack a stranger can check without the workbench | proven | `tests/test_evidence_pack.py`: changed document bytes fail, the reading stage's recorded hash is checked against the packed sections, `verify.py` imports nothing outside the standard library | |
| The interface | proven for the flows named | twenty Playwright flows against the production build and the real API in replay: seven happy paths, ten reliability flows, three critical flows (review against guidance, malformed upload, refresh mid-run); axe on three surfaces; Lighthouse; seven Vitest tests | no visual regression suite; earned by the first layout regression that escapes |
| Field extraction over a corpus | proven once | one recording, 20 contracts by 3 fields: 47 answered with a verified citation, 10 not found, 3 withheld (`docs/BATCH.md`) | one corpus, one run |
| Document families | proven once | precision, recall and F1 against hand labels with the threshold sweep (`docs/FAMILIES.md`) | one corpus |
| A baseline on labelled data outside the sample | missing | pre-registered: corpus, labels, floors and scorer are in the tree (`docs/CUAD.md`) | about 4.3 hours of GPU, not yet run |
| Scale | measured on one machine | `scripts/load_envelope.py`, `docs/SCALE.md`: 1, 5, 10 and 20 concurrent questions | the model is the bottleneck above one; two defects at twenty were found and fixed; nothing beyond one process and one GPU is claimed |
| Continuous integration | missing | the workflow is written and sits on branch `ci` | it has never run: the GitHub token lacks the `workflow` scope; every check runs locally by hand before a push |
| Dependency and code scanning | partial | Dependabot configuration in the tree; CodeQL in the CI workflow | neither has run, for the reason above |
| Domain correctness | missing | ten findings packed for a lawyer, built from the record by document, model, prompt and retrieval (`docs/DOMAIN-REVIEW.md`) | not yet reviewed by anyone qualified |
| Independent scrutiny | done once | a read-only reviewer told to assume the tree was AI-generated and find where the story becomes fake: seven findings, all true (`docs/REVIEW-INDEPENDENT.md`) | one reviewer, one pass |
| More than one user, authentication, tenancy | not justified | | a local single-user tool; `docs/SCALE.md` names what would earn each |
| A worker queue, PostgreSQL, object storage, a persistent vector index, a virtualised document view, an agent framework | not justified | `ENGINEERING_CONSTITUTION.md`, `docs/SCALE.md` | each waits on a measurement it would have to win |
| A mutation-testing dependency | not justified | sixteen hand mutants in `scripts/mutate_by_hand.py`, each named for the decision it breaks | earned when the hand mutants stop finding gaps in the suite |

## The order the validators ran in, and what each found

1. **Retrieval, before anything else.** BM25 had never been scored against a label. Recall@6 0.85
   on CUAD and 0.92 on the goldens, with one family of questions at 0.44. Hybrid retrieval was
   built, measured better, and kept behind a flag because one golden regressed under it
   (`docs/RETRIEVAL.md`).
2. **Boundaries.** One table of cases, expected, observed and the test that holds each
   (`docs/FAILURE-ENVELOPE.md`). Writing it earlier found two 422s that were a 500; today it
   gained the encrypted PDF, the oversized unpack, and the two defects the load envelope found.
3. **Properties and state.** Seven Hypothesis properties of the verifier (offsets return the
   quote, whitespace and typographic differences are forgiven, a changed digit never matches, a
   located span never splits a word or a number) and one stateful machine over the API: ask,
   review, memo, in any order, and no finished run ever changes. Every budget scales with
   `WORKBENCH_FUZZ_SCALE`; the deep pass at twenty (properties at 4,000 to 8,000 examples each, the
   machine at 120 runs of 30 steps, Schemathesis at 240 examples per operation) ran on 2026-09-29
   after the day's changes: 31 tests, 8 min 55 s, nothing falsified.
4. **Schemathesis.** Every operation in `openapi.json`, twelve generated examples each, the
   event stream excluded because it never ends: no 5xx.
5. **Hand mutants over the named targets.** Sixteen, one decision line each: a mismatch counted
   as verified, the verified flag inverted, relocation disabled, a run complete with nothing
   verified, the status decided as if all quotes verified, an offset drifting by one, digits
   ignored by the letters-and-digits tier, the label-strip tier losing its name, the immutability
   trigger never firing, a duplicate request creating a second run, a provider failure leaving
   the run complete, the pack skipping the document hash, and, since the review, a match starting or
   ending inside a word, the pack skipping the hash the run recorded, and section text of a finished
   run changing. All killed; the duplicate-request mutant needed both the lookup and the unique index
   off, because the index alone caught it.
6. **Browser truth for the three critical flows.** A review against guidance to a finding with
   a status and the guidance in the drawer; a malformed upload refused with the reason and nothing
   opened; a refresh once the run is in the URL, which brings it back (the run id reaches the URL
   only when the run has finished, so the reload happens after completion; a true mid-run refresh
   is unproven, see `docs/SYSTEM_TRUTH.md`). Twenty
   flows pass in replay in under a minute; the axe pass found one scrollable region without a
   keyboard focus, fixed.
7. **The load envelope** at 1, 5, 10 and 20 concurrent questions with the live model
   (`docs/SCALE.md`). The API's own queue stays under two seconds; the model serves one
   generation at a time and is the bottleneck at every level above one, so no throughput work
   follows. The envelope found two defects at twenty: the request's session pinned a connection
   through the background task and ran the pool dry, and the staleness window was shorter than a
   legitimate wait and failed six live runs. Both fixed, tested, and re-measured.
8. **One independent read-only review** with the instruction to assume the tree was heavily
   AI-generated and find the first place the engineering story becomes fake. Seven findings, all
   true, recorded as delivered before any fix; the two that broke the story were the CI sentence
   and the lawyer pack, both corrected at the source (`docs/REVIEW-INDEPENDENT.md`).

## What the phase changed in the code

Only fixes to what the validators found: `create_run` commits before returning; the staleness
window is four model timeouts plus a minute; the verifier refuses a match that splits a run of
letters and digits; the evidence pack carries and checks the reading stage's recorded hash;
sections and documents of a finished run are immutable; the lawyer pack is built by a script from
the record. Checks after the phase: backend 151 tests, ruff, mypy strict, import-linter; twenty
browser flows; sixteen mutants killed; the verifier replay over 611 spans lost nothing.
