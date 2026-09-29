# Independent read-only review, 2026-09-29

One instruction to a reviewer with no write access, given the repository after every deterministic
check passed: *assume this was heavily AI-generated; find the first place where the engineering story
becomes fake.* The reviewer read the code, the tests, the docs and the SQLite record (read-only) for
about seventeen minutes. Findings are recorded here as delivered, before any fix, with the status
after the fixes in the last column.

| # | Finding, as delivered | Severity given | True? | After |
|---|---|---|---|---|
| 1 | `docs/DOMAIN-REVIEW.md` says every finding is on the Common Paper sample; two of its ten runs belong to `UK05.docx` (a Cabinet Office charges schedule) and five are `qwen3:4b` runs on the reader-v3 parse, the candidate `docs/ROUTING.md` rejected. Selected by question text, not by document and model. | breaks the story | yes | pack rebuilt by `backend/scripts/domain_review_pack.py`: the sample found by its sha256, model `qwen3:8b`, prompt `answer-v2`, BM25, the latest complete run per question; the header states all of it and every row carries its run id |
| 2 | README and the constitution's audit say CI runs the checks; `.github/workflows/` exists only on the local branch `ci`, never pushed; no CI has run against any commit. | breaks the story | yes | wording corrected in the README, the constitution and `CLAUDE.md`: the workflow sits on branch `ci`, has never run, and waits on the token's `workflow` scope; every check runs locally, by hand, until then |
| 3 | The evidence pack's "sections hash the run recorded" is computed from the sections the pack serialises, not compared with the hash the run stored at its reading stage; `sections` and `documents` carry no immutability trigger, so an `UPDATE sections` after the run passes both hash lines. | weakens | yes | the pack carries the reading stage's recorded hash and `verify.py` recomputes it from the packed sections (an older pack without it says so); `sections` and `documents` read by a finished run are under the same triggers; a test for each |
| 4 | The verifier has no token boundary: `"5 days"` verifies inside `"fifteen (15) days"` at the letters-and-digits tier with the highlight `"5) days"`; `"$1,500"` inside `"$11,500"`; `"less than 30 days"` inside `"not less than 30 days"` as exact. | weakens | yes for the digit cases; the negation case is a verbatim quote with visible context | verifier v3: at every tier a match may not split a run of letters and digits at either edge; the reviewer's probes are tests (the negation case stays found: a verbatim quote whose highlight shows the dropped word); replayed over the record before adoption: 611 spans, none lost, no tier changed. A first draft that demanded a non-alphanumeric neighbour on both sides would have downgraded one verbatim quote ending in "(" from exact to alnum; the replay caught it |
| 5 | A live run is declared dead at model timeout + 60 s, while a legitimate run can span four 600 s calls (one transport retry, one corrected retry); the fingerprint is freed and the live worker's next commit hits the immutability trigger. The doc cites a stale-run test in `test_failure_matrix` that lives in `test_api_flow`. | weakens | yes | reproduced under load before the fix: at twenty concurrent questions, six live runs still waiting on the model were failed at 660 s and their workers then hit the immutability trigger (`docs/SCALE.md`); the window is now four model timeouts plus a minute; README, the envelope table and the test reference corrected; re-measured at twenty: all twenty finished, none failed (18 complete, 2 unresolved: the model answered and nothing verified); run wall p50 455.4 s, p95 807.0 s |
| 6 | `CLAUDE.md` and constitution rule 8 say fake providers live only under `backend/tests`; the record/replay provider with fault markers ships in `app/providers`. | weakens | yes | `CLAUDE.md` and rule 8 name the exception and why: selected only by `WORKBENCH_PROVIDER=record|replay`, never by default, so the browser flows run without a GPU |
| 7 | Counts the tree does not reproduce: "nine hand mutants" (twelve), "113 tests" (139), "seventeen flows" (20), `docs/BATCH.md` not found 9 / withheld 4 (report today 10 / 3), `hashing.py` says nothing else imports hashlib (three scripts do; the test scans `app/` only), `docs/GOLDENS.md` "forty-two" (44). | cosmetic | yes | each corrected: twelve mutants, 146 tests, twenty flows, batch 10 not found and 3 withheld re-read from the report (governing law 2 and 1, liability cap 8 and 2), the hashing docstring scoped to `app/`, forty-four goldens |

**Supported, checked by the reviewer and not listed:** the golden recordings (BM25 37/44, hybrid 40/44
with the exact failing ids; v3 parse 32/42 and 34/42), the qwen3:4b comparison, the batch record,
the citation record to the span, the replay of verification, `scripts/eval_retrieval.py` reprinting
`docs/RETRIEVAL.md`, `openapi.json` against `app.openapi()`, the immutability triggers, idempotency
including the stateful property, hybrid's refusal to fall back, and the sample's hash against the
corpus manifest.

**Where the reviewer would stop trusting the repository:** the CI sentence in the README, then the
lawyer pack: "the one artefact written for someone outside the loop was assembled by question text
rather than by fingerprint". Everything numeric in the internal docs reproduced from the database;
the failures were at the two edges where the repository talks to the outside world.
