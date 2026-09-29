# Decisions log

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
