# System truth

A comprehension pass over the code at commit `43a67f3` (2026-09-29). Nothing here comes from the
README or the design brief; every statement was traced to a file and, where it mattered, executed
in memory. No code was changed for this pass. Marks: **UNPROVEN** means no test holds the claim;
**UNKNOWN** means the code does not decide it (or, for Ivo, the public evidence does not say).
Defects found while tracing are listed at the end, so nothing below is quietly improved; a fix is
recorded there with its date and its measurement.
The index of files and functions is `docs/SYSTEM_MAP.md`.

## B. The workflow, as it runs

| Step | Frontend | API | Backend owner | Persisted | Code decides | Model | Failure → what the user sees |
|---|---|---|---|---|---|---|---|
| Open the app | `Workbench.tsx` mounts; `health()`, `listDocuments()` | `GET /api/health`, `GET /api/documents` | `api/health.py` → `provider.healthy()` (`/api/tags`) | nothing | whether the model is pulled | none | "Model offline: …" on the empty landing; an unreachable API reads "Model offline: The workbench API at … is not reachable." Recent list fails silently |
| Upload, or "try a sample agreement" | `loadFile` / `loadSample` (the sample is fetched from `public/samples/` and posted like any upload) | `POST /api/documents` | `application/ingest_document.py` → `ingest/` readers | `documents`, `sections`; the bytes as `documents/{sha256}{ext}` | everything: extension dispatch, size caps, parsing, sectioning, sha256 identity, reuse | none | the API `detail` verbatim on the landing (role=alert): "the file is not a readable .docx package", "the file is not a readable PDF", "the PDF is encrypted; …", "unsupported file type …", "no readable text found in the file", "file larger than 25 MB" |
| Add guidance | `GuidanceScope` → `useGuidance.apply` | `POST /api/guidance` | `application/save_guidance.py` | `guidance` (one row per stripped text, sha256) | dedup by hash | none | error kept as `runError`, shown only in the idle Assistant; the popover stays open |
| Ask, or "Review against instructions" | `ask` → `useRunFollower.ask` → `createRun` | `POST /api/runs` (202 new, 200 reused) | `application/start_run.py` (fingerprint, `active_run`, unique index) then `api/runs.py` `_worker` → `runs/service.py` `execute_run` | `runs`, `run_stages`, `candidates_json`, `raw_output`, `findings`, `evidence_spans` | fingerprint, reuse, retrieval, prompt assembly, schema validation, verification, status, terminal state | one call (up to four with retries) returns findings with quotes and hints | `createRun` failure: "The run did not complete" · "Failed" · message · "Try again" |
| Follow progress | `followRun`: SSE `/events`, then poll `/detail` every 3 s on stream error | `GET /api/runs/{id}/events`, `/detail` | `api/runs.py` `events` (stored stage rows, then live bus) | nothing new | stage labels from stored rows | none | stream drop → polling; if a poll fails, polling stops and the stage list keeps spinning with no message (found, see end) |
| Receive the result | `AssistantPanel` → `FindingCard` / `RunOutcome` | `GET /api/runs/{id}` on the final event | `api/runs.py` `run_out`: findings only for complete runs; `withheld` list | — | which findings are shown: only fully verified ones | none | unresolved: "No supporting passage found" or "Evidence could not be verified" with the withheld quotes struck through; failed: "Analysis couldn't complete" / "The model could not be reached" / "The run did not complete", with "Try again" |
| Click evidence | `jumpTo` (scroll, `<mark>` at stored offsets), `openEvidence` (drawer) | none | — | — | the highlight is a slice of the stored section text at `[start, end)`; only verified spans mark | none | an unlocated span highlights nothing, silently |
| Confirm or dismiss | `FindingsView.decide` (Findings surface only) | `POST /api/findings/{id}/review` | `application/review_finding.py` | `finding_reviews` (append-only; `cleared` = undo) | 409 for withheld or incomplete; idempotent repeat | none | the API sentence in the view's notice line, e.g. "only a finding shown as an answer can be reviewed; …" |
| Findings | `FindingsView` | `GET /api/findings` | `api/findings.py` | — | complete runs, status not unresolved, ≤ 500 | none | notice line; empty state "No findings yet…" |
| Memo | `useMemoAction.generate` | `POST /api/memos`, then `GET /api/memos/{id}/{html,docx}` | `application/create_memo.py` → `memo/service.py` | `memos` row, HTML, `memos/memo-{run}.docx` | the whole document: projection of stored findings, spans, reviews at that moment | none | inline: "run is {stage}; a memo needs a complete run with verified findings" |
| Evidence pack | link in the Runs record | `GET /api/runs/{id}/evidence-pack` | `application/evidence_pack.py` | nothing (rebuilt per request) | zip with `verify.py` (stdlib only) that re-checks every stored span and three hashes | none | a plain link; a 404 is unhandled |
| Runs | `RunsView` | six GETs (`/runs`, `/engineering/*`, `/batches`) then `/runs/{id}/detail` | `api/runs.py`, `api/engineering.py`, `api/batches.py` | — | staleness recovery runs on every run read | none | per section: "Experiment records are not connected…", "The golden set could not be loaded.", or the section is hidden |

Nothing in `src/` calls a model. The browser never recomputes findings or verification; it displays
the persisted run, with the exceptions in J.

## C. What can be uploaded

The upload endpoint accepts one multipart file of any media type and dispatches on the lower-cased
filename extension (`ingest/readers.py`). The content type is never read. Bytes identical to a stored
document are reused before the extension is checked.

**DOCX** (python-docx 1.2.0, lxml 6.1.3)

| Aspect | Mark | What the code does |
|---|---|---|
| Representation | PARTIAL | python-docx opens the package; the reader walks the main body (`w:p`, `w:tbl` and block-level `w:sdt`, entering content controls and the cells of nested tables; reader v5, 2026-10-01) plus styles for heading levels, `docProps/app.xml` for the page count, and the zip directory for declared sizes |
| Tracked changes | SUPPORTED (accepted view) | `w:ins` / `w:moveTo` kept, `w:del` / `w:moveFrom` dropped; a deleted paragraph mark joins paragraphs; a deleted row is skipped; count shown as "accepted view of N tracked changes". Moves and formatting revisions: UNPROVEN / not counted |
| Hidden runs | PARTIAL | a run's own `w:vanish` is dropped and counted ("N hidden runs left out"); text hidden through a style is kept |
| Tables | SUPPORTED as text | each row becomes one line of cells joined by " \| "; a table nested in a cell is read inside that cell; a horizontally merged cell once, a vertical continuation not repeated; a deleted row skipped; never a heading (`tests/test_reader_sweep.py`) |
| Headers, footers, comments, footnotes, endnotes | IGNORED (accepted, not read) | parsed by the library or not at all; never walked |
| Fields | PARTIAL | cached result text kept; field codes dropped; nothing recomputed |
| Hyperlinks, external relationships | SUPPORTED, display text only | targets never dereferenced; no network during ingest (tested with sockets blocked) |
| Content controls | SUPPORTED | block-level and inline `w:sdt` are read through their content, including a control that wraps a whole table (`tests/test_reader_sweep.py`; dropped before reader v5 while coverage called them read) |
| `w:altChunk`, `w:customXml` at block level, auto-numbering (`w:numPr`) | IGNORED | not in the body loop; list numbers never appear in text (coverage says `automatic_numbering=omitted(N)`) |
| Macros | REJECTED by extension | `.docm` → 422 "unsupported file type", checked before the bytes are looked up (before 2026-10-01 a known file under a `.docm` name or no name was "reused" past the check); a `.docm` renamed `.docx` fails the content-type check inside python-docx → generic 422 (measured 2026-10-01, sweep file g4b) |
| Malformed ZIP / XML | REJECTED at open | `BadZipFile`, `PackageNotFoundError`, `XMLSyntaxError`, `KeyError`, `ValueError`, `AttributeError`, `TypeError` → 422 "the file is not a readable .docx package". The sweep of 2026-10-01 (missing style ids, `outlineLvl` 42 and `x`, degenerate tables, corrupt `footnotes.xml`, under-declared members) produced no 500; a body-walk exception remains uncaught in principle |
| Limits | SUPPORTED | 25 MB upload (checked after the whole body is read into memory); declared unpacked size > 256 MB → 413; sections over 6,000 characters split "(part n)" |
| Headings and numbers | SUPPORTED | style named Title, style names containing "heading", `w:outlineLvl` (own or inherited); numbers read from heading text or computed from levels; the computed flag is not persisted, so a computed number looks printed |

**PDF** (pypdf 6.19.0)

| Aspect | Mark | What the code does |
|---|---|---|
| Extraction | PARTIAL, text only | layout-mode `extract_text`, falling back to plain mode; runs of spaces collapsed; a page ends a paragraph; no font, size or position |
| Tables, multi-column | UNKNOWN | no table logic; columns interleave as the extractor emits them |
| Scans, image-only | REJECTED when every page is image-only; OMITTED per page otherwise | no OCR; no text at all → 422 "no readable text found in the file"; an image-only page among text pages contributes nothing and is counted as `scanned_pages=omitted(N)` (reader v5; before, `unknown`) |
| Encrypted | REJECTED | 422 "the PDF is encrypted; …"; no empty-password attempt, so PDFs that open without a password are refused too |
| Malformed | REJECTED | `PyPdfError`, `ValueError`, `KeyError` at open → 422 "the file is not a readable PDF"; the plain-mode fallback is unguarded (500, UNPROVEN) |
| Limits | SUPPORTED | > 2,000 pages → 413 |
| Headings | PARTIAL | line rules shared with TXT; running headers and footers are not removed: measured 2026-10-01, an all-caps running header becomes a heading on every page with computed numbers that collide with real clauses, and the footer text sits inside each clause body (sweep file h2); two-column pages interleave line by line (h1). Not fixed: needs a reader with page geometry, entered against the parser tournament |

**TXT**: decoded by its byte-order mark, else as UTF-16 when every other byte is a NUL, else strict UTF-8, else Windows-1252; the encoding is named in coverage; control characters are dropped (reader v5; before, everything was UTF-8 with replacement characters, so a UTF-16 file was NUL-interleaved garbage and "€1,500" lost its sign);
the only size limit is 25 MB; blank lines split paragraphs; a line ≤ 90 characters is a heading when
numbered or all-caps; a line starting "30 days notice" becomes section "30".

**Common**: sections are (ordinal, number, heading, text) with random ids; text is not verbatim
bytes (paragraphs stripped, lines joined, tables flattened, tabs and breaks mapped, symbols dropped;
typographic quotes kept, no Unicode normalisation). Once a finished run has read a document, its
rows cannot change.

## D. Garbage

| Case | Accepted / rejected → where → state → what the UI shows | Held by |
|---|---|---|
| Random bytes named `.docx` | rejected → `read_docx` (`BadZipFile`) → 422 "the file is not a readable .docx package", no rows, no file → the string on the landing | `test_failure_matrix` (PK-prefixed junk), `e2e/critical.spec.ts` |
| Empty DOCX (0 bytes) | rejected → same branch and string | measured 2026-10-01 (sweep file g8): 422 "the file is not a readable .docx package" |
| Corrupt DOCX (zip fine, XML broken) | rejected → `XMLSyntaxError` at open → 422 same string; a broken part the reader never opens (`footnotes.xml`) is not noticed: 201, `footnotes=absent` | measured 2026-10-01 (g12, g13) |
| ZIP-bomb-like archive | rejected → declared sizes summed before parsing → 413 "the .docx unpacks to N MB; the limit is 256 MB" | `test_failure_matrix` (API level); the UI string UNPROVEN; under-declared members measured 2026-10-01: an unreferenced 300 MB member is never read (201 in 35 ms), an under-declared `document.xml` fails the zip CRC → 422 (g3b, g3c) |
| Macro-enabled `.docm` | rejected → extension check → 422 "unsupported file type .docm; …" | `test_failure_matrix` |
| External relationships | accepted → 201, rows written; targets never fetched | `test_failure_matrix` (hyperlink relationship, sockets blocked); a linked picture measured 2026-10-01: not fetched, not counted as an embedded object (g7); OLE UNPROVEN |
| Empty PDF | rejected → `EmptyFileError` → 422 "the file is not a readable PDF"; blank pages → 422 "no readable text found in the file" | measured 2026-10-01 (h6b, h6) |
| Encrypted PDF | rejected → 422 "the PDF is encrypted; remove the password and upload it again" | `test_failure_matrix` |
| Scanned / image-only PDF | rejected when every page is image-only → 422 "no readable text found in the file"; a mixed file is accepted and its textless pages counted as `scanned_pages=omitted(N)` | measured 2026-10-01 (h3b); `tests/test_reader_sweep.py` (h3) |
| Random bytes named `.pdf` | rejected → `PdfStreamError` → 422 "the file is not a readable PDF" | `test_failure_matrix` (a "%PDF-1.4 garbage" case) |
| 100,000-character paragraph | accepted → split at sentence ends into parts no longer than a section, each of which fits the prompt whole; a title or first line longer than 200 characters becomes its first words and an ellipsis (reader v5). Before: one section, cut in the prompt, and as the file's first text also a 100,000-character title that reached the prompt whole and held the GPU 24 minutes until the provider timed out (sweep file f8, run `6d6fbd7ed8dc4889`) | `test_failure_matrix`, `tests/test_hardening.py`, `tests/test_reader_sweep.py` |
| Prompt injection in the document text | accepted; the text goes into the user message unescaped; no prompt rule addresses it. Defences: schema-constrained decoding, and a finding is shown only when every quote is located in the stored text. Gaps: the injected sentence is document text, so a quote of it verifies; conclusions are never verified; the status is the model's hint unless day counts parse | UNPROVEN (g43 in the golden set covers an instruction inside the question, not the document) |
| Malicious lawyer guidance | accepted (1–20,000 characters, stripped); into the user message as "LEGAL GUIDANCE: …" and into the retrieval query; no sanitisation. Same defences; in addition `observed` and `required`, which drive the computed status, are model-written and never checked against the quote | UNPROVEN |
| No legally meaningful clauses | accepted; fewer than 3 numbered sections shows "Little structure was found in this file's text, so sections are approximate…"; the run ends unresolved (`insufficient_evidence`: "No supporting passage found" with "Sections searched: …"), or complete with a `missing` finding ("Closest provisions read · N · none states the point"), or withheld, or failed `invalid_output`, depending on the model | UNPROVEN |
| Gibberish only | accepted (TXT never fails to decode); BM25 finds no overlap, so the first k sections are handed over; outcome as above | UNPROVEN end to end (the empty-overlap retrieval case is tested) |

## E. Where the data comes from

**Runtime user data.** Uploaded bytes are written once to `documents/{sha256}{ext}` under the data
directory, only if absent (until 2026-10-02 after the commit; since then before it, written aside
and renamed, so no document row exists without its bytes). Identity is the sha256 of the bytes; the document
*id* is a random 16-hex string, not a hash prefix. The same bytes under the current reader version
return the stored row (200, `reused: true`); an older parse of the same bytes is kept and a new row
is created when the reader version changes; both share the file. Sections are stored as text rows;
the evidence pack carries the original bytes plus the sections. All of `backend/data/` is gitignored.

**Bundled sample.** `public/samples/cloud-service-agreement.docx`, 135,097 bytes, sha256
`cb72dad74b3af676…`: Common Paper Cloud Service Agreement v2.1, CC BY 4.0. The repository says
"unmodified"; the hash equals the one recorded when the file was downloaded for the corpus
(`ivo-experiments/…/corpus_sources.csv`, row CP01). Whether it matches Common Paper's current file:
UNKNOWN. The stored v4 row is named `CP01.docx` because the batch ingested the same bytes first; the
"try a sample" path therefore opens a document called CP01.docx (the sample attribution line is
shown only until a reload).

**Evaluation data, and whether it can reach the product path**

| Set | Where, size, source | Enters the runtime path? |
|---|---|---|
| Golden set | `backend/app/goldens/set.json`, 44 questions in 11 categories about the sample, written by the builder | Read-only by `GET /api/engineering/goldens`, which judges runs already recorded; the runner script records ordinary runs in the same store |
| CUAD | `backend/data/cuad/data.zip` (18.3 MB, CC BY 4.0, The Atticus Project, provenance in `SOURCE.txt`), `corpus-30/` texts, manifest and expert labels under `backend/app/batch/corpora/` | Scripts only. `run_batch.py` ingests the texts into the **same default store**, so they appear in the documents list unless a separate data directory is used |
| Public 20-contract corpus | `ivo-experiments/experiments/{b1-word-structure, pilot-redline-integrity}/corpus`: 8 Common Paper (CC BY 4.0), the rest UK OGL v3.0; per-file licences in the CSVs | Batch CLI input only; ingested into the same store |
| Family labels | `backend/app/families/labels.json`, hand labels by sha256 prefix | Read-only by `GET /api/engineering/families` over whatever labelled documents are stored |
| B1 Word corpus | the same 19 files; the B1 experiment (killed) lives in `ivo-experiments` | Not read by the workbench |
| Synthetic fixtures | `backend/tests/support.py` (`CONTRACT`, `GUIDANCE`, `FakeProvider`), `backend/tests/fixtures/services-agreement.pdf` (printed from Chrome) | Tests only; every test gets a fresh temp database and data directory |
| Recorded model answers | `e2e/replay.json`: 3 qwen3:8b answers | Only under `WORKBENCH_PROVIDER=replay|record`; the default is `ollama` |
| Experiments record | `ivo-experiments/docs/results.json` | Read-only by `GET /api/engineering/experiments` |

The interactive path touches only user uploads and the sample. Nothing in the API ingests a corpus.
The one way a test corpus becomes "product data" is running a batch script against the default
data directory, which is what the recorded batches did.

## F. What the model does, and what code does

**The model receives**, in one user message: `QUESTION: …`; `LEGAL GUIDANCE: …` or `LEGAL GUIDANCE:
none supplied`; `CONTRACT: <file name>`; then at most k = 6 retrieved sections, each as
`[sec_<ordinal>] <number> <heading>` plus its body cut at the run's window (6,000 characters since 2026-10-01, the reader's split, so a part is handed whole; 5,000 before, recorded as absent), in retrieval-rank order.
The system message is the prompt file. Never the whole contract.

**The model may decide**: which of the handed sections answer, up to five findings, each with a
topic, a one-or-two-sentence conclusion, a `status_hint` (pass / needs_review / missing), one to
three evidence items of (section id, quote), and, under guidance, `observed`, `required`,
`guidance_reference`, `suggested_position`; or `insufficient_evidence` with a note. Decoding is
constrained to the JSON schema (temperature 0, seed 42, `think` off).

**Code decides**: file acceptance and parsing; sections and their identity; sha256 identity of
documents, guidance and prompts; the run fingerprint and reuse; which sections are retrieved (BM25,
heading ×3, question + guidance as the query); the prompt text; schema validation and the one
corrected retry; whether each quote exists in the stored text and at which offsets (the verifier);
whether a finding is shown or withheld; the finding status when day counts can be compared, and the
downgrade when a conclusion names a section the document lacks; retries and terminal states;
staleness; persistence and immutability; human review; the memo and the evidence pack.

**The pipeline as implemented**:

`bytes → sha256 identity → reader (v4) → sections (stored, immutable once read by a finished run) →
BM25 top-k over (heading, text) with question + guidance → one schema-constrained model call (≤ 4
with retries) → pydantic validation → per-quote location in the stored text (exact → normalized →
casefold → alnum; label strip; relocation to another candidate) → finding shown or withheld → status
(no_evidence / position_check / computed_days / model_hint, then reference_check) → complete / unresolved / failed →
immutable run record → drawer, Findings, memo, evidence pack read that record`

## G. Is this an agent?

No. It is a **stateful, single-call LLM pipeline with deterministic verification and an immutable
record**. Point by point: no autonomous planning; no tool selection (the model returns JSON, calls
nothing); no iterative reasoning (thinking is disabled; the second call, when it happens, is a
schema-repair retry with the validation error appended, not a step); model calls per run 1 to 4,
all retries of the same question; no fan-out (a batch is a loop of independent runs); no
reconciliation; persistent state is the run record, not agent memory; human checkpoints exist
(confirm / dismiss) but never gate the pipeline; no action modifies external state (the only network
target is Ollama; the only writes are the data directory and, in record mode, the replay file).

## H. What guidance means

Pasting "We accept termination for convenience with 30 days' notice or more. Anything below 30 days
needs review." does this: the text is stripped and hashed; the oldest row with that hash is reused,
else a row is inserted (`guidance` table: id, text, sha256, source, created_at; no versions, no
updates, no immutability trigger; the API has no list, update or delete). The guidance *id* is part
of the run fingerprint, its presence selects the task `guidance_comparison`, and its sha256 is
stored on the run. Retrieval appends the guidance text to the query. The prompt carries it in the
user message as `LEGAL GUIDANCE: …`, and rule 4 of `answer-v2` tells the model to fill `observed`
(the contract's position) and `required` (the guidance's position) and a hint.

Then `decide()`: if any span is unverified → unresolved (`no_evidence`); else a day count in
`observed` must appear in a verified quote and one in `required` must appear in the guidance, or the
finding is needs_review with the source `position_check` (2026-09-29); else if guidance is present
and both yield a day count → `computed_days`: pass when observed ≥ required, or ≤ when `required`
contains a ceiling phrase (within, no more than, at most, no longer than, not to exceed, up to, no
later than, …), otherwise needs_review, the hint discarded; else the model's hint (`model_hint`).
Against a 15-day
clause, "15 days' written notice" versus "at least 30 days" → needs_review by code whatever the
model hinted. The code never reads the sentence "Anything below 30 days needs review" itself.

What holds and what does not:
- Contradiction (contract outside the guidance): needs_review by code when the numbers parse.
- Vague guidance (no day counts): the model's hint stands, labelled "Status taken from the model's hint".
- No guidance: the hint stands; rule 5 tells the model "pass" for a plain answer and "missing" when silent.
- **A pass is worded by what it was checked against.** The run (`RunOut.has_guidance`) and the findings
  list (`FindingRecord.has_guidance`) say whether guidance was given; `statusLabel` (`src/lib/types.ts`)
  and the memo's `status_label` write "Within guidance" only then and "Answered" otherwise. Before
  2026-09-29 every pass read "Within guidance", next to a memo row saying "none supplied". Since 2026-10-01 a pass
  whose status is the model's hint (`status_source = model_hint`) reads "Within guidance (model's view)": the interface
  sweep found the plain chip on two findings that said the contract provides no notice period at all.
- Whitespace-only guidance is refused with a 422 (2026-09-29); guidance is text or absent.
- `observed` and `required` are model-written; since 2026-09-29 a day count in them is checked against
  the verified quotes and the guidance before anything is computed from it (`position_check`). Over
  the 595 recorded findings, nine statuses had been computed from day counts and none disagreed with
  its quote; the check guards the rule, not a failure seen.
- Ceiling phrases: "no longer than", "not longer than", "not to exceed", "up to", "no later than",
  "not later than" and "or shorter" join "within", "no more than", "at most"; "twenty-one (21) days",
  "30 (thirty) days" and "20 Working Days" parse (fourteen recorded quotes and positions say
  "Working Days"). A working day is compared as a day, like a business day before it.

## I. What "verified evidence" means

`verified` is `located is not None` in code; the schema has no `verified` field; the model
influences it only through the quote and the section id. Offsets always index the stored section
text, and the interface highlights that slice. There is no similarity or fuzzy tier anywhere.

| Tier | What is compared | Guarantees | Does not guarantee |
|---|---|---|---|
| exact | raw quote as a substring of raw text | identical characters | context, relevance, which occurrence (the first bounded one) |
| normalized | curly quotes and dashes unified, zero-width and bidi marks removed, whitespace runs collapsed, on both sides | letters, case, digits and all other punctuation identical, in order | quote style, dash style, line breaks, amount of whitespace |
| casefold | normalized plus Unicode casefold | as normalized, minus case | capitalisation of defined terms |
| alnum | letters and digits only, casefolded, on both sides; a full stop between two digits is kept as a decimal point (verifier v4) | the same letters and digits in the same order, none inserted or removed; "$15.00" is not "$1,500" and "1.5%" is not "15%" | punctuation and symbols otherwise, including a thousands separator ("1500" matches "1,500"); word splits ("not ice" matches "notice"); parentheses |
| typed | `verify/tokens.py` (**since verifier v6, 2026-10-02, words are compared whole and the join or split described in this row is no longer forgiven: it made "the rapist" equal to "therapist"; 7 of 1,475 recorded spans had needed it.** As written for verifier v5, in place of alnum; measured over 1,058 recorded spans before wiring: keeps 52 of the 53 alnum spans, gains 3, moves none; replay over 1,299 after: +10, −0) | numbers as values (Decimal), words as letters at word boundaries, punctuation nothing; a match is whole tokens and carries its count of occurrences | a word join or split between words (the reader's own artefact, four spans in the record); nothing about digits |
| unprefixed:<tier> | the section's label (its number as written, then its heading) or its heading alone (at least two letters or digits) cut off the front of the quote, the remainder through the ladder; the number alone is never cut (verifier v4) | the remainder meets the tier; digits at the front of a quote are always part of what must be found | anything about the cut heading: "12.11 No Third-Party Beneficiary There are no…" is verified from "There are no…" |
| relocated:<method> | the quote searched in the other handed candidates, in retrieval order | the quote exists in a section the model was given | that it came from the cited section; the found section is what is stored and shown |

At every tier a match may not split a run of letters and digits at either edge (`bounded()`), so
"5 days" is not inside "fifteen (15) days", "$1,500" is not inside "$11,500", "Section 1" is not
inside "Section 12". A verbatim quote that drops a neighbouring word is still found, and the
highlight shows the dropped word.

- **Can "30 days" become "90 days" and verify?** No: a changed digit is found only where the text
  carries it, bounded, in a handed section. Two exceptions were found by tracing on 2026-09-29 and
  closed the same day by verifier v4: the number alone is no longer cut off a quote, and a decimal
  point between digits counts as a digit. Neither had fired in the record: 847 recorded spans
  replayed under v4, none changed.
- **Can a quote spanning a word boundary match?** Not across a letter or digit ("5 days" in "15
  days"). Across a word ("less than 30 days" in "not less than 30 days"): yes, exact, by design.
- **Can a quote from the wrong section verify?** Yes, if it exists in another section handed to the
  model; it is labelled `relocated:*` and the section where it was found is stored and shown.
  Sections not handed over are never searched. Since verifier v5 the search is bounded to the
  characters the prompt carried (the run's recorded window), so a quote from a tail the model never saw does not verify.
- **Can the model set verified=true?** No.
- **Unverifiable quote**: span start −1, end −1, verified false, method `none`; the finding becomes
  unresolved (`no_evidence`) even if its other quotes verified; the run is complete if another
  finding is fully verified (that finding is shown, this one listed as withheld), else unresolved
  with reason `citations_unverified`; the interface shows "Evidence could not be verified" and the
  withheld quotes struck through; nothing is highlighted; the memo and reviews refuse it.
- Offsets are Python code points; the interface slices a UTF-16 string. They agree unless a section
  contains characters outside the Basic Multilingual Plane (UNPROVEN either way).

## J. After the answer

`finding → jump and highlight → drawer → confirm/dismiss → Findings → memo → evidence pack → Run`
all read the persisted run, findings, spans and reviews. No step calls a model. Four places drift:

1. The drawer's Guidance quote comes from the guidance currently in the UI scope, not from the run;
   it can differ if the guidance was edited after asking (it matches when the run was opened by URL).
2. The memo is stored once per run; a review recorded after the first memo never appears in it. The
   evidence pack is rebuilt on every request and carries the review as it stands.
3. A review made in Findings does not refresh the run already loaded in the Assistant; the drawer
   shows the old review until the run is reopened.
4. For one round trip the run is marked finished before its findings arrive; a transient wrong
   outcome can render (UNPROVEN whether visible against the exit animation).

## K. Does it edit the contract?

No. It does not edit Word documents, create tracked changes, generate redlines or modify the
uploaded agreement. The readers only read; the bytes are copied once, unchanged; triggers block
section and document edits after a finished run. The only DOCX the system writes is the memo, built
from scratch. Outputs are findings on screen, a memo (HTML and .docx), an evidence pack (.zip) and a
batch CSV. "Suggested position" is a sentence in a finding, not an edit.

## L. Scale

**Measured** (`docs/SCALE.md`, `docs/PERFORMANCE.md`, `docs/BATCH.md`, the load-envelope JSON):

| Case | Numbers |
|---|---|
| 1 document, 1 question | run wall 20.3 s, of which model 19.9 s, verification 13 ms; API peak 110 MB |
| 20-document batch, 3 fields, concurrency 1 | 57 min wall, 0.82 values/min, 0 failures; model p50 44 s, p95 135 s |
| 5 / 10 / 20 concurrent questions | run wall p50 105 / 172 / 455 s; API queue ≤ 1.1 s p95; model p50 104 / 172 / 232 s; verify ≤ 41 ms; memory +1.8 MB per concurrent run. Level 20 found two defects (connection pinned through the background task; staleness window shorter than a legitimate wait), fixed and re-measured: 20 of 20 finished, none failed |
| 2,001-section document | first paint 1.6 s, citation jump 35 ms, 8,094 DOM nodes, no virtualisation |
| Largest real parse | UK02, 2,659 sections, 12.2 s (in the database, not in any doc) |

**Measured bottleneck**: model inference, one generation at a time on one GPU. Everything else is
under two seconds at twenty concurrent.

**Architectural inference** (not measured): at 200 contracts nothing breaks; about ten to twelve GPU
hours per three-field pass, and interactive questions queue behind the batch. At 2,000: four to
five days of GPU in one CLI process; the first strains would be two writers on one SQLite file (the
batch CLI and the API), the unpaginated documents list, and the synchronous parse inside an async
upload handler (a 12-second parse stalls other requests). At 1,000,000: years of GPU on this
machine, ~166 GB of originals on one disk, exact pairwise Jaccard for families is O(n²), and every
row of the "what each next step would have to earn" table in `docs/SCALE.md` is met (worker queue,
object storage, PostgreSQL, a persistent embedding index for cross-document search, more GPUs). The
repository says "nothing here says millions", and it does not.

## M. How this differs from Ivo

Ivo column from the supplied notes only (`ivo-research`: memo of 2026-09-26, site crawl of 151
pages, job description); vendor claims stay claims; internals are UNKNOWN. Absence of evidence is
not a gap.

| Capability | Ours, demonstrated in code | Ivo, from supplied / public evidence |
|---|---|---|
| Document upload | .docx / .pdf / .txt, single file, 25 MB, sha256 identity, reuse | upload into Assistant; repository bulk upload; sync connectors (Box, Drive, OneDrive, SharePoint, NetDocuments, DocuSign) |
| Contract Q&A | one question over one document's retrieved sections, every quote located by code before display | Assistant with citations over a document, a selection, rooms, the repository and the web; Slack; an MCP connector. Retrieval method and citation checking: UNKNOWN |
| Guidance / playbooks | one pasted text per run, content-addressed, compared by day counts in code | Review 2.0 positions and fallbacks, up to three playbooks, playbook builder citing the source contract, personal playbooks |
| Evidence / source navigation | offsets into stored text, highlight of the matched characters, method shown, withheld quotes shown as withheld | cited answers, sentence-level citations in Research, provenance on hover; how citations are checked: UNKNOWN |
| Redlining | none | headline positioning: surgical redlining, apply as tracked changes, redline by instruction, Compare Versions |
| Word editing | none (a memo .docx is generated) | Word add-in is the primary surface; Google Docs extension |
| Repository search | none (retrieval is within one document) | Search Agent, repository Q&A, MCP QueryRepository |
| AI fields / extraction | batch of ordinary runs per (document, field), values only with a verified citation, CSV | AI Fields / Columns in plain English, lockable, extract-first engine, prompt optimiser |
| Multi-contract reasoning | none | Assistant over rooms and the repository; benchmarks against executed agreements; method UNKNOWN |
| Clustering | structural families by headings, terms and shingles, measured against hand labels | AI clustering and family detection since 2025-06 |
| Composite contracts / amendments | none | relationships, composite by effective date with a timeline, online terms fetched |
| Deviation analysis | none | Repository Deviations: median exemplar, side-by-side, risk tiers |
| Collaboration | a named confirm / dismiss per finding, append-only | Collaborate (early access): intake, routing, approvals, signature; comment-aware review |
| Generated artifacts | memo (HTML, .docx with bookmarks and custom properties), evidence pack with a standalone checker, batch CSV | issues list, summary and email memo, Word / PPT / Excel outputs, composite export |
| Model / evaluation infrastructure | one local 8B model behind a provider; 44 goldens judged by code; recorded runs; replay of the verifier; hand mutants; load envelope; pre-registered experiments | frontier models; "400+ model calls per review" (claim); a vendor-run benchmark; a CUAD score with the metric unstated; internal evaluation: UNKNOWN |

Where Ivo already has the user-facing capability, what this implementation demonstrates is not the
feature but the discipline under it: a verifier that owns the word "verified" and is measured by
replay and mutation; an immutable, hash-addressed run record that a stranger can re-check offline;
statuses whose source is recorded and shown; retrieval, prompts and models changed only by a golden
set that can refuse; failure states that name their reason; and a repository whose numbers reproduce
from its own database. That is the engineering skill, and it is the same skill a larger product
needs behind each of the capabilities in the right-hand column.

## N. What would break the demo today

Ten questions an Ivo engineer could ask after five minutes, derived from the implementation.

| # | Question | Today |
|---|---|---|
| 1 | How do you know retrieval did not miss the governing clause? | partial: Recall@6 measured at 0.85 (CUAD) and 0.92 (goldens), k = 10 reaches every golden; but a single run has no miss signal beyond "Sections searched" and the candidate list in the record |
| 2 | Why should I trust the "verified" badge? | partial: verification is code-only, replayed over 611 spans, sixteen mutants killed; but the numeric label strip and the alnum tier's number-punctuation blindness are real holes (I) |
| 3 | The document has tracked deletions. What did you analyse? | answer now: the accepted view, counted and shown; moves and formatting revisions untested |
| 4 | Does the evidence survive a model or prompt upgrade? | answer now: runs are immutable; a prompt or option change is a new fingerprint and a new run; a reader change is a new document row; `reverify.py` measures a verifier change against the record first |
| 5 | The provider dies after persistence but before I get the result? | partial: the record is independent of the client; the URL and polling restore it; the same question returns the same run; a stuck run is failed after 41 minutes; but an open event stream to a run that recovery failed hangs on keep-alives |
| 6 | Why BM25 and not semantic retrieval? | answer now: measured; hybrid built, better on labels, one golden regressed, kept behind a flag with the rule written down |
| 7 | Your computed status uses `observed` and `required`. Who checks them against the quote? | cannot answer: nobody; they are model text |
| 8 | Why does a finding say "Within guidance" when I supplied no guidance? | it no longer does: a pass without guidance is labelled "Answered" (H, fixed 2026-09-29) |
| 9 | Headers, footers, footnotes, comments and content controls: where did they go? | cannot answer for those parts: dropped silently; only hidden runs and tracked changes are counted and shown |
| 10 | Show me exactly what the model saw for this run. | answer now (2026-09-30, reordered 2026-10-01): `GET /api/runs/{id}/explanation`; the drawer reads it as Model proposed · Source · Code decided · Human and keeps the full projection behind "Prove it", also on the Runs record: the reading and its coverage, the candidates in rank order with the ContextSlice of each, the exact input rebuilt and hashed against the checking stage, the model's proposal by ordinal, each SourceMatch with the cited and the located section and whether its offsets lie inside the slice the model saw, and the recorded status with its source and sentence; the evidence pack carries the messages themselves |

Also true and quick to find: the CI workflow has never run (it sits on branch `ci`); the batch CLI
and the API can write the same SQLite file at once, unmeasured; the "refresh mid-run" browser test
reloads after the run has finished, because the run id reaches the URL only then.

## O. One-page system truth

**What goes in.** One .docx, .pdf or .txt under 25 MB, a question, and optional pasted lawyer
guidance.

**What happens to it.** The bytes are hashed and stored once. Reader v4 turns the body into
numbered sections: DOCX as the accepted view of tracked changes, tables flattened, headers, footers,
footnotes and comments unread; PDF as text; TXT as lines. Sections are stored and, once a finished
run has read them, cannot change. A run is identified by document, guidance, question, prompt hash
and options; the same question returns the same run. BM25 over the sections, weighted toward
headings, picks six; they go to a local Qwen3 8B with the question, the guidance and a JSON schema.

**What the model does.** In one call (at most four with retries) it proposes up to five findings:
topic, conclusion, status hint, and one to three quotes with section ids. It sees only those six
sections, each cut at the run's window (6,000 characters since 2026-10-01), never the whole contract. No tools, no memory, no second
step.

**What code does.** Everything else. It validates the JSON, locates every quote in the stored text
through a fixed ladder (exact; unified punctuation and whitespace; case; letters and digits only),
refuses matches that split a word or a number, strips a copied section label, searches the other
handed sections, and stores the offsets. A finding is shown only if all its quotes were found;
otherwise it is withheld and shown as withheld. The status is computed from day counts when guidance
and the model's observed and required phrases carry them; otherwise it is the model's hint,
labelled as such; a pass naming a section the document lacks is lowered to needs review. It records
every stage, retries once per failure kind, fails stalled runs, and never alters a finished run.

**What comes out.** Findings with highlighted evidence and the verification tier; withheld quotes;
a status with its source; a memo (HTML and .docx) linking citations to the run; an evidence pack
whose `verify.py` re-checks every span offline; a CSV for batches. No redlines, no edits.

**What is persisted.** Documents, sections, guidance, runs, stage rows, findings, spans, reviews,
memos, batches: one SQLite file, one process.

**What can fail.** Unreadable, encrypted, oversized or empty files are refused with the reason. A
model that is offline, times out or returns invalid JSON gives a failed run with the reason, never
a verdict. A quote not in the text is withheld. A restart mid-run fails the run by staleness.
Silently: dropped parts of a DOCX; observed and required phrases the code trusts; a "Within
guidance" label with no guidance; two holes in the verifier (label stripping, number punctuation).

**What it deliberately does not do.** Edit contracts, search across documents, reason over more
than one model call, use a queue, a vector database, Postgres or an agent framework, fall back to
fake data, or claim unmeasured scale.

**What has been measured.** Retrieval (Recall@6 0.85 on CUAD, 0.92 on the goldens); the golden
set (37 of 44 under BM25, 40 under hybrid); a 20-contract batch (47 of 60 values verified); 611
recorded spans replayed after every verifier change; sixteen hand mutants; a deep fuzz pass; the
concurrency envelope to twenty; a 2,001-section document on screen; an independent adversarial
review. Not measured: real users, a lawyer's judgment, CI, more than one process.

**Where it overlaps Ivo.** Upload, contract Q&A with citations, guidance, field extraction and
clustering exist on both sides. Ivo's redlining, Word editing, repository search, composites,
deviations and collaboration have no counterpart here. What this repository shows is how the word
"verified" is earned and kept.

## Found while tracing, not fixed

Recorded so that the truth above is not quietly improved. Each is a candidate for a measured change;
an item fixed since carries the date and the measurement, and the rest stand.

1. **Verifier, numeric label strip**: a quote beginning with the section's number loses those digits and verifies against a different number (I). **Fixed 2026-09-29, verifier v4:** the number alone is never cut off a quote; a label is recognised only as written, number then heading. Census of the record first: 20 `unprefixed` spans, none cut by the number alone; replay over 847 spans, nothing changed; sixteen hand mutants killed.
2. **Verifier, alnum tier**: punctuation inside numbers and currency or percent symbols are invisible ("$1,500" vs "$15.00"; "15%" vs "1.5%"). **Fixed 2026-09-29, verifier v4:** a full stop between two digits is kept in the letters-and-digits tier; a thousands separator still is not, because "1500" and "1,500" are one number to a reader. Census first: 24 alnum spans in the record, none with a decimal; replay unchanged.
3. **Verifier window**: quotes are checked against the full stored text, not the 5,000 characters the prompt showed. **Measured and fixed 2026-09-29:** of 976 verified spans in the record none ended beyond the window (495 handed sections were longer); verifier v5 bounds the search to the slice the prompt carried (the run's recorded window; 6,000 characters since 2026-10-01, 5,000 before), and `verify.py` in the evidence pack reports any span beyond it.
4. **Status trusts model text**: `observed` / `required` are never compared with the verified quote; `AT_LEAST` is defined but unused; "no longer than", "up to", "not to exceed" read as minimums; "twenty-one (21) days" parses as no count. **Fixed 2026-09-29, twice:** first `position_check` (a stated day count must be in a verified quote or in the guidance), the ceiling phrases, the parenthesised and working-day forms; then, after the chain, the status computed from typed facts parsed from the quote and the guidance (`policy/durations.py`), with units, ambiguity (`ambiguous_fact`) and the evaluation's sentence on the finding; the model's numbers can no longer be the operand. Census first: 9 computed statuses in the record, none disagreeing with its quote; 14 more recorded day counts parse, all "Working Days".
5. **"Within guidance" without guidance**: the label and the memo heading say it for any `pass`. **Fixed 2026-09-29:** `has_guidance` on `RunOut` and `FindingRecord`; a pass without guidance reads "Answered" in the chip, the tables and the memo heading (`tests/test_api_flow.py`).
6. **Whitespace-only guidance** is accepted and stored empty while `decide()` is told guidance is present. **Fixed 2026-09-29:** refused with a 422 that says so; guidance is either text or absent.
7. **DOCX content dropped silently**: headers, footers, footnotes, endnotes, comments, block-level content controls, `altChunk`, auto-numbering; style-level hidden text kept; a deleted paragraph mark joins paragraphs with no separator. **Dropped no longer silently (2026-09-29):** `ingest/coverage.py` records what the reading did with each of seventeen parts; the document carries it, the paper says what was not read, the pack records it. Census of the 36 licensed contracts and the sample: 32 footers and 12 headers with real text, 2 footnotes, 5 content controls, 17 fields, 27 automatic numbering. Reading those parts is a reader change to be measured in the parser tournament, not made here.
8a. **Hostile packages, measured (2026-09-29):** an entity bomb and absurd nesting in `document.xml` are refused as unreadable packages in 0.02 s (lxml refuses them before python-docx sees a body); twenty thousand members are read in 0.5 s; these are tests now (`tests/test_hostile_packages.py`), so a change in the envelope is deliberate.
8. **Unguarded exception paths**: the DOCX body walk and the PDF plain-mode fallback can surface as 500s; a password-protected Word file gets the generic message.
9. **Long first paragraph** becomes the title and reaches the prompt untruncated through the heading line.
10. **Reuse before validation**: identical bytes are reused under any filename or extension; the 25 MB check runs after the whole body is in memory; the upload handler parses synchronously inside an async route. **Partly fixed 2026-09-29:** the declared size is refused before a byte is read and the bytes are checked again once read; the parse runs in the thread pool, off the event loop. Reuse by bytes under any name stands: the same bytes are the same document, whatever they are called.
11. **Two rows possible**: no unique constraint on (document sha256, parser version) or on `memos.run_id`; concurrent first requests can duplicate, and a second memo overwrites the file. **Fixed 2026-09-29:** unique indexes `ux_documents_sha256_parser` and `ux_memos_run_id` (added to an existing database at startup; rows from before reader versioning carry NULL and stay distinct); a request that loses the insert is handed the winner with `reused`; the memo is written aside and moved into place only after its row is in, so a loser never touches the winner's file (`tests/test_uniqueness.py`; mutants M20, M21).
12. **Recovered runs and event streams**: recovery does not publish to the bus; an open stream to a recovered run receives keep-alives forever. **Fixed 2026-09-29:** recovery publishes the failed stage on the bus, and the stream re-reads the run's stage at every heartbeat, so a run ended by another process ends its streams within fifteen seconds (`tests/test_run_endings.py`; mutants M17, M18). Stored events carry ids and a reconnect resumes from `Last-Event-ID`. A stage row names its process, and a run whose process provably died on this host is recovered at once rather than after the staleness window (`runs/owner.py`).
13. **Error handlers without rollback**: after a database error inside a run, `_finish` itself can raise and the run waits for staleness recovery. **Fixed 2026-09-29:** `_fail` rolls the session back, re-reads the run and, when another writer has already ended it, keeps that record and leaves; the case seen at twenty concurrent runs (recovery in another process, then the immutability trigger) is now a test (mutant M19).
14. **Frontend**: a failed poll after a dropped stream stops polling and leaves the stage list spinning; "Open in workspace" on an in-progress run never follows it; a new upload does not stop the previous follower or close the drawer; the finished stage is applied one round trip before the findings; the drawer's guidance text is the UI's, not the run's; the memo does not pick up later reviews. **Fixed 2026-09-29** (the drawer now shows the run's own guidance, `RunOut.guidance_text`): the follower is a state machine (polling retries five times, then a disconnected state with resume; a run in flight loaded from the record is followed; a new upload stops the follower and closes the drawer; the terminal stage is applied only with the record), and the Assistant re-reads its finished run when shown again, so reviews reach the drawer and the memo's review head.
15. **Claims to correct**: the "refresh mid-run" browser flow reloads after the run has finished (README and `docs/VALIDATION.md` are corrected in this commit to say so; **since 2026-09-29 it refreshes mid-run**: the replay provider holds its answer back and the page reattaches to the same run); `DECISIONS.md` still carries the batch's earlier 9 / 4 counts in an older entry; the goldens runner ignores the routing policy (harmless while it is empty); one comment says sections are sent in document order when they are sent in rank order (the Runs note said so too; fixed 2026-09-30); a whitespace-only reviewer name is stored as an empty string; one oversized file aborts a whole batch; the staleness window ignores embedding calls under hybrid retrieval.
16. **Evidence in gitignored data**: the CUAD archive, the load-envelope JSON and logs, the Lighthouse reports and the 2,001-section fixture exist only under `backend/data/`; a fresh clone re-checks them through recorded hashes and URLs only.
