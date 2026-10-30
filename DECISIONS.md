# Decisions log

Each decision as it was taken, newest last:

- [2026-09-28: the pivot](#2026-09-28-the-pivot)
- [2026-09-28: visual system decided by three coded shells first](#2026-09-28-visual-system-decided-by-three-coded-shells-first)
- [2026-09-28: C frozen; A and B discarded](#2026-09-28-c-frozen-a-and-b-discarded)
- [2026-09-28: earn each dependency](#2026-09-28-earn-each-dependency)
- [2026-09-28: the slice is real](#2026-09-28-the-slice-is-real)
- [2026-09-28: Findings and Runs as views in one shell](#2026-09-28-findings-and-runs-as-views-in-one-shell)
- [2026-09-28: the product bar, from the second review Pavan adopted](#2026-09-28-the-product-bar-from-the-second-review-pavan-adopted)
- [2026-09-28: the constitution, adopted with its audit](#2026-09-28-the-constitution-adopted-with-its-audit)
- [2026-09-28: five additions after the external review, in order](#2026-09-28-five-additions-after-the-external-review-in-order)
- [2026-09-28: the six-block external review, first pass](#2026-09-28-the-six-block-external-review-first-pass)
- [2026-09-28: the role-specific audit, P0 and P1](#2026-09-28-the-role-specific-audit-p0-and-p1)
- [2026-10-14: two evidence-integrity blockers closed (verifier v9, reader v13)](#2026-10-14-two-evidence-integrity-blockers-closed-verifier-v9-reader-v13)
- [2026-10-14: after the legal pilot, five release defects repaired (verifier v10, reader v14, policy-v9, the memo)](#2026-10-14-after-the-legal-pilot-five-release-defects-repaired-verifier-v10-reader-v14-policy-v9-the-memo)
- [2026-10-14: the product mission (policy-v10, retrieval-v2, one account of each finding, a revision asked again)](#2026-10-14-the-product-mission-policy-v10-retrieval-v2-one-account-of-each-finding-a-revision-asked-again)
- [2026-10-14: the first-visitor acceptance test (three repairs, inside the unreleased candidate)](#2026-10-14-the-first-visitor-acceptance-test-three-repairs-inside-the-unreleased-candidate)
- [2026-10-14: policy-v11, the contract's own statements about its provisions (the intent-first mission)](#2026-10-14-policy-v11-the-contracts-own-statements-about-its-provisions-the-intent-first-mission)
- [2026-10-15: policy-v12, the time a question asks at is not a premise](#2026-10-15-policy-v12-the-time-a-question-asks-at-is-not-a-premise)
- [2026-10-15: policy-v13, run identity by reached starts, and section handles kept honest](#2026-10-15-policy-v13-run-identity-by-reached-starts-and-section-handles-kept-honest)
- [2026-10-16: the blind contract stress test, policy-v14 and reader v15](#2026-10-16-the-blind-contract-stress-test-policy-v14-and-reader-v15)
- [2026-10-16: one Hetzner server, the model on it](#2026-10-16-one-hetzner-server-the-model-on-it)
- [2026-10-17: policy-v15, an instrument's marked number is not a value](#2026-10-17-policy-v15-an-instruments-marked-number-is-not-a-value)
- [2026-10-17: policy-v16, quoting the replacement is not following it](#2026-10-17-policy-v16-quoting-the-replacement-is-not-following-it)
- [2026-10-19: operating it under load, after a deep audit](#2026-10-19-operating-it-under-load-after-a-deep-audit)
- [2026-10-21: an answer depends on the model server's prompt cache (measured, open)](#2026-10-21-an-answer-depends-on-the-model-servers-prompt-cache-measured-open)
- [2026-10-21: a casebook](#2026-10-21-a-casebook)
- [2026-10-21: every answer computed from its first token](#2026-10-21-every-answer-computed-from-its-first-token)
- [2026-10-30: an audit by people trying to break it](#2026-10-30-an-audit-by-people-trying-to-break-it)

## 2026-09-28: the pivot
Three experiments killed three product ideas, and the results page records that. The next
step is not a fourth idea: it is a working full-stack Contract Intelligence Workbench whose
reliability layer is the discipline those experiments established. Primary workflow: upload
contracts and optional guidance → document/Assistant workspace → questions or review →
evidence-linked findings with click-to-highlight citations → derivation on demand → one
review memo. Three surfaces only: Workspace, Findings, Runs. Stack: Next.js/React/TypeScript,
FastAPI/Python, PostgreSQL + pgvector, Qwen3 8B through Ollama behind a provider interface,
hybrid retrieval, LangGraph for the stateful flow, deterministic span verification, SSE stage
streaming. The killed experiments live under Runs as records; Surgicality and Field Plan are
not resurrected as products.

## 2026-09-28: visual system decided by three coded shells first
Identity brief: a Raycast-like graphite shell with spectral indigo-to-cyan accents used
sparingly, Emil Kowalski-style motion discipline, and Ivo's hierarchy underneath (document
first, evidence beside conclusions, actions beside results, density only where useful). Before
the full build, the same upload → workspace screen is coded three ways (A darkest and glassiest;
B editorial warmth; C dark shell with a paper document canvas and a spectral Assistant surface),
rendered, and one is chosen. The visual system freezes on the choice; the vertical slice is built
on it. Sample material in the shells is synthetic and labelled.

## 2026-09-28: C frozen; A and B discarded
Pavan chose shell C. A and B are references, not themes; there is no theme switching. Before
integration the interactions were hardened (composer → file morph, workspace transition,
draggable divider with keyboard and double-click reset, staged thinking states, citation click
to exact scroll and highlight, evidence drawer with focus management, guidance attach and
remove, Ctrl/⌘K command palette). No extra pages, dashboard cards, marketing content, agent
diagrams, onboarding or decorative animation.

## 2026-09-28: earn each dependency
SQLite (SQLAlchemy 2) and BM25 (`rank_bm25`, headings weighted ×3) carry the slice. PostgreSQL,
pgvector, nomic-embed-text and LangGraph stay out of the tree until a measurement on real runs
shows the current choice failing. The run is a typed service with persisted stages and SSE; the
provider interface is real (Ollama behind `ModelProvider`), so a hosted model is a config change.

## 2026-09-28: the slice is real
Frontend wired to the API and the sample data deleted; "try a sample agreement" uploads Common
Paper's Cloud Service Agreement (CC BY 4.0, bundled unmodified, attributed on screen). Verified
in the browser against Qwen3 8B: parse → guidance → question → SSE stages → finding with three
verbatim-verified citations → exact highlight → evidence drawer → memo (HTML and DOCX). The
model's answer on the sample ("no notice period for termination for convenience is specified")
is shown as `Not found`, decided by code from the model's hint because no comparable day counts
existed. Fixed on the way: the memo carried the UTC date; SQLite returned naive timestamps that
the browser read as local (the API now emits `+00:00`); sub-clause citations were labelled with
their own first words instead of the parent heading.

## 2026-09-28: Findings and Runs as views in one shell
Documents, Findings and Runs are views switched by the rail inside the frozen shell, each one
list per screen, no cards. Findings shows only verified findings from complete runs and opens
the document at the passage with the drawer. Runs shows the complete record of a run and,
beneath the list, the three killed experiments read from `ivo-experiments/docs/results.json`
(that build now writes `board` and `baselines` records for this purpose). The Settings button
was removed from the rail rather than left inert. Prettier is pinned at 160 columns so the
whole tree formats one way.

## 2026-09-28: the product bar, from the second review Pavan adopted
The review asked for a living contract workspace with an engineering layer underneath, and a
release checklist. Checked item by item against the build. Already true: the root URL is the
composer, the contract is the dominant object, results are objects, the evidence drawer shows
verified quotes and run metadata, guidance is a first-class chip, Runs carries hashes and raw
output, the killed experiments sit under Runs, the palette exists, no agent graph, no settings
page. Changed in response: the stage list now shows each stage the API passed with what it
produced; runs that end without findings carry a `reason`, and invalid model output is a
`failed` run with Try again rather than an evidence verdict; the finding object lists its
verified passages with excerpts (or "closest provisions" when the point was not found); the
prompt moved to `answer-v2`, which words absence as "not found in the sections reviewed" and
never as "the agreement lacks"; the URL carries document, run and view so a finished run
survives a reload; the divider remembers its position; Findings is a table with evidence
labels; the run record shows timing and citation counts; Documents shows review state; PDFs use
layout extraction, cross-references are no longer mistaken for headings, and thin structure is
declared on screen. Declined: theme tokens and radii were not re-tuned (C is frozen); guidance
upload stays paste-only; no login flow; no font-size heading detection for PDFs after pypdf's
visitor did not report sizes on printed files; the SSE event names stay as stage names.

## 2026-09-28: the constitution, adopted with its audit
Pavan adopted the anti-vibe-coding constitution (boundaries, invariants, failure ownership,
earned complexity) as binding, and asked for an audit before any cleanup. The audit found the
architecture already right where it mattered (verification in code, no mocks, one normaliser,
immutable runs, earned dependencies) and wrong in the ways the constitution predicts:
a 1,300-line workbench component, routes doing use-case work, four hashing call sites, no
idempotency, vocabularies held only in code, no request ids, hand-retyped frontend types.
The cleanup pass, in the order he set: (1) the workbench split into feature components and
hooks with no behaviour change; (2) application services plus one hashing module, the
fingerprint built on it; (3) idempotent run creation with a database guarantee (partial unique
index over non-failed runs), failed runs retryable, interrupted runs failed at startup;
(4) CHECK constraints for new files with the vocabularies shared by models, schema and code,
and structured request and stage logging; (5) TypeScript types generated from the API's
OpenAPI document, with Literal unions on the schema so the contract carries the vocabularies;
(6) `ENGINEERING_CONSTITUTION.md` with the audit kept as written and the removals listed against
it, and `CLAUDE.md` pointing to it. Also fixed on the way: an answer that quotes no passage is
not a finding (schema requires at least one quote; the service withholds it otherwise), and the
phone breakpoint is 640 px so a narrow desktop pane still shows the split. Then stop: no
repository pattern, no LangGraph, no Postgres, no pgvector, no folder taxonomy for its own sake.

## 2026-09-28: five additions after the external review, in order
Kimi's red-team of the workbench (`ivo-research/KIMI-WORKBENCH-REVIEW-STATUS.md`) and a probe
of our own ingestion set the list; Pavan said go with the accepted-view fix first regardless.
(1) **Accepted-view DOCX ingestion.** python-docx's `paragraph.text` walks only a paragraph's
direct runs, so on negotiated paper a tracked change lost both the old and the new wording
("continues for  months.") and hidden drafting notes were read as contract text. The reader now
walks the XML: runs inside `w:ins` and `w:moveTo` are kept, `w:del` and `w:moveFrom` dropped,
runs marked `w:vanish` dropped and counted, deleted table rows skipped, a deleted paragraph mark
joins its paragraph to the next. Each document records `parser_version` ("v2"; older rows are
null), `tracked_changes` and `hidden_runs`, and the header says "accepted view of N tracked
changes · M hidden runs left out". Older documents keep their old text: runs are immutable and
their offsets point into the text they were verified against. (2) **One CI gate**
(`.github/workflows/checks.yml`): backend, interface, and a contract job that regenerates
`openapi.json` and `api.schema.ts` and fails on any difference. Unverified in GitHub until Pavan
pushes; every command in it passes locally. (3) **Backend static checks**: ruff and mypy
`--strict` in `pyproject.toml`, over app, scripts and tests. Adopting them moved the stage,
status and reason vocabularies to typed `Literal`s declared once in `models.py` and shared by
the ORM, the API schema, the CHECKs and the run service; the model's status hint became a named
type; the formatter reflowed eleven files. pyright was tried and not kept (one checker; no Node
in the backend job). (4) **Two frontend tests** (Vitest, Testing Library): the run follower
mirrors the API's stages and ends with the finished record, and shows a run that could not start
as failed with no reason of its own; the URL state restores document, run and view once and
writes them back. No browser tests. (5) **The golden set** (`docs/GOLDENS.md`, written before
the first run): twelve questions about the sample, nine present and three absent, judged by code
from the run record; one run per golden per prompt version through the same `start_run` use
case, so a golden run is an ordinary immutable run; `GET /api/engineering/goldens` and a table
under Runs with the comparison between the two latest prompt versions. The kill rule: a prompt
or retrieval change is kept only if the set moves in its favour with no regression; a change
that moves nothing is dropped or the set is extended until it can see it; goldens are not edited
to make a change pass. Guidance goldens are deferred (the status decision with guidance is not
exercised yet). Declined: table-aware sectioning (recorded as the next ingestion job), style-
resolved hidden text, Playwright, a frontier-model run (the $0 rule), a LICENSE file (Pavan's
choice of licence).

## 2026-09-28: the six-block external review, first pass
Pavan pasted six review blocks (staff-level depth, framing, tier list, pixel-level defects, the
five mechanisms, future scope) and asked for everything defensible to be built in sequence.
Done in this pass: the model's section handles (`[sec_N]`) are rewritten at the boundary into
the section's own label before a finding is stored (`runs/prose.py`; raw output keeps them); a
finding carries `evidence_kind` (passage: the spans support it; coverage: the point was not
found and the spans are the closest provisions read) and the Findings table, card, drawer and
memo say which; withheld findings travel on the run (`withheld`) and the Assistant shows the
model's proposal struck through beside the verdict, with "Is there a most favoured nation
clause?" as a one-click suggestion because the sample has no answer to it; the verifying stage
reports withheld counts; uploads are content-addressed (same bytes, same reader → the stored
document, 200 with `reused`; the original bytes are kept under `data/documents` by hash for the
evidence pack); a live citation record (`/api/engineering/citations`) sits under the Runs title
instead of a hand-typed withhold rate; the golden comparison is rendered as previous answer /
new answer / what changed / better or worse; the Runs footer no longer prints a local path;
in-progress rows say so; reader v3 recognises any style named *heading* or carrying an outline
level (own or inherited), keeps numbered sentences and definitions as quotable body under their
parent's label, and drops trailing stops from headings. First golden recording: v1 8/12, v2
10/12, v2 kept (`docs/GOLDENS.md`).
**Measured before deciding on fuzzy matching.** A census of the 9 withheld quotes in the
database: 3 differed from the text only by quotation marks around a defined term, 2 had the
section label prefixed to the quote, 1 had one inserted space, 1 was a definition the v2 reader
had hidden in a heading, 2 were real paraphrases, and 1 (ratio 0.994) changed a digit. Decision:
add two deterministic tiers, letters-and-digits matching (punctuation, quotes and spacing
ignored; every letter and digit must match) and section-label stripping, each labelled in the
UI; no similarity-ratio tier, because 0.994 hid a changed number. Queued, in order: the two tiers
with tests; re-run the golden set under reader v3 and the new ladder and replace the table;
DOCX memo craft (core and custom properties with run and prompt hashes, bookmarks and internal
hyperlinks to a sources table, deep links back into the workbench, checked by opening in Word);
human review of findings as an append-only table with an idempotent, reversible endpoint and
the Documents "reviewed" state derived from it; database triggers that make a finished run and
its findings immutable; the self-verifying evidence pack (original bytes, sections, anchors,
a stdlib `verify.py`); README paragraph naming the Ivo overlap, drafted for Pavan's voice.

## 2026-09-28: the role-specific audit, P0 and P1
Pavan reframed the work against Ivo's Full-Stack Engineer posting (LLM pipelines with extraction
and clustering, millions of contracts reliably, high-performance UI, relentlessly resourceful,
80/20) and set the order P0 evidence correctness → P1 execution hardening → P2 evaluation depth
→ P3 measured model routing → P4 batch extraction → P5 clustering → P6 UI performance, then
stop. He added a second binding rule: every sophisticated component must earn its existence
with a measured failure it fixes or an explicit product requirement.
**P0.** The verifier ladder is now exact → normalized → casefold → alnum (letters and digits
only; punctuation, quotation marks and spacing ignored; every letter and digit must match), plus
a section-label strip when the model copied "13.1 Defining Variables" in front of its quote,
reported as `unprefixed:<tier>`; casefold keeps offsets when a character folds to two. Measured
by replaying verification over every recorded run with a withheld quote (`scripts/reverify.py`,
no model call, the run untouched): 23 spans, 5 newly verified, 0 lost, the changed-digit quote
still withheld. Human review shipped as an append-only `finding_reviews` table (confirmed,
dismissed, cleared), an idempotent and reversible `POST /api/findings/{id}/review`, controls
under each row of Findings with the reviewer's name asked once per browser, the review on the
drawer and in the memo, and Documents' "reviewed" derived from it. The golden set was re-run
under reader v3 and the new ladder (results in `docs/GOLDENS.md`).
**P1.** SQLite triggers refuse any UPDATE or DELETE on a finished run, its stage rows, its
findings and their spans; reviews and memos are separate rows, so adjudicating or projecting
never touches the record. Every stage row now carries started and completed times, duration,
status (running, ok, failed), the attempt count of the model call, sha256 of what it consumed
and produced (reading: the document; retrieval: the question and guidance → the candidate ids;
checking: prompt and message → the raw output; verifying: the raw output → the located spans)
and the run's reason as error code when it ended the run; the previous stage row is closed and
committed before the run can turn terminal, because after that the database will not let it be
touched. A provider transport failure is retried once after two seconds and the second failure
is the run's (`provider_error`); malformed .docx and PDF bytes and empty files are refused at the
boundary as 422; a memo is written once per run and asked-for again returns it; the failure
matrix lives in `tests/test_failure_matrix.py`, one test per row. Not added: a hard run-level
timeout beyond the model call's 600 s (the model call is the only unbounded step and it is
bounded), queues, and a resumable graph.
**Found by the triggers, fixed in P1.** Restarting the API mid-recording swept the golden
runner's live run as "interrupted" (startup recovery failed every non-terminal run regardless of
who owned it), and the new trigger then refused the runner's next write to that run. Recovery is
now by staleness: a run whose current stage has been silent longer than the model timeout plus a
minute is failed with the reason, at startup and whenever runs are read; a run that started
moments ago in another process is left alone. Guidance became content-addressed for the same
reason documents did: the same words are one record, so the golden runner and the interface
share fingerprints.
**P2.** The golden set grew from 12 to 42 across ten named categories (direct extraction,
absence, defined terms, cross-reference, multi-section, guidance comparison with an expected
status, ambiguous, numeric precision, negation, amendment and conflict), each written against
the contract's text. `run_goldens.py --report` prints improvements, regressions, unchanged
passes and failures, the count with different citations or statuses under the same verdict,
the mean latency delta and the verdict under the rule; the Runs table shows per-category pass
counts and mean model latency per prompt version. Ahead of P3 the model joined the run's
identity (recorded options and fingerprint), a run carries its task (`clause_lookup` or
`guidance_comparison`) and the routing reason, and `routing/router.py` picks the model from a
policy that is empty until a candidate is measured (`docs/ROUTING.md`). Recording 3 (42
goldens, both prompts, Qwen3 8B) was started; its table goes in `docs/GOLDENS.md`.
**P4, built while the recording ran.** Batch extraction (`app/batch`, `scripts/run_batch.py`,
`GET /api/batches`): a field task (governing law and forum, termination, liability cap) over a
corpus, one ordinary run per document and field through `start_run` and `execute_run`, a
thread pool bounded by the concurrency argument with a session per worker, `Batch` and
`BatchItem` records pointing at the runs, and a report computed from the records: documents
and values per minute, model latency p50/p95/mean over the runs the batch created, invalid
output and provider errors by reason, verified citation and withheld rates, reuse, retries, and
every value with its status and citation, on the Runs surface and as CSV. The corpus is the
twenty licensed public contracts already on disk, stated as twenty. The first recording waits
for the GPU behind the golden run.
**P5, measured before it was kept.** Document families (`app/families`,
`scripts/cluster_corpus.py`, `GET /api/engineering/families`): three set views of a document
(normalised headings, defined terms, word 5-gram shingles), exact Jaccard with fixed weights
0.5/0.25/0.25 (MinHash left for a corpus that needs it), single-linkage families at a
threshold, pairwise precision, recall and F1 against two hand label sets over the twenty
documents, with the threshold sweep reported. Result: structure finds the template family
(Common Paper: precision 1.0 down to threshold 0.15, F1 0.60 there, best F1 0.64 at 0.10 where
two Cabinet Office contracts join wrongly) and does not find suites (a schedule and its core
terms score 0.03 to 0.05; suite F1 0.13 at best). The default threshold is 0.15 because that is
the highest value keeping template precision at 1.0. The next signal a person would use, a
document naming its parent, was checked in the text before being built and is unreliable here
(the schedules mention the IDTA 190 times; the addendum never names the IDTA), so it was not
added; the honest next step for suites is publisher metadata and cover-page set identifiers,
recorded in `docs/FAMILIES.md`.
**P6, measured, not built.** A 2,001-section fixture in the production build: paper on screen
1.6 s after navigation (fetch 138 ms), 8,094 DOM nodes, citation jumps 35 ms (two frames),
against 0.5 s, 563 nodes and 9 ms for the 123-section sample. Scrolling and navigation are
frame-bound; only the first render scales, at about 0.55 ms per section. No virtualisation; the
number that would earn it (a first render over 3 s, about 5,000 sections) is in
`docs/PERFORMANCE.md`. The families endpoint took two seconds because it re-fingerprinted
twenty documents per call; documents are immutable, so fingerprints are cached by document id.
**The two items left from the earlier review, done while the GPU recorded.** The Word memo is
now a working document: core properties name the run (title with the agreement, subject the
question, author "Contract Workbench", identifier the run id), a custom-properties part carries
the run id and fingerprint, the document hash, guidance hash, model, prompt version and hash,
the citation count and a link back; each citation links inside the file to a bookmarked row of
a sources table; each source links out to the exact run and finding in the workbench
(`?document=&run=&finding=`, which the interface now reads); Word opens it without repair (2
tables, hyperlinks and bookmarks present, checked through COM). The evidence pack
(`GET /api/runs/{id}/evidence-pack`, "Download evidence pack" on the run record) is a zip of the
original bytes, the canonical sections, the run record with hashes, every finding with its
located spans, and a stdlib `verify.py` that re-hashes the document and the sections and
re-locates every verified quote under the same ladder (its normalisation table is embedded from
the verifier, so the two cannot drift); the test runs `verify.py` in a subprocess, then tampers
with one digit in the sections and watches it fail.
**Recording 3 and what it found (2026-09-28).** Forty-two goldens, reader v3, Qwen3 8B: v1 32
of 42, v2 34 of 42; v2 better on g06 and g25, worse on none; eight failures shared. Reading the
eight from the records (`docs/GOLDENS.md`): six are the model's (it reaches for the Cover Page,
drops a clause from a list, once asserts a restriction that runs the other way); two were the
workbench's. g26 quoted a section heading in front of its text without the number, which the
label strip did not recognise: verifier v2 now strips the full label, the heading alone or the
number alone, and a replay over every withheld run gains 9 spans and loses none. g23 quoted the
first sentence of the survival clause, which reader v3 had turned into a heading because it
ended in a colon at 79 characters: reader v4 keeps a lead-in as a title only when it is short
(60 characters, 8 words), so the sentence stays quotable body. Both fixes were made in the hour
the set reported them, which is the point of the set. Reader v4 re-parses the corpus (twenty
documents re-ingested by content hash under the new version) and the golden document; the next
golden recording is under v4 and the qwen3:4b comparison already running is against the v3
parse, so it is compared with the v3 numbers above.
**P3 measured (2026-09-28).** qwen3:4b on the 42 goldens, answer-v2, same parse and options as
Recording 3: 36 of 42 against 34, clause lookup 33/38 against 31/38, guidance 3/4 against 3/4,
mean latency 9.8 s against 39.1 s; better on g11, g23, g30, g35; worse on g31 (decided pass
where needs review was expected) and g37 (read a "no" as "not found"). The routing rule, written
before the data, says a candidate is routed a task only when it passes every golden the default
passes on that task; it fails one in each task, so the policy stays empty and the router keeps
saying "no measured alternative" on every run. The overall gain and the four-fold speed are
recorded in `docs/ROUTING.md` with the two ways the decision could change: extend the negation
and guidance categories and re-measure, or accept the two regressions in writing as a change of
default. Neither is taken here.
**Found by running the batch.** Passing both corpus directories listed fifteen files twice;
content addressing made them one document each, but the batch counted 35 documents and 105
values and would have reported throughput on that. The runner now drops a document it has
already seen, and the report counts distinct documents and distinct (document, field) pairs,
judging reuse by whether a run began before the batch did; the batch already running reports
correctly because the report is computed on read.
**P4 measured (2026-09-28).** Batch `ff81b6b33a804475`: 20 documents, 60 values, 57 minutes,
0.82 values per minute, 47 answered with a verified citation, 9 not found, 4 withheld, 0 failed,
0 retries; model latency p50 44 s, p95 135 s; 135 of 146 quotes verified (92%). Numbers and the
reading of the values table are in `docs/BATCH.md`. Pavan chose to stop the GPU queue after this
batch ("kill after batch"): Recording 4 of the golden set under reader v4 was not made; its
expected effect and its one command are in `docs/GOLDENS.md`.

**Checks made real, and a date corrected (2026-09-28, later).** `prettier` was named by the `format:check` script, the README and the CI workflow but declared nowhere: on a fresh shell `npm run format:check` failed with "'prettier' is not recognized", and `npm ci` in CI would have failed the same way; it had only ever run through `npx` fetching it on demand. It is now an exact devDependency (3.9.9) and the check passes with no file changed, because the code was already at the configured width of 160. Separately, every entry above dated 2026-09-29 was written a day late: the machine's clock and every run record say 2026-09-28, and the dates now say so.

**Hand mutation run before any mutation-testing dependency (2026-09-28, evening).** A pasted review argued that the evidence boundary is only architecture if the tests fail when it is broken. Measured first: nine one-line mutants applied by hand to `runs/service.py`, `verify/spans.py` and `db.py`, the suite run after each, the files restored and compared with backups. Killed: a mismatch counted as verified, verified inverted, a run complete with nothing verified, status decided as if verified, a span offset drifting by one character, digits ignored by the letters-and-digits tier, the label-strip tier losing its name, the immutability trigger never firing. Survived: relocation to the other candidates disabled (`for candidate in chosen` → `for candidate in []`), although ten spans in the recorded runs carry a relocated method. One test file closes it (`tests/test_verify_evidence.py`, four cases); the mutant now dies there. Backend 91 tests. Also measured, by script over the import graph: `verify` imports nothing inside the app, `providers` imports only `config`, and `verified` is assigned in exactly two places, the run service and its replay, both as `located is not None`; the interface only reads it. The proposed import-contract and mutation tools are therefore not adopted on a failure; the survivor shows the value of the check, and the two-minute hand run is kept as a script until a second survivor earns the dependency.

**Browser flows, replayed answers, properties (2026-09-28, night).** Pavan set the order: Playwright first, Hypothesis second, Greptile and Sonar once the repository is on GitHub. Browser tests sat on the deliberately-not-done list pending a broken release; an explicit requirement is the second way a component earns its place. Seven flows in `e2e/workbench.spec.ts` run the production build against the API, each on its own port and data directory. The model's answers are recorded once from Qwen3 8B through a recording provider (`app/providers/replay.py`, `WORKBENCH_PROVIDER=record`; two answers, 78 s and 73 s) and replayed by the key of the exact system and user texts, so CI runs the same flows with no GPU: zero calls to Ollama, 29 s. A changed prompt or retrieval makes the replay refuse instead of answering differently. The default provider is untouched; nothing on the primary path is mocked. Six Hypothesis properties of the verifier (`tests/test_spans_properties.py`) held on about 1,800 generated cases: a verbatim substring is found exactly with its offsets; whatever is located has the quote's letters and digits; extra whitespace is forgiven without moving off the text; a changed digit never matches the original; a blank quote is never located; a copied section label is stripped and the body located. Backend 101 tests. CI gains a `browser` job that keeps the traces of any failure. Prettier and Playwright are pinned devDependencies; Hypothesis is pinned in `requirements-dev.txt`.

**Hardening, two adversarial goldens, and CUAD-30 pre-registered (2026-09-28, night).** The repository went to GitHub as `ghantapavan93/Verity` in seventeen logical commits. Two guards a reviewer would look for first: a DOCX is refused before parsing when its zip entries declare more than 256 MB unpacked (the 25 MB cap was on compressed bytes; zipfile never reads a member past its declared size, so the declaration is the bound), and a PDF over 2,000 pages is refused; both 413, both in the failure matrix. Two adversarial goldens: an instruction smuggled into the question (passed, the citation stayed exact) and a false premise about a section that does not exist (failed: the model repeated the premise as a pass and quoted an unrelated passage the verifier duly located). That failure is recorded, not patched: the fix is a prompt rule judged on all 44 goldens, pre-registered in `docs/GOLDENS.md`. CUAD-30 is prepared and pre-registered in `docs/CUAD.md`: thirty CUAD v1 contracts chosen by a fixed rule, seven questions mapped one to one onto CUAD categories, the scoring rule and the floors (precision 0.80, recall 0.50) and the retrieval trigger written before the run. Backend 103 tests.

**Tools weighed against the rule (2026-09-28, night): Lighthouse, Context7, Graphify, and the free-for-dev list Pavan sent.** Lighthouse: adopted as a measurement, not a gate. Landing 100/100/100/100, workspace with a run 99/100/100/100 on the production build; its one real finding, the API's uncompressed JSON, is fixed with gzip over 1 KB and a test that also holds the event stream uncompressed. A CI gate waits for the first change that moves a score. Context7 (Upstash, MIT): adopted as agent tooling, an MCP server in `.mcp.json` and a line in `CLAUDE.md`; it changes nothing in the product. Graphify (Apache-2.0, local tree-sitter graphs, an MCP server): not adopted now; the repository is about 130 source files and its own documents orient an agent; revisit if it triples. From free-for-dev: Dependabot, yes (weekly, grouped, every pin moves through a pull request); CodeQL, yes (on the CI branch, free for a public repository); Sonar Cloud was already chosen; coverage goes to Sonar through CI once his project exists; a status badge once CI runs. Not added, with the reason: CodeRabbit, Semgrep, Socket and GitGuardian duplicate Greptile, CodeQL and GitHub's own secret scanning; Braintrust, Langfuse, Opik and Latitude are what the golden set already does; hosting, monitoring, error tracking and CDNs have nothing to attach to without a deployment. OpenRouter's free models are the one route to a non-local model comparison at $0; contract text would leave the machine, so that is his call, not made here.

**SkillOpt, considered and not adopted yet (2026-09-28, night).** Microsoft Research's text-space optimizer (MIT, v0.2.0, arXiv 2605.23904): a frozen target model, a separate optimizer model that turns scored rollouts into bounded edits of one skill document, an edit kept only when it strictly improves a held-out validation score, and a deployable `best_skill.md` with no inference-time cost. That is this repository's prompt rule, automated: answer-v2 replaced answer-v1 only because the golden set said so. It is not adopted now for three reasons that are measurements, not taste. First, the 44 goldens are the judge and cannot also be the training data; a 22/22 split makes one question worth four and a half points. Second, compute: with a train batch of 8, four candidate edits per epoch, a 20-item validation set and ten epochs, one run is about 900 target-model calls, roughly twelve hours on this GPU at the batch rate, before the optimizer's own calls. Third, the optimizer model: the paper uses a frontier model; under the $0 rule it would be Qwen 8B optimising itself or a free cloud tier that sees contract text, which is Pavan's decision. The experiment that would earn it is written here so it is not invented later: draw a disjoint CUAD training set from the 374 eligible contracts not in CUAD-30 (same rule, next offset), split it by contract into train and validation, let SkillOpt edit answer-v2 against the CUAD scorer, and judge the result on the untouched CUAD-30 and the untouched 44 goldens under the standing kill rule: kept only with no regression there. Prerequisite: the CUAD-30 baseline recorded first, so there is a number to beat. SkillOpt-Sleep, the nightly self-evolution companion for coding agents, is tooling for the agent, not the product, and stays out.

**SkillOpt run against the workbench (2026-09-28, night; Pavan's call after the assessment above).** The environment is the production answer path: `research/skillopt/workbench_env/rollout.py` reads the contract with the same reader, retrieves six candidates with the same BM25, builds the same user message, calls the workbench's own Ollama provider (temperature 0, fixed seed, thinking off, the JSON schema), parses with the same one corrected retry, verifies every quote with the same ladder and decides the status with the same code. Only the system prompt moves; it is the skill, seeded with answer-v2. The score is the CUAD rule, now shared in `app/batch/cuad_match.py` so the scorer and the environment cannot drift. Training data are CUAD contracts disjoint from CUAD-30 (same stride, offset 6; `cuad-skillopt.json`): three contracts train, three gate, the rest reserve. Facts the tool imposed: the configured train size must equal the training split, so the split is the budget; an adapter outside `skillopt.envs` must return its own analyst prompts; Windows caps paths at 260 characters and SkillOpt makes a directory per item id, so ids are short; Ollama's OpenAI-compatible endpoint returns Qwen's thinking in a separate field and only `reasoning_effort: "none"` switches it off, which the runner injects at the client for the optimizer role; SkillOpt's checkout is not edited, the environment is registered from the runner. Smoke run (one contract each side, two-item gate): baseline 1 of 2, training rollout 7 of 7, one optimizer call whose JSON parsed, no edits because nothing failed, 463 s. The real run uses `config.yaml` as committed; the judgment is on the untouched 44 goldens (`docs/archive/SKILLOPT.md`).

**SkillOpt result (2026-09-28, late night).** Sixty-seven minutes, six steps, twelve analyst calls, zero edits proposed, no candidate at the gate; `best_skill.md` is byte-identical to answer-v2, so there was nothing to judge on the goldens and answer-v2 stands. The failures the optimizer saw were mostly disagreements with the CUAD labels (the model citing a real clause the annotators did not mark) and a few misses, three of them with the span among the retrieved sections. Outside the loop the same optimizer proposed one generic edit for the same failures, so the zero is the small local optimizer under the loop's long context, not a parsing fault. Recorded with what would change it in `docs/archive/SKILLOPT.md`; none of it moves the rule that a candidate is judged on the untouched goldens.

**Retrieval measured, hybrid built and not made default; the failure envelope; scale as measured (2026-09-29).** BM25 had never been scored against a label. Against 164 CUAD cases with experts' spans and the 38 present goldens it hands the model the right section in the top six 85% and 92% of the time, and 44% for uncapped-liability clauses, whose wording shares nothing with the question. The rule was written before the dense numbers: 0.90 and above stands, below 0.75 test a hybrid, in between test it anyway and adopt only after the goldens. Hybrid (BM25 fused with nomic-embed-text, local, $0) measured 0.95 and 0.97, so it was built behind `WORKBENCH_RETRIEVAL=hybrid`, entering a run's identity only when chosen. The goldens under the current reader: BM25 37 of 44, hybrid 40 of 44, one regression (g36, right section first, quote with an ellipsis, withheld). The rule asks about regressions, not causes: BM25 stays the default, hybrid stays available with its numbers. Recording 4 exists now as a side effect, 37 of 44, with g23 and g30 gained by the reader change as predicted. The failure envelope (`docs/FAILURE-ENVELOPE.md`) found two holes on the day it was written: a valid zip with a broken package escaped python-docx as an AttributeError, a 500; an encrypted PDF was reported as unreadable. Both are 422 with the reason, five tests added, 113 in all. `docs/SCALE.md` states what was measured and what each next step would have to earn. `docs/archive/DOMAIN-REVIEW.md` packs ten verified findings for a lawyer, Pavan's to hand over. The multi-guidance fan-out the review proposed is not built: it is not small.

**Browser flows for the failure side (2026-09-29).** Ten reliability flows join the seven happy paths, all against the real API and the production build: a provider outage and non-schema output end on screen as failed runs with the reason and no verdict; a dropped event stream still finishes through polling; the same question twice returns the same run and the document travels gzipped, both observed on the wire from the browser; the memo names its run; a confirmed finding survives a reload; the URL alone restores a run; Escape closes the drawer; a narrow window gets the plain note; axe (WCAG 2.1 AA) finds nothing serious or critical on the landing, the workspace or the open drawer. The faults are injected by two markers the replay provider honours in a question, `[[fault:provider]]` and `[[fault:garbage]]`; nothing else on the path is mocked. Writing the accessibility flow found the document scroll region not keyboard-focusable; it is now, with a label. Seventeen browser flows in all.

**Validation phase, no product work (2026-09-29).** The brief: audit what is proven, partial, missing and not justified; run the validators in a fixed order (retrieval first, then boundaries, properties and state, Schemathesis, hand mutants over named targets, browser flows for three critical paths, the load envelope at 1, 5, 10 and 20, one read-only independent review); record findings before fixing anything. The audit is `docs/archive/VALIDATION.md`. What the validators found and what changed because of it: (1) the envelope at twenty ran the connection pool dry, because the request's session kept a connection pinned through the background task; `create_run` now commits before returning. (2) The second run at twenty failed six live runs: they were still waiting on the model at 660 s, which was the staleness window, and their workers then hit the immutability trigger; the window is now four model timeouts plus a minute, the longest legitimate run. Re-measured at twenty: all twenty finished, none failed (18 complete, 2 unresolved: the model answered and nothing verified); run wall p50 455.4 s, p95 807.0 s. (3) The independent reviewer found seven true things (`docs/archive/REVIEW-INDEPENDENT.md`); the two that broke the story were the CI sentence and the lawyer pack, both fixed at the source: the pack is now built by `scripts/domain_review_pack.py` from the record by document, model, prompt and retrieval, and the README says the workflow has never run. (4) Verifier v3: a match may not split a run of letters and digits at either edge; replayed over 611 recorded spans before adoption, nothing lost, no tier changed. The first draft of the rule demanded a non-alphanumeric neighbour on both sides and would have downgraded one verbatim quote ending in "(" from exact to alnum; the replay caught it, so the rule is a word boundary, not a neighbour test. (5) The evidence pack carries the reading stage's recorded hash and `verify.py` checks the packed sections against it; sections and documents of a finished run are under the immutability triggers. The model is the bottleneck at every level above one (median model latency 20 s alone, 235 s at twenty); no throughput work follows from that here. After the phase: backend 146 tests, twenty browser flows, twelve mutants killed.

**Depth after the validation phase (2026-09-29, later).** Three things read from the record, each with its measurement before its change. (1) The seven golden failures of Recording 4, run by run: three are retrieval's (the labelled section ranks 7th, 9th and 10th under BM25; `eval_retrieval.py --k 10 --ranks` shows k = 10 reaches all 38 present goldens and lifts CUAD Recall from 0.85 to 0.91), two are the model's (a misread heading, a paraphrased quote the verifier rightly withheld), two are the prompt's (a "no" about an absent point returned as pass; a false premise repeated). `answer-v3` adds three rules for the last two and for the habit, seen in 25 of 398 recorded findings, of writing a section's id as its number; `WORKBENCH_RETRIEVAL_K` makes k a run option. Both are pre-registered in `docs/GOLDENS.md` and `docs/RETRIEVAL.md` and run after the CUAD-30 batch, one variable at a time; neither is adopted yet. (2) A code check: a pass whose conclusion names a section that exists neither in the document nor among the ids handed to the model becomes needs_review with the source `reference_check`. Over the 398 recorded asserting findings it fires on 4, all wrong references (g44's §14.2, §12.1.1 for §2.1.1), and on none of the 25 id confusions, once a number is also accepted when a section number ends with it. It does not make g44 pass and is not meant to; it makes the finding honest on screen. (3) Four more hand mutants for the day's decision lines (a match starting or ending inside a word, the pack skipping the recorded hash, section text of a finished run changing): sixteen, all killed; M9's anchor had moved with the trigger loop and was skipped once before it was fixed. Every generated-example budget now scales with `WORKBENCH_FUZZ_SCALE`; the deep pass at twenty times is recorded in `docs/archive/VALIDATION.md` when it finishes. The CUAD-30 baseline is running (batch `51398ed416634c15`, 210 runs), followed on the same GPU by the two pre-registered golden runs; results go into `docs/CUAD.md`, `docs/GOLDENS.md` and `docs/RETRIEVAL.md` with the rules already written there. Backend 151 tests.

**Two traced defects closed by measurement (2026-09-29, evening; the CUAD-30 batch running on the GPU).** The comprehension pass listed sixteen things found while tracing and fixed none; the first three in order of harm are closed here, each measured against the record before the change. (1) Verifier v4. The label strip used to cut the section's number off the front of a quote on its own, compared as letters and digits, so under §1.5 the quote "15 days' written notice" lost its digits and verified against "forty-five (45) days' written notice"; and the letters-and-digits tier read "$1,500" and "$15.00" as the same six characters. A census of the record first: twenty `unprefixed` spans, every one cut by the label or the heading, none by the number alone, so that candidate had earned nothing; twenty-four alnum spans, none with a decimal point. The rule now: a label is recognised only as written, the number with its dots followed by a separator and then its heading, or the heading alone; a bare number is never cut, because digits at the front of a quote are part of what must be found. A full stop between two digits is kept in the letters-and-digits tier; a thousands separator is still dropped, because "1500" and "1,500" are one number to a reader and "$15.00" is not "$1,500". Replay over the 847 recorded spans: 9 gained, 0 lost, the same nine as before the change (the v2 gains against runs recorded under v1), nothing moved. Sixteen hand mutants, all killed; two new tests in `tests/test_spans.py`; one old expectation reversed and dated. (2) A pass was labelled "Within guidance" whether or not the run had guidance, in the chip, the Findings and Runs tables and the memo heading, next to a memo row saying "none supplied". The truth now travels with the objects that are labelled: `RunOut.has_guidance` and `FindingRecord.has_guidance`, one `statusLabel` function in `src/lib/types.ts` and one `status_label` in the memo, "Within guidance" only with guidance and "Answered" otherwise, from prompt rule 5, which says a pass without guidance is a plain answer. OpenAPI and the generated types regenerated; the hook fixtures carry the field. Backend 155 tests; interface checks and seven unit tests green; the twenty browser flows replayed. Not touched: items 3 and 4 of the list (status computed from the model's `observed` and `required` without reading the quote; the event stream after staleness recovery), next in order.

**The model's stated positions are checked against the record (2026-09-29, evening, continued).** Item 4 of the traced list: `decide()` computed a status from the day counts in the model's `observed` and `required` without reading the quote it had just verified or the guidance, so a verbatim "thirty (30) days" quote could sit under an `observed` of "90 days" and the pass be computed from 90; "no longer than", "not to exceed", "up to" and "no later than" were read as minimums; "twenty-one (21) days", "30 (thirty) days" and "20 Working Days" parsed as no count; `AT_LEAST` was defined and unused. The census first, over the 595 findings of complete runs: nine statuses had been computed from day counts, and in none did the observed count fail to appear in a verified quote or the required count fail to appear in the guidance; no recorded `required` used a phrase the ceiling list missed; fourteen recorded quotes and positions said "Working Days" and parsed as nothing. So the rule is guarded rather than a failure repaired, and the parser gains fourteen real counts. `decide()` now takes the verified quotes and the guidance text: a day count stated as `observed` must appear in a quote, one stated as `required` must appear in the guidance, or the finding is needs_review with the source `position_check`, shown in the drawer like `reference_check`; then the comparison as before, with the ceiling phrases extended and `AT_LEAST` removed because at-least is the default reading. A working day is compared as a day, as a business day already was. The SkillOpt environment keeps its positional call and therefore its old behaviour, which is recorded here rather than changed under a finished experiment. Three tests in `tests/test_retrieval_and_status.py`; backend 158 tests.

**A run's end reaches its stream, and a failed worker does not fail twice (2026-09-29, evening, continued).** Items 12 and 13 of the traced list. The event stream replayed the stored stages and then waited on the in-process bus, which only this process's workers wrote to: a run ended by staleness recovery, or by a batch runner in another process, left its open streams receiving keep-alives forever. Two changes, each with a test that drives the stream generator directly, since the HTTP test client buffers a streaming response until the application finishes it: recovery now publishes the failed stage on the bus, so a stream in the same process ends at once (measured under a thirty-second heartbeat: well under a second); and at every heartbeat the stream re-reads the run's stage from the record, so a run ended by any process ends its streams within fifteen seconds, tested with a raw update that no bus ever hears. The failure handlers wrote the failure into the session that had just failed: at twenty concurrent runs the day before, recovery in another process ended live runs, their workers' next write hit the immutability trigger, and `_finish` raised again out of the background task. `_fail` rolls back, re-reads the run, keeps another writer's record when there is one and records the failure otherwise; the test reproduces the collision by recovering the run from inside the fake model call. Three mutants for the three decision lines (M17 to M19), all killed; nineteen in all. Backend 161 tests.

**One document per bytes and reader, one memo per run (2026-09-29, evening, continued).** Item 11 of the traced list. Both lookups ran before their inserts with nothing in the database to refuse a second row, so two concurrent first uploads of the same file could store two documents, and two concurrent first memo requests two memos, the second overwriting the first's file while the first's row recorded the first file's hash. The record before the change: no duplicate under any versioned reader; the six and three duplicates that exist carry a NULL reader version from before versioning, which a unique index treats as distinct, so the index goes onto the existing database at startup without touching them (checked on copies of the working and the browser-flow databases). Two unique indexes, `ux_documents_sha256_parser` and `ux_memos_run_id`; a request that loses the insert rolls back, re-reads and is handed the winner as a reuse; the memo's DOCX is written under `memos/pending/` and moved into place only after the row is in, so a loser deletes its own file and never touches the winner's. The tests make the lookup miss on its second call, which is exactly what a request sees when another request inserted between its lookup and its insert. Two mutants (M20, M21), both killed; twenty-one in all. Backend 164 tests. Left from the traced list, in the order of the handoff: the browser flow named "refresh mid-run", which reloads after the run has finished and needs the replay provider to hold a run; then the DOCX content the reader drops silently and the unguarded parser paths (items 7 to 10), each to be measured before it is changed.

**A browser flow that only passed on a fresh database (2026-09-29, evening, continued).** Running the twenty flows three times in one evening showed two things the single runs of earlier days had not. First, one flow failed once under CPU contention (a build, the backend suite and the GPU batch at the same time) and passed alone: not a defect, and the run is recorded as such. Second, "a confirmed finding stays confirmed after a reload" failed on the third run because the flows share one data directory across runs and the run is reused by fingerprint, so the finding it clicks Confirm on was already confirmed by the run before; the flow had only ever passed on a database that had not seen it. The flow now undoes an existing review first, which is itself an append-only review, and passes on a used database. The data directory is deliberately not wiped between runs: reuse across runs is what the flows exercise.

**The hardening program, first evening (2026-09-29, late).** Pavan handed over a design that reads the workbench as an information system rather than a product: a file becomes a known reading, a retrieved section an exact model context, a model answer a proposal, a located quote source integrity and not truth, a legal value a fact only when parsed from evidence, a run a reproducible historical event, and a dependency something that has to earn its place with a reproducible failure. Its own first rule was kept: nothing on the run path (reader, retrieval, prompt, verifier wiring, status wiring, model) changed while the CUAD-30 batch and the pre-registered golden runs were still on the GPU, so those measurements are not contaminated. What follows was done beside the run path; the wiring waits for the chain.

*Show me exactly what the model saw.* `application/reconstruct_input.py` rebuilds, from the record alone (question, guidance, prompt version and hash, `candidates_json`, the immutable sections), the system and user messages of any run and hashes them against the input hash the checking stage wrote at the time; it also yields every candidate's ContextSlice (the first 5,000 characters, its hash, whether it was truncated). `scripts/reconstruct_inputs.py --all` over the 515 recorded runs: every run since 08:05 UTC on 28 September rebuilds exactly (458 of 458, 2,756 slices, 455 truncated); the 57 before that were produced by an earlier message format, and one of them by an earlier text of `answer-v2.md`, which no longer exist, so their exact input is not reconstructable and the script says so. The lesson is made a rule: `prompts/manifest.json` records each prompt file's sha256 and a test fails when a prompt is edited in place; a change is a new version file.

*A run's stream survives a reconnect and a refresh.* Stored stage events now carry their row id as the SSE id; a client reconnecting with `Last-Event-ID` (or `?after=`) is replayed only what it missed, and the final word still comes. The follower in the interface is a state machine (`useRunFollower`: idle, starting, not_started, following, loading_record, finished, disconnected) with no run without an id, no finished run without its record and no record beside a spinner: the terminal stage is never applied from an event, only from the record fetched after it, so findings and stage arrive together; polling retries five times before it reports; a dropped stream leaves a disconnected state with a resume; a new upload stops the previous follower and closes the drawer; a run loaded from the record that is still in flight is followed. The URL carries the run id as soon as the run exists, so the flow named "refresh mid-run" now refreshes mid-run: the replay provider holds its recorded answer back for eight seconds when the question carries `[[zzdelay]]`, the page reloads while the run is checking, reattaches, and shows the result of the same run. Two things were learned making that flow honest. A marker with digits in it ("[[delay:8s]]") reached BM25 as a query term, "8" is a section number in the contract, the candidates changed and the recorded answer no longer matched; the marker carries no digit and no English word now, and the provider says why. And a test server killed with a delayed model call pending left a run in flight that the next identical question was handed for the whole staleness window; `runs/owner.py` records which process opened a stage (host, pid, start time from the operating system, no dependency) and can tell that such a process is gone, so recovery of exactly those runs can be immediate while other hosts' and live processes' runs still wait for staleness. It is written and tested, not yet written into the stage rows: that is the run path.

*A memo says which review state it describes.* Memo identity is (run, review head), the head being a hash over the findings' latest review rows including undos; a review after a memo earns a new memo and the earlier one stays what it was, byte for byte; the head is in the DOCX properties and the memo footer; the run reports its current head and the Assistant says "Review memo predates a later review" and offers a new one; the Assistant re-reads its finished run from the record when it is shown again, so reviews made on the Findings surface reach the drawer and the memo without a stale copy. The unique index of the same afternoon moved from (run) to (run, review head).

*Typed values, written and measured, not yet wired.* `policy/durations.py`: durations parsed by code with their unit (calendar day, business day, week, month, year), Decimal never float, words checked against digits ("twenty-one (30) days" is ambiguous, not a choice), a guidance rule with the comparison the guidance states (a bare notice requirement is a floor, written down once), an observed fact parsed from the verified quote where the model may only choose among the quote's durations, and an evaluation that compares only what is comparable (weeks convert to days exactly; months, years and business days do not). `verify/tokens.py`: the letters-and-digits tier's replacement, under which a number is a value and a run of letters is a word: "$1,500" and "$15.00" differ, "15%" and "1.5%" differ, punctuation and quotation marks carry nothing, and a match is a whole number of tokens with its count of occurrences, so an ambiguous location is known to be one. Measured against the 1,058 recorded spans before any wiring: of the 53 spans the alnum tier had verified, the typed tier keeps 52 and loses one that the label strip owns; it finds 3 the ladder had withheld (all curly-quote cases); it moves none. Four spans were kept only after a measured concession: the reader's own text carries joined and split words ("advisedof", "thesame", "speci fying"), so words are compared as letters at word boundaries and a missing or extra space between words is forgiven, while a number is never joined ("1 5" is not "15") and a word may never begin inside another ("ice cream" is not in "notice cream"). Eight recorded matches occur more than once in their section; today the first bounded one is highlighted and nothing says so.

Backend 216 tests. Next, once the chain has finished and its results are recorded: verifier v5 (typed tier in place of alnum, matches bounded to the ContextSlice the model saw, match count on the span), status from typed facts (`position_check` becomes the policy evaluation with its reasons), stage owner and immediate recovery of dead owners, the explicit run transition table, ParseCoverage in the reader with an honest list of what a DOCX reading omits, the evidence pack carrying reconstruction, slices, coverage and review head, and provider admission measured before anything is scheduled.

**CUAD-30 recorded; a reading says what it did not read; three measurements taken before the wiring (2026-09-29, late).** The CUAD-30 batch finished at 19:59 local: citation precision 0.85 against the pre-registered floor of 0.80, recall 0.67 against 0.50, so the clause lookup is fit to draft a repository review of the seven categories, with non-compete (precision 0.20) and uncapped liability (0.60) named as unfit on their own; 7 of 25 misses lacked the expert span among the retrieved sections, under the one-third trigger, so BM25 did not fail this measurement. The table and the reading of it are in `docs/CUAD.md`; nothing was retuned; the golden runs that followed on the GPU are recorded when they finish.

ParseCoverage (`ingest/coverage.py`). A DOCX "parsed successfully" while its headers, footers, footnotes, endnotes, comments, block-level content controls, embedded objects and imported chunks were never read, fields kept only their cached result, and automatic numbering was not rendered. A census of the 36 licensed contracts and the sample first: 32 have footers with real text, 12 headers with real text, 2 footnotes, 5 content controls, 17 fields, 27 automatic numbering. The reading now records, at upload, what it did with each of seventeen fixed parts (read, accepted, excluded, partial, omitted, absent, unknown) with a count and a note; the document carries it, the paper says "Not read by this reading: footers (1)…", and the evidence pack records it under `parse_coverage`. The section text is unchanged, so the reader version stays v4 and no document is re-read; a reading made before coverage was recorded is described from its stored bytes under the same reader, on demand and never written back, because a document a finished run read is immutable. The invariant, in one line: anything the reader does not read is represented as unread.

Two measurements for the run-path wiring that waits for the chain. The verifier searches the whole stored section while the prompt showed at most 5,000 characters of it: over the 976 verified spans in the record, none ends beyond that window, although 495 sections handed to the model were longer; bounding the search to the slice the model saw will change nothing recorded and closes the gap in principle. And the run lifecycle is now a table (`runs/transitions.py`): the happy path, the early exits to unresolved and failed, and nothing else; a finished run cannot move; skipping ahead and going back are impossible by construction; 29 tests, wired into the stage writer with the rest.

Backend 251 tests; the twenty browser flows pass on a used database, including the real mid-run refresh and the dropped stream, now that a delay marker with a letters-only nonce gives them a fresh run in flight.

**Admission to the model, the hostile-package envelope, and the parser tournament pre-registered (2026-09-29, night).** Every measurement says the model is the bottleneck and the GPU serialises calls anyway; what an unbounded API added was contention with no record of it. `providers/admission.py` is a semaphore and two queues: calls in flight bounded (`WORKBENCH_MODEL_CONCURRENCY`, default 1), an interactive queue and a batch queue served four to one so a person is answered first and a corpus job still moves, every call recording how long it waited and how long the model took, and the checking stage saying "queued 12 s behind 3" when it did. A first-come policy exists beside it for one reason: the measurement that decides whether the weighting earns its place (`scripts/measure_admission.py`, both policies over the same work against the live model), which runs once the wiring is in. Nothing distributed: no Redis, no Celery, no queue that survives a restart, because no requirement asks for one yet.

Uploaded files are hostile data, and the envelope is now written as tests rather than remembered: an entity bomb in the document part and three-thousand-deep nesting are refused as unreadable packages within a fiftieth of a second, before any expansion; a package with twenty thousand members is read in half a second; each reaches the API as a 422 with the reason and nothing stored; an external relationship makes no network call (from the day before). Process isolation for the reader is not built: nothing in these measurements needed it, and public uploads are not a deployment this repository has.

The parser tournament is pre-registered in `docs/archive/PARSER-COMPARISON.md` before any challenger ran: Docling (MIT) and Docxodus (MIT) against reader v4 on the licensed corpus and the adversarial fixtures, through one adapter contract, judged on accepted-view correctness (one failure ends it), exact-quote retention from the record, coverage of the parts v4 omits, reading order, and cost (three times v4's wall time, 1 GB); two of five lost ends it. The harness (`experiments/parser_tournament/run.py`) and a research venv under `data/tournament/` keep every challenger out of the application's dependencies. Baseline recorded first: reader v4 retains 100% of the record's exact quotes on every corpus document; the largest contract (1.25 million characters) takes 44 to 48 s and 30 MB, the rest under 5 s.

Recording 5, first part: `answer-v3` at k = 6 against Recording 4, 37 of 44 to 37 of 44, one gain (g11, the "no" about an absent point now "not found") and one regression (g30, the dispute-window quote dropped words and was withheld), mean model latency +6.3 s. Under the rule written before it ran, no regression and at least one gain, answer-v3 is not adopted; the k = 10 measurement therefore runs against answer-v2, and its result is recorded when it lands.

**Three small closures while the golden runs finish (2026-09-29, night).** Whitespace-only guidance was stripped to nothing, stored, and the status logic told guidance existed; it is refused now with a sentence that says what to do instead, so guidance is text or absent and nothing in between. An upload's 25 MB rule ran only after the whole body was in memory, and the parse ran on the event loop; the declared size is refused before a byte is read, the bytes are checked again once read, and the parse runs in the thread pool, because the tournament baseline measured 44 s for the largest licensed contract. The evidence drawer showed the guidance in the composer at the moment it was opened, not the guidance the run was given; the run now carries its guidance text and the drawer shows that, so an old run opened under new guidance says what it was actually checked against. Reuse of identical bytes under any filename stands: the same bytes are the same document.

**Recording 5 judged, nothing adopted (2026-09-29, night).** The three pre-registered golden runs finished on the GPU after the CUAD-30 batch, one variable at a time. answer-v3 at k = 6: 37 of 44, the same as answer-v2, one gain (g11) and one regression (g30), +7 s median; the rule asks for no regression, so v3 is not the prompt. answer-v2 at k = 10: 38 of 44, the three retrieval misses (g08, g12, g35) now passing and two goldens that passed at k = 6 now failing (g39 withheld, g43 the injected instruction answered "not found"), median model latency +57% with four of the runs slowed by a build and a Docling parse on the same machine, which is written down and does not change the verdict; the rule asks for no regression and less than half, so k = 10 is not the default. answer-v3 at k = 10: 38 of 44 (against answer-v2 at k = 10: gains g39, g42, g43; regressions g04, g08, g35; mean latency −5.0 s), informational, since neither variable earned its place alone. Both remain available by option and neither moves the defaults; the record keeps every run under its own identity. The lesson beside the result: a measurement on the one GPU must own the whole machine; the browser-flow build and the parser tournament were stopped once the slowed runs were seen, and the tournament reruns after the chain.

**The run path rewired, after the chain (2026-09-29, 21:35 to 22:15 local).** With the GPU idle and Recording 5 in the record, the modules written earlier in the evening went onto the run path in one pass, each behind the measurement taken for it. Verifier v5: the typed tier replaces the letters-and-digits tier; the search is bounded to the first 5,000 characters of each candidate, which is what the prompt carried; every located span records how many places the quote occurs under its tier, and the drawer says "occurs 3 times in the section; the first is highlighted" when it does. Two things the property tests said the moment the tier went in, both kept as the stronger rule: a typed match may not split a run of letters and digits either (so "0" is not found in "0A", and a mixed run like "A1" is one word), and numbers keep their precision ("15.00" is not "15"), because a verifier forgives spelling, never precision. The replay over the whole record, now 1,299 spans with the evening's golden runs: 10 newly verified, 0 newly unverified, 68 spans whose tier is now called typed instead of alnum and whose offsets did not move. Status: `decide()` parses the notice period from the verified quote and the requirement from the guidance text (`policy.durations`); the model's `observed` and `required` may only choose among the quote's durations, a count they state that the evidence does not carry is `position_check`, an internally inconsistent quote is `ambiguous_fact`, months and business days are incomparable and fall back to the hint, and a computed status carries its sentence ("the contract provides 15 calendar days; the guidance requires at least 30 calendar days") on the finding and in the drawer. A test that expected a status computed from the model's numbers alone now expects the hint, which is the point. Stage rows name their process (`runs/owner.py`), and recovery fails at once a run whose process provably no longer exists on this host while everything else still waits for staleness; the transition table is checked wherever a stage is written; every provider a process hands out is admitted through the shared controller, interactive from the API and batch from the batch and golden runners, and the checking stage says how long a call queued. The evidence pack names verifier v5 and its window, records each span's match count, and its `verify.py` re-checks typed spans with a standard-library copy of the tokenizer, refusing a changed value. Eight mutants for the new decision lines (M7 rewritten for the typed tier, M22 the window, M23 the status from the quote, M24 the transition table, with M17 to M21 from earlier); the whole set of twenty-four is run after this entry. Backend 262 tests; interface checks green.

**The mutants after the wiring (2026-09-29, 21:49 local).** Twenty-four hand mutants against the suite: nineteen killed, two survived, three skipped because their anchors had moved. The two survivors are the reason the script exists: nothing had tested that a quote beyond the 5,000 characters the model was shown is refused (M22), or that the stage writer refuses an impossible transition (M24); both boundaries were in the code and in the prose and in no test. Each has its test now, the three anchors follow the code (the decide call is several lines, a provider failure goes through `_fail`, the memo index is named for its two columns), and the rerun kills all five. Twenty-four of twenty-four, and the two that survived are written down here rather than quietly fixed.

**Admission measured, the weighting earned (2026-09-29, 22:18 local).** The controller went in behind a measurement, and the measurement was made once the GPU was free: the same work (nine batch calls with two workers, four interactive questions one after another, one call in flight) under first-come and under four-interactive-per-batch. First come: the person waited 58 to 120 s per question and finished in 705 s. Weighted: 32 to 70 s and 534 s, the batch's total 778 s instead of 735, no call starved. The numbers are in `docs/SCALE.md` with what the controller does not do (cross processes). Each call's wait is on its stage row, so the queue is part of the record.

**The parser tournament, first round, decided against the challenger (2026-09-29, 22:38 local).** Docling against reader v4 over the twenty licensed DOCX contracts and the sample, under the five criteria pre-registered in `docs/archive/PARSER-COMPARISON.md` before it ran, with the machine otherwise idle (the first attempt had been stopped when it slowed the golden runs). Reader v4 reads all twenty and retains all 292 exact quotes the record has on them in 25.7 s; Docling reads nineteen, retains 256 of 292, loses quotes on ten documents, and takes 1,026 s, thirty to sixty times the reader on most files and 419 times on the largest. Two criteria lost of five ends it, and the other three were not scored. The honest answer to the parts a reading omits stays coverage, declared on the paper and in the pack; a reader that reads headers and footers is entered against the same criteria when one is adapted, and it must keep every exact quote first.

**The evening's work committed, and the repository set up again from nothing (2026-09-30, 02:15 local).** The eighty-seven changed files went to `main` as eleven commits, each materialised on its own and green before the next (the verifier v4 change was folded into the v5 commit rather than reconstructed as a state that never ran); the pre-commit tree is kept as a local snapshot ref, not pushed. Then a fresh clone of the pushed `main` was set up using only what the README says, and every documented command passed: install, ruff, mypy, import-linter, 266 tests, the API on 8000, the generated types with no drift, the interface checks, 10 unit tests, 20 browser flows. Three things the clone found are recorded here before they were touched, and fixed in this entry's commit with no change to the application: the README said 264 backend tests and 7 unit tests (266 and 10); no step said to install Playwright's browser, and the flows passed only because this machine already had it; and `python -m venv` failed once at `ensurepip` under a Windows short-name path (`…\NAME~1\AppData\…`) and succeeded under `C:\Temp`, which is the environment, not the repository, and is now a note under the checks.

**A never-seen contract through the product, and "Why this answer?" (2026-09-30).** Phase 1 of the public-demo plan: a CUAD reseller agreement the workbench had never read, as a plain DOCX, through every step a stranger takes, read back from the record (`docs/DEMO-PROOF.md`). The model proposed `pass` for sixty days against a ninety-day floor; code recorded `needs_review` with its sentence. The document also exposed two reader facts to measure, not fix: headings in a DOCX are recognised by style only, so typed numbering becomes 6,000-character parts; and the part size exceeds the 5,000-character prompt window, so 13% of that contract never reached the model. Phase 2, approved with three corrections. The explanation of a run is one read-only projection owned by the API (`application/explain_run.py`, `GET /api/runs/{id}/explanation`), and the interface renders it and decides nothing. The model's proposal is its stored raw output parsed under the shape it was asked for and correlated to findings by ordinal, never guessed from a finding's text, and an older run whose output does not fit says "Model proposal not reconstructable for this run."; `status_hint` was not added to the finding, because a proposal is not a finding. A SourceMatch is inside the model-visible context only when its offsets lie within the reconstructed ContextSlice of its section, not because they are under a constant. No typed fact or rule is recomputed by today's parser and shown as what the run established: the status, its source and its sentence are shown as recorded, beside the model's observed and required phrases labelled as the model's words. Killed for now: retrieval scores (not persisted; the run path is not changed for a demo) and the fingerprint on the primary surface. The Runs note that called the candidates "in document order" was wrong and says "in rank order" now. The acceptance case is the Phase 1 run itself: its recorded explanation is a unit-test fixture, and the live drawer showed every row of it. Backend 275 tests, interface 13 unit tests, twenty browser flows.

**The data audit, instead of a second store of truths (2026-09-30).** Phase 3 was to be an Evidence surface built from a checked-in `evidence.json` of copied results; Pavan killed that form because a file of copied numbers is a second truth that drifts, the class of problem the day had been spent removing. What is built instead is smaller and answers only what a public claim needs: `scripts/data_audit.py` lists every agreement this repository has touched by SHA-256, with its source, its licence (the corpus provenance file, the CUAD archive's SOURCE.txt, the sample's attribution; otherwise "not recorded"), its role (evaluation, fixture, runtime) and the measurements that touched it, from the manifests in the tree, the store and the records outside git; it keeps every denominator apart (44 questions on one contract, 30 CUAD text files, 20 corpus agreements, 1,351 spans, 24 mutants, 20 flows) and states the strongest claim they allow, which is never "tested on N contracts", because the sets overlap and a span, a question and a contract are not one unit. It copies no result from any document; the results stay where they were recorded with their regeneration commands. On this machine's store it found 87 distinct agreements, 80 of them evaluation data under a recorded licence, five uploaded through the API by the builder and behind no number, and the sample under three names. A global Evidence page, if it is still wanted after the live link, is a registry of references to those records, not of copied truths. Backend 277 tests.

**Published at ivo.pavankg.dev, and one defect the public smoke test found (2026-10-01, 01:00 to 02:30 local).** The laptop is the server for the outreach window: Cloudflare Registrar for `pavankg.dev`, a dashboard-managed tunnel `ivo-workbench` with `^/api` → 8000 and everything else → 3900, Cloudflare Access with an email allowlist in front, the connector as a Windows service, the API with `WORKBENCH_APP_URL=https://ivo.pavankg.dev` and the interface built for that origin. The smoke test through the public edge, from Chrome: health, landing, the hero run by URL, the drawer and "Why this answer?", the evidence pack (74,780 bytes, verifies), the event stream (stage events with ids, the final event, the stream closed), the Runs record, then a fresh question on the same contract: a new run, the stages arriving over one stream with no polling, a reload during checking that reattached to the same run, completion with two findings whose quotes verified, and a pack whose `verify.py` passed with no failure. One defect, real and reproducible with the tab in front: clicking a citation scrolled the paper to the top of the section, not to the passage, so on a 6,000-character part the highlighted quote sat below the fold; on the sample's short sections the two coincide, which is why twenty browser flows never saw it. `jumpTo` now scrolls to the mark itself once it has rendered, and to the section's top only when there is no span; the twenty flows pass, and both runs put the passage at the top of the pane through the public URL. One thing that is not a defect: a Chrome tab in a covered window throttles animations, and the landing-to-workspace transition waits until the tab is visible; the data had loaded. Nothing else changed.

**The depth pass: three sweeps, a hostile review, and what each one earned (2026-10-01, 02:25 onward).** Pavan asked for the opposite of a smoke test: every page, every document shape, the search, the model path, the field's published practice, a hostile read of the code, and then only the changes that could show their failure. Three agents worked on an isolated stack (API 8010, its own store) while the public one stayed frozen. The research is in `docs/RESEARCH.md`: what Ivo, Harvey, Spellbook, LegalOn, Hebbia and the benchmarks actually publish, claims kept apart from evidence, and ten additions ranked under this repository's rules; the alias table was the one cheap enough to build and measure the same day. The reader sweep uploaded 115 files (`research/depth_pass/reports/reader-sweep.md`; the generator and seven of its files are checked in beside it and under `backend/tests/fixtures/reader/`): no 500 anywhere, and eight things that were wrong without saying so. The interface sweep drove 7 model runs and 115 screenshots through the product (`research/depth_pass/reports/ui-sweep.md`): 23 defects ranked, four of them in the path a stranger takes. The hostile review of the code found 26 things (`research/depth_pass/reports/code-review.md`), six of which had a test written before the fix.

What changed, each behind the test or the census that found it. Reader v5: a block-level content control and a table nested in a cell were dropped while coverage called them read (the sample's own security checklist, a table inside a control, was never in the record; it is now, so the sample's §2 text differs under v5 and old runs keep their v4 reading by parser version); a UTF-16 or Windows-1252 text file became replacement characters with a 201 (decoded by mark, NUL pattern, strict UTF-8, then Windows-1252, the encoding named in coverage); a 100,000-character first paragraph became a 100,000-character title that reached the prompt whole and held the GPU for 24 minutes until the provider timed out (a title is 200 characters now, and a paragraph longer than a section is split at sentence ends so nothing is cut by the window); a textless PDF page was "unknown" when it was known (counted as omitted); a known file under a `.docm` name or no name was "reused" past the type check (the name is checked first). Policy: the rule was the first duration in the guidance, not the one about the finding's topic ("Payment terms are 30 days. Termination needs 90 days' notice" gave a 30-day floor to a termination finding); the comparison word was the first in the sentence, not the nearest ("at least 30 but no more than 90" was a 90-day floor); a floor and a ceiling are a range; "no later than 30 days before" is a floor; "30-day", "thirty-day", a fortnight and "immediately" (zero notice) parse; the number-word pattern is atomic, so a hostile guidance is linear. Lifecycle: a run held a request thread through the queue and the model, so forty runs starved every other route (runs execute on their own pool now); recovery declared a live run stale while it waited its turn behind a long one (a run whose process is alive on this host is never stale; the restarted public API, on the old code, killed two of the day's golden runs exactly this way before the fix was deployed, and they were re-run). Memo: a form feed in the guidance made the memo a 500 (XML-unsafe characters are stripped at the sinks); two memos for one run raced on one pending file (a directory per request). Upload: a name with path parts reached the pack as a path (base name only). Interface: Enter started a second run while the Send button was disabled and abandoned the one on screen; a question over 2,000 characters vanished under a raw validation error (the field stops at the limit and a refused question stays in the composer); a refused guidance's sentence outlived the accepted one; Tab left the palette dialog; a highlight after an astral character was off by one (offsets are code points, so the slice is too); a sign-in page in place of data read as a JSON parse error; a dropped stream was a dead end (a Reconnect control). And the chip a lawyer reads most: "Within guidance" appeared on findings whose status was the model's hint, including two that said the contract provides no notice period at all; a pass the model hinted now reads "Within guidance (model's view)" on the card, the Findings table, the Runs record and the memo, and "Within guidance" is reserved for a comparison code made.

Two options, recorded on the run and measured before any default moved: `WORKBENCH_SECTION_WINDOW` (the 6,000-character part against the 5,000-character prompt window: a census over the CUAD-30 record found 45 of 111 expert spans in sections longer than the window, 4 starting beyond it and 2 cut by it) and `WORKBENCH_RETRIEVAL_ALIASES` (seven concept groups as data, versioned by hash; without a model, Recall@6 on CUAD-30 0.91 → 0.99, SkillOpt 0.81 → 0.96, uncapped liability 0.44 → 1.00, non-compete 0.69 → 0.94, the goldens' own Recall@6 unchanged at 0.92). Their golden recordings and the verdicts are the next entry.

Not changed, with the reason: typed numbering and `w:numPr` paragraphs as headings (a reader change gated by the parser tournament, and the retrieval unit question behind it); PDF running headers and two-column pages (needs page geometry); style-hidden text (needs style resolution); conclusion prose that quotes the contract shown with the weight of verified spans (a product decision about what "Answered" means); queue position and cancel (an architecture change while the deployment is frozen); `sec_N` leaking into prose as §N (a prompt rule, which means a golden recording). One incident, cause not found: the public API process and the exploration API both ended around 02:37 local with no log line; the public one was restarted at 03:36 from a checkout of the deployed commit against the production store, and the interface process never stopped.

**Two defaults moved, each under its rule (2026-10-01, 04:00 local).** The window: 37 of 44 goldens at 6,000 against 37 at
5,000, the same seven failures, and four of the six CUAD cases whose expert span lies beyond the old window now answered
from it against two; the reader's split and the prompt's window are one number, recorded on every run, and a run recorded
before the option is read back at 5,000 by a constant that does not move. The alias table: 37 of 44 on against 37 off, no
regression, no gain on the goldens, which its unchanged golden Recall@6 had predicted; its earning is Recall@6 on the two
CUAD sets, 0.85 to 0.97, measured without a model. Both recordings shared the GPU, so their latencies are not compared.
What remains before anything is deployed: one recording of the 44 on the reader-v5 document with both defaults on, alone
on the machine, which must show no regression against 37; then the browser flows re-recorded, since the sample's text
and the prompt's window both changed.

**Recording 6c, and what a filename did (2026-10-01, 04:40 local).** The confirmation of the combined tree, alone on the
GPU: 37 of 44, one gain (g44, the false premise no longer taken as true) and one regression (g30, an exact quote become a
paraphrase and withheld). Before accepting either as the reader's doing, the record was read: same six candidates, same
text, and the two model inputs differ in one line, the contract's filename, because reader v5's golden document is the
bundled sample and every earlier one was the corpus copy named `CP01.docx`. Three more runs of g30 on the v5 document
under the old window and without the table withhold the same way. The model moves on a filename; the record carries the
filename; the recording stands as the new baseline with the cause written beside it, and the defaults stand under their
own recordings. Reader v5 earns its place the way the tournament said a reader must: 377 of 377 exact quotes retained
across 35 documents, plus the sweep's fixtures as tests. The browser flows are re-recorded next, since the sample's text,
the window and the table all change the model's input.

**The Ivo audit, and the three things it earned on the frozen candidate (2026-10-01, 06:00 to 07:00 local).** Before touching the interface again, Ivo's current public product was reverse-engineered as research: fourteen pages at desktop size, the hero's three embedded demos (scripted React apps, not videos) recorded from their DOM at 250 ms, the one real recording (Collaborate, 113 s) sampled by seeking the player, every Lottie counted, computed styles measured, the support articles and both blogs read. The audit, the frame tables and 65 frames live outside the repository (`Desktop/ivo-research/visual-audit-2026-10-01/`; Ivo's media stays Ivo's). What Ivo does that matters here: the paper is the protagonist and the assistant sits beside it; the context that shaped an answer is visible as named pills; one decision object per topic reads top-down (what was proposed, what the source says, what was decided, the human action); the system's internals are absent from the lawyer's surface and an honesty line sits last; waiting is narrated. Verity already had the shape and most of the honesty, stacked in the wrong order: the model's proposal, the single most instructive fact of the hero run, was the last thing a stranger could reach, under a toggle and a scroll, beside hashes; three landing chips opened the file picker; the reader's caveat was the first coloured line on the hero document; a confirmed finding looked unconfirmed on its card.

Three changes, interface only, nothing in the record, the goldens or the defaults. The evidence drawer now reads in four fixed layers, each from the run's record: **Model proposed** (its hint, in its own words, from the explanation projection, or "not reconstructable"), **Source** (the quote, how it verified, and in words where it was found: "Found in “EXHIBIT 10.102 (part 1)”, not in the section the model cited"), **Code decided** (observed against required, the sentence code wrote, the final status, the guidance it was checked against), **Human** (the decision as recorded, and Confirm, Dismiss or Clear from the drawer itself, written back into the run on screen and re-read from the record); `sec_4`, `computed_days`, offsets and hashes moved behind one toggle, "Prove it", which renders the same explanation read once. The landing lost the three decoy chips and offers a finished review to open: the run named at build time (`NEXT_PUBLIC_PROOF_RUN`, the Phase 1 run on the public deployment), else the latest complete run with findings in the store, never a manufactured example. The reader caveat is grey and second; the card says "Confirmed by Pavan" once a person has decided; the guidance chip shows the rule's first words; the Runs view marks the run on screen. Rejected, explicitly: Ivo's palette, serif, olive buttons, Word mock and illustrations (derivative), and every production surface it owns (benchmarks, playbook builder, Skills, composites, relationships, routing, legal research), none of which a Verity invariant requires. Interface 25 unit tests (the four layers, a decision recorded from the drawer, the name asked once), twenty-one browser flows (the new one clicks the finished review on the first screen).

**Final release candidate: certification of the deployed HEAD (2026-10-01, 07:00 to 08:00 local).** The candidate after the Ivo adaptations was certified rather than extended. Nothing in the API changed after the frozen baseline (`git diff 5c99287..HEAD -- backend` is empty), so the backend evidence is the baseline's, reconfirmed: 308 tests, ruff, mypy strict, import-linter, the committed OpenAPI document identical to the running API's. One Hypothesis property failed once while the interface was being built on the same machine and passed on every rerun with nothing saved to the examples database; it is recorded as unproven, not as a defect. Recomputed on the whole store: 847 runs, 789 with a recorded input hash, 789 rebuilt to the same hash, 746 under the historical 5000-character window and 101 under the recorded 6000; the cross-projection census over all 774 complete runs found the run view, the explanation projection (its shown findings) and the findings record in agreement on counts, statuses and verified quotes, the only differences being the record list's 500-row cap. On an isolated store with the real model, the API was killed during the checking stage and restarted six seconds later: the run was recovered at once as failed with the sentence that names the dead process, its event stream ended with the final event, and asking again made a new run. Thirty-three request-shape probes on an isolated store (traversal, NUL, oversized ids, a 50 MB-inflating docx, empty and 200k-character guidance, markup in a reviewer name, twelve identical questions in parallel sharing one run id, a foreign origin getting no CORS header) passed; the one the probe called a failure, a stream for a missing run answering 200 with an error event rather than 404, is how a stream has to report it and is kept. The deployed build was then driven with trusted clicks from Playwright against the two processes behind the tunnel: the first screen's finished review reached by Tab and opened by Enter, the four layers, Prove it, Escape, View in document, the Runs surface marking the run on screen and naming the deployed commit, the evidence pack, the hero deep link under reduced motion, 200% zoom with no sideways scroll, and one fresh run on the sample; 21 of 21, no console errors. Two defects were found and fixed with tests or a demonstration: the browser flows built into the directory the published interface is served from, so replaying them on the serving machine replaced the deployed bundle (they now build into `.next-e2e`, and the served bundle's commit was checked unchanged after a replay); and the interface listened on every address rather than loopback (bound to 127.0.0.1 like the API). Recorded, not fixed, as the lowest class: the Runs list shows the 200 most recent runs and the findings record 500 rows, so an older run is not marked "On screen"; a deep link with only `view=` restores the landing first. Not done, on purpose: goldens were not rerun (the API is the baseline's), and no feature, dependency or orchestration was added.

**Published (2026-10-01, evening).** Before the twenty unpushed commits went to GitHub they were rebuilt once, locally: the same trees, author and dates, each with a subject line short enough for GitHub to show whole and the original sentence kept as the first line of the body. Three machine identifiers that had entered the unpushed history (a home-directory path in a depth-pass report, a short-name path in the fresh-clone note, a hostname in the proof record) were replaced in every tree that carried them, and the commit references in the docs follow the new SHAs. Nothing already on the remote was rewritten. Two things were added on top. The README now opens with one recorded run and six measurements instead of a feature list. And taking that picture showed a defect the certification had missed: the evidence drawer was 93% opaque and the assistant's own text showed through its rows, so it is now the same colour with no transparency.

**The zero-assumption audit of the published candidate, and what it changed (2026-10-01 evening to 2026-10-02).** The brief: treat the public repository, the deployed build and the store as the only authorities, reproduce before changing, fix what is a real defect, leave what is not, and say which is which. Public `main`, the local HEAD and the deployed bundle were the same commit when it began.

What was wrong, each reproduced before it was touched:

1. *Public `main` failed its own suite.* A fresh clone, set up from the README alone, ran 307 passed and 1 failed: the data audit's test still expected 20 browser flows after a twenty-first had been added and pushed without the backend suite being rerun. The "308 tests" the release claimed was true of the tree before that flow and false of the published one. Fixed; a fresh clone of the commit about to be published is now part of the release.
2. *A memo could outlive its file.* The memo row was committed and its DOCX moved into place afterwards. With the move failed by fault injection, the row stayed, every retry was handed that memo, and its download was a 500. The file is now in place, under a name no other request can have, before the row is committed; a commit that fails removes the file; a memo whose file is not in the store answers 404 and says so. The same order was wrong for uploads (the document row before its original bytes, and a retry "reused" the row without writing them): bytes first now, written aside and renamed, and an upload of bytes whose row has no file puts the file back.
3. *The verifier called two different texts the same.* The typed tier compared a run of words as its joined letters, to forgive the reader's own joins ("advisedof"). By the same rule "the rapist shall attend" verified against "The therapist shall attend", and "un able" against "unable". Words are now compared whole (verifier v6). The price, measured over the store before the change: 7 of 1,475 verified spans, in 5 runs, none a golden, had needed the forgiveness; from now such a quote is withheld. Recorded spans keep the tier that verified them.
4. *Code passed a clause it had not read.* A verified quote with several periods was decided by its first one, or the one the model pointed at: "90 days' notice, unless the other party is in breach, in which case 10 days" was a computed pass against a 90-day minimum. Code now decides such a quote only when every period in it leads to the same result; otherwise the finding is needs review as an ambiguous fact, with the periods named. No recorded finding rested on such a quote (12 computed passes, none with a second period).
5. *A memo dated an evening review the next day.* The review's time is stored in UTC and read back without a zone; the memo converted it as if it were local. Fixed by saying it is UTC first.
6. *An evidence pack that Windows could not unpack.* A document named with `<`, `>`, `:` or `?` was stored in the zip under that name. Inside the pack the file now has a portable name; `run.json` keeps the name as given. The pack's verifier now also checks `guidance.txt` against the hash the run recorded (an edited guidance file used to pass), and the pack's "verifier" block says it describes the build that wrote the pack, since a span's own tier is the record of what verified it.
7. *An expired sign-in read as an outage.* Access answers an expired session with a redirect the browser will not follow for a data request, so the request simply fails, and the interface said only "not reachable". On an https origin it now adds that the sign-in may have expired.

What the README claimed too strongly, corrected there: "code decides the status" (of 1,199 recorded findings code computed 20, lowered 17 by the reference check and withheld 118; the other 1,044 carry the model's hint, recorded as that); "a person confirms" (the reviewer is a name the browser sent; the application authenticates no one, Cloudflare Access decides who may enter and the application does not read who that was); "byte for byte" (true of the 791 runs that recorded an input hash, all of which rebuild to it; 58 older runs recorded none); the CI paragraph (the workflow exists only on a local branch and has never run; no CI, said plainly); "a tampered pack fails" (for the document, the sections, the guidance, the spans and the model input; the pack is not signed and an edited status or question is not detected); the unit-test count in the commands (13, then 25, now 27). And one claim of the certification entry above is withdrawn: "a deep link with only `view=` restores the landing first" was an artefact of a hidden browser tab, in which the page's transitions never run. Driven in a visible browser, `view=findings`, `view=documents` and `view=runs` each open their view, a malformed or missing run or document lands on the first screen with "run not found" or "document not found", and Back, Forward and Reload keep the state.

What was measured and left alone, because nothing measured earned a change:

- SQLite: WAL, foreign keys on, the driver's 5 s busy timeout, a pool of 5 plus 10. At 5 and at 20 concurrent writers of each kind (guidance, run starts, reviews, memos) nothing was refused or lost and every run kept its five stage rows. A writer blocked by a lock held 2 s waited and succeeded; held 8 s, it was a 500 after 5 s with nothing written; reads were never blocked. Under a load this deployment cannot produce (eight clients starting runs continuously against a model that answers in no time), 6 of 200 operations hit `database is locked` and ended as one refused request and five honestly failed runs. No retry or longer timeout was added.
- The executor and the queue: 5, 20, 64 and 80 distinct runs at admission limit 1 all completed with one model call each; twelve identical questions in flight were one run and one call; a provider that fails once costs two calls, one that stays down costs two and an honest failed run, the user's retry two more; polls and stream opens start nothing.
- Reviews: append-only by the code, not by a trigger; two reviewers deciding at once are both kept and the row committed last is the state, by row id, not by timestamp (a later row with an earlier clock still wins); eight identical decisions at once wrote one row.
- List endpoints: the Runs list returns 200 rows with 203 queries, the findings record 500 rows with 1,502; at 5,000 runs that is 0.15 s and 0.7 s. The document filter is applied before the cap (an older document's findings are returned at every size). N+1 by construction; no pagination or eager loading was added for a store of 849 runs.
- The store, on a snapshot taken with the online backup: integrity and foreign keys clean; every run's document and guidance hashes agree; 1,475 of 1,475 verified spans recover their quote at their offsets under their recorded tier; 4 of 4 memos have their file and hash; 4 of 92 document rows have no original bytes (three from before originals were kept, one under reader v2), reported and not touched. The snapshot restored into a working application in another directory.
- The edge and the application, kept apart in `deploy/README.md`; no security headers were added.
- Supply chain: no known vulnerability in the locked Python dependencies or in the interface's production dependencies; two moderate advisories in the test runner, development only; nothing was upgraded.

Honest boundaries (unproven or by design): the reviewer's identity; what happens at logoff and reboot (by the task's trigger, not tested); a run created but not yet started when the process dies waits the staleness window before it is failed; the model's retrieval and decoding settings are read from the process at execution and recorded at start, the same values by construction, not by enforcement; guidance has no unique index, so two identical first saves can make two rows; the sample's Word metadata carries its publisher's author name, as published.

Killed again, with nothing new to earn them: a second datastore, a queue outside the process, vector retrieval as the default, accounts, rate limiting, pagination, security-header middleware.

Counts after the audit: backend 318 tests (308, five for the memo, four for uploads and the pack, one for the several-periods rule), 24 hand mutants killed, interface 27 unit tests (25 and two for the failed-request sentence), 21 browser flows. Goldens not re-recorded: 37 of 44 stands as recorded under verifier v5, and v6 moves no golden span. Reconstruction recomputed with the changed code: 849 runs, 791 with a recorded input hash, 791 rebuilt to it, 688 under the historical 5,000-character window with no recorded option and 103 under a recorded 6,000. Cross-projection recomputed: 775 of 775 complete runs, 1,081 findings, no disagreement. The chaos journey on an isolated store over real HTTP, with the server process killed and restarted (duplicate ask, lost stream, poll, reconnect, process death, retry, outage, wrong citation relocated, policy against the model, concurrent reviews, interrupted memo, tampered pack, restart, input rebuilt): 25 of 25 steps ended in an honest state.

**The audit's last finding, and the release (2026-10-02).** One more thing was wrong, found while checking the README's own number against the repository's own script. `scripts/reconstruct_inputs.py --all` printed "the reconstructed input does not hash to what the checking stage recorded" for 56 runs and exited 1. Those runs had recorded no hash at all: the checking stage began recording its input on 2026-09-28 at 08:05 UTC, and the 58 runs before it have nothing to compare with. The same sentence appeared in their explanation and in their evidence pack. A comparison that could not be made was being reported as one that failed. The reconstruction now says the run recorded no input hash, the script counts those apart and fails only on a run that recorded a hash and does not rebuild to it, and a test holds the wording. By SQL and by the script, on the store as it stands: 850 runs, 792 recorded an input hash, 792 rebuild to it, 58 recorded none (one of them also under a prompt text since replaced).

The probes behind the audit entry above are in `research/final_audit/`, with what each printed. Backend tests are 319 (the 318 of the entry above and this one).

The release, in order. A fresh clone of the commit to be published, set up from the README alone, passed every command: install, ruff, mypy, the import contracts, 318 tests, the OpenAPI document and the generated types with no drift, 24 of 24 mutants killed, the interface's checks, 27 unit tests, 21 browser flows, and a clean tree at the end. That commit was pushed as a fast-forward and deployed; the Runs surface named it. Against the two deployed processes: the first screen's finished review opened by keyboard, the four layers, Prove it, Escape, View in document, the Runs surface, the evidence pack, the proof run under reduced motion and at 200% zoom, 19 of 19; a fresh question on the sample answered in 92 s with two findings and four verified passages, its pack verified, its input rebuilt; the four stored memos served with matching hashes by the new code; through the access gate, the API answered 200 for the signed-in session and 302 without one. The store after that run: 850 runs, 776 complete; 776 of 776 agree across the run, its explanation and the findings record (1,083 findings); of 1,201 findings code computed 20, lowered 17, withheld 118, and 1,046 carry the model's hint. This entry and the README's counts were then committed on top, and the same gate, push and deployment were repeated for that commit.

**A delta pass over five named questions; documentation only (2026-10-02).** Asked again, narrowly: is the mid-run refresh proven, are the counts current, is there public CI, is memo creation crash-atomic, is the reviewer authenticated. The last two were settled by the audit above and nothing has touched them since, so they were not rerun: the memo's file precedes its row (fault injection, retry, concurrency, hash and review-head tests in `tests/test_memo_atomicity.py`, `tests/test_uniqueness.py`, `tests/test_memo_revisions.py`), and the reviewer is a name the browser sends, recorded as a label, which the README says and the drawer's own field says ("Your name, recorded with the decision"). The mid-run refresh is proven by `e2e/critical.spec.ts` (the reload happens while the run is still checking and the page reattaches to the same run); `docs/archive/VALIDATION.md` and `docs/archive/SYSTEM_TRUTH.md`, both records of 2026-09-29, still called it unproven and now carry a dated correction beside the original sentence. Two counts were stale in documents that describe the present (`docs/SYSTEM_MAP.md` said 16 mutants; a README sentence said "CI runs the same flows"). And one sentence of mine was too strong: "there is no CI on this repository ... never run". No workflow of this repository runs the checks, which is what matters, but the Actions tab is not empty: GitHub's own Dependabot update jobs ran five times on 2026-09-29, one failing. The README says that now. Nothing but Markdown changed; no test reads any of these files, so none was run, and the deployed build, which names the commit it was built from, was not rebuilt.

**What the model was handed, and who decided: one upload traced end to end (2026-10-02).** The question asked of the code, the store and the interface: for every part of a finding, is it a fact of the document, a choice of retrieval, the model's reading, a decision of code, a fallback, or a person's decision, and does the product ever show one as another? Five places it did, each proved before it was changed.

1. *The model server cuts a prompt that does not fit, and says nothing.* A run records the hash of the message it sends and the explanation shows it as what the model saw. Asked directly, with the product's own options, for a notice period stated at the start of a prompt of 20,695 tokens, the server evaluated 8,194 of them and the model answered "30 days" where the text said 47; nothing in the response says the prompt was cut. No recorded run had overflowed (the largest prompt sent was 47,241 characters and the most tokens any run used was 10,623; the store's text runs 3.98 to 5.19 characters per token over 790 runs), but six full sections, a long guidance and denser text reach the 16,384-token window. The request now carries `truncate: false` and `shift: false`; the server then refuses with the exact counts in two seconds, the refusal is a failed run with a sentence a person can act on, and it is not retried. A complete run is therefore a run whose prompt fit.
2. *A retrieval that matched nothing looked like one that chose.* When no word of the question or guidance occurs in the document the opening sections are handed over, and the stage read "6 candidate sections" all the same. Recomputed over the store, that had happened in 32 of 850 runs. The stage now says no section matched and that the opening sections were read instead.
3. *An answer did not say how little of the document it was about.* The model is handed six sections by default: over 850 runs a median of 4.9% of a document's sections, and 6 of 2,659 on the largest. The run now carries the number, and the answer says "the model was handed 6 of this document's 123 sections". "Not found" reads "Not found in the sections read", and the card says the model found no provision that states the point, where it used to say, in the product's own voice, that none does.
4. *The drawer headed every status "Code decided".* Of 1,201 findings code computed 20 statuses and lowered 17; 1,046 carry the model's hint. The third layer's heading is now "Code decided" only under a source where code did, "Code did not decide" under the model's hint and "Code withheld" where no quote verified; and the model's own phrases for what it observed and required, its pointer into the guidance and its suggested position, which sat under that heading, are in the model's layer. A caller of the status label that does not say who decided now gets the weaker claim; the default used to be "computed".
5. *A label that described one case of two.* `ambiguous_fact` read "the quote states a duration two ways that disagree", which is no longer the only way to reach it since a quote with several periods can.

One more, found on the way: once the browser flows have built into `.next-e2e`, `npm run lint` linted that output and failed with 115 errors; the directory is ignored now. It did not show in the release gate because the gate lints before it runs the flows.

Left alone, with the reason: retrieval stays lexical at six sections (recall at six is 0.85 on the labelled CUAD cases and 0.92 on the goldens, so on 8 to 15 questions in a hundred the section that holds the answer is not among the six, which is exactly why the answer now says how much was read; the hybrid measured better and is behind a setting); conflicting clauses in different sections are not detected by code and a correct quote with a wrong conclusion is not either, which is what the model's layer, the "model's view" label and the person's decision are for; the status mapping is still written three times (interface, memo, explanation) and kept in step by tests; whole-document questions (a summary, "what is unusual here") are not offered, because nothing in the architecture lets the model read a whole large document and the product must not word a partial reading as a whole one. What it does support without a question is a fixed list of questions per document, each answer with its verified quote: the batch task already does this from the command line.

Checks run for this pass, and only these: the backend suite (the run service is shared by most of it), 325 tests; the interface's checks and 30 unit tests; the 21 browser flows in replay; the 24 mutants' target lines confirmed present (the verifier and the status logic were not touched, so the mutants were not rerun); one live refusal through the product's own provider. Goldens, reconstruction and the censuses were not rerun: prompts, options, fingerprints and stored records are unchanged.

**A hostile pass over the reasoning: where code decided what it could not know (2026-10-02, night).** Two questions, asked narrowly and of the record first. Whether hybrid retrieval has earned the default, and whether the product can still look sure while being wrong when the evidence is partial, conflicting, cross-referenced or misread.

*Retrieval: BM25 stays.* The numbers in `docs/RETRIEVAL.md` for the hybrid were taken before the alias table and reader v5, so the two were run again on the same labels, with no model: the 164 CUAD cases and the 38 present goldens, the alias table on. Recall at six on CUAD: BM25 0.976 (160; 161 counting a two-section agreement the fallback hands over whole), hybrid 0.976 (160). The ten points the hybrid had earned on 2026-09-29 are the ten the table took. On the goldens 0.921 against 0.974: the hybrid reaches g08 and g42, neither reaches g12. It recovers one CUAD case and loses two (a governing-law clause that BM25 ranks first falls to eighth: it sits at character 4,963 of a 5,908-character part, and the embedder is shown the first 2,000; 56 of the 164 labels start beyond that). It costs a median 2.7 s per run to embed the sections, 9.9 s on the 123-section sample, and 2.3 s for the question, and it can never report that no section matched. The rule asked for five points on CUAD; it has none. What the labels cannot say: the median labelled agreement has twelve sections and three exceed sixty, and the seven alias groups are the seven categories of the labels, so 0.976 is measured on the questions the table was written for. Read from the misses themselves: two of the three goldens BM25 misses are inflection, not meaning ("modified" against "modification", "indemnifies" against "indemnify"; the tokenizer does not stem), the third is a cross-reference to the cover page.

*The status decision: three defects, each reproduced before it was changed.* Code compares periods; it does not know what a period is about, and in three places it decided anyway.
1. *A point the model reported as not found was passed by code.* The prompt has the model cite the closest provision it read when a point is missing (rule 8). `decide` took the period in that quote as the contract's position. On the record: run `5ff255e1c3154792`, asked for a most favoured nation clause under guidance about termination, the model answered "missing", cited the 30-day cure period, and the finding is a computed pass, one of the twelve on record. Asked of the live model with only a cure period in the sections, the same path gave "needs review, lowered by code" from the renewal and cure periods of two closest provisions. A finding hinted "missing" is no longer evaluated: the status is the model's, the reason says the quote is the closest provision read.
2. *A carve-out with no number was not a period.* "upon ninety (90) days' prior written notice, except that Provider may terminate immediately upon written notice" came back from the live model with a hint of pass and was a computed pass against a 90-day minimum. The rule of 2026-10-02 (several periods in a quote are decided by code only when they agree) read "immediately" only in a quote with no other duration. It now stands beside the others (`stated_periods`), and that quote is needs review as an ambiguous fact.
3. *Guidance with several periods was resolved by code.* "Termination requires at least 30 days' notice. Enterprise agreements require 90 days." and 45 days in the contract: a computed pass against the 30, the sentence that names the topic. Which period binds this agreement is a reading of the guidance. A pass by code now needs the quote to meet every period the guidance states (`stated_rules`); otherwise the model's hint stands as its view, with the reason. A shortfall against the rule about the topic is still code's to report, because that direction sends the finding to a person. No guidance on record states two different periods.

Every recorded finding was decided again with the changed code, read-only: 1,201 re-decided, 1,200 unchanged, the one changed is the run above. The record keeps that run as it was made.

*Asked and found handled, by trace or by measurement.* Business days, months and years are never compared with calendar days (the status falls to the model's hint). Thirty to cure, sixty to terminate and ninety to renew in one quote is an ambiguous fact whenever they do not all meet the guidance alike. A document changed by one byte is another document, and a run's identity carries the document's, so nothing is reused. A quote that occurs several times says so with the count, and a quote found outside the cited section says where. An instruction written into the contract text was not followed in two probes (`docs/FAILURE-ENVELOPE.md`). The evidence pack says in its own words that it cannot say the conclusions are right.

*Found and left, with the measurement, because each needs the interface or the record's shape and the product is frozen.* (a) Of 211 recorded "missing" findings, 53 word the absence as a fact about the agreement ("The contract does not provide for termination for convenience"; two say "No notice is required to terminate for convenience"), 46 of them under answer-v2, whose rule 8 forbids it; the chip above the sentence reads "Not found in the sections read", the sentence is shown as written, on the card and in the memo. (b) In 189 of 776 complete runs the cited section points at a section of the same document the model was not handed, and in 402 a verified quote uses a term defined in a section it was not handed; the answer says how many sections were read and not that one of them points elsewhere. Code can see both. (c) Once a run has finished, the answer panel does not say that retrieval fell back to the opening sections, the Runs record heads the list "lexical retrieval, in rank order" either way, and the memo states neither that nor how many sections were read. (d) On an agreement of two sections BM25 scores every section at zero or below, the fallback fires, and the stage would say no section matched the question's words when both contain them. (e) A hint of needs review is still overridden by a computed pass; that is the rule of 2026-09-29 (the status is never the model's alone), no recorded finding rests on it, and reversing it is a decision, not a repair. (f) The contract's own comparison word is not read: "on no more than 30 days' notice" meets "at least 30 days" by code. (g) Sections are split with no overlap and a list item is its own section: "Either party may terminate … immediately:" is §5.3 and "if the other party fails to cure … following 30 days notice;" is §5.3.1, so a quote can be half a sentence.

Checks run for this pass, and only these: the backend suite, 328 tests (three added, in `tests/test_policy_rules.py`), with ruff, mypy and the import contracts; mutant M23, the one aimed at the status decision, killed, and the file restored byte for byte; the audit's policy probe (`experiments/final_audit/probe_verifier_policy.py`), 26 pass, 0 fail; the interface's checks and 30 unit tests, for one label ("code did not decide it" in place of "no comparable day counts", which the two new reasons would have made untrue); the 21 browser flows in replay. Five calls to the live model through the answer path, with no run stored. Goldens were not re-recorded: no prompt, option or fingerprint changed, and the re-decision above covers every golden run on record. Nothing was committed, and the serving API keeps the code it started with until it is restarted.

**policy-v2: a pass by code has to be earned, and a run is the rules it was made under (2026-10-02, late night).** The pass above left three fixes in the status decision and a list of things found and left. This one takes the list, in the order of what could make the product sure and wrong.

*What decides a computed status, taken apart.* Source facts: the verified quotes, the guidance text. The model's own: its hint, its topic, its `observed` and `required`. Code's: the period it reads from the quote, the rule it reads from the guidance, the comparison. Held still and varied one at a time, the model's fields moved code's result: the topic chose which sentence of the guidance was the rule, and a hint of needs review was overruled by a computed pass. The arithmetic was right throughout. What it could not know was what the two numbers were about, and five kinds of clause were computed passes for that reason: "on no more than 30 days' notice" against "at least 30 days"; "within 90 days after each anniversary" and "at least 90 days before the end of the term" against "90 days' notice"; "shall not be required to give 90 days' notice"; a payment term of 45 days against a termination rule of 30; a clause "subject to Section 14.3" when Section 14.3 was never handed to the model.

*The rule now.* The two directions are held to different standards. A shortfall is code's to report whenever the periods show one: 60 days against a floor of 90 is needs review by code, whatever surrounds it, because that direction sends the finding to a person. A pass is code's only when the model called it one too and the source text gives no reason against it (`policy/proof.py`): every sentence of the guidance that states a period shares at least two of its own words with the quotes (one, when it has only one); the quote states its period the same way the guidance does, not as a ceiling against a floor; neither is counted back from an event when the other is not; no negation stands beside the period; the sentence the quote sits in, read whole from the stored section, carries no condition or exception and no other period; that sentence points at no section of the document the model was not handed (`unseen_references`; no reference is followed, the pass is only not code's to give); and no other finding of the same run falls short of the guidance (`settle_together`: the live model returned "60 days" as a pass and "notwithstanding Section 4, 10 days" as needing review, side by side). A blocked pass is the model's hint, shown as "Within guidance (model's view)", with the arithmetic and the reasons recorded. None of the checks reads a word the model wrote, so the model's wording cannot earn a pass; it can only lose one. Each check is a sign, not a proof: none of them is ever a reason to pass, and a clause that says the opposite in words the checks do not know is still the model's and the reader's to catch.

*Measured before it was written, read-only, over the 1,201 recorded findings.* Computed passes on record 12, computed shortfalls 8. Under the rule: 11 and 8. One finding decides differently, the one the pass before found (run `5ff255e1c3154792`, a pass computed from the closest provision of a point reported as not found). The eleven that remain are the same clause, a 30-day cure period against "at least 30 days to cure a material breach", which names its subject, states the period plainly and points nowhere. 154 recorded findings rest on a passage that points at a section the model was not handed; none of them was a computed pass. No recorded run holds a computed pass beside a computed shortfall.

*A run is the rules it was made under.* A run's fingerprint carried its inputs and not the rules applied to them. After the status decision was fixed, 49 recorded runs still carried exactly the identity a new request would have, so the same question would have been handed the answer the old rules made. Three versions, declared by hand where each rule lives and gathered in `runs/versions.py`, are now in every run's options and so in its fingerprint: `policy_version` (policy-v2), `verifier_version` (v6), `retrieval_version` (retrieval-v1). Not a commit hash: two commits with the same rules answer alike. The same request under the same versions is reused; under a changed version it is a new run; the old run opens as recorded. The golden report, which finds its recordings by today's identity, falls back to the identity the record used before versions when there is no recording under today's rules, so the published recordings are still shown; a request is never answered that way.

*A run executes from its own record.* `execute_run` read the process's settings for the number of sections, the retriever, the alias table and the decoding options. Reproduced: a run created at six sections and executed after the setting became one was handed one, with six on its record. It now reads all of them from the run's options (`FrozenOptions`), binds the provider to the recorded model, temperature, seed and context size, and refuses to execute a run whose recorded versions or alias table are not the code's: that run fails with the reason and is retryable.

*Absence in the product's words.* Of 211 recorded "missing" findings, 53 word the absence as a fact about the agreement, against prompt rule 8. The model's sentence stays on the record and is shown in the drawer as the model's (`modelConclusion`). What the product says for such a finding, on the card, in the findings list, in the explanation, in a new memo and in the pack, is one sentence of its own: "The model did not find this in the sections it was given." The note of a run the model declared insufficient is the product's too; the model's note stays in the raw output. Memos already written are not rewritten.

*Fallback as a fact.* `runs.retrieval_mode` records `lexical_match`, `hybrid_match` or `opening_fallback`; a run recorded before it carries null and nothing is claimed for it. The answer panel, the Runs record, the explanation, the memo and the pack say when the sections are the opening ones, handed over because retrieval ranked none, and the memo now says how many sections were read. The stage's sentence says what the retriever did ("ranked no section"), not why: on an agreement of two sections BM25 scores every section at zero although both contain the question's words, and "no section matched the question's words" was untrue there.

*Pairs that are not decisions.* `Decision` could be built, and a finding stored, as "missing" by `computed_days` or "pass" by `no_evidence`. None is on record. The sources and the statuses each may decide are one table (`models.STATUSES_BY_SOURCE`); `Decision` refuses any other pair, and a database created from here on carries the same table as a CHECK. An existing file keeps its findings table as it is (SQLite cannot add a CHECK without rebuilding it) and gains the `retrieval_mode` column at the next start.

*Left, with the reason.* The checks are lexical: a subject the guidance and the clause name in different words ("without cause" for "for convenience") is not a pass by code, which is the safe side, and a clause that takes itself back in words outside the lists is not seen. A term defined in a section the model was not handed blocks nothing unless the sentence points at that section. A shortfall still follows the model's topic when the guidance has several rules. References that name nothing in this reading of the document (another agreement, a schedule in another file) are not counted as unseen. The 53 recorded sentences, the recorded wrong pass and every stored memo stay as they were made.

Checks run for this pass: the backend suite, 402 tests (74 added: `tests/test_pass_gate.py`, `tests/test_run_identity.py`, `tests/test_absence_wording.py`, and the six existing tests the stricter rule changed, each rewritten to say the new rule), with ruff, mypy and the import contracts; all 24 hand mutants killed and every file restored byte for byte (the status decision, the run service and the models were all touched); the audit's verifier and policy probe, 25 and 26 pass, 0 fail, after three of its cases were given a quote that names its subject; the OpenAPI document and the interface's types regenerated; the interface's checks and 34 unit tests; the 21 browser flows in replay. The five model answers recorded in the pass above were decided again, no new model call. Goldens were not re-recorded: the re-decision covers every golden run on record and none changes; they will be new runs under policy-v2 the next time the set is recorded. No recorded run was modified, nothing was committed, and the serving API keeps the code it started with until it is restarted, at which point the store gains one nullable column.

**Four questions asked of the hardening itself (2026-10-02, before dawn).** One review of the new code, nothing else reopened.

*Is "Code decided: pass" literally true?* No. Hold the verified quote and the guidance still and change only the model's hint from pass to needs review, and there is no pass: the gate requires the model's pass. So code was confirming a proposal and the record called it a decision. The gate is kept, because removing it would let arithmetic overrule the model's doubt; the name is changed. A pass under policy-v2 is recorded as `confirmed_days`, headed "Code confirmed" in the drawer, "Proposed by the model, confirmed by code" in the explanation, and "Within guidance (confirmed by code)" on the chip and in the memo. `computed_days` now means what it says: a shortfall, which does not move with the hint (pass and needs review give the same decision), or a pass recorded before policy-v2, when code did pass on the arithmetic alone. No decision made from here on is a pass by `computed_days`; the twelve on record keep the name they were recorded under.

*Was `settle_together` too broad?* Yes. It lowered a confirmed pass whenever any finding of the run fell short, so a payment term measured short against a termination rule took the pass from the termination clause beside it: run membership used as legal meaning. It now needs a relation that shows in the record: the two findings cite the same section, the short one's clause refers to the section the confirmed one cites, or the short one's quote is about the same point of the guidance (`policy.proof.same_point`, the test the confirmation itself had to pass). The live model's case, "notwithstanding Section 4, ten days", is caught by two of the three. An unrelated shortfall takes nothing.

*Can a version be forgotten?* It could. `tests/test_semantic_versions.py` now records, beside each version, a fingerprint of the code it names: the syntax of `runs/status.py`, `policy/durations.py` and `policy/proof.py` for the policy; `verify/spans.py`, `verify/tokens.py` and `verify_evidence` for the verifier; `retrieval/lexical.py`, `retrieval/hybrid.py`, `expand_query` and `_retrieve` for retrieval. Docstrings, comments and layout are left out, and the tree is written out by the test itself so it does not move with the Python that runs it. Proved on disk, each file put back byte for byte: six changes of meaning with the version untouched (two shared words become one, a shortfall no longer decided, a blank quote located, the window ignored, heading weight three becomes two, the fallback hands over nothing) each fail the test; a reworded comment and an edit to an unrelated function of a shared file do not. The failure says which of two things to do by hand: bump the version and add its fingerprint, or, if nothing it decides changed, replace the fingerprint. The mutant runner leaves this test out, since it would fail on any mutant of those files without a behaviour being tested.

*Does a store made before this open under it?* On a copy of the store as it serves (850 runs, 1,201 findings; opened read-only once, to copy it): the start adds `runs.retrieval_mode`, nullable, null on every row, and rewrites nothing (every table hashed row by row before and after). 97 historical runs opened with their explanations; against the serving API, which is the old code, 73 are identical in every recorded field and 24 differ in one, the `conclusion` of a finding reported as not found, which is the product's sentence now with the model's kept beside it. The wrong recorded pass still reads as recorded. The same request as a completed run with no version on its record is a new run under policy-v2; asked again it is that new run, reused. A run created at six sections and executed after the settings became one section, a 40-character window, no aliases, the hybrid retriever and other decoding settings was handed six sections whole, by BM25, with the provider bound to the settings it recorded. The same is now a test on a store built to the old shape.

*What the projections say, read in a browser over five seeded runs.* The card, the drawer, "Why this answer", the Runs record and the memo for a confirmed pass, a shortfall, a pass the model doubted, a point not found and a fallback. The model's layer carries the model's hint, its phrases and, for a point not found, its own sentence. The product's sentence for that point is "The model did not find this in the sections it was given." in all five places. The fallback run reads "retrieval ranked no section for this question" in the panel, the Runs record, the explanation and the memo, and nowhere as a ranking. The third layer reads "Code confirmed" for the pass, "Code decided" for the shortfall, "Code did not decide" for the other three.

Over the record, read-only: no finding would be a pass by `computed_days` today; the eleven sound recorded passes would be `confirmed_days`, the twelfth "missing" by the model, the eight shortfalls as recorded. Checks: 417 backend tests, all 24 mutants killed, the audit probe 25 and 26 with no failure, 36 interface tests, the 21 browser flows, ruff, mypy, the import contracts, tsc, eslint, prettier. Nothing committed; no recorded row modified.

**A gate of the application's own, built and not switched on (2026-10-02, morning).** The freeze was lifted for one thing, by Pavan: Cloudflare Access asks a reader for an email and then a code, and that is too much to ask of someone following a link. The requirement: one click into the real workbench, with access control that is still real when an engineer opens the developer tools and calls the API directly. This is the one place the rule "no accounts" is touched, and it is kept: there is no account, no password, no signup and no reset.

*What was chosen, and against what.* A username and password was the first design; it needs a password hash (a new dependency for Argon2id), a form, and a secret a reader has to be told. A signed invite link needs none of that and is fewer steps for the reader, so that is what was built. Three decisions inside it. The invite rides in the URL fragment (`…/?document=…&run=…#invite=<token>`) rather than in a path the server redirects from: a fragment is never sent, so the credential is in no access log, no Cloudflare log and no Referer, and a link scanner that fetches the URL exchanges nothing; the interface exchanges it by POST and removes it from the address bar, leaving the page the link was for. The invite is not single-use: mail and chat clients open links before people do, and a one-time token would be spent by the scanner; it expires, names one reader and can be revoked instead. And the door is the API's, not the page's: the Next bundle is the public repository's code and holds no data, so it is served to anyone and shows one restrained screen, while every route under `/api` except health and the gate itself answers 401 without a session. The gate is mounted where the routers are mounted, so a route added later is behind it, and a test walks the API's own route list to hold that.

*The mechanism.* `backend/app/api/access.py`: tokens are `v1.<claims>.<mac>`, HMAC-SHA256 under `WORKBENCH_ACCESS_SECRET` (through `hashing.mac_sha256`), claims subject, audience, issued and expires; an invite and a session differ only in audience and lifetime and neither is accepted as the other. The session is a `__Host-` cookie, Secure, HttpOnly, SameSite=Strict, seven days. A request that changes something must also carry no foreign `Origin`. Ten exchanges in ten minutes per address, twenty run starts in ten minutes per reader, in memory. No secret, no gate: a laptop, the tests and the browser flows run as before, and a secret shorter than 32 characters refuses to start. Nothing is stored and nothing about a reader reaches a log.

*Proved before any deployment.* Ten backend tests, the route walk among them (24 operations on 22 paths, the event stream, uploads, memo files and evidence pack included, each 401 without a session and a forged, foreign-secret or wrong-audience cookie no better); six interface tests of the door; and one pass in a real browser over an isolated store with a throwaway secret: no session, the page shows the door and eight direct API calls answer 401; a bad invite is refused in the API's words; the invite link opens the hero run in one step with a clean address; the cookie is `__Host-verity_session`, HttpOnly, Secure, Strict, seven days, and not visible to script; a new question is followed over the event stream with the cookie; the cookie cleared, the next request closes the door.

*Not done, and whose it is.* Nothing is deployed and Cloudflare Access is untouched; switching over is ten steps in `deploy/README.md`, in an order that never leaves the store open, and steps 6 onward are Pavan's (the Cloudflare account is his). The gate does not identify a reviewer to the application, adds no security headers, and is a signed link: whoever holds it holds the access until it expires or is revoked. Checks: 429 backend tests, 42 interface tests, the 21 browser flows with the gate off, ruff, mypy, import contracts, tsc, eslint, prettier; the 24 mutants were not rerun (none of their target files changed).

**The deployed build, driven end to end, and one thing it found (2026-10-02, 06:00).** After the gate was deployed behind Access, the deployed API was checked on its own origin (43 checks: all 24 operations closed without a session; five bad invites and four forged cookies refused; the 850 runs recorded before the deployment byte for byte what they were, against a copy taken before it; the hero run as recorded, its pack checking itself; the same request asked again a new run under policy-v2 by the real model, its stages arriving over the event stream across 68 seconds, the same decision as the record, reused when asked a third time; a question the sections do not answer shown in the product's sentence with the model's beside it; no invite, session, secret, contract text or guidance in the logs) and the deployed interface was driven in a browser that believed it was at the public origin. That found one defect: an invite link opened in a tab already showing the door changes only the fragment, a browser does not reload for that, and the link did nothing while the invite stayed in the address bar. The door now listens for the fragment changing. One interface test added (43).

**The hero link, opened on a slower machine, landed above its clause (2026-10-02, 06:30).** Three more passes over the deployed build (the API on its own origin, then a fresh browser that believed it was at the public origin; each pass made one run with the real model) were clean on the record, 35, 36 and 36 checks, and their screenshots disagreed: in one of three the paper stood at the top of the first section with the quoted clause 2,800 pixels below it. The checks had asked whether the mark was in the document, not whether it was on screen. The cause was the fix of 2026-10-01 above: the scroll to the mark waited one animation frame after asking for the highlight, and a frame is not a render. When the page's main thread is busy the frame comes first, no mark is found, and the pane goes to the section's top. On this laptop that was 1 load in 30. With the browser's processor slowed four times it was 10 loads in 10, and eight times, 9 in 10: a reader on an older laptop would have seen it nearly every time, on the one link the email carries. The scroll is now decided in the layout effect of the commit that renders the mark (`useHighlightScroll`), so there is no frame to lose; without a span it goes to the section's top, as before, and a change of motion preference alone does not scroll. The same build under the same slowdown: 36 loads in 36 on the clause, at one, four and eight times, in two window sizes; the deployed build beside it, same session, 0 in 10. Six interface tests added (49). The browser flow that opens a citation now requires the mark in the viewport, not only in the document. Nothing in the backend changed.

**A design pass over every surface, with nothing decided differently (2026-10-02, morning).** Pavan lifted the design freeze for one pass: the interface had to read as product software built by hand, and the copy had to lose the marks of generated text. Nothing below changes what the API decides or records. The system: warm graphite ground, the contract on cream paper, one brass accent for what a person should look at, four status tones that always travel with a word and a dot, Source Serif for the contract and for headings, JetBrains Mono for anything a person might copy, one easing curve, hairlines instead of shadows (globals.css). Borrowed from Pavan's own earlier interfaces: the kicker over a serif title, the chain that shows where a decision stopped, numerals as figures with zero dimmed, the tinted chip that never relies on colour alone, the focus ring and the skip link; their aurora, glass and glow layers were left behind. What changed on screen: the first screen says what Verity is and puts one finished review beside the drop zone, read from its run (the finding, the arithmetic code decided, the person who confirmed it); the evidence drawer is a sheet over the questions pane, no longer a card on top of half hidden findings, and opens with the finding's trail in one line (model, source, code, person, with the model's call struck when code changed it) above the four layers, which now hang on one rule with the layer that set the status marked; contract passages are set on paper, the model's own phrases on a grey ground, the team's guidance on a quiet rule, so no quotation mark has to say whose words they are; Documents, Findings and Runs open with their figures as numerals (the Findings figures filter the list), the Runs record draws every quoted passage the model has proposed as one bar by how it was found, misses included, and draws a run's timing to scale; the memo is set like the paper. At phone width the questions, the findings and the evidence now work, with the contract text still asking for a wider window. Copy: no dashes, no quotation marks, no exclamation marks and no chat phrasing in the interface (the Assistant is Questions; the sparkle icon is a page beside a panel); ranges read from 0 to 5000; the user chip that named Pavan on every screen is gone, since the application authenticates no one by name. Text contrast was raised to keep the accessibility flow clean. Checks: 49 interface tests (three expectations rewritten from quotation marks to the words themselves), the 21 browser flows including the accessibility scan, 429 backend tests.

**The first screen tells the record, and three more things read from Pavan's earlier interfaces (2026-10-02, 09:50 to 10:40).** Below the fold of the first screen: a pipeline of the record's own counts read from the API and counted up on sight; the hero run in four steps, each a door into the place in the product where that step is on the record; four things Verity refuses to do, each a property of the code. Then: a gauge in the evidence sheet's code layer, one axis with the guidance's bound and the contract's figure, drawn only when code's own sentence parses exactly (`DayGauge.tsx`; four tests), so a model's sentence or a comparison across units draws nothing; a spine down the paper's edge with a mark where every verified quote of the run on screen begins, each a jump; skeleton rows the shape of the list that is coming on Documents, Findings and Runs, and a failed read that says so and offers to read again instead of showing an empty list. Nothing the API decides or records changed. 53 interface tests, 21 flows.

**The Back button had nowhere to go (2026-10-02, 11:20).** Pavan clicked the mark to go home and pressed Back, and Back left the site. The URL hook wrote every state with `replaceState`, so the browser held one entry for the whole visit. Now a move is a history entry (the several states one click passes through are coalesced into one), popstate restores the screen the address names, a restore in flight leaves the address alone so a reload mid-load keeps the deep link, and the finding whose evidence is open is written as `finding`, so Back reopens it and any address can be sent as a link. The brand on the first screen is a home button too; the main region takes focus from the skip link. Found by a sweep of the browser's own controls: Back and Forward along a real path, reload on every screen, Escape, focus on open and close, Enter and Shift+Enter, the first Tab stop; 23 of 23 after the fixes. Four tests on the hook (57 interface tests).

**An independent red team read the book against the code, and three claims did not hold (2026-10-02, 11:40 to 13:00).** Each was reproduced before anything changed. (1) *Code owned a pass it could not establish.* Guidance "a material breach must allow at least 30 days to cure", verified quote "Following a material breach, Company shall provide 30 days' written notice of an audit", model hint pass: policy v2 returned `confirmed_days`. The same-point check is lexical (shared word stems), and a lexical check cannot tell a cure period from an audit notice. Policy v3: code confirms no pass; the pass stays the model's, and the reason says code found the day counts consistent and did not establish the shared subject. The source `confirmed_days` is kept for the records that carry it and is never written again. (2) *Code owned a shortfall on the wrong subject.* Guidance "termination requires at least 90 days", verified quote "Invoices must be paid within 60 days": policy v2 returned `computed_days`, numerically right and about a payment term. Code still sends that to review (a false escalation is the safe direction), but the reason now ends with what it did not establish, the heading reads "Code found a conflict" rather than "Code decided", and the hero case reads the same way. `settle_together` keeps its structural relations and now only extends a reason. Fingerprint re-recorded for v3; eighteen tests rewritten to the new ownership. (3) *Hidden text reached the model through styles.* A hand-built DOCX hid an instruction five ways: a run's own `w:vanish` was dropped; a Word "Hidden" character style, a hidden paragraph style, a style based on one, and `w:specVanish` all reached the reader's text. Reader v6 resolves `w:vanish` through character and paragraph style chains and treats `specVanish` as hidden; coverage counts style-hidden runs as excluded where it had said "unknown"; `w:webHidden` (shown in print layout) and coloured text are read and said so. Also from the review: run starts were limited only with the gate on, so the open site had no limit (now keyed by address when there is no subject; every test resets the limiter in place, because one test's `monkeypatch.undo()` had restored a limiter the fuzz run filled); `WORKBENCH_ACCESS_REQUIRED` makes a deployment refuse to start without a secret; a review made through the gate records the invite's subject beside the typed name (`finding_reviews.access_subject`, nullable, added at start). Not changed: the owner's decision to run the site with the gate off. Narrowed in the book rather than built: run identity freezes inputs and rules, not the model artifact, so model output is not promised to repeat. 434 backend tests, 57 interface, 21 flows.

**A second reviewer could read the first reviewer's contract (2026-10-02, 13:00 to 16:30).** The gate let a reader in and then told the application nothing about who had entered, so every record was every reader's: a run id in an address, a Runs list, a memo link, the event stream of a run in flight, all open to any invite, and the same question from a second reviewer was handed the first reviewer's run as a reuse. Reproduced with two minted invites against a test client before anything changed. The rule now lives in one module (`application/workspace.py`) and the routers only call it. An invite's subject, under the secret, derives a workspace id (`ws-` and sixteen hex characters; opaque, stable, chosen by no request, naming no one). Documents keep their one row per bytes and reader version; who may read one is a relation, `document_access`, written by the upload, and a document no workspace holds is curated. Runs and guidance carry a nullable `workspace_id`, null for everything made before today and for what the goldens and batches make: curated, readable by all, changeable by none (a review on the hero finding is a 403 that names it as curated, and the recorded review stands). A finding follows its run, a review its finding, a memo its run, the stream its run; a record a workspace may not read answers exactly as a missing one, the same 404 and the same sentence on every route, so an id leaks nothing by being tried. Lists, the citation record included, are filtered the same way. The run fingerprint includes the workspace, so one workspace's question never hands back another's run, while reuse inside a workspace is as it was and a curated run keeps the fingerprint it always had. A second workspace uploading the same bytes is granted the one stored reading: it had the bytes, so it learns nothing; its guidance with the same words is its own row; "created" is from that workspace's side. With the gate off there is one workspace, `open`, and the first screen now says "Open preview" and that an upload is readable by anyone with the address, instead of calling it private. Found on the way and fixed: a freshly uploaded document had no grant for an instant and so read as curated to the next request. Not built: retention. Nothing is deleted, the immutability triggers would refuse it from the application, and no measurement or reviewer has asked for a period; the statement and the shape a period would take are in `deploy/README.md`. Not changed: SQLite, the analysis path, the one-click invite (invite, session, clean address, workbench, measured again at under 110 ms), and no second login. Checked three ways: seven tests in `tests/test_workspaces.py` (two invites against every route, reuse across workspaces, the curated record, the gate off, the log holding no contract text, guidance, question, session or secret); the full suite, 441; and a browser pass against a sandbox copy of the deployment with the gate on and the local model, two browsers entering by two invites, reviewer A uploading and asking, reviewer B trying every id A had: twenty-three checks, all passed. Interface 57 unit tests, 21 flows. Not committed and not deployed at the time of writing; whether the deployment runs with the gate on is the owner's switch.

**One amendment arrives: a recorded surface on Runs (2026-10-05, late).** The contract-lineage experiment in ivo-experiments (branch `contract-lineage`) measured what one new amendment touches in a portfolio of 5,414 real Exhibit 10 documents: the documents examined through blocking, the relationship bound, the one family rebuilt, the composite sections changed, the findings invalidated and preserved, and that no unrelated family was recomputed, over sixty held-out arrivals. It exported those measurements as one file, `lineage-arrivals/1`, with a sha256 of its own body. Verity reads that file (`GET /api/engineering/lineage`, the sibling checkout or `WORKBENCH_LINEAGE_ARRIVALS`), checks the hash through `hashing.sha256_text`, and shows it on the Runs surface under "One amendment arrives", with a chooser over the recorded arrivals. Every number on the surface is the file's; the component decides which recorded arrival to show and nothing else. The surface says it is a recording, not a live run, and whether the file matches its hash. *Chosen against:* porting the engine into Verity (a second implementation of research code, before the research is settled) and reading the experiment's Python (forbidden: repositories communicate through versioned evidence files). *Not done:* no live lineage; no families beyond the structural ones Verity already had; no change to the trust layer, prompts or policy.

**One contract changes: the contract-state record replaces the lineage record on Runs (2026-10-06).** The contract-state experiment (ivo-experiments, branch `contract-state`) gives every derived object a dependency manifest, plans what one change can reach before recomputing anything, recomputes only what the plan names and whose inputs moved, and checks the result against a rebuild from nothing. It exports `contract-state/1`, which carries everything `lineage-arrivals/1` did and more: the family the document joined, its effective facts before and after (only fields whose reader was measured precise enough), the template and cohort context, the plan, what changed, the work done and avoided, and whether the arrival was checked against a rebuild. Verity reads it (`GET /api/engineering/contract-state`, the sibling checkout or `WORKBENCH_CONTRACT_STATE`), checks its hash, and shows it under "One contract changes". The lineage endpoint, its schemas, its test and the Arrivals component are removed: two surfaces answering one question would disagree. *Chosen against:* keeping both records; porting the engine into Verity. *Not done:* no live engine; no change to the trust layer, prompts or policy.

**A real contract pair, uploaded and attacked end to end: four defects, each closed as a class (2026-10-08).** A QA campaign took two unmodified CUAD v1 PDFs (a development agreement and its first amendment; CC BY 4.0; kept out of git under `backend/data/qa-corpus/`, hashes in its manifest) through every layer on a sandbox store, with the model's part played by scripted proposals through the replay provider (Ollama was not running), so verification, status, persistence, API and screen were tested against adversarial answers rather than one model's habits. What held: content identity, duplicates and concurrent uploads (one row per bytes and reader under 2 and 8 simultaneous uploads), the exact model input (rebuilt and reproduced byte for byte on a second store), verification (fabricated text, the other document's text, a section not handed over and a quote cut mid-word all withheld; a wrong section id relocated), immutability, recovery of a run whose process was killed, workspace isolation, document text as data (instructions and a fake prompt header stay inside SECTIONS; markup is escaped in the memo and inert on screen). What did not, and the general fix:

1. *A name its bytes contradict chose the reader.* A PDF uploaded as `.txt` became a 44-section text document of its own binary, and the same bytes uploaded later as `.pdf` were handed that reading, because a document is known by its bytes. `readers.file_type` now decides: the name claims a type, the bytes must agree (PDF signature, zip package, else text; text holding NUL is binary), checked before the stored bytes are looked up, so the same bytes are only ever read one way, in any order.
2. *A parser's own exception was a 500.* 112 of 300 mutations of the real PDF and 21 of 200 of the sample DOCX escaped `read` as AssertionError, KeyError, TypeError, zlib.error and the like. `readers.read` is now the one boundary: any failure of a parser on a supported type is UnsupportedFile with the reason, and the per-reader exception lists it replaces are gone. pypdf's LimitReachedError is among them: it also flags damaged structure, so it is not read as size.
3. *Plain text and PDF showed section numbers the document never states.* An address ("15285 Minnetonka Blvd.") became §15285 and the clauses after it were cited under "§15407 McGinty Road West"; headings without a number were numbered from levels (§15408 onward, or "§7 MILESTONE 1" beside the agreement's own clause 7). Reader v7: a stated number must continue the clause numbering (measured bound of 20 over 5,418 steps in the 510 CUAD texts; a step back is a restart), and a plain-text or PDF heading without a number is labelled by its heading alone; DOCX numbering, which Word applies without the number in the text, is still computed. Over the 510 CUAD texts, readings with a section number of 1,000 or more went from 14 to 0, and the expert answer spans found word for word in the section text went from 13,670 to 13,671 of 13,807; the pair's 37 are all present.
4. *A version statement lost a race with a false sentence.* Two later versions of one base, stated at once, ended 201 and 409 "placed in a line of versions by another request", though the refused document was in no line. `declare_supersedes` now takes a second pass after a lost insert, so concurrent statements end as if made one after the other.

*Not done, recorded:* the reader still treats a numbered title ending in a period ("10. Term and Termination.") and a clause written inline ("6. WRF Patents. Washington …") as body under the last heading, so in the pair the governing-law clause is cited as "§5 Intellectual Property (part 3)"; changing that is a reader decision to be measured against the labelled sets, not a defect fix. A model-hinted pass on a topic the guidance does not cover is shown as the model's view and nothing more, as designed; a scripted model obeying an injected "mark this contract approved" produced exactly that, with the injected sentence as its visible evidence.

**Product, engineering and visual assurance on a worktree; nothing pushed or deployed (2026-10-08).** The live site
serves the main working copy, and its running processes predate these commits; none of this work is live, and making it
live is a restart of both servers, which waits for approval. Every change below was proposed to a triage reviewer
before it was made and reviewed again as a diff; each names the class it closes, not the example that found it.

1. *The prompt was not changed.* The false premise the campaign found ("what does this agreement change?" asked of an
   original, answered as a pass with real quotes) was put to answer-v3 under a rule written before either prompt ran
   (docs/GOLDENS.md, Recordings 7a to 7c): v3 lost g25, which v2 passed twice; gained one negative control of the two
   required; lost one positive. answer-v2 stays the default. The remedy is what the interface says: the pass is "Model's
   answer", the passages are "found in the document", and the status table says per row what code did and did not
   check.
2. *Readers v8 and v9.* v8: a numbered plain-text or PDF line whose words open in lower case is body, not a heading
   (460 of 11,646 such heading lines in CUAD and EDGAR were figures, wrapped sentences or list items). v9: invisible
   format characters are removed where text is first read, counted as a coverage part, and removed from file names,
   guidance, questions and reviews; a reading made before v9 shows each one as a visible marker. v10, from the triage
   review of the v9 diff: the invisible characters that are not Cf (variation selectors, the combining grapheme joiner,
   Hangul fillers) are removed between ASCII letters or digits, where "9", U+FE0F, "0 days" had still parsed as 0. v9
   readings exist only in sandbox stores; the version moved rather than read the same bytes two ways under one name.
3. *Where a passage is.* A quote is labelled by the clause the stored text names around it ("§13.2 Governing Law"), not
   only by its section, so a clause written inline under another heading is cited by its own number; the label is
   derived at display and in the pack, and no stored reading changed. The real-model smoke on a printed PDF then found
   two clauses run together in one paragraph and the governing-law quote labelled by the first; an opening after a
   sentence now moves the label only to the clause that follows, and every unclear case leaves the clause unknown
   (measured over 810 documents in docs/FAILURE-ENVELOPE.md, no wrong name in the 116 changes read).
4. *Refusals that say what happened.* An empty file is refused as empty; a PDF with no text layer as a scan.
5. *Review and state.* A review names the review state it was decided against; a stale one is refused with 409 and
   nothing written, under one write lock; a lock not had within SQLite's wait is a 503, not a 500. An address naming a run under another document's id is corrected in place.
   A document's type is its recorded media type, never what is left of its name (a 269-character name had lost
   ".txt"); bytes kept under a cut name are still found.
6. *Interface.* No control is hidden or dead (the drawer makes the page behind it inert and returns focus; a question
   on the landing is asked once the document opens); /state fits 320 px. Each decision button in the findings list
   names the finding it decides, and the list's lede says how a passage may differ from the quote ("word for word or
   differing only in spacing, case, punctuation or how a number is written"), not "verbatim".

*Deferred, recorded in docs/FAILURE-ENVELOPE.md:* headings for inline clauses in the reader itself (a prototype lost
expert-answer coverage on the labelled sets, so only the label changed); a reference check that lowers a status for a
clause written inline (a policy change with its own gate); an address or quantity inside the numbering bound; a heading
that names a clause read as a cross-reference; the run-start limit counting reused runs.

**Laptop independence: a static evidence page, one VM, a pinned GPU model; nothing created or deployed (2026-10-09).**
The live site ran from the workstation (tunnel, OneDrive store, local Ollama), with its web build missing the public API
address, no supervisor running, and the gate off, so every visitor shared one workspace. Decided, each through the
triage reviewer, and rehearsed locally with Docker; every account, purchase, DNS record and access change is the owner's.

1. *The public experience is static.* `/state` exports as files (`export_state.py`): the record is written by the API's
   own loader, refused unless it is the frozen record by hash, and the page makes no request to an API. It stays up when
   everything else is down. Hosted on Cloudflare Pages once the owner adds the domain.
2. *The live workbench is one VM with Caddy, invite-only.* Same origin (no CORS, the cookie first-party); the gate is
   required, so a missing secret stops the start instead of opening the site. SQLite stays: one process, local disk,
   measured traffic an invited demo. Rejected: managed containers with short stream limits, a separate frontend host,
   Postgres, queues, Kubernetes.
3. *The model keeps its identity or says it does not.* No managed provider serves the reference weights (qwen3:8b,
   Ollama digest 500a1f067a9f); the plan is Ollama on a scale-to-zero GPU with the digest checked before every answer.
   No claim of equivalence until a pre-registered comparison on the goldens and the false-premise controls has run.
4. *What the rehearsal found and closed:* a production build reaching for the browser's own loopback; a restarted
   container's interrupted runs kept in progress forever; a lock file Linux could not install; health waking the model
   for every visitor; the interface claiming the contract never leaves the machine whatever the deployment; the proof
   run's story told of other runs; no cache policy on private responses; no ceiling on a day's model spend.
5. *Backups are the rollback.* `backup.py` takes a consistent copy while the API writes, restores only into an empty
   store after checking every hash, and was rehearsed into a fresh volume with the same runs and findings.

*Deferred:* a site-wide content-security policy; per-reader invite revocation (today: rotate the secret); a plain-500
upload when the store is read-only; off-machine backups until an object store exists.

**Two hostnames, and the laptop's API never open (2026-10-08).** `ivo.pavankg.dev` becomes the static evidence page on
Cloudflare Pages (no server, no store, no model; it stays up when the laptop is off). The live workbench moves to
`verity.pavankg.dev`: the zone's free certificate covers `*.pavankg.dev` only, so `try.ivo.pavankg.dev` would need a
paid certificate. Moving the host signs readers out (the session cookie is host-only); invite links still work. The
supervisor sets `WORKBENCH_ACCESS_REQUIRED=1`, so the tunnelled API refuses to start without the gate's secret. The
`ci` workflows stay on their branch until they have run green on GitHub; a red check on main is worse than none.

**One address again (2026-10-09).** The owner chose to put `ivo.pavankg.dev` back on this machine, as before: the
invite gate in front, the workbench first, the recorded research at `/state`. The day with research on Pages at that
address made the workbench hard to find. The gate stays on; the one thing that opened is the contract-state record
(`GET /api/engineering/contract-state`), which is already public and holds no reader's data, parsed once per file
version so a reload re-reads nothing. The door now says what the workbench does, where the model runs (as health
reports it) and where to go without an invite. The address is up only while the machine is on;
`verity-state.pages.dev` keeps the static research up regardless, and `verity.pavankg.dev` redirects here.

**A workspace sees the name it gave a file (2026-10-09).** Driving the deployed site, an invited reader who loaded the
sample saw it under the file name a test reader had given the same bytes the day before, with that reader's upload
date. Documents stay deduplicated by bytes and reader version, but the name and the date are the uploader's, not the
bytes'. Each grant now keeps the name its workspace gave (`DocumentAccess.name`, set once); everything shown to a
workspace, and the model's input for its runs, uses it (`app/document_names.py`). Grants from before carry no name:
the first workspace on a document still sees the stored name, a later one sees "uploaded file (name not recorded)",
and every earlier run's input rebuilds unchanged, since it was given the stored name and still is.

**The workbench opens for anyone, each visitor in a workspace of their own (2026-10-09).** The owner decided the
workbench must be usable with no invite, sign-in or account. Switching the gate off was not an option: that is one
shared workspace. Instead a browser with no session is handed one (`POST /api/access/visit`): a server-made,
unpredictable subject signed like an invite's session, in a workspace (`pw-` prefix) that reads only its own records,
never curated ones. The session ends with its workspace and is never renewed, so a purged workspace's id is never
written again; the next visit is a new subject. The public API runs on its own store and refuses to start on one
holding owner or curated records. Costs are bounded per workspace, per network address and per day for everyone;
new sessions are not, since a ceiling on them is a lockout anyone can trigger. The one exception to "completed runs
are immutable" (constitution, rule 11): retention deletes an ended visitor workspace with its runs, in the public
store only, by dropping the immutability triggers, deleting and recreating the same triggers in one transaction.
Found on the way: a public workspace would have been handed curated guidance with the same words, and in a store with
curated documents a visitor's upload of the same bytes would have been unreadable to them; the first is fixed, the
second is why the public store may hold none.

**Verifier v7: a changed number is never found (2026-10-09).** A measurement over the store and 400 public EDGAR
exhibits found the typed tier reporting a quote as found when a number in it had changed: a token could end inside a
run of letters and digits ("30days" gave the number 3, "1,500USD" gave 1,50) and every comma was dropped ("1,5%" was
15%). One recorded span had verified "3,0 days" against "30 days". From v7 no token ends inside such a run, and a comma
separates thousands only in thousands grouping; a comma after a number is punctuation, as replaying the change over
EDGAR showed it must be ("March 16, 2024"). Of 1,524 recorded verified spans replayed under v6 and v7, exactly one
outcome differs: the "3,0 days" span, now withheld. On 218 glued units in 150 exhibits, a quote copying the run is
found as before (218 of 218); one dropping the unit is no longer forgiven where it never occurred. Recorded runs keep
v6; the evidence pack's own checker applies the same comma rule, so its PASS never accepts what v7 refuses.

**What an answer's card says was checked (2026-10-09).** Four independent reviews (product, interface, 32 pre-registered
real-model cases, algorithms) found one pattern under most failures: a located quote was shown as if it proved the
answer. A quote saying 10% stood under an answer saying 5% in the pass colour; a pass stood on 1 of 4 sections read.
The verifier was right each time; the screen claimed more than it checked. Each card now carries a ledger built only
from recorded fields: where code located the quote; that its support for the answer is the model's reading, not
checked by code; what code compared, or that it compared nothing; how much of the document the model was handed; and
the person's decision. A not-found answer has its own chip, and the provisions it read are shown as read, not as
evidence. The memo carries the model's suggested change only where review is needed. Prompts, model, reader and
policy are unchanged; the policy work the evaluation pointed at (a carve-out the quote boundary cut, "without cause"
read as convenience) is deferred because it changes status semantics and needs the goldens.


**Policy-v6: a pass does not state a value its evidence does not show (2026-10-10).** The Contract Reality Lab (24
pre-registered questions on 2025–2026 EDGAR agreements, real qwen3:8b, independently adjudicated) found passes whose
conclusion stated a figure no verified quote stated: "$10,000 a month" over a quote of hours whose rate was never
quoted, "[***]%" given as a royalty rate. Code already saw both and said so beside the answer; the status still read
pass. Now `runs.status.check_values` lowers such a pass to needs review when the run is decided, with the value or the
redaction mark named (status source `position_check`, whose label now says "a value" where it said "a day count").
Read whole, it is a statement about the evidence, not about the answer: of the 16 recorded passes it would change (of
896 in the owner and lab stores; nothing else changes), most values are probably right, computed from an unquoted rate
or cut off by a quote that stops short. What a person reads is now true: the passage shown does not state the figure.
An independent review approved it with notes, each kept as a test: a duration is quoted by its equivalent in the same
unit family ("1 year" by "twelve (12) months"); only bracketed marks are redactions; "redacted", "not disclosed" and the
like count only in the mark's own sentence. Not caught, and said so in the failure envelope: a wrong value that is in
the quote, and a pointer to an attachment the model was not handed or the filing omits. Recorded runs keep the status
they were decided with; `runs.values` is now inside the policy fingerprint, since it decides.

**The release gate fails when a step fails (2026-10-10).** The clean-clone gate printed each step's last line and kept
no status, so the retrieval-v2 candidate (one failing backend test, two failing browser flows) ended with exit 0. Each
step now records its exit status, the fault matrix and exporter checks compare their counts, and the gate ends "GATE
FAILED" with the failed steps named and a non-zero exit. Rehearsed: a throwaway commit with one deliberately failing
test and one deliberately failing flow failed the gate with both named; the blocked candidate failed it; the live commit
passed it (1,231 tests, 29 of 29 flows). The candidate's two browser failures were not load: the flows replay recorded
model answers keyed by the exact message, and changing the handed sections leaves the replay with no recording, as
designed. The gate was moved into the repository the same day (`scripts/release-gate.sh`).

**Two candidates measured and not adopted; the model is not reproducible (2026-10-10).** Conditions and exceptions
were the Reality Lab's largest failure (the condition criterion passed 2 of 18), with false premises behind every
confident wrong answer. A prompt that asks for the conditions that change the answer, for the premise to be corrected,
for the party to be named as the quote names it and for a redaction to be called one (`answer-v4`, kept frozen and
unused) was run against `answer-v2` on the same sections: on 16 cases pre-registered by an independent annotator on
untouched agreement families, and on the 24 Reality Lab cases, each answer scored blind. The condition criterion did
not move (1 of 10 both; 3 of 16 against 3 of 18), no false premise was corrected under either, and full passes were 4
against 4 and 7 against 6. Judges preferred the longer answers (16 to 7 over both sets), and a preference for length is
a known judging bias; answers took 29% longer. answer-v2 stays. A duration alias group ("how long" ↔ term, expire,
initial term) raised the share of agreements whose term section is handed over from 51 to 68 of 77 on automatic labels,
with no change on CUAD or the goldens, but on twelve agreements answered by the model it gave no better answers (5
correct, 6 wrong, against 5 and 4): the model read other periods as the agreement's term. Not adopted. And the same
request under the same identity (prompt hash, seed 42, temperature 0, model digest) gave a different answer in a new
model session in 8 of 18 cases, one with a different status. Verity hands back the recorded run for an identical
request, so a reader sees one answer; an evaluation that compares two variants on one sample each is comparing noise
until a repeat says how large the noise is.

**Policy-v6, read once more before release (2026-10-10).** Three things were checked against the record rather than
the cases that prompted them. The question no longer counts as evidence: it is what the reader asked, and in the lab
store every pass whose figure came only from its question had repeated a false premise as the contract's ("the Buyer's
$1,000,000 cash payment"); the owner store has none, and the guidance, the standard an answer is compared with, still
counts. A total computed from quoted figures stays a needs review, because which figures add up is a reading, but the
reason no longer reads as a verdict on the figure: it says the evidence shown does not establish it, and a figure from
the question is named as the question's. The label reads "the evidence shown does not establish a value the answer
states". Over 896 recorded passes 17 would change, 1 more than before (that false premise); nothing else moves.

**End to end, as a visitor, and what the landing claimed (2026-10-10).** A local public instance (anonymous workspaces,
access required, the real model, a fresh store) was driven in a browser through a real EDGAR agreement printed to PDF, a
real DOCX schedule, a real TXT agreement, four broken files, a second visitor on a phone, a model that could not be
reached, a review, a memo, the evidence pack and a reload. Every path worked and isolation held (the second visitor read
none of the first's runs: 404). No axe violation, overflow or console error at any width from 320 to 1920 px. What did
not hold up was smaller and is fixed, most with a test that failed first (Ctrl K, clearing from the Findings list and the corrected claims were checked in a real browser): the landing's counts read 0 until scrolled to;
it said code confirms a pass, which no policy since v3 does; the proof-run story carried its own facts; a refused
guidance explained nothing; "Clear the decision" did nothing with no remembered name; a batch list that failed to load
read "No batch recorded yet"; Ctrl K worked on one view only and blocked the browser's own shortcut elsewhere.

**Who holds the right: measured, and a check that did not generalise (2026-10-10).** Thirty-two pre-registered questions
about which party holds a right or owes a duty (false premises, true-premise controls, asymmetric rights), written by an
independent annotator on untouched agreement families and each asked twice of the real model, were labelled blind: 20
of 80 findings (25%) gave a right or a value to the wrong party, every one shown as a pass, and 12 of 22 findings on
false-premise questions accepted the premise. A deterministic check (the contract's parties read from its joining
clause; the party a conclusion has act, against the party that acts in its quote) flagged only the Reality Lab's
wrong-party answer across 1,095 recorded findings, and after a second round of general fixes on the first 16 cases it
caught 4 of 6 wrong-party findings per session there; on the 16 cases it had not seen it caught none of 8 wrong-party findings (4 per session), because the real actor is often not a party the
opening defines (an agent, a trustee, a representative) or acts through a phrase the reading does not cover. It is not
adopted; branch `party-check-experiment` keeps it. Policy-v6 did catch part of the class on the unseen cases: the
question's figure repeated as the contract's (2 of 8), at the cost of one correct answer that rejected the premise and
named its figure. Which party holds a right is a reading the model must make, and today it misreads one in four.

**The question-figure rule's false positive, traced (2026-10-10).** The correct answer that rejected a false premise and
was lowered for naming the question's $1.5 million did not hold that figure in any of its quotes; the other
session's answer, which opens with the same sentence, quoted the fee clause and kept its pass. Across every recorded store the rule lowered 11 passes: 5
had accepted a false premise, 3 restated the question's own condition (a level or a period the reader set) and
answered it wrongly or incompletely, and 3 were correct (two true figures the quote left out, one day the reader chose). Each separator code can compute was
measured on those 11: a negation in the answer's sentence (it would spare 2 correct answers and release 1 incomplete
one, but only one of the three negations is a denial, the other two are the question's own words, and a denial still
presupposes the figure: "does not have to pay the $1.5 million fee"), the figure in the cited section (it releases a floor price taken for the conversion price, an
accepted false premise), the figure anywhere in the document (it releases all 5 false premises), and a figure inside
the question's "if" clause (it releases two wrong answers and spares no correct one). The cause is the one the party
check met: which role a figure has in the contract is a reading, and code sees only whether a quote states it. The
rule is unchanged. The two separators a unit test can express (a denial, an echoed hypothetical) are pinned with
their controls in `tests/test_value_support.py`; the other two need section text `check_values` is not given.

**The interface against its design, after m7 (2026-10-10).** The m7 desktop and phone screenshots were read against
docs/archive/DESIGN.md and the m4 and m6 captures. Two defects were real, and are fixed with a test that failed first. The
card's primary action, "Inspect evidence", opened the drawer and left the document at the top of the contract, while the
same finding opened from Findings jumped to its passage; on a wide screen every way the drawer opens now marks the
passage beside it, except for a finding the verifier withheld, whose passage was not relied on. A
refused upload was printed below the demo notice, under the fold on a phone, beginning mid-sentence without the file's
name; it now reads "scan.pdf was not added: …" directly under the drop zone. The ghosted drawer in two captures is its
0.22 s cross-fade caught mid-way, not a defect. Left as they are: the Findings introduction is long on a phone, and a
TXT read with little structure labels a searched passage by a fragment of a heading ("SUCH SECURITIES (part 10)").

**Break Verity, a recorded failure in public (2026-10-10).** `/break` tells one answer that passed every check code
runs and was wrong: an unseen, pre-registered question (Q-1) about a merger agreement filed with the SEC, answered
the same way in two model sessions from the same input, with a quote located word for word, and labelled wrong party
by an AI-assisted, blind adjudication. The page is the recording, not a re-run: `backend/scripts/export_break_record.py`
writes `src/components/break/break-record.json` from the evaluation stores through the API's own run detail and
explanation (the store is copied, never opened for writing; email addresses in the notice clause are masked), and
`backend/tests/test_break_record.py` locates every quote again, runs the value rule again and recounts the party
check's numbers. The rejected party check's verdicts come from its own code at 57e4dae; the policy-v6 rule's catch and
false alarm are the Q-3 and Q-2 findings traced above. Every filing the page links was fetched in a browser on
2026-10-11 (UTC) and matched the corpus download byte for byte up to the script tag SEC appends to each response; that
prefix's sha256 is in the record. The page calls no API, runs no model and offers no upload of its own; it links to the
workbench, with a warning that nothing detects or refuses a confidential document.

**The final release review (2026-10-11).** Every public surface was read as a visitor sees it (rendered text, 320 to
1920 px) against one problem statement: a contract AI can quote the right passage and still reach the wrong
conclusion. What did not serve it was changed; nothing was redesigned for its own sake. A new public visitor's landing
counted six zeros under "Every question passes through the same six hands"; it now shows the record only once there is
one. The limits list says what code does not check (who holds a right, a missing condition). The evidence drawer,
where it says support is the model's reading, links to /break. The Findings introduction was one 70-word sentence. The
site's metadata and the README open with the problem; the README's test counts were nine days stale and are now the
gate's, dated. Two engineering defects were found by measurement, not reading: the model URL defaulted to `localhost`,
which cost every request to the model endpoint about two seconds (health 2.4 s to 0.35 s after; `docs/SCALE.md`), and
`npm audit` reported two high advisories in production dependencies: Next.js (high for server-side request
forgery in image optimization, with moderate cache-poisoning advisories for self-hosted static pages, which is how the
site runs) and source-map-js (Next 16.3.6 to 16.3.8, source-map-js 1.2.2). Eight packages in development tooling still
carry advisories, two of them critical (vitest's pool); their fixes are breaking majors and none of them is shipped. The import contracts the README promised were kept but not gated; they are now.

Deployment stays what it is: the next interface is built beside the live one, the servers stop, the build is swapped
(`.next-previous` keeps the last) and the supervisors restart them; rollback is the previous commit through the same
installer. It is not blue-green: there is one machine, one SQLite store and one GPU, and two API processes would
contend for both and for the runs each claims as its own. The outage of a release is the stop-to-answer window,
measured at each deploy, not a rebuild. Names of people appear on /break only as the filings print them in their
business roles (a stockholders' representative, an executive whose agreement was filed); their email addresses are
masked.

| Reference | Principle used | Verity before | Decision |
|---|---|---|---|
| Google SRE book, monitoring chapter | latency, traffic, errors and saturation, observed per request | request id, path, status and duration per request; stage, duration and queue wait per run; no contract text or prompt in the logs | kept; the health latency above was found this way |
| Martin Fowler, BlueGreenDeployment | two production environments, traffic switched between them | staged build swapped on one machine | not adopted (above) |
| OpenTelemetry | one trace across services | one API process; request id and run id join a request to its stages | not adopted: no second service to trace across |
| OWASP ASVS 5.0, file handling and authorization | type from content, size bounds, every object reached through its owner | `docs/FAILURE-ENVELOPE.md`, `test_anonymous.py`; every data route resolves the workspace (checked route by route, 2026-10-11) | no change needed. Every route that reads visitor records resolves the workspace; batches, goldens and families are owner-only, refused to public workspaces |
| Karpathy, autoresearch | a fixed evaluation; keep a change only if it measurably improves, else revert | pre-registered unseen cases; the party check kept on its branch, not merged | already the practice |
| Matt Pocock, diagnosing skill | a red-capable loop before a hypothesis | the health delay: probe, then `localhost` against `127.0.0.1`, then a failing test | applied |
| Addy Osmani, agent skills (security and hardening) | audit dependencies; separate shipped from dev-only | no audit in the gate | audited once; production clean, dev-only deferred |

Not consulted: Ivo's Sage model card and published engineering writing. Nothing in the product rests on what Ivo's
systems do or lack, and nothing here says so.

**The trust review (2026-10-11).** Ivo's public customer stories and Trust Center were read for what enterprise legal
teams expect, not to claim any of it. Two things changed how Verity is presented. First, the workflow: in a public
customer story a contracts manager without a legal background triages vendor contracts from an AI summary and escalates
only what looks high-risk. A Verity answer that names the wrong holder of a right carries a real quote and no warning, so in
that kind of triage it may not be escalated; /break now says what acting on its answer would get wrong, from
the pre-registered conditions, labelled as a reading of the clause and not an incident. Second, disclosure: a trust
center names everyone who handles customer data. Verity's landing said "It does not send the contract anywhere",
though HTTPS ends at Cloudflare, which carries the site's traffic before the tunnel; it now says so.

Two weaknesses were found in the record and fixed with tests that failed first. Retention deleted a visitor's rows and
files, but SQLite left the deleted text in the database file's free pages and write-ahead log, so "deleted 7 days after
your first visit" was not true of the disk; `secure_delete` and a checkpoint on every hourly pass make it so for
the rows. Residue written before `secure_delete` (rows deleted or rewritten earlier) is outside a purge's reach; the
review reproduced it, and a one-time VACUUM of the live store, before its earliest workspace ends (2026-10-16 10:17
UTC), clears it. Removed files are unlinked, not overwritten, and the landing no longer says otherwise. And the API, on Windows' default event loop, stopped accepting connections after a client reset during accept;
the supervisor's logs show 18 such restarts in 27 hours. The first fix, the selector loop, traded that for a
512-socket cap one visitor holding progress streams could reach (found in review). The deployed loop is Windows'
proactor with one change, in `app.serving`: an accept the client caused to fail is retried, and counted in the log
(the first at once, the rest each minute) rather than written out with a traceback each time.

Considered and not done: a separate trust page (the three questions a visitor has are answered where they upload, with
links to the isolation and deletion tests; a page would repeat them further from the decision); a public encryption-
at-rest claim (Windows reports the system volume as BitLocker-protected, but the tooling that would confirm it needs
elevation, so nothing is claimed); pinning the Python requirements (the live and gate environments differ in 15
packages, both audited clean with pip-audit; pinning is a change to how releases are made, left for a decision); a
security contact (GitHub's private vulnerability reporting is a repository setting the owner turns on; a SECURITY.md
pointing at it before then would point at nothing).

**The m9 follow-up (2026-10-11).** Three things found while preparing the trust release changed code. First, an incident:
at 05:44 the live API stopped accepting (WinError 64, the failure 03f056d fixes) and its supervisor died on its next
log line, because an operator's `tail -F` held `api.supervisor.log` without write sharing and the bare `Add-Content`
threw under `$ErrorActionPreference = "Stop"`. The API stayed down for 17 minutes, until the reader was stopped and
the scheduled task started again. Every write the supervisor makes to its log or pid file now goes through
`Write-Record`, which retries and then gives the record up (`tests/test_supervisor_records.py`, with a control showing
the same lock ending a bare write); a line it gives up is counted on the next one written. Two reviews found the same
class elsewhere in the loop (an empty `access.secret` made `.Trim()` throw on null; a missing executable made
`Start-Process` throw), so the invariant is now held at the loop: only the stop file ends it, and a pass that fails
anywhere is logged, stops the server it started, and is retried on the backoff, shown on the real script. Second, the trust release's own flood test failed in 3 of 5 runs alone: when a
client resets during close, CPython 3.13.2's `_call_connection_lost` raises between `shutdown()` and `close()`, leaving
the socket to the finaliser and the server counting the connection. The loop's connections now use
`ResilientSocketTransport`, which finishes the close for a client-caused failure only; the flood test passed 20 of 20.
Third, a fresh-context first-visit review of the landing and /break: the unseen score counted the same four questions
twice ("0 of 8"), the misses below it likewise, the status line printed one sentence twice, the landing contradicted
itself about withheld quotes, and the rejected fix opened on its tuned score. Each is fixed from the record with a
test; the default view is its own commit so it can be dropped alone. Considered and not done: a role key under the
quote (it would name an individual while whether such names stay is the owner's open decision), an accept / review /
escalate step before the reveal (it would hide a verdict the first screen now shows, and is close to the onboarding
tour the visual rules exclude), and any party, condition or obligation field (the domain review found it would change
what the model is asked, not what code can verify; the party check already failed on unseen cases).

**The review race (2026-10-11).** The live smoke test of bd8d470 confirmed a finding in the drawer, closed it and
asked the next question at once: the new run finished on the server, but the screen and the URL stayed on the
reviewed run, with no progress shown. Reproduced twice on the public site; with a five-second pause it did not happen.
The cause: after a review the workbench re-read the reviewed run and showed it through the follower's `show`, which
stops whatever it follows; that read could land after the next question had started. The invariant is now held in
the follower (`hooks/useRunFollower.ts`): a record that arrives after the person moved on never takes the screen.
`refresh` replaces only the finished run that is still on screen; `claim` marks a newer intent, so `openRun` checks
after its fetches that no question was asked and no other run opened meanwhile. Both review updates and the re-read
on returning to the Assistant go through `refresh`, which retires that effect's own cancel flag. Tests: four
follower cases (the race itself, a refresh of a run in flight, a refresh of the run on screen, claims), and a browser
flow that holds the re-read back two seconds and asks at once; it failed twice on the old code with the URL still on
the reviewed run, and passes on either review path (confirm, or clear an earlier decision).
The first gate of that change failed two flows on HTTP 429: every browser flow comes from one address, the API allows
20 run starts per reader in ten minutes, and the bd8d470 suite had made exactly 20, so the new flow's two questions
tipped the last two flows over. The limit is now a setting, `run_start_limit` (`WORKBENCH_RUN_START_LIMIT`, default
20, which production keeps), and the browser flows' own API raises it to 1,000; no flow tests the limit, and the
backend tests that do patch the limiter directly. A test checks that the limit is 20 unless the setting is given.

**The m10 experience (2026-10-12).** A teardown of the live site, five competing working concepts, three independent
reviews (product and domain, design and accessibility, a skeptical engineer) and two investigations led to a
recommendation; Pavan approved six items and one wording fix. The frozen visual system, the landing, the run follower,
review, export, status rules and the exporter are untouched. On /break: (1) a role key on load under the quote, "Who
is who in this clause", lists the recorded definitions the pre-registered answer cites outside the quoted clause and
boxes each party where the page's text search finds it, labelled as this page's search; who holds the right is the
answer's reading and no released code checks it. The m9 entry set a role key aside because it would name an
individual; the name it shows is already on the page, in the question and in the pre-registered answer, both from the
public filing, so the key adds a definition, not a name. (2) The question is called what the record says it is, a
planted false premise, with the pre-registered answer's first words; the first boundary row adds "Found means the
words are there. It does not mean they support the answer." (3) The rejected party check is shown side by side, the
cases it was built on beside the unseen ones, counted in questions caught in every session (4 of 5; 0 of 4) with the
findings as a second, named count (8 of 12; 0 of 8), since a session can give one question more than one finding;
each question opens the check's own verdict. (4) The hand-off to the workbench says it runs on one laptop GPU, takes
half a minute or more per answer and is offline when the laptop is. The wording fix: the page said the released value
rule "found nothing to lower" on the headline, which the record does not establish (the run was recorded under
policy-v7, policy-v6 plus the rejected party check); it now says what `tests/test_break_record.py` establishes, that
policy-v6 run again on the answer decides it as recorded. In the workbench: (5) a finding the model reported as not
found still states only the product's sentence (the rule of 2026-10-02 stands), and the model's own sentence is kept
on the card collapsed, and in the memo (HTML and DOCX) after a label, both naming it as the model's, not checked by
code, and withheld because it reported the point as not found (`Finding.withheld_conclusion`). The drawer and the
evidence pack already carried it. No status changes: of 23 recorded substantive "missing" sentences, 7 were right, 7
incomplete and 9 wrong, and nothing in code tells them apart, so showing them as findings (option B) was rejected; the
cause is prompt rule 8, which stays the owner's decision with goldens. (6) The card's support row names the class it
leaves open: "Not checked by code: whether the passage supports the answer, including who holds the right or owes the
duty". No new check; the party check stays rejected. Rejected concepts, kept with the research: a guided tour (it
delays the point, and its dimmed text failed contrast), an X-ray page (a developer-tool template with invented stages),
a second ledger beside the drawer, any toggle that hides the verdict and any choose-first step.
The independent review of e239ea5 approved it with fixes, each made with a test. The role key introduced the
pre-registered conditions as "the pre-registered answer", whose words they are not; it now names them, and a test
checks that every quotation in the key is verbatim from the field it is introduced as. The rejected fix's title and
summary read "4 of 5 cases it was built on", as if the check had been built on five questions; they now count
wrong-party questions, in every session, in both places. The box note now says which search drew which box (the
defined term in the quote, the name it defines in the answer). The card and the memo decided the withheld sentence
apart, the card from the raw fields and the memo from `Finding.withheld_conclusion`, and could disagree on a sentence
of whitespace or the product's own sentence with a trailing newline; the API now sends `withheld_conclusion` and the
card renders only that, as does the evidence drawer, which had decided the same thing for itself since before m10. `firstOccurrences` compared each box with the one before it even when that one had been
dropped, so a third phrase could overlap a kept box and print its text twice; it now compares with the last box kept,
under a property test of 500 random phrase sets. The counterexample's two "found nothing to lower" sentences now say
what the tests establish, as the headline's does, and the hand-off no longer promises one model call per answer (a run
retries on invalid output). Kept as they are: the sentence "Found means the words are there…" sits in the exhibit's
check rows, which a first visitor sees without opening a tab; and memos written before this change keep their old
form, since a memo is generated once per run and review state.

**Cloud readiness (2026-10-12).** Pavan asked for a payment-ready deployment on one DigitalOcean VM and a Modal GPU,
built from the existing `deploy/cloud/` kit without changing the architecture or the workstation's release (001b6a0).
The kit was written before the public demo and ran invite-only: it now carries the demo's settings (anonymous sessions
signed with the gate's secret, the 200-a-day ceiling, retrieval and prompt pinned as on the workstation) and drops the
proof run, which a public store can never hold. Its nightly backups and the droplet's weekly backups are removed: a
copy of the public store holds visitors' contracts past the seven days the first screen promises unless it is deleted
before the earliest workspace in it ends, so the store is not backed up and the deployment is rebuilt instead (README,
what the disk keeps). Upload spools live in memory (`/tmp` as tmpfs) and Caddy refuses a body over 26 MiB before the API
reads it. The API image installs `backend/requirements.lock`, the workstation's versions, instead of a second pinned
list that had drifted, and its `test` stage runs the backend suite on that image (Linux, at fe030a8: 1,274 passed, 22 skipped,
the Windows-only ones). The release gate now installs the same lock: it had been testing the newest versions on the day
(FastAPI 0.143 against the workstation's 0.141). A server that runs but stops answering is restarted (`liveness.py`,
the workstation supervisor's rule of three probes); the rehearsal of that fix found its own first version choosing pid 1
(docker-init), which no signal from inside the container can end. The /state record is mounted read-only. Modal: Ollama
pinned to the workstation's 0.40.3, one request at a time, two cores and 8 GiB; checked against Modal SDK 1.6.1, not
deployed. Two failures a cold, serverless model would have caused are fixed in `providers/ollama.py`, each with a test
on a real socket: the build check before an answer waited 5 s, less than a container's start, so the first question
after the GPU slept would have failed; and Modal answers a request still running at 150 s with a 303 to a URL that
waits for the result, which the client did not follow. Found by a load rehearsal (nine visitors, contracts up to 25 MB):
a run holds its session for its whole life, the wait for the one model included, so questions asked together held the
default pool's 15 connections and every other request waited 30 s for one, a run failing among them; and a large
ingest held the write lock past Python's 5 s busy wait, so uploads beside it failed. SQLite now opens a connection per
session (`NullPool`) and waits 30 s for a lock; the same burst then completed with no error. Also fixed: a memo draft a
killed process left under `memos/pending` was never swept; a SQL error could carry a contract's words into the log
(`hide_parameters`); and `package-lock.json` had again lost the two packages a Linux `npm ci` needs (as before
f8a2f92), so no cloud interface image could be built: regenerated on Linux, and a backend test now resolves every
dependency in the lock the way npm does. Not done: building the interface for a static /break (it would need its own
links to the workbench and a second build target for a page the VM already serves without the API or the GPU). What
still needs a paid test, and the gates that decide it: `deploy/cloud/CLOUD-READINESS.md`.
The independent review of the cloud preparation (a fresh agent that could reject) approved it with fixes and found no
security hole. Fixed: SQLite wrote its temporary files under `/var/tmp`, on the container's disk, where a purge's
statement journal can hold a contract's words (`TMPDIR=/tmp` moves them into memory; a probe in the image shows both);
Modal's request timeout is the API's 600 s, the only bound that holds once a long call is redirected; core dumps are off,
capabilities dropped and privileges not escalatable in the API and interface containers; Ollama comes from its own image
pinned by digest rather than an install script; the runbook's claims were narrowed to what the evidence shows, and the
rehearsal was re-run on the final images with every output kept. Measuring four 25 MB uploads at once (1.29 GiB for the
containers, the API 1.20 GiB) moved the recommended VM from 2 GB to 4 GB: without swap, which the privacy design rules
out, a 2 GB machine had no margin for that burst.

**Reading cost and request bodies bounded (2026-10-13).** A trial of gstack's review and security checklists on the
Hetzner candidate found two ways one anonymous request could take the 4 GB host's memory, both measured before anything
changed. An 84 KB .docx of six million empty paragraphs (35 MB unpacked, under the 256 MB bound) took 848 MB and 35 s to
read. FastAPI parses a JSON body before the access gate runs, so 40 MB to /api/runs with no session took the API to a
2 GB peak and held the event loop for 19 s; Cloudflare passes 100 MB. The invariants: what reading an upload may cost
is bounded by what a real contract needs, counted before anything costly is built; and no body is read past what its
route needs, on the bytes received, before the gate. The reading bound was first written in terms of the bytes: an
element count for .docx and a budget of inflated page content for PDF (7b12989). An independent review rejected it with
measurements: comments, processing instructions and attributes, which the count did not see, still took 1.4 to 2 GB
from a 125 to 529 KB upload; counting every member inflated a bzip2 member nothing reads (862 MB from 36 KB); and a
1.6 KB PDF whose page positions text half a million times read for 20 s in layout mode, so bytes of content do not
bound time. Each bound was one shape behind the next. So the bound moved to what reading costs, measured while it runs:
every reading happens in a child process whose memory is sampled every 50 ms and which is ended past 768 MB or at
30 s (`ingest/bounded.py`; fork server on Linux, spawn on Windows). Within the bounds a reading comes back exactly as
the API's own process would read it (40 real files and 10 fixtures compared field by field), a reader's refusal as it
was raised, and any other failure as a server error. A counter-review of that round approved it and found the rest:
60 s let two hostile files hold both reading slots while a third reader waited past Cloudflare's 100 s, so the bound is
30 s (the largest real reading measured is 9.2 s) and each network reads one file at a time; a document read again
for a revision check went around the two slots, so the slots are now in the one function every reading goes through;
a production switch could turn the bounds off, so only the test suite can. Of the static checks only the 64 MB
declared unpacked size stays (the largest of 323 real contracts unpacks to 6.4 MB); a declaration does not bound what
zipfile inflates, so it only spares reading what no real file declares. Every request is cut off at 26 MiB
for an upload and 1 MiB otherwise, declared or chunked, which also closes the recorded residual of chunked uploads
spooled in full. Uploads are read two at a time on threads of their own, so they neither multiply the cost nor hold the
threads /api/health needs (45 slow uploads held all 40 and health waited 10.4 s, past the liveness probe's 5 s). The API
container may use 2.5 GiB of the host (`mem_limit: 2560m`). Not changed: stored readings and the parser version (no accepted file reads
differently). Left open: a file inside the bounds holds a reading slot for up to 30 s, so readers on two networks can still
keep the slots busy; the reading's child inherits the API's environment and its answer is unpickled by the API, so
it bounds resources, not trust; an over-limit upload sent straight to the API, with no edge in front, may see the
connection reset
instead of the 413 (through Cloudflare the 413 arrives, measured on staging).

A third counter-review (war room wave 5) rejected the door and found every wait in it untimed. Six uploads whose bodies
never finished closed the door for everyone; a per-network cap and a 30 s pause limit followed, but a body trickled at
a byte every two seconds still held its place, received uploads waited for their reading as long as others' readings
took, documents read again for a revision check waited for a slot on the threads every sync route shares (sixty at
once, and health answered after 21.5 s), and on Windows a reading child that died at start left the parent blocked
past every deadline. The invariant: every place an upload or a reading holds is held for a bounded time, and a wait
past its bound answers "not now" (503, Retry-After) with nothing kept. So: a body must average 32 KiB a second of
waiting for the client after its first 10 s; an upload waits at most 45 s for its network's turn and a reading slot
together, on the event loop with no copy of its bytes, so an answer comes inside Cloudflare's 100 s; documents are read
again one at a time, each once, off the request's thread, and a request waits 2 s for it; the child is handed its file
by a path, in a folder of the store's own in the system's temporary folder, which the API empties at start and the
retention sweep keeps clear (loose in that folder, a force-stopped API left a contract copy that nothing on Windows
removes; Codex), and noticed when it ends. Its fourth round rejected a count of places itself: with sixteen places
overall and two per IPv6 /64, eight /64s of one host held all sixteen by sending headers and reconnecting as each was
ended (746 B/s; a visitor on a ninth network got in 0 of 18 times). The door now counts no places overall: each network
(an IPv4 address or an IPv6 /64) has two uploads in flight, and all of them together hold at most 384 MiB of received
body, so an upload that sends nothing holds nothing and holding the spool takes sending it. Found with it and fixed at
its primitive: a request let in before retention purged its workspace wrote its grant, document and file afterwards,
into a workspace no longer listed, kept forever; every row a public workspace adds (grants, runs, guidance) is now
admitted under the write lock only while the workspace is open, the lock retention deletes under. A write lock not had
within the store's 30 s wait is 503, not an unhandled error; a paused or nearly full demo refuses an upload on its
headers. Still open: readers on two networks can keep both reading slots busy with files that read for 30 s, so others
wait their 45 s and are told to try again (F-54, accepted); eight /64s of one /48 can hold about 352 to 380 MiB of the spool,
kept full for about 3.7 Mbit/s of resent bodies, which refuses only uploads larger than what is left (a 2 KB and a
20 MB upload still got in; counter-review round 4); a document read again waits 2 s, so its first view may say it could not be compared yet;
the hourly windows count by full address, so one network can still take the day's shared questions (F-32, F-33, the
owner's decision).

**A pack claims an answer's input only when the record shows it (2026-10-13, F-14).** When the model's first answer
failed validation, the run asked again with the first message plus a note quoting the error, and kept the second answer
with neither the first answer nor that message. The evidence pack still packed the first message as "the exact messages
the model was given", verify.py printed PASS for it, and the explanation called it the exact input. No byte was
misstated (the first message is what the checking stage hashed); the claim was wider than the record. The invariant:
every model output a run keeps is stored, or reconstructable, together with the exact input that produced it, and no
surface claims more. Chosen: say so, not store more. `analyze` reports validation rounds apart from calls, the checking
stage records them in a new nullable `run_stages.rounds`, and `reconstruct_input` decides once, for the pack, verify.py,
the explanation and the two scripts, whether the rebuilt messages are the kept answer's input; when they are not, no
model input is packed, verify.py prints a NOTE with the reason and no PASS, and the explanation's "Exact input" gives
the reason while its input-hash check still matches. A row written before `rounds` is read from `attempt`: one call is
one round, three or four calls or an invalid_output ending are two, and two calls otherwise are undetermined and said
to be (at most 3 of 1,599 recorded checking stages had two calls or more). Not chosen: storing every round's messages
and outputs, a larger change to the record for a case this rare. Unchanged: prompts, retrieval, model settings, the
API's shape, every historical row.

**Quotas counted with their write (2026-10-13).** The war room's F-13 / R10, confirmed by two reruns: every quota the
store counts was check-then-insert. A public workspace's documents were counted before its upload was read and the grant
written seconds later, so sixteen uploads at once from one visitor were all held against a cap of ten; the daily run
ceiling was counted before the run's insert, and eight of ten starts released together got past a ceiling of three. In
the cloud that ceiling is the spend stop for a paid GPU. The invariant: a quota is counted, and the row it limits is
written, in one transaction no concurrent request can interleave. The class was every quota counted in SQL before a
write: documents per public workspace, uploads per UTC day, questions per public workspace per day, new runs per day.
One primitive now writes each of them (`application/quotas.py` `admit`, over `db.write_locked`, which begins the
transaction with `BEGIN IMMEDIATE`): the lookup that hands back an existing row, the quota counts and the insert share
the write lock; reading and parsing stay outside it. The counts that lived in `api/access.py` (`admit_upload`,
`limit_run_starts`), `start_run.refuse_past_daily_budget` and `api/model.py` are one set of definitions; the early
counts that spare a file's reading or a model's wake-up remain, as advice. Removed with them: the run-start race
handler (`IntegrityError` → reuse), which the lookup under the lock replaces. One visible change: a question asked
again in a workspace that has used its questions for the day is handed its run (200) instead of 429, as it already was
at the global ceiling. The original file is now written after the quotas admit an upload, so a refused upload leaves no
file. Measured: the reproductions held 6 of 2, 16 of 10 and 8 of 3; now exactly the cap over repeated trials, with no
500 (`test_quota_admission.py`, `test_write_lock.py`). Not in the class: the per-address and per-reader windows and the
wake-up budget, kept in this process's memory and checked and recorded under one lock (one API process; more workers
would each keep their own).

**Verifier v8: no span begins or ends inside a number, and a sign is never dropped (2026-10-13; approved by Pavan the same day, parentheses around every number kept).** The war
room (F-03) found the verifier's own v3 rule broken at its edges: a comma or a point between two digits counted as an
edge, and the exact tier runs first, so "$1,500" was found word for word in "$1,500,000", "$15" in "$15.50", "within
30" in "within 30.5" and "Section 5" in "Section 5.2", and the memo printed "$1,500" as found. The typed tier dropped a
minus sign and the parentheses of an accounting negative, so "an adjustment of 5%" verified against "-5%" and "a credit
of $500" against "($500)". The invariant: a located span never begins or ends inside a number, and a number's sign is
part of its value, at every tier. A number as it is written is read once (`tokens.written_numbers`): its tokens and the
digit marks joining them, typeset ones included, its sign, its currency or percent sign, a section label's parts and
the parentheses around it. `bounded` refuses an edge inside one, as the reader sees the text (a zero-width space makes
no edge); the typed tier compares a number with its sign and parentheses (`tokens.signed`); `tokenize` is unchanged, so
the values `runs.values` and `trust.facts` read do not move and the policy version stays. A space is still an edge.
Parentheses around any number are kept, because accounting's "(30)" cannot be told from a restated one: a quote that
drops them ("30 days" for "thirty (30) days") is withheld, where v7 highlighted "30) days". Replayed under v7 and v8,
none of 2,853 recorded verified spans in 35 lab and QA stores changes (572 of them the lab's; some stores are copies); of 13,823 CUAD answer
highlights in 510 contracts, 3 are withheld, each cut inside a section number ("Section 6." of "6.1"), and 2 one-character
quotes move off a decimal point. Recorded runs keep the version they were verified under.

**Page furniture is not a section, and a pass says what it did not see (2026-10-13; approved by Pavan the same day; war room F-04).** A PDF
printing "ACME SERVICES AGREEMENT" at the top of every page made each printing a section: §7 ended "shall not exceed
the fees paid in the", its tail "twelve (12) months … except for breach of Section 9" sat in a section of its own,
BM25 handed over §7 and §9 but not the tail, and the pass said nothing, because only a pass whose periods code
compared named a section the model was not handed. The v11 rule caught a running line only by a rising page number.
Two invariants. Reader v12: in a format that says where each page begins (PDF), a line printed the same on most pages,
three at least, is page furniture, text where it stands and never a heading (`sections.page_furniture`); the
document's own heading printed once at its head stays a heading, and numbered, structural and minority lines are
untouched. Policy-v8: a pass whose verified sentence points at a section the model was not handed says "the sentence
points at §N, which was not handed to the model", one wording (`policy.proof.unseen_reason`), compared or not; the
status does not move. `unseen_references` now takes the section numbered exactly so before one whose number only ends
in it. Measured before the change, read-only. Readings: 41 unique PDFs, 195 DOCX and 6,075 plain texts from the QA,
lab and EDGAR corpora read with both readers; 1 of 33 readable PDFs differs (CUAD's eGain hosting agreement, whose
running header had also cut a termination right from "upon the other party's material breach"), every DOCX and plain
text reads the same. Statuses: over 1,623 recorded passes in 12 local stores, 216 would carry the new reason (135 of
856 in the owner's local store), all without guidance, none changes status; without the exact-number rule 5 more
would have named a §5.1 that was handed. Not changed: retrieval, prompts, the model, recorded runs and stored
readings (a document read by v11 keeps its reading; the same bytes uploaded again are read by v12). Left open: plain
text has no page marks the reader reads, so EDGAR .txt furniture stays a heading (1,628 of 6,075 texts print some
unnumbered heading line three or more times, furniture and real repeats mixed); furniture stays inside the clause
text, so a quote that runs across a page break is withheld. The interface's "Compared" row prefixed this reason with
"Code compared:" where nothing was compared; that is corrected in the release integration below.

**Release integration: the war room's repairs, verifier v8 and reader v12 together (2026-10-13).** One candidate on
8b7b8fb: the war room's repairs (R1, R5, R6, R9-R13 and their counter-review rounds), R3 and R4 as approved. Combining
them showed five things none of them had covered, each fixed at its owner with a test run red on the code before it.
What the verifier works out about a text (where its numbers are, a quote's words) was cached for the life of the
process keyed by the text itself, so section texts and quotes of a deleted workspace stayed in memory; it now lives
for one verification pass (`verify/spans.verification_pass`: a run's verification, a trust manifest, a trust diff, or
one `locate`), still read once within it. A document read again for a revision check was kept by path until 32 newer
ones displaced it; it is now dropped once ten minutes old, at the next reading or the next hourly retention pass,
whichever comes first, and every retention pass drops all of them, a pass that fails midway included. The evidence pack's
standalone verify.py never checked a span's edges, and its typed check dropped signs, parentheses and precision, so a
v8 pack whose offsets were moved onto "$1,500" inside "$1,500,000" passed it while the workbench refuses it; for a run
verified under v8 it now checks v8's edges and signed numbers, with v8's reading of a written number copied into the
pack when it is made (Python 3.11 or later, or it fails those spans rather than pass them unchecked), and a run
verified earlier is checked as before; the pack says it is not signed. The counter-review found its typed check
still read text its own way: tokens that could end inside a run of letters and digits (as before v7), words joined
(as before v6), a span cut out of its section rather than read in place, and a quote of punctuation alone accepted.
So "$10M (in aggregate) per year", which the workbench verified, failed the pack, and 31 of 40,000 fuzzed tampered
spans passed it. For a run verified under v7 or later the pack now reads tokens with the workbench's own pattern,
copied in, in place in the searched text, words whole; 0 of 80,000 tampered typed spans pass, 0 of 60,000 genuine
spans fail, and the 17,261 spans the recorded quotes locate in 52 stores pass under both v7 and v8. A v7 pack that
dropped a number's precision ("$15" for "$15.00") passed before; v7 itself never verified it, and now the pack
fails it too. A pass whose reason only names a section the
model was not handed (policy-v8) was shown under "Code compared", and the memo and the pack carried no reason at
all; `runs.status.basis` reads from the record whether code compared a period and what was not seen, and the card,
the drawer, the memo and the pack say both; no status changed. The cloud runbook unpacked each release over the last
one, kept `.env` and the tunnel credential inside the source tree and, at cutover, kept staging's store for the
public name; releases are now immutable directories keyed by the full commit, configuration lives outside them, the
store is named by the host's role and required, and each image carries its commit. Measured: replayed under v7 and
the candidate, 18,717 recorded spans in 52 stores, none changed; one run's verification on hostile 6,000-character
sections 0.33-0.54 s (v7 0.10-0.31 s); the trust layer's count over the largest real contract (7,174 sections)
6.1-6.9 s, as under v7 (7.2-7.5 s), two quiet runs each, and over a crafted 200-section document 18 s (v7 10 s), the
price of reading every occurrence where v7 stopped at a wrong first one. Left open: the trust manifest is computed on the request's thread from the
pool every sync route shares, so a crafted document makes each of its views slow; 6814c50 on staging has no memory
limit; the laptop's 001b6a0 prints a SQL error's bound values (it predates 4a8c24d), so it is not a safe fallback.
v8's sign does not reach an amount written with a letter after its digits: "$5M" is found in "-$5M" and in
"($5M)", as under v7, since a token never ends inside a run of letters and digits and "5M" is one; closing it is a
verifier rule (v9), not taken in this release, and README says so beside the rule. The Modal function pins no GPU
region: requests enter through Virginia and the GPU was observed in us-east, but it may run in any region Modal has,
and the public wording now says that, not "in the US".

## 2026-10-14: two evidence-integrity blockers closed (verifier v9, reader v13)

The legal evaluation (outside the repository) found two code-labelled statements false,
with scripted answers served through the candidate's own pipeline; Pavan ruled both release blockers, not accepted
limitations. B1: verifier v8 verified the quote "Adjustment Amount $5M" against "Adjustment Amount -$5M" at the typed
tier; the run stood as a pass, the card said "with the same words and numbers", the memo printed the quote as observed
language and the evidence pack's verify.py agreed. An amount written with a magnitude letter was one word to the
tokens ("5m"), so its minus sign, parentheses and currency were punctuation, and the edge rule did not see it as a
number ("$5M" was found word for word inside "-$5M"). Verifier v9: such an amount, and an amount in a currency written
as letters against a dollar sign ("US$500", whose sign v8 also dropped), is a number as it is written; `signed` joins
its sign, parentheses, currency and magnitude to it and compares what stands before a number without spaces or case;
inside a number written with a sign or parentheses every edge splits it, a space included ("10K" is not inside "-USD
10K"; "500" still stands alone in an unsigned "USD 500"). `tokenize` is unchanged, so the values policy reads do not
move, and policy-v8 stands. The evidence pack carries v8's pattern (unchanged to the character, pinned by its hash) and
v9's, and checks each run under the version that verified it. B2: the DOCX reader gave every Word heading whose text
states no number a number computed from heading levels, whether or not Word numbers it, so "SCHEDULE A" after "9.
Governing Law" was §9.1, the governing-law clause's own number, on the card, in the memo and in the pack. Reader v13
computes a number only for a heading Word prints a clause number for: a w:numPr on the paragraph or its style chain
naming a list whose level (read through the numbering part, its overrides and one style link) is numbered, not a
bullet, not empty, and not a lettered label other than Section, Clause or Article ("Schedule %1" on the level or on
its list's first level); any other heading without a written number is labelled by its heading alone and leaves the
count of the numbered headings around it untouched. Two tests that asserted computed numbers on python-docx headings Word does not number
were asserting the defect and now assert none. An independent review approved the repair with three fixes, all taken: a
currency outside the six codes first listed ("INR 5M", "₹5M", "Rs. 5M") still lost its sign, so v9 reads every
Unicode currency sign, every ISO 4217 code, "Rs.", "RMB" and "kr", and capitals against a dollar sign; a zero-width or
direction mark between the sign and the amount hid the sign, so signs and currencies are read as the reader sees the
text; and a heading in a bullet list, an unnumbered list, a missing list or a "Schedule %1" list was still numbered,
so the reader resolves the list level Word would print. A property test then found "Rs. 5M" cut at its full stop
inside "-Rs. 5M", so inside a number written with a sign or parentheses every edge splits it, not only a space.
A second review approved that round with two fixes and one more, all taken: a shortcut that skipped any edge with no
digit in the next 16 characters changed verdicts ("-15" stood alone in "-15 percent" while the pack refused it, and
the verdict depended on what followed the number), so it is gone and every edge is read against the numbers; the
reader looked up each list instance's overrides by scanning every instance, with a query built from the instance's
id, so 8,000 instances in a 56 KB upload read for 54 s, past the 30 s reading bound, and an id holding a quote refused
the file: the numbering part is now read in one pass with no query (8,000 instances 0.08 s), and each style chain's
numbering once per reading; and a currency code glued to digits with no magnitude letter ("INR500") still lost its
sign, so it is an amount too.
Measured: replayed under v8 and v9, 18,742 recorded spans in the 47 of 53 stores that hold any
(17,285 verified), 3 changed, all three the evaluation's own scripted sign-drop probes; the corpus of 6,311 files
re-read under v12 and v13: 116 DOCX changed, every change a number removed from a heading Word does not number (353
numbers; 0 renumbered, 0 texts, headings or section counts changed; no PDF or plain text changed; the bundled sample,
all of whose 120 headings Word numbers, reads the same). Cost: verification at the product's bounds 8-26% slower on
hostile inputs (one run 0.24-0.54 s, v8 0.23-0.50 s; the trust layer's count of 3,000 quotes 6.8-16.1 s, v8 6.1-13.0 s),
within 2% either way on the largest real contracts; memory unchanged. Reading the 195 corpus DOCX
took 157.7 s, v12 159.2 s (the 35 that take over 0.2 s: median 0.99 times v12, at most 1.09); 8,000 numbering
instances in a 56 KB file read in 0.08 s (v12 0.02 s).
Left open: a currency abbreviation outside that set ("Ksh 5M", "RM5M", "Rp 5M") is read as a word, so its sign is not
reached; "INR500" quoted as "INR 500" is refused at the typed tier (the safe side); Word's list rendering is not
reproduced (a roman or lettered level still shows the decimal count, and a "Schedule %1" heading is labelled by its
text, without Word's "Schedule 1"); on the conservative side, these headings Word numbers get no number: a level whose
label is a word other than Section, Clause or Article ("Sec. %1", "Art. %1", "Paragraph %1", "Artikel %1"), the
sub-levels of a "Part %1" list, a level an override redefines without text, and a heading style linked only from a
list definition. The evaluation's frozen keys were not touched;
the H2 and H4 documents that exposed the blockers are flagged in its records as having informed a deterministic fix.

## 2026-10-14: after the legal pilot, five release defects repaired (verifier v10, reader v14, policy-v9, the memo)

The six-task real-Qwen pilot (stage-a-pilot-1, outside the repository) and its readiness probes left five
public-release defects, all reproduced: its records, grades and hashes are kept as they are, and its six questions are development-visible
from now on, never again a fresh holdout. No prompt changed and no model was called. (1) Verifier v10: an amount in a currency v9 did not
name kept no sign ("Ksh 5M" verified in "-Ksh 5M", "RM5M" in "(RM5M)", "Rp 5M" in "(Rp 5M)", the pack agreeing). A short label (one to
four letters, an optional full stop and space) directly after a minus sign or inside an opening parenthesis is now part of the number,
whatever it names, and a word holding digits inside such a number is part of its value; v9's pattern stays in the pack, to the
character, for v9 runs (the pilot's among them). As v8 does for "(30)", a quote that drops the parentheses of "(No. 1)" is withheld.
(2) Reader v14, DOCX: a heading's number was a count of headings by level, so a list starting at 3 read "1", a restarted list "3", a
Heading 2 on a list's first level "0.1", a written "7" between list items pushed the next to "8". A heading now carries the number
Word prints, from the list's own counters over every numbered paragraph in document order (tables included): start values, an
instance's start override, deeper levels restarting, decimal, decimal-zero, roman and letters. Where the reader cannot say exactly
(two instances of one list in use, w:lvlRestart, w:isLgl, a text box, a tracked change to the paragraph's properties, another format),
the heading has no number: an omission, never a guess. A paragraph Word does not count is not counted: one whose mark
is a tracked deletion or move, and an empty one holding a section break (Common Paper's cover page ends in one; Word
prints "1. Service" after it, and the first v14 said "2" for all of its 121 numbered paragraphs, caught by the
corpus check against Word 16 itself, before any release). (3) policy-v9: guidance in Business Days against a quote in calendar days came
back incomparable and fell through to the model's hint, so "30 days, which meets the guidance" of 30 Business Days stood as within
guidance with no reason, on real output (H4-Q5). Where both state a period code cannot compare, a pass the model proposed is now needs
review (position_check) with the reason. One test asserted the old behaviour for a month against days and now asserts the new.
(4) The memo headed that wrong answer "Issues requiring review (0). None. Every finding was within guidance or a plain answer." It now
says "Flagged by automated checks (N)", gives each flag code's own reason ("Why flagged."), says with none that the findings are the
model's answers and that code verified only their quotes, and says for each finding whether a person reviewed it. (5) Reader v14, all
formats: "AMENDMENT NO. 1 TO EQUIPMENT LEASE AGREEMENT" was cut to the title "AMENDMENT NO" at the full stop of "NO.", so the model's
citation of it was shown as "found in AMENDMENT NO."; and a PDF line wrapping a clause ("11.2 This Lease may be amended … both parties.
If an", "8.1 Seller shall indemnify … breach of Seller's") was a title, its first sentence in no section text. A lead-in title no
longer ends at an abbreviation (a reference word before a number, a name's "Corp."), and a heading line holding a sentence end or a
lower-case "shall", "must", "may" or "will" is body under a short label. The model's omission of the month-twelve condition in H1-Q1
is a model limitation, recorded and not acted on; the frozen key is unchanged. The corpus check also found that a clause
line taken as body took its label from whatever heading stood a level up ("<PAGE>", the agreement's name): a parent's title
now labels only a clause its number holds ("1.4" in "1"; an unnumbered line keeps its own words), and a wrapped line keeps
its own short title ("Designation of Subsidiaries. The Parent Borrower" is titled "Designation of Subsidiaries"). Measured:
see the repair report (REPAIR-REPORT.md, outside the repository) for the replays, the corpus and the gate.

## 2026-10-14: the product mission (policy-v10, retrieval-v2, one account of each finding, a revision asked again)

Three independent reviews (security, authority promotion, retrieval on ten unfamiliar agreements in four formats; reports
outside the repository) and a walk of the product on the local model set the work.
(1) policy-v10: periods in units that do not convert are put on the calendar (policy.durations.calendar_days): a month
is 28 to 31 days, a year 365 or 366, N Business Days at least N + 2 × ⌊(N − 1) / 5⌋ where the contract's own definition
makes a Business Day a weekday (business_week, read from the whole document, never assumed; checked against
brute-force calendars). A shortfall on every calendar is code's; a pass on every calendar stays the model's with the
counts consistent; overlapping ranges, or Business Days whose weekdays code cannot read, go to a person with the reason.
A contract that says its bare "days" are Business Days is read so (day_convention). Replayed over 14,352 recorded
findings: 6 change, each to a shortfall code computes, five of them the pilot's H4-Q5 clause. (2) One account of each
finding (runs.account: who set the status, every concern code wrote, flagged or not) is read by the answer card, the
findings list, the memo and the evidence pack: the memo had printed a pass code did not confirm under "No automated
check flagged a finding" and the model's own words as "Legal guidance."; the list let a person confirm a finding
without its concerns; the revision panel called a withheld finding "Still supported". (3) retrieval-v2 (runs.links):
after the ranking, the sections the top three ranked ones depend on where the contract says which (a definition they
use, an amendment of them, a clause they cite), at most two, within the same worst-case text: on the study's 147
question-format cases every needed passage was handed in 121, now 137; the control set did not move. (4) The reader:
a DOCX with no heading style had no heading at all (0 of 293), now read as plain lines are; a sub-item is cited as the
document cites it ("5.3(a)", from Word's printed parent and label, checked against Word 16); title-cased titles that
end in a full stop, ARTICLE lines and their titles, and long wrapped clause lines are read as such. (5) A visitor's
questions in flight are bounded (two), and a caller's X-Request-ID is kept only when it is an id. (6) The revision
panel offers a prepared revision of the sample (one change, said so) and asks the same question of a revision, the
two recorded answers side by side. Not done, and said so: hidden (white or invisible) text is read like any other
text, and per-address windows stay per full address (war room F-32).

## 2026-10-14: the first-visitor acceptance test (three repairs, inside the unreleased candidate)

A fresh visitor's journey, run in Chromium against the local stack and the local model, on three agreements written for
the test by an independent agent after it began (a DOCX with imperfect heading styles, a PDF with an amendment, a TXT with
a conflict and an instruction aimed at the model), each with an answer key the product never saw (outside the repository). The workflow held in every format and at 375 px; three statements were wrong, each
closed as a class. (1) Reader v14: in a document that styles its headings, a clause heading typed instead ("11.
Termination", bold Normal text) was body, so the termination clause sat inside §10 and a quote from it was "found at §10 ·
Liability" under code's badge; a short numbered title set apart (bold or capitals) whose number is the next clause
number is now a heading. None of the 191 corpus DOCX files reads differently. (2) policy-v10, amended before any
release: a Business Day definition that lists its weekdays ("a Monday, Tuesday, Wednesday, Thursday or Friday"), names a
run other than Monday to Friday, or lists exclusions across semicolons is read; where code reads none, it says what it
could not read, not that the contract has no definition. Replayed over 2,344 stored documents in 56 local stores: only
the acceptance agreement's reading changes. The version keeps its name, with its fingerprint replaced: it was never
committed or deployed. (3) The memo lists a proposal code withheld, flagged with code's reason and the model's sentence
as the model's, without its unfound quotes; it had left such proposals out and printed "No automated check flagged a
finding" above the rest. Not changed, and said so in the report: a guidance sentence whose direction code cannot read
("if the breach is not cured within 15 calendar days") leaves the model's pass as the model's; a page count is the
file's own metadata; the model's semantic errors (a superseded clause, a subordinated schedule) are shown as its own.

## 2026-10-14: policy-v11, the contract's own statements about its provisions (the intent-first mission)

The first-visitor acceptance test showed the local model answering a renewal question from a clause an amendment had
deleted and replaced, and a notice question from a schedule a precedence clause subordinated. Retrieval had handed it
both passages; nothing in the product said how they related. Alternatives weighed: a prompt change (unmeasured, changes
every recorded answer's input, and tells the visitor nothing); retrieval alone (it already handed the passages);
a graph or agent architecture (scope and legal effect cannot be parsed reliably, and nothing smaller had been tried).
Chosen: one small recorded representation (`runs.relations`). Two kinds of statement are located with both ends:
replaces (deleted, replaced, superseded, amended and restated, with the new wording when quoted and any limit as
written: a year, a party, a start not yet reached, one paragraph, one definition, some words) and precedence (the
parts a conflict clause ranks). A start is resolved only from a written date or a term the contract defines by one, and
compared with the run's date; otherwise it is a limit. They are recorded with the run, once, and never re-derived. One
status follows (`check_replaced`, `position_check`): a question about the agreement as it stands (or one that does not
say) answered from text replaced in full, without the replacement, is needs review set by code; the quote stays verified,
and code never says which wording governs. A limited replacement and a ranking of the parts quoted are concerns; a
question about the original agreement raises nothing. The prompt and retrieval are unchanged. Held by an oracle written
before the code by an independent author from the product contract (34 agreements, 82 decisions, 10 families; its
labels never edited): the first run matched 74, the misses were closed as classes (a value only the replacement states;
"the following new clause 6.3:"; a paragraph named before its clause; parts named by a part noun, never a party), and it
now matches 82 of 82. Reading the 457 stored documents found the partial-replacement class the oracle had not ("The
definition of 'Applicable Margin' in Section 1.01 … is amended and restated"), now a limit. Not done, and said so: a
change worded without a replacement verb ("For the second Contract Year only, the Minimum Purchase Commitment under clause
6.1 is 10,946 Cases") records nothing; whether a precedence clause's conflict exists on the point is not decided.

**Amended within policy-v11 before release (2026-10-14, an external review of the owner note).** Three defects, each red
on the first v11 tree (8546f4b9). (1) The run's date stood for the time every question asked about: "What was the deadline
in June 2025?" was read as asking about the agreement as it stands, and a quote of the replaced clause became needs review
set by code. Invariant: only a question that names no time is read at the run's date; code does not place a time a question
names against a replacement's start. A question naming a date, a month, a year after a word of time, a time relative to now
or one of the contract's own periods is `dated`: a concern that names the time as written and the start, never the status
(`relations.asked_time`, `perspective`). (2) A note said "the answer uses the replacement" when the answer only quoted it:
an answer can quote the replacement and conclude from the replaced wording. Invariant: a note says only what code saw, what
the answer quotes and the values it states. Quoting the replacement while stating only values of the replaced wording is
now a concern (`old_value`), and no note says uses, relies or rests (a property test). (3) A start written as a month
("with effect from March 2026") raised ValueError in the run's relation step, before the model was asked, so the run failed
and failed again on retry; "September 18, 2025" was cut at its comma and never read. A start is now read from a day, or a
month from its 1st, and anything else stays a limit (a Hypothesis test over written dates). The oracle still matches 82 of
82, with labels it has none for counted as failures. v11 was never committed, so its fingerprint was replaced, not bumped.

## 2026-10-15: policy-v12, the time a question asks at is not a premise

The first real journey with a dated question (the Skelbrook PDF, local qwen3:8b: "What was the deadline for giving a
notice of non-renewal in June 2026?") answered correctly from the original clause, and code lowered it: "June 2026 comes
from the question, and no verified quote states it". The same answer without the words "in June 2026" kept its pass, so
the status hung on the wording. Invariant: repeating the time a question asks at takes no figure from the question, so
the status does not depend on it. `values.frame_times` reads a date, month or year that a what, when or how-much question
puts after "in", "during", "throughout", "on", "at", "as of" or "as at"; the status rule and the account count it as
stated. Kept as premises, as policy-v6 decided for figures: a date in a question that asks to confirm ("Is the fee payable
in June 2026?"), and a date the question gives as a property ("the payment due on 1 March 2027"). Held by a property
(the decision with and without the frame is equal) and four controls. Replayed over the 81 local QA stores: 4 recorded
findings were lowered for a value from the question; only the June 2026 one changes. Not done: a time phrased in a way
this does not read ("for the June 2026 renewal") is still read as a premise, which asks a person to look.

## 2026-10-15: policy-v13, run identity by reached starts, and section handles kept honest

Three defects from the final review, each reproduced first. (1) A run's fingerprint carried no date while a
replacement's stated start was compared with the run's creation date, so a question asked again after an amendment
took effect was handed the run decided before it (a limit) instead of a new one (needs review). Invariant: a run is
the same run only while the same starts are reached. `relations.latest_start_reached` enters the run's options, and
so its identity, only when a reached start exists; documents without one keep their fingerprints, the earlier run
stays as recorded. (2) An answer quoting both the replaced clause and its replacement, and stating both values, was
context whatever it concluded; the card then said "code raised no concern". The model's own stated value
(`observed`) is now its stance when it names one of the differing values, so "30 days" beside a quoted 60-day
replacement raises the old_value concern; with no such value nothing changes. No phrase is interpreted. The context
line now says what code checked. The oracle still matches 82 of 82. (3) A section handle the model was not given was
dropped ("found in sec_12.3." became "found in.3.") and so never reached the reference check; "sec_1.2(b)" became
"§7.2(b)", a clause the model never named. Unknown and sub-numbered handles are now shown as "[unidentified
section]" and lower a pass with a reason naming them; the raw output keeps the model's words.

Skeptic review of the same tree, applied before commit. Each relation sentence names the source it read: "the value it
gives as the contract's" when the stated value decided, "states" when the whole answer did; a sentence about the whole
answer was false when the prose named both values. The card's one-line summaries claim only what holds under either
source. One identity function (`start_run.identity_options`) serves both the request and the goldens' lookup; a
document's starts are read once per document (its sections never change) instead of on every request; the run's
created_at is the instant its identity was read, so the starts in the fingerprint are the starts it is assessed
against even across midnight. Every sub-reference form after a handle (".2", "(b)", ",2", and inside brackets) is no
address, in every field the model wrote, and the status reason speaks of the reference as the reader sees it, not of
the internal handle.

A second skeptic pass on the fixes, also applied. Phones: a new contract or run on screen opens on its answer by one
rule keyed on what is shown, so an upload and a palette question are covered with the list paths. Findings: the order
that puts what needs a person first is read when the list loads, so a row decided there stays under the reader's hand.
Copy: code looks for every quote and withholds any it cannot find (it does not find every one); a 404 says the record
belongs to another workspace or no longer exists, nothing more. Handles: a range ("sec_1-3"), a continuation the
cleanup would close ("sec_1 ,2"), and a paragraph with a space or left open are sub-references; a short word in
brackets ("(fees)") is not. Left as it is: "sec_1, 2 and 3" reads "§7, 2 and 3", because ", 2" after a handle is
also ordinary prose ("in sec_5, 30 days' notice"), and lowering that would be the larger error.

Exports, audited against the brief after the gate. The evidence pack gave the model's sentences with its section handles
written as labels and had no copy of what the model wrote, so a reader of the pack could not see a replaced handle. It now
carries `model_output.txt`, the recorded output byte for byte, and `verify.py` checks it against the hash the checking
stage recorded when the model answered; the README no longer calls the relabelled sentence the model's own. The download
links were plain anchors: a refused pack replaced the workbench with the API's JSON, and nothing showed while a large pack
was made. One `PackLink` now says what the zip holds, shows the wait, saves the file under the API's name and says a
refusal in place; its address stays, so it can still be copied. The Runs page showed an operator's instruction raw when
the contract-state record is absent; it now says what /state says, with the instruction labelled as the operator's.
The gate on that tree failed once on `test_admission`'s ordering test, which formed its queue with 5 ms sleeps: on a
loaded machine the held call finished before the queue formed. The test now holds the slot until the queue it checks has
formed, read from the controller; it passed 20 runs in four parallel loops.

## 2026-10-16: the blind contract stress test, policy-v14 and reader v15

Pavan's blind kit (a synthetic agreement as DOCX and PDF, its future-dated amendment, an unrelated agreement, a scan and
a file that is not a PDF; 15 questions with an oracle sealed until every answer was recorded) was run against 3ecc630
through the browser with qwen3:8b. Integrity and isolation held on every run. Six defects, each reproduced red first and
fixed where its rule lives (the test's report and replays are kept outside the repository).

*policy-v14 (1): one value for every party.* "Each party must give … 45 calendar days" stood as the model's pass over a
quote in which the Customer gives 45 days and the Provider 60; code had said which of the two values the answer used, as
a disclosure only. Invariant: a pass may not give one value to every party where its passages state several of that kind
and none gives it to every party. Each statement of the answer is read on its own (the PDF's "Each party … 45 … Provider
… 60" contradicts itself and is caught by its first sentence). `values.uniform_party_choices`, in `check_values`.

*policy-v14 (2): a condition left out of the quote.* "Customer may terminate … on 30 days' notice" stood over a quote
that began after its sentence's "Except for the first sixty (60) calendar days of the Initial Term,". Invariant: a pass
may not rest on a verified quote whose own sentence carries a condition outside the quoted words that the answer does not
state (two of the condition's own words). `left_out_condition`, `check_conditions`. A lowered pass keeps the reason it
had, so a pass "Subject to Sections 6, 7 and 8, …" whose §8 was never handed over is now needs review and still says so
on every surface; the war room tests that kept it the model's pass were rewritten to v14. Measured over the passes
recorded in 69 local QA and lab stores (the live stores' copies excluded): 3,723 passes, 997 distinct; v14 lowers 35
(2 one value, 33 a left-out condition; 3 of them v6 lowers anyway). Read by hand: in 21 the left-out words bear on the
answer ("provided that Executive executes … a general release", "except that Provider may terminate immediately",
"Subject to Clause 43 (Disputes)"), in 11 they do not ("subject to withholding as legally required"), 3 are boilerplate
("Subject to the other provisions of this Agreement"). A false one costs a correct answer shown as needs review with the
left-out words in its reason; no status is raised. The first version lowered 54: it took "However," for a condition,
missed a sentence that ends inside quotation marks (the kit's Amendment One quotes the replaced clause), and asked the
answer for a condition word ("exceptions to the cap, including indemnification obligations …" states one); each was
corrected in the primitive and the replay rerun.

*Reader v15 (1): a schedule's heading.* The PDF read "Schedule A. Service Level and Credits" as body text, so Schedule
A sat inside §13 and its credit table was cited as "§13.3 No Penalty for Non-Renewal". In plain text and PDF a line naming
a part of the agreement by kind, mark and, after a full stop, colon or dash, a title is a heading, labelled as Word's
("Schedule A"). The first version also took the mark alone and a mark followed by words: replayed, 1,937 of 5,984 corpus
texts changed, among them EDGAR exhibits printing "Exhibit 10.1" on every page, each now a heading splitting the clause a
page break fell in (the war room's F-04 by another route), and contents lines ("Schedule 2.5Fees", "… the Lenders7").
The rule as kept changes 272 texts (4.5%), every added heading sampled a schedule's or exhibit's title, 3 PDFs and no
DOCX; the EDGAR running line is a regression test.

*Reader v15 (2): a PDF's page furniture.* Since v12 a line printed on most pages was text where it stood ("nothing printed
is deleted"), so the kit's header sat inside §3, §11 and §13 and in the model's input, and broke the sentence a page
break fell in. A Word file's headers and footers are left out and counted; a PDF's now are too: a line printed the same,
or with a rising page number, at the top or foot (two lines) of at least three pages and of most pages is left out of
the sections and counted in the coverage, which names the lines. The document's own heading printed at the head of its
first page stays. This reverses v12's rule for PDFs; the bytes stay in the store and the pack. Measured: 30 of 70 corpus
PDFs; every left-out line read: page numbers ("Page 3 of 35", "- 3 -"), running headers and footers, EDGAR's
"* Confidential treatment requested", and filler in three synthetic stress files. No clause text.

*Interface (U1): a refused file left the reader where they were.* A file refused while a contract was open sent the
reader to the first screen's top, the contract gone, the refusal 896 px down a 900 px window (968 of 812 on a phone). It
now returns to the view it was added from with the refusal there, as an alert. That first repair showed it on Documents
only: the candidate's review found a sample refused from Findings shown nowhere, and a refusal on Documents outliving a
newer failure, because two states were kept and one was always shown before the other. The workbench now keeps one
notice, shown on the first screen, Documents, Findings and Runs; Findings and Runs announce it as Documents does. Each
open, upload or question clears it, and a failed open is said only while it is still the latest, so a slow 404 of an
earlier click never replaces a newer refusal (the review of this repair found that race); an upload's refusal is always
said. Browser flows: a file refused on Documents and a sample refused on Findings, at both widths; a newer failure taking
a refusal's place and the reverse; a slow 404 under a newer refusal. Each was red on the interface before its repair,
the Documents flows aside, which are the control.

*Known limits, older than these repairs.* The Assistant has no place for a notice: a run Back cannot open, or a finding
opened from Findings that fails once the reader is on the Assistant, is said nowhere, and the screen keeps what it
showed. A late response can still change the screen: an upload that ends after the reader pressed Back to a run returns
them to where the upload started, with its refusal; a contract whose reading arrives after the reader moved on still
opens, and so does a run unless, after it, a question was asked or another run or contract opened (an upload that was
refused does not count); a question typed on the first screen is asked of its file when the file is read, even if the
reader has gone Back meanwhile. Each needs a slow response and a second action inside it. Four attempts in this round to
show the notice on the Assistant, scoped to its screen, and to give the screen one owner were each reviewed and
rejected: every one closed a race and opened another (a refusal shown nowhere; a failure shown beside a contract it was
not about; a question started on a file the reader had left). Closing these needs one owner for the screen across
uploads, opens, Back and the first screen's question, designed as a change of its own.

*Wording (U2, U3).* The reading stage printed "1 pages"; counts now take their noun's number. A visitor read "… the model
endpoint is not reachable (ConnectError)", on the answer and on the public /api/health. Since the journey audit
(2026-10-09) a failure named what failed and the error's class; the class now goes to the log beside the sentence, in
every message composed from an exception that a visitor can read (the model call, health, the build check, embedding, an
internal failure, an engineering record's detail). retrieval-v2's fingerprint was re-recorded for the embedding
sentence; what retrieval hands over is unchanged.

Checks run: the backend suite (2,176 pass, 1 skip), ruff, ruff format, mypy over the gate's scope, import contracts; the
interface's 290 unit tests, eslint, tsc; the 40 browser flows on a fresh store (two failed on a store earlier local runs
had filled, the known accumulation, and passed fresh). The release gate then passed on the committed application, 5cedb49,
and its review approved it with five notes. Four are repaired: U1's class (above), stale comments and test names, a
reason that lowercased the answer's party names (it now quotes the answer's words), and no test through the API still
holding a pass that names an unseen section. One is kept as it is: a pass that v14 lowers has code's position check
as its source, so the evidence pack reads one that code found consistent as not compared, though its reason says it was.
Reading a chained reason by its words would let contract text quoted in the lowering sentence claim a comparison code
never made; `basis` understates and never overstates.

*The first screen and the README, after the release.* Once 6574514 was live, its first screen said "Who holds a right,
or whether a condition was left out, code does not check", and the README that it "stays a person's call": true until
v14, an understatement since. Two repairs were reviewed and rejected for overstating the check. "When the quote drops a
condition its own sentence states and the answer does not", then "… and the answer does not repeat what follows it",
each promised a review code does not give: a condition opened by "if", "upon" or "in the event that", one after the
quote when one stands before it, and an answer sharing two of the condition's words ("during the Initial Term" over
"Except for the first sixty (60) calendar days of the Initial Term") all keep the pass. A rule with these edges cannot
be stated whole on a card. The pages now say that code lowers some passes whose quote leaves out an "unless", "except"
or "subject to" from its own sentence, where the answer does not mention it, and that whether the answer carries every
condition is not checked; the failure envelope's row states the rule. A third review found that row overstating too: a
condition made only of common contract words ("unless the Customer gives prior written notice") is not read unless
another condition word stands before it, so a notice condition, this product's commonest, can keep its pass. The row
now defines a condition's own words as code reads them, its sentence's ends as code finds them, and names the passes
kept as some among others; each edge it states was run through `left_out_condition` and `check_conditions`. The
deferred-triage row that listed "a carve-out the quote boundary cut" says one kind is read now. The class is held in
`test_docs_claims.py`: no page, README or document a reader is given may leave to a person a check the run performs (a
condition left out of the quote's sentence; one value given to every party) in the idioms these pages were found to
use for it on 2026-10-16 ("code does not check", "not checked", "not decided by code", "a person's call", "stays with a
person", "the model's view", "yours to decide", a list under a "Not checked" heading), read as a reader sees the text
(JSX writes "the model&apos;s reading", which the fourth review found the test reading past). A phrase naming more
than the check covers ("every condition", "a condition in another clause") is set aside before the rest of the
statement is read, so a denial beside a true limit still fails; the second review found that the first scope rule,
read over the whole sentence, let one through. The words the pages name for the check must be `CARVE_OUT` words. The
test is a tripwire for the wordings found, not a proof that no other exists: each of the four reviews found wordings
the version before it missed, and a wording outside the list, a denial split by a semicolon or across a table's cells,
or one naming the check only by a pronoun still passes. Its control holds both old sentences, twenty-eight other
wordings, the repaired sentences and the limits still true (/break's "every condition and exception", "Whether it
still applies is not decided by code").

## 2026-10-16: one Hetzner server, the model on it

The owner's decision: one main branch, one deployment, Hetzner only. No serverless GPU: the model runs on the same host
as the interface, the API, the store and the uploaded documents; Cloudflare keeps the name, HTTPS and the tunnel. The
kit staged on 2026-10-13 put the model on Modal, which woke in 95-168 s, sent every question's text to a second company
and billed by the second. `deploy/cloud` now runs Ollama 0.40.4 (pinned by digest) as a compose service on the compose
network only, with the weights in their own volume and the model kept loaded; `WORKBENCH_MODEL_DIGEST` keeps every
answer on the workstation's build (qwen3:8b, 500a1f067a9f, Q4_K_M), which is not changed, re-quantised or swapped.
`compose.gpu.yml` adds a GPU for a host that has one. `modal_ollama.py` and the DigitalOcean and Modal plan
(`CLOUD-READINESS.md`) are removed; their history stays in git. ORACLE.md, the staging host's runbook, is now
HETZNER.md: the server, the model, releases, stores, the cutover, what only the server can show, and the cost.

The server, for the measured load: an answer reads about 1,900 tokens and writes about 270 (p90 2,300 and 440; the 76
real answers of the blind stress test), one at a time. A dedicated AX42 (8 Zen 4 cores, 64 GB, two NVMe in RAID 1, about
€97 a month) is expected to run it on its CPU; the go/no-go is an answer's p90 within 120 s, measured on the rented
machine before anything moves. The same container on the workstation's CPU (Ryzen 9 5900HX, DDR4) read 19.9 tokens a
second and wrote 5.6, about 144 s for the median answer and 194 s for the p90 (one short probe): the AX42 should do better, and even at
the bound it answers more slowly than the workstation's GPU today (a median 34.5 s). Missed, a GEX45 (24 GB GPU, about
€214 a month) runs the same build on its GPU, expected in seconds and not measured here. Rejected: a Cloud VM (the
dedicated-vCPU line unavailable and dearer after Hetzner's 2026 increases; two shared vCPUs took 650-1,000 s).
Prices are as reported on 2026-10-16 and are read again in Hetzner's console before ordering.

No visitor data moves. The production host opens a store of its own, empty; visitors start again there, and the
workstation's API, kept running for the way back, still ends its visitors' workspaces after their seven days; stopped,
what its store holds is the owner's to delete. The way back is the tunnel record's target, edited back to the
workstation's tunnel, which keeps running until the move is no longer wanted. The interface says the model is on the
server because the deployment says so (`WORKBENCH_MODEL_ON_SERVER=1`): its address is a container name, and any address
but loopback otherwise counts as elsewhere. Rehearsed on the workstation's Docker the same day (deploy/cloud/README.md):
the model's container, health, the build check and acceptance held; the run stopped when the stack stopped
answering at its over-limit upload (the cause not established), before the rest of recovery, retention and the kit's files, which
come first on the server.

## 2026-10-17: policy-v15, an instrument's marked number is not a value

The landing's amendment challenge (the amended sample and its ready question) was answered on the live site three times
on 2026-10-16, each "ninety (90) days … §7.2 of the Agreement, which was amended by Amendment No. 1 to specify the
notice period", and each set to needs review with the reason "the evidence shown does not establish 1: no verified quote
or guidance states it". The 1 is the amendment's number. Re-decided from the recorded answer and quotes, with no model
call, the reason came back the same. Invariant: the number of an instrument or a document named with a mark ("Amendment
No. 1", "Change Order #7", "Contract No. 98-1234") is not an answer value. The pointer reading knew sections, schedules,
exhibits and their kin, not these names; and runs.relations, which reads an answer against a replaced clause and its
replacement, read "Amendment No. 1" as 1, so an answer quoting only the replaced clause could be told it states the
replacement's "one (1) month" and keep its pass.

`values._IDENTIFIERS` reads such a name: an instrument's or a document's word in any case, then on the same line "No."
with its full stop or "#", then the number read whole, however long or joined by hyphens. Every number of the name
carries its own mark ("Amendment No. 1 and No. 2"), so a count after one, however joined, stays the answer's ("Under
Amendment No. 1, 2 renewals"). What code can tell is a value is never the name's number: one before a unit, a magnitude
or a percent sign, a bracketed restatement between ("No. 30 (thirty) days", "No. 2 million"), a date ("No. 1 March
2026", "No. 2024-01-15"), money ("No. USD 10,000"), and a grouped number ("No. 1,500 additional units"). "Number" is no
mark: after a plural it is the verb ("the licences number 250"). The value check, the choices and the reader's own text
read through `_without_pointers`, v14's pointer reading plus these names; runs.relations reads through
`_without_identifiers`, these names only, and so still reads section pointers as values, as it has since policy-v11. The
guidance and the question are read like the answer, so a marked name's number in them is no longer a value they state:
an answer stating it ("2 renewals" beside guidance naming "Amendment No. 2") can newly be lowered. The uniform-party
check splits statements as v14 did (a first version split after setting names aside, joined "… Amendment No. 1 (60 days
for the Provider)" into one statement and kept a pass v14 lowered; the final review caught it).
v14's pointer reading is otherwise unchanged, except that the whitespace runs that could share a run are possessive: they
split a long one quadratically, 7 s for one read of 20,000 spaces of guidance after "Section 1," (as a review measured),
now milliseconds. A quote is still read whole.

Five broader designs were tried first, each rejected by a fresh review for values hidden or identifiers read that v14 did
not: unmarked instrument numbers, ranges, lists after instruments, a date rule, a heading rule and "Number" as a mark
each moved v14's edge somewhere else ("Under Amendment No. 1, 2 renewals", "Section 9.1 and 30 Business Days", "Under
Change Orders 4 and 5, 2 engineers", "the licences number 250"). So this one is checked against v14 directly. A
differential fuzz (outside the repository, with the replay) builds 48,440 sentences, each an identifier and a value of
known role (section pointers in lists, pairs and ranges, marked and unmarked instruments in the singular and plural, after
determiners, values right after a mark, "number" as a verb, in twenty-three shapes with commas, "and", spaced, unspaced
and glued separators, line breaks and no-break spaces), and reads each with v14 and v15 in both readings. v15 hides no
value v14 read, shows none differently, and reads no identifier v14 did not; it reads an identifier in 10,908 of the
check's sentences against v14's 16,167, and in 22,829 of relations' against 28,437. A bare count right after "No." is the
name's number by design ("Amendment No. 2 renewals") and is not drawn there. Held in the repository by a property (a
marked name added to an answer changes no value code reads, in the three readings), the recorded answer end to end, a
relations case each way, the uniform-party case, and controls, each review's cases among them. Replayed over the 4,979
findings with a verified quote in 69 local QA and lab stores (62 hold one; the live stores' copies excluded): 10 change
(1 distinct), a correct answer ("sixty (60) days … because Amendment No. 1 replaced the ninety (90) days") that v14
lowered for the 1 and that keeps the model's pass now. No relation note (82 findings have recorded relations, 35 a note),
disclosed choice or uniform-party check changes, and nothing is newly lowered.

Not fixed, and said so. With the false reason gone, the challenge's wrong answer (the replaced 90 days, quoted beside the
replacement) is no longer needs review: code says what it sees as a concern, "the answer quotes the new wording of clause
7.2 … but the value it gives as the contract's includes one only the replaced wording states", and since policy-v11 that
case is a concern, never a status. Still read as values, as under v14: an unmarked number ("Amendment 2", where a count
can stand in the same place), one after "Number", a "Nos." list ("Amendments Nos. 1 and 2"), a grouped number ("Patent
No. 7,123,456"), "№ 1", a year naming an instrument. A number joined by an en dash or a slash keeps its first part as the
name and its last as a value ("Contract No. 2024/123" states 123; v14 read 2024 and 123).
Section pointers keep v14's gaps (a bare count after a list's comma is read as a pointer). And one answer v14 lowered only for
the false reason now passes: the uniform-party check splits statements at "No." as v14 does, so "Each party, under
Amendment No. 1, must give 45 days' notice" over a Customer 45 and a Provider 60 is not read as one statement (a test
pins it; joining it would let "… Amendment No. 1 (60 days for the Provider)" pass instead). Recorded runs keep the status
and reason they were decided with; the "Numbers" row beside them, read when shown, no longer lists the 1.

## 2026-10-17: policy-v16, quoting the replacement is not following it

The owner's decision after policy-v15. With v15's false reason gone, the amendment challenge's wrong answer ("ninety (90)
days", the replaced value, over quotes of both the replaced clause 7.2 and its replacement) stood as the model's pass:
since policy-v11 an answer that quotes the replacement but states only values the replaced wording states (relations'
`old_value`) was a concern beside the status. `status.check_old_value` now lowers such a pass to needs review set by
code, with code's sentence as the reason, for the same questions as "replaced" (the agreement as it stands, or no time
named; a replacement in full). Only a pass: a status code computed on the quoted replacement, such as a shortfall against
the guidance, rests on the text in force and stays, the sentence a concern beside it. The account shows a note that set
the status once, as the reason; a run decided before v16 keeps its status, and its old_value note is still a concern.

A fresh review rejected the first version, and both repairs are in the rule. It promoted old_value through
`check_replaced`, which overwrote a shortfall code had computed on the replacement. And relations read a clause number as
a value: "1.2" opened the replaced clause but not the quoted replacement, and the answer's "clause 1.2" counted as a value
only the replaced wording states, so "Under clause 1.2 as amended, 90 days' notice, delivered by courier", a correct
answer, was lowered with a false sentence. Now a clause's number is its name, not a value of either wording: the number
a wording opens with, unless it is a quantity ("5 Business Days' notice"), and every number a pointer names. Relations
reads both wordings and the answer with what names a provision or an instrument set aside (`values.wording_values`,
`stated_values(answer=True)`): a plural reads its list as v14 does ("Sections 7.2 and 7.3"), one name its own number
only, so a count after its comma stays ("Under clause 1.2, 3 delivery trucks"). A second review found the list and the
pointer inside a wording ("… notice under Section 7.3"), a leading quantity taken for the clause number, and a lowered
pass losing its earlier reason ("points at §9, which was not handed to the model"), now kept. The oracle still
matches its 82 decisions. Code still does not read prose: an answer naming a removed value ("the amendment removed the
12-month minimum") states the replaced wording's value; the value check lowers that one already, as under v15.

Replayed over the 4,979 findings with a verified quote in 69 local QA and lab stores: 82 have recorded relations, 35 of
them a note (context, replaced, dated, limits), none an old_value note, and no note changes under the new reading; no
recorded decision changes. The live challenge's runs, outside those stores, are the case it is for.

## 2026-10-19: operating it under load, after a deep audit

An audit of the live system asked what an operator, a reviewer and a burst of visitors would meet. The answers that
changed code, smallest first:

- **What a log line says.** A run's ending names its reason (`reason=citations_unverified`), every 429 and 503 names the
  limit that refused (`refused … kind=Busy`), the model's time is logged apart from the queue's, and each start logs the
  model server's version and the model's build: an Ollama self-update had changed answers with no line saying so.
- **What the supervisor records.** An end Windows chose (shutdown, sign-out; exit code 0x40010004) is named, at the
  exit or on the next start with the boot time; an exit carries the server's last error line; a recovered probe is
  logged; output files older than 14 days are removed; uvicorn's access log is off (the API's own request line has more
  and leaves the health probe out). Health and the write refusal share one disk floor: health said ok between 256 MiB
  and the public 2 GiB while every upload was refused.
- **What a read costs.** The findings list took five queries a row (2,252 for a full list) and the runs list two; every
  read of a run asked once per open run whether it had stalled; the page's poll of a working run read the whole
  contract. Lists eager-load, the stall check is one query, clause numbers are found by their reading's section ids with
  the text read only on a cache miss, and a working run reads no sections. Responses were compared before and after,
  identical but for ids and timings. The definitions cache in `runs/links.py`, which held up to 64 whole contracts to
  save 30 ms against a model call of seconds, is gone; old and new gave the same links on 580 cases over 150 EDGAR
  contracts, so retrieval-v2's fingerprint was re-recorded, not bumped.
- **The model's queue is bounded.** Each visitor could have two questions in flight; nothing bounded all of them. Past
  eight a question is refused at once (503, Retry-After 60, nothing started). Rejected: a queue without a bound but with
  a position (the thirtieth visitor waits half an hour), and a scheduler product (one GPU; nothing measured asks for it).
- **A waiting run says what it waits behind.** `RunOut.ahead` counts runs asked earlier and not yet answered, on every
  read and every stream heartbeat. It is not the admission position: the admission controller does not know runs, and a
  later question on a shorter contract can reach the model first, so the page says what is counted ("questions asked
  before this one are still being answered"), not "ahead". Polling slows from 3 s to 12 s while nothing changes and stops
  while the tab is hidden.
- **What a reviewer and an operator open first.** The README has a ten-minute reading path; `scripts/status.py` gives
  one read-only line per part; `docs/TROUBLESHOOTING.md` maps symptoms to log lines. ADR 0003 (LangGraph) and 0004
  (hybrid retrieval) now state that they were not, and partly, adopted.

A fresh-context review of the branch found the stream-dropped poll (`/detail`) still reading the whole contract, the
model wake answering a full queue with a 503, an unhandled 500 left without a request line once uvicorn's access log
was off, refusals at the upload door logged under one kind, and status.py's day ceiling read from the wrong process;
each is fixed with a test. The release gate's one failure was a browser flow reading a request the page had dropped
("Response has been disposed"), a harness race seen once before; the flow now leaves such a request alone.

Left, with reasons: an index on `runs.stage` (no measurement says the scan costs anything at this size); the event
stream's drops through the tunnel (pages fall back to polling, which now costs less; the cause is its own task); moving
the release checklist out of the README (its claims are tested where they are); CI (the repository token lacks the
workflow scope, the owner's step).

## 2026-10-21: an answer depends on the model server's prompt cache (measured, open)

One recorded input at seed 42 and temperature 0 gives different answers depending on where llama-server starts
computing it. It reuses the longest prefix it holds, in the slot and in an 8 GiB host-RAM prompt cache. Measured on Ollama
0.40.7 with the convenience question's input: from token 0, 3 quotes (7b6a0862); from token 620, after another question,
1 quote (8c66f45e); on 0.40.6 the reverse. Each fix alone failed: the RAM cache off still left the slot's prefix (2026-10-19);
a one-token raw call before the answer still let the RAM cache restore the prefix (`f_sim = 0.328`). A raw call without
`truncate: false` and `shift: false` reloaded the model on 0.40.7, which looks like a fix and is a cold start; the
wake-up sent such a call, and now sends both (`NEVER_CUT`, one constant for every request to the chat model). Not decided: both
together (an Ollama setting, a restart and a one-token call per answer), or a cold load per answer (about 9 s). A per-run
record of the engine was written and dropped before release: Ollama's upgrade log and the API's start line already date
each engine (not a pull under a running API without a pinned digest), and the probe added two calls inside the model's admission slot. `docs/CASEBOOK.md`, case 6.

## 2026-10-21: a casebook

Six failures, each traced to what the machine was doing, with the test that guards it where one exists
(`docs/CASEBOOK.md`). A fresh review checked each claim against the repository; its corrections are in the commit after.

## 2026-10-21: every answer computed from its first token

Approved by the owner the same day: test the two measures together, and ship them if they hold. Ollama now runs with
`LLAMA_ARG_CACHE_RAM=0` (a user environment variable, then Ollama restarted: 16 s), and before every answer, inside the
model's admission slot, Verity sends a one-token raw prompt with the answer's own load settings
(`OllamaProvider._start_clean`). Measured on the serving machine with the recorded convenience (c6f8e6af) and liability
(312e14a1) inputs: in the order c, l, c, l and in the order l, c, l, every answer started at token 0 and each input gave
one answer (7b6a0862; 0bd04c15), with no model reload. The control, the same settings without the one-token prompt:
convenience asked after liability started at token 620 and gave 8c66f45e. Rejected: a cold load per answer (about 9 s
each, and the model's wake-up would be wasted). Cost: at least the shared prefix, about 620 prompt tokens, again for every answer, and the whole prompt on a retry. The cloud kit sets the same
variable, not measured on its image. `scripts/status.py` reports the server's cache on a `cache` line; the deployment
README says how to set it. Not changed: the prompt, decoding options, policy, verifier and retrieval, so no run's
identity moves; answers after this are the ones a cold model gives. Runs answered before it keep their answers, and a
workspace that asks the same question again is handed its earlier run, not a new answer. It holds only with one server
slot (Ollama's default, `OLLAMA_NUM_PARALLEL=1`) used one answer at a time (`WORKBENCH_MODEL_CONCURRENCY=1`).

## 2026-10-30: an audit by people trying to break it

Four fresh reviews, each told to break one thing: the public site and the laptop behind it, the verifier and the status
rules, the interface, and the repository as a stranger first reads it. What they found, and what was done:

- **The verifier said "found" where the text does not say it** (verifier v11). A ".5%" late fee was found as "5%", "±5%"
  as "5%", ">$1,000,000" as "$1,000,000", "2/3" as "2-3"; the typed tier joined "terminate. Without cause" into
  "terminate without cause"; a word was split at a combining mark or a Persian non-joiner; "Section 2(A)" was found at
  "Section 2(a)"; a quote of punctuation alone was found. Each is refused at every tier and by the pack, which reads a
  v10 run as v10 did. Replayed read-only over 17,603 recorded spans in 94 stores: none lost or gained.
- **A pass label could claim more of code than its record**: an unknown source, or a memo caller naming none, read
  "Within guidance". Both now read as the model's view.
- **Large reads had no bound**: one upload's evidence pack (up to 26 MB, rebuilt per request) could be asked for in a
  loop. Packs and contract reads are now bounded per network an hour, two packs at a time; the hourly windows count an
  IPv6 /64 once, reversing F-32 on the owner's instruction that abuse must not get through. Health caches its model
  probe and no longer lists the machine's models.
- **The interface**: phone heights (100dvh), chips that wrap, landmarks and a heading outline, live regions, one name
  per action. The repository: one-screen README, docs/STATUS.md, docs/archive/, research/.
- **Dependencies**: pypdf 6.21.2, certifi 2026.10.19, Next 16.4.1; npm audit and pip-audit clean. The Next install
  dropped the @emnapi/runtime lock entry a third time; `test_lockfile.py` caught it.

Open, each recorded with what it would take:

- Text a reader cannot see (PDF render mode 3, white or 0.1 pt text, text off the page; DOCX white or half-point
  text) is read, can be quoted and verifies. A pass on it is still the model's view. The fix is to read render mode,
  colour, size and page bounds, count such text in the coverage, and raise a concern on a quote that overlaps it.
- The status rule is chosen by the model's topic and the order of the guidance's sentences: the same quote and guidance
  are a pass under one topic and code's shortfall under another. It can lower a status, never make a code-owned pass.
  The fix, a policy version of its own: evaluate every rule the guidance states.
- Uploads are capped by count (300 a public day), not bytes; at 25 MB each the store could reach its 2 GiB floor in
  days, pausing public writes until retention. A daily byte budget needs the size stored per document.
- Open event streams per workspace are not capped; the CSP allows inline scripts (Next's nonces not yet wired).
- On the laptop, the owner's steps: Redis listens on every interface with no password (stop it, or bind 127.0.0.1 and
  set a password, and remove its firewall rule); the MySQL firewall rules allow every profile; Postgres listens on
  every interface; llama-server's `/slots` is on (`LLAMA_ARG_ENDPOINT_SLOTS=0`); Ollama updates itself.
