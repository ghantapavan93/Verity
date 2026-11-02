# The Verity Book

A complete guide to the Verity prototype for an engineer or an AI coding agent who has not read the code. Read this
file, then open only the files a task needs. Every path is relative to the repository root.

Written against commit `865356b` (the release live at https://ivo.pavankg.dev since 2026-10-30). Code moves; where this
book and the code disagree, the code is right and this book is stale. Section 11 says how to keep it current.

## Contents

0. [How to use this book](#0-how-to-use-this-book)
1. [Verity in one page](#1-verity-in-one-page)
2. [The system at a glance](#2-the-system-at-a-glance)
3. [One upload and one question, end to end](#3-one-upload-and-one-question-end-to-end)
4. [Reading a contract](#4-reading-a-contract) (`backend/app/ingest`)
5. [Answering a question](#5-answering-a-question) (retrieval, the model, the verifier, the policy)
6. [Records, reviews and proofs](#6-records-reviews-and-proofs) (trust, memo, evidence pack, goldens)
7. [The API, access and the store](#7-the-api-access-and-the-store) (routes, sessions, limits, tables)
8. [The interface](#8-the-interface) (`src/`, the browser flows)
9. [Running, testing and shipping](#9-running-testing-and-shipping) (setup, tests, the gate, deploy, docs)
10. [Changing Verity safely: a recipe index](#10-changing-verity-safely-a-recipe-index)
11. [Keeping this book true](#11-keeping-this-book-true)
12. [Glossary](#12-glossary)

## 0. How to use this book

- **New to the project:** read sections 1, 2 and 3 (about fifteen minutes). They give the whole shape.
- **About to change something:** find the task in section 10. It names the files, the tests and the version that the
  change touches. Then read that part's chapter.
- **Looking for a file:** every tracked file appears in one of chapters 4 to 9, in a "file by file" table. Search this
  book for the file's name.
- **Before saying a change is done:** run the checks in section 9 ("Checks") and read the house rules there. Two rules
  catch most newcomers: a change to code that decides an outcome needs a version decision (section 5, "Versions"),
  and the interface decides nothing (section 8).

Conventions: `file.py:function` names a function in a file. "The model" is the local language model (Qwen3 8B through
Ollama). "Code" means Verity's own deterministic checks. "The store" is the SQLite database. "A reader" is either a
person reading the screen or the module that reads a file into text, and the text says which.

## 1. Verity in one page

**What it is.** A contract-review workbench. A visitor uploads a contract (PDF, DOCX or TXT) or opens a sample, asks a
question ("Can the customer terminate for convenience on 30 days' notice?"), and gets findings. Each finding is an
answer with the passages it rests on. The visitor can open each cited passage in the contract, see who decided each
part of the answer, confirm or dismiss it under a name, and download a memo and an evidence pack.

**The idea it is built around.** A contract AI can quote the right passage and still reach the wrong conclusion. Verity
separates what code can check from what remains the model's reading, and shows both.

| Who | Decides | Example |
|---|---|---|
| The model | proposes findings, quotes passages, suggests a status | "Customer may terminate on 30 days' notice", quoting §5.1 |
| Code | whether each quote stands word for word in the stored text (else the finding is withheld); a status where a rule can be compared or a quote leaves out a condition | "Code lowered it: the quote leaves out of its sentence 'Except for the first sixty (60) calendar days…'" |
| A person | confirms, dismisses or clears a finding, under a name | "Confirmed by Reviewer" |

Code verifies that each quoted passage stands in the document's own text. It does not verify legal interpretation.

**What it is not.** Not a legal advisor, not a hosted SaaS, not multi-tenant with accounts. There is no sign-in: each
browser gets its own workspace, deleted with everything in it seven days after its first visit.

**Where it runs.** One Windows laptop serves the public demo: the API (FastAPI, port 8000), the interface (Next.js,
port 3900), the model (Ollama, port 11434) and a Cloudflare Tunnel to https://ivo.pavankg.dev. Two supervised scheduled
tasks keep the API and the interface running. The public visitors' store is a SQLite file kept outside the checkout;
the owner's historical store is a different file and is never served publicly.

**Three public pages.**

| Page | What it shows |
|---|---|
| `/` | The landing, then the workbench: the contract, the questions panel, answers, the evidence drawer, Findings, Runs |
| `/break` | One recorded answer whose quote passed every check and still gave a right to the wrong party, the fix built to catch it, and why that fix was rejected on unseen cases |
| `/state` | A frozen research experiment on 5,414 SEC exhibits: when one contract arrives, which derived facts need another look |

**The numbers that describe it today** (from the release gate's log for `865356b`; each gate run keeps its own counts):
3,403 backend tests passed, 411 interface unit tests, 46 browser flows, 17 of 17 planted trust faults caught by the fault
matrix, all run on a fresh clone of one commit.

## 2. The system at a glance

### Processes and data

```
 Browser ──HTTPS──► Cloudflare ──tunnel──► cloudflared (laptop)
                                              │
                         ┌────────────────────┴───────────────────┐
                         ▼                                        ▼
            Next.js interface :3900                    FastAPI API :8000
            (src/, renders what the API                (backend/app/main.py)
             decided; decides nothing)                     │        │
                         │  fetch /api/* and an           │        │ HTTP, one call at a time
                         └── event stream of a run ──────►│        ▼ (admission queue)
                                                           │   Ollama :11434, qwen3:8b
                                                           ▼
                                   SQLite store (WAL): documents, sections, runs, run_stages,
                                   findings, evidence_spans, finding_reviews, memos, guidance,
                                   visitor_workspaces, document_access, document_versions, …
                                   plus files beside it: originals, memos (DOCX)
```

The interface never talks to the model. The API never trusts the interface: every rule (who may read what, how many
uploads, what a status is) is decided in the backend.

### The backend's layers

The backend is layered, and `backend/.importlinter` enforces it (`lint-imports`). From top to bottom:

| Layer | Packages | Owns |
|---|---|---|
| API | `app/api` | HTTP routes, sessions, limits at the door, response shapes |
| Batch, goldens, families | `app/batch`, `app/goldens`, `app/families` | multi-run measurements and evaluation sets |
| Application | `app/application` | one use case per module: ingest a document, start a run, create a memo, export a pack, retention |
| Runs, routing, trust | `app/runs`, `app/routing`, `app/trust` | executing a run and deciding statuses; choosing a model route; the trust layer over a finished run |
| Analysis, retrieval, ingest, memo, policy | `app/analysis`, `app/retrieval`, `app/ingest`, `app/memo`, `app/policy` | the model input and schema; ranking sections; reading files; the memo document; period and condition rules |
| Verify | `app/verify` | whether a quote stands in a text, and where. It imports nothing else from the app (a test checks it uses only the standard library) |
| Providers | `app/providers` | the model call: Ollama, the admission queue, the record/replay provider |
| Leaf modules | `document_names`, `models`, `db`, `schemas`, `config`, `hashing`, `errors`, `unseen`, `log_sink` | names, tables, the database, API shapes, settings, hashing, error types, invisible characters, the log |

`app/main.py` and `app/serving.py` are exempt: they assemble the app and its event loop.

### The repository

| Path | What is there | Chapter |
|---|---|---|
| `backend/app/` | the API and everything it decides | 4–7 |
| `backend/tests/` | about 195 test files: behaviour, properties (Hypothesis), a fuzz of every route (Schemathesis), hostile files | 9 |
| `backend/scripts/` | operator and research tools: status, backup, data audit, goldens, CUAD scoring, exports | 9 |
| `src/` | the Next.js interface | 8 |
| `e2e/` | 49 Playwright browser flows against the production build, with recorded model answers replayed | 8 |
| `deploy/` | the laptop deployment (supervisor, installer, stop and build swap) and a one-server cloud kit not used live | 9 |
| `docs/` | status table, casebook, failure envelope, troubleshooting, measurements, ADRs, archive | 9 |
| `research/`, `proof/` | experiments run against the product, kept as run; a static page of one recorded run | 9 |
| `scripts/release-gate.sh` | the release gate: every check on a fresh clone of one commit | 9 |
| `public/samples/` | the sample agreements the landing offers | 4 |
| `DECISIONS.md` | every decision as taken, dated, with what was rejected | 9 |
| `AGENTS.md`, `CLAUDE.md`, `ENGINEERING_CONSTITUTION.md` | the house rules for anyone, human or agent, changing the code | 9 |
| `openapi.json` | the API contract, generated from the backend; the interface's types are generated from it | 7, 8 |

## 3. One upload and one question, end to end

This is the whole system in one pass. Each step names the code and the chapter that explains it in depth.

### 3.1 A visitor arrives

1. The browser loads `/`. The Next.js server answers with a page whose Content-Security-Policy carries a nonce made
   for that response, so only the page's own scripts run (`src/proxy.ts`, §8.3).
2. The page asks `GET /api/health` and, with no session yet, `POST /api/access/visit`. The API mints an anonymous
   subject and a workspace `pw-…`, and sets a signed `__Host-` cookie (HttpOnly, Secure, SameSite=Strict). From now on
   every request is scoped to that workspace; nothing is shared between browsers (§7.3).

### 3.2 The upload

3. The visitor drops a file or picks the sample. `POST /api/documents` (`api/documents.py`) checks the size (25 MB) and
   the type against the bytes, not the name, counts the upload against the workspace and the day's budgets
   (`application/quotas.py`), and hands the bytes to `application/ingest_document.py` (§4.2, §7.3).
4. The file is hashed (SHA-256). If the same bytes were already read by the same reader version, that reading is
   reused and only a grant for this workspace is added. Otherwise the file is read in a bounded child process
   (`ingest/bounded.py`) by its reader: PDF by position (columns, tables, invisible text left out and counted), DOCX as
   Word displays it, TXT as text (§4.2).
5. The reading becomes numbered sections (`ingest/sections.py`): headings, clause numbers, long clauses cut into
   recorded parts at passage ends. A coverage record says what was not read (headers, footers, hidden text). Sections,
   the document row and the original file are stored (§4.4, §7.5).
6. The page shows the contract as read, with "Not read by this reading: …" above it (§8.2).

### 3.3 The question

7. The visitor types a question and presses Enter. `POST /api/runs` → `application/start_run.py`: the question is
   cleaned, the run's options are fixed (model, decoding, retrieval k, section window, alias table hash, and the four
   rule versions), and a fingerprint is computed. If a run with the same fingerprint exists, it is returned
   (`reused: true`, HTTP 200). Otherwise a new run is created (HTTP 202) and executed on a worker thread (§5.1).
8. `runs/service.py:execute_run` runs the stages, each recorded with input and output hashes:
   - **reading**: the stored sections;
   - **finding_evidence**: `_retrieve` ranks sections with BM25 (plus alias groups), adds the sections the top ones
     depend on (definitions, amendments, cited clauses), or hands over the opening sections when nothing ranks;
   - **checking**: `build_user_message` writes the model's input (question, guidance, contract name, sections cut at
     the window), and `analysis/service.analyze` calls the model through the admission queue
     (`providers/admission.py` → `providers/ollama.py`) and validates the JSON answer against a schema, with one retry
     that feeds the validation error back;
   - **verifying**: every quote is looked for in its cited section (`verify_evidence` → `verify/spans.locate`: exact,
     normalized, casefold, then typed tokens). A finding with any quote not found is withheld. For the rest, the policy
     chain decides the status: `decide`, `check_references`, `check_values`, `check_conditions`, and with the
     contract's relations `check_replaced`, `check_old_value`, `check_unhanded`; then `settle_together` across
     findings (§5.1, §5.2, §5.3).
9. The run ends `complete`, `unresolved` or `failed`. Its findings, evidence spans and a hash of the finished record are
   written; a finished run, its findings and spans, and the text they cite can no longer be changed (database
   triggers, §7.5).
10. The page follows the run through an event stream (`GET /api/runs/{id}/events`), with polling as a fallback, and
    shows each finding as a card: the answer, its status chip, and who decided it (§8.2, §8.3).

### 3.4 After the answer

11. **Evidence drawer.** "Inspect evidence" opens what the model proposed, what the source says, what code decided
    and what a person decided, each labelled MODEL, CODE or a reviewer's name; the cited passage is highlighted in the
    contract (§8.2, §6.1).
12. **Review.** The visitor confirms, dismisses or clears a finding under a name (`application/review_finding.py`). A
    decision made in an out-of-date tab is refused (§6.1).
13. **Memo.** "Generate review memo" writes an HTML and DOCX memo from the stored findings and reviews, with no model
    call. A memo is identified by its run, its review head and its content (§6.1).
14. **Evidence pack.** "Download evidence pack" gives a zip with the run, findings, sections, the model's raw output
    and a plain-Python `verify.py` that re-checks every quote under the verifier version the run recorded (§6.1).
15. **Trust and revisions.** The trust layer (`app/trust`) says, per finding, which obligations hold today. When the
    visitor records a later version of the contract, the revision check tells which findings still stand, which are
    stale and why, with no model call (§6.1).
16. **Retention.** Seven days after the first visit, the workspace and everything in it is deleted, with secure delete
    and a checkpoint (`application/retention.py`, §7.5).

### 3.5 Where each decision lives

| Question | Decided in |
|---|---|
| Is this upload allowed? | `api/access.py`, `application/quotas.py` |
| What does the contract say, section by section? | `app/ingest` |
| Which sections does the model see? | `runs/service.py:_retrieve`, `app/retrieval`, `runs/links.py` |
| What exactly is the model sent? | `analysis/service.py:build_user_message`, `analysis/prompts/`, `providers/ollama.py:chat_request` |
| Is a quote really in the contract? | `app/verify` (only) |
| What is a finding's status? | `runs/status.py` and the modules it reaches (`policy/`, `runs/values.py`, `runs/relations.py`) |
| What does code say it checked? | `runs/account.py` |
| Who may read this run? | `api/access.py`, `application/workspace.py` |
| What does the page show? | the API's response; the interface decides nothing (`src/`) |

## 4. Reading a contract

Slice: every file under `backend/app/ingest/`, plus `backend/app/application/ingest_document.py`,
`backend/app/application/versions.py`, `backend/app/document_names.py`, `backend/app/unseen.py`,
`backend/app/hashing.py` and the three files in `public/samples/`. Written against `865356b`. Line numbers are from that
commit. Facts marked "probe" were checked by running the reader in a Python process on that commit.

### 4.1 What this part does

This part turns an uploaded file into stored, numbered sections of plain text. It checks the bytes against the claimed
type, hashes them, and reuses a stored reading when the same bytes were already read by the same reader version. A new
file is read in a child process held to 30 s and 768 MiB. The reader produces the text Word or a PDF viewer would
display: tracked changes accepted, hidden and invisible text left out and counted. It then cuts the text into sections
at headings, numbers them only with numbers the document itself shows, and splits long sections at passage ends. It
records a coverage report: each part of the file, and whether it was read, left out, or unknown. Everything later
(retrieval, the model's prompt, the verifier, the evidence pack) works only from these stored sections.

Where it sits. The route `POST /api/documents` (`backend/app/api/documents.py:upload_document`) calls
`application/ingest_document.py:ingest_document`. That use case calls `ingest/bounded.py:read_file`, which runs
`ingest/__init__.py:ingest` in a child. It hands back a `Document` row with its `Section` rows and a grant
(`DocumentAccess`) for the uploading workspace. The batch runner (`batch/service.py`) and the goldens runner
(`goldens/service.py`) call `ingest_document` too, with no workspace. `application/trust_run.py` calls `read_file`
again to re-read an original under today's reader.

### 4.2 The flow of an upload, step by step

| # | Step | Where | What happens |
|---|---|---|---|
| 1 | Admission | `api/documents.py:upload_document` | `admit_upload` (owner pause, public quotas), then `refuse_if_too_large(file.size)` on the declared size. |
| 2 | Turn | `api/documents.py:reading_turn` | One reading at a time per client network, then one of `READINGS_AT_ONCE` (2) slots; 45 s total wait, else 503 `Busy`. The read runs on a thread (`to_thread.run_sync`). |
| 3 | Size | `ingest_document.py:refuse_if_too_large` | 25 MB (`MAX_UPLOAD_BYTES`, line 33) on the real bytes: `TooLarge` (413). The body middleware allows 25 MB + 1 MiB (`api/body_limit.py`). |
| 4 | Type | `ingest_document.py:refuse_unsupported_type` → `readers.py:file_type` | Name must end `.docx`, `.pdf` or `.txt`. Empty file refused. Bytes sniffed by `content_type`: `%PDF-` in the first 1024 bytes is a PDF, `PK\x03\x04` at the start is a zip. A `.txt` must be neither; a `.pdf`/`.docx` must be what it claims. Failure: `InvalidInput` (422). |
| 5 | Name | `ingest/__init__.py:base_name` | The name the workspace gave, cleaned (see 4.2.6). Kept on the grant. |
| 6 | Dedupe | `hashing.py:sha256_bytes`, `ingest_document.py:stored_document` | Look up `Document` with this sha256 **and** `parser_version == PARSER_VERSION`. If found: `_reuse` rewrites the original file if missing or damaged, grants the workspace, and returns 201 when the grant is new to this workspace, 200 only when the workspace already held these bytes. No reading happens. |
| 7 | Quotas | `quotas.refuse_if_spent(document_quotas(...))` | Counted before reading, so a refused upload is never read. Counted again later under the write lock. |
| 8 | Bounded read | `bounded.py:read_file` → `ingest_bounded` → `_read_child` | Slot (`BoundedSemaphore(2)`), handoff file, child process, memory sampled every 50 ms, killed past 768 MiB or 30 s. See 4.2.1. |
| 9 | Read | `ingest/__init__.py:ingest` → `readers.py:read` | In the child. `file_type` again, then `_read_as` dispatches to `read_docx`, `read_pdf` or `read_txt`. Any parser exception becomes `UnsupportedFile` ("the file is not a readable PDF"), logged by exception class only. |
| 10 | Clean | `readers.py:read` (lines 136-161) | A second pass of `invisible.remove_format_characters` over every block and the title; the count is appended as coverage part `format_characters`, then the reader's extra parts (`more_coverage`). |
| 11 | Text bound | `ingest/__init__.py:ingest` | Total block text over `MAX_TEXT_CHARS` (13,200,000) → `TooLargeToRead`. |
| 12 | Sections | `sections.py:build_sections` | Headings, numbers, labels, size splits. See 4.2.4. |
| 13 | Section bound | `ingest/__init__.py:ingest` | More than `MAX_SECTIONS` (21,522) → `TooLargeToRead`. No section with text → `UnsupportedFile` ("no readable text", or "no text layer on any page (a scan?)" when every PDF page is textless). |
| 14 | Answer | `bounded.py:_read_in_child` → `_outcome` | The child pickles back `Ingested`, or a refusal kind. Parent maps: `ReadingBusy` → `Busy` 503 (Retry-After 30), `TooLargeToRead` → `TooLarge` 413, `UnsupportedFile` → `InvalidInput` 422, anything else → `RuntimeError` (500). |
| 15 | Rows | `ingest_document.py:ingest_document` (147-163) | Build `Document` (name, media type, sha256, pages, `parse_ms`, `parser_version`, counts, `coverage_json`, `size_bytes`) and `Section` rows (`ordinal`, `number`, `heading`, `text`, `part`). |
| 16 | Store | `ingest_document.py:store` via `quotas.admit` | Under the write lock: quotas recounted, original bytes written durably (`keep_original` → `write_durable`), row added, flushed, grant written, one commit. |
| 17 | Race | `ingest_document.py` (185-196) | `IntegrityError` on the unique index means another request stored the same bytes first: hand back the winner via `_reuse`. If the winner is already gone at the lookup, the `IntegrityError` is raised again (500); if it vanishes during the grant (`_Vanished`), 503. |
| 18 | Reply | `api/documents.py:to_document_out` | 201 new to this workspace, 200 already held (`reused: true`). The body carries sections (with `part`) and the coverage report. |

`parse_ms` is measured around `read_file` (lines 136-145), so it includes any wait for a reading slot and the child's
start-up.

#### 4.2.1 Reading in a bounded child (`ingest/bounded.py`)

- `read_file(filename, data, wait=None)` is "the one way the application reads a file" (line 88). It takes one of two
  slots, then calls `ingest_bounded`, or `ingest` directly when `READ_IN_CHILD` is False (only the test suite sets that,
  in `tests/conftest.py`).
- `ingest_bounded` writes a handoff file with `tempfile.mkstemp(prefix="verity-reading-", dir=HANDOFF_DIR)`: a 4-byte
  big-endian name length, the name in UTF-8 (`surrogatepass`), then the bytes. The child gets only the path and a pipe.
  The file is passed by path because a large write into the start-up pipe blocked the parent on Windows.
- `_read_child` starts the process. On Windows the context is `spawn`; elsewhere a `forkserver` that preloads
  `app.ingest`. It waits on the answer pipe or the child's sentinel, sampling memory (`_memory_bytes`: resident pages
  from `/proc/<pid>/statm` on Linux, committed memory via `GetProcessMemoryInfo` on Windows) every 50 ms.
- Bounds (lines 49-51): `READ_SECONDS = 30.0`, `READ_MEMORY_BYTES = 768 MiB`, `READINGS_AT_ONCE = 2`. Past a bound the
  child is killed and the reading is `TooLargeToRead` with the reason. A child that ends without answering is
  `TooLargeToRead("reading the file failed in a way no contract causes")`.
- In the child, `_seal_output` disables logging, ignores warnings and points stdout/stderr at the null device, because
  pypdf messages quote file content. The answer goes back only through the pipe.
- The handoff folder is per store: `handoff_folder(data_dir)` = `<system temp>/verity-readings-<16 hex of sha256 of the
  store path>`. `main.py` lifespan calls `use_handoff_dir` (empties leftovers, checks ownership on POSIX) and
  `release_handoff_dir` at shutdown. `retention.py` also sweeps old `verity-reading-*` files.

#### 4.2.2 The three readers (`ingest/readers.py`)

Every reader returns a `ReadResult` (4.4): a list of `Block`s (heading or text), page count, title, counts, coverage.

**DOCX, as Word displays it** (`read_docx`, line 945).

1. Refuse a package whose declared unpacked size exceeds `MAX_DOCX_UNPACKED_BYTES` (64 MiB). Open with python-docx.
2. Build the walk state `_Walk`: styles (`_Styles`, for hiding and colour through `basedOn` chains, depth 12), markup
   compatibility (`word_display.Compatibility`), data bindings (`word_display.Bindings` over `customXml/*` and
   `docProps`), field balance (`fields_balance`), page background colour.
3. Work out printed list numbers once: `_Numbering(document).printed_numbers(...)` gives, per numbered paragraph, the
   clause number Word prints (decimal, roman, letters, start values, overrides, restarts). Where the reader cannot say
   exactly (two instances of one list in use, `w:lvlRestart`/`w:isLgl`, other formats, text boxes, tracked property
   changes), the value is `None`, never a guess. A lettered sub-item is cited with its parent ("5.3(a)").
4. `walk_container(body)` visits paragraphs and tables in document order. It enters block content controls (`w:sdt`,
   or the bound value when data-bound) and block `w:customXml`.
   - Paragraph text: `accepted_text` keeps runs, `w:ins`, `w:moveTo`, hyperlinks, smart tags, simple fields, inline
     controls; drops `w:del`, `w:moveFrom`, property bags. `_run_text` renders `w:t`, tabs, breaks, `w:sym`
     glyphs, symbol-font text, and the legacy form-field box or drop-down entry; nothing while a field instruction is
     open. Other elements holding text are counted in `walk.unread` by name.
   - A paragraph whose mark is a tracked deletion is carried into the next paragraph (`carry`).
   - Heading level: `_heading_level` (style named "Title", any style with "heading" and a digit, the paragraph's own
     `w:outlineLvl`, or its style chain's). If the document uses heading styles anywhere (`_uses_heading_styles`),
     unstyled paragraphs are body unless `_typed_heading_level` finds a short, bold-or-capitals, numbered title whose
     number is the next clause within `MAX_TOP_STEP` (2). If it uses none, every paragraph is judged like a plain-text
     line (`_unstyled_heading_level` → `sections.looks_like_heading`).
   - Tables: `table_rows` → `row_slots`: one slot per grid column, `w:gridBefore` slots empty, a spanned cell's text in
     its first column, merge continuations empty, trailing empties dropped, joined `" | "`. Deleted rows skipped.
     Nested tables are read inside their cell.
   - Text boxes found in a paragraph are read once each, as blocks after it (`read_boxes`), with their own field state.
5. Counts: tracked changes = every `w:ins|w:del|w:moveFrom|w:moveTo` in the body. Pages come from `docProps/app.xml`
   `<Pages>` (what Word last saved; not computed). The title is the first text block, shortened to 200 characters.

**PDF, by position** (`read_pdf`, line 1218).

1. pypdf `PdfReader`. Encrypted → `UnsupportedFile`. More than `MAX_PDF_PAGES` (2000) → `TooLargeToRead`.
2. Each page: `pdf_layout.page_text(page)` walks the page's own operators (4.3, `pdf_layout.py`). If that walk raises,
   the page is read by pypdf's layout mode, then by plain `extract_text`, and counted (`tally.as_given`).
3. Annotations with visible values (filled form fields, ticked boxes, free-text notes, stamps) are counted, not read
   (`_annotation_texts`).
4. Format characters removed. A page with no text and no text-drawing operator counts as textless (scanned).
5. Runs of two or more spaces/tabs collapse to one space. Each page ends with a blank line (line 1253), so a paragraph
   that crosses a page break is stored as two paragraphs.
6. Running headers and footers: `sections.page_edge_furniture(lines, line_pages)` finds lines among the first or last
   two lines of a page that repeat (same text, or same text with a rising number) on at least 3 pages and more than
   half the pages. Those lines are blanked out and listed in coverage. The document's own heading at the top of page 1
   stays. Lines opening with a clause number or a structural word (Exhibit, Schedule, Annex, ...) are never furniture.
7. `_blocks_from_lines(lines, line_pages)` makes blocks; each carries the page of its first line.

**TXT** (`read_txt`, line 1322).

1. `decode_text`: UTF-8 BOM, UTF-16 BOM, UTF-16 without BOM (over a quarter of the first 4096 bytes are NUL), strict
   UTF-8, else Windows-1252 with replacement. The encoding is named in coverage.
2. A NUL left after decoding means binary: refused.
3. Format characters removed; control characters other than tab, LF and CR removed (form feeds go too).
4. `_blocks_from_lines(lines)` with no pages.

**Lines to blocks** (`_blocks_from_lines`, line 1366; PDF and TXT). A blank line ends a paragraph. A line is a heading
candidate if `sections.looks_like_heading` says so: at most 90 characters, and either a numbered title opening with a
capital (not a cross-reference, not a lower-case continuation), an attachment line ("Schedule A. Fees"), or a short
capitals line that does not read as a sentence. Then:
- a numbered candidate whose top number jumps more than `MAX_NUMBER_GAP` (20) past the last is text (addresses, years);
- an unnumbered capitals line before any heading is the title, kept as text;
- "ARTICLE II" followed by "PURCHASE AND SALE" is one heading; a capitals title that wraps is one heading;
- an unnumbered title line inside a paragraph that goes on (no passage end, capitals or ending in a function word) is
  the paragraph's next line;
- level is 1 when the first token has no dot, else 2. Every heading gets `implicit_number=False`.

#### 4.2.3 Invisible text

The rule (stated in `invisible.py`, `pdf_layout.py`, `word_display.py`): the text a person reads is the text that is
checked; what a reader cannot see is left out and counted.

| What | Where handled | Result |
|---|---|---|
| Unicode format characters (Cf): zero-width space, soft hyphen, word joiner, BOM, tags, direction controls | `invisible.remove_format_characters`, called in each reader and again in `readers.read` | Removed; count in coverage `format_characters` (status `excluded`). |
| Joiners, direction marks, other default-ignorables (`unseen.py`) | same | Kept, except between two ASCII letters/digits (joiners, ignorables) and inside an ASCII number (marks too, e.g. `9\u061c0`). |
| DOCX run hidden by its own `w:vanish`/`w:specVanish` | `readers._hidden_by` | Left out; `hidden_runs`. |
| DOCX run hidden through a character/paragraph style or the document default | same | Left out; `style_hidden_text`. `w:webHidden` is read. |
| DOCX run drawn white on nothing shaded, or at 1 pt or less | `readers._invisible` | Left out; white text becomes one space. Counted as `invisible_text`. |
| DOCX field instructions, the non-chosen `mc:AlternateContent` branch, ignorable-namespace elements | `word_display.Fields`, `Compatibility` | Not read. If field marks do not balance, all field text is read and `fields` is `unknown`. |
| PDF text in render mode 3 or 7, white on nothing painted, 1 pt or less, off the page | `pdf_layout._Walk._hidden` | Left out; `invisible_text` with a breakdown by reason. |
| PDF invisible or white text over an image (an OCR layer) | same | Read; counted as `image_text` (`partial`). |
| PDF rotated text | `pdf_layout.page_text` | Not read; `rotated_text`. |
| PDF digit, currency sign or % whose ToUnicode differs from the glyph name, in a non-embedded font | `pdf_layout._Walk._check_text_layer` | Read as U+FFFD; `text_layer`. |
| PDF text in a font pypdf cannot interpret | `pdf_layout.page_text` | Not read; `unreadable_fonts`. |
| File names | `ingest/__init__.py:base_name` | Control and format characters removed; a name that draws nothing becomes `document.<ext>` or `document`. |

`unseen.py` is the one definition of the joiners, marks and ignorables. `invisible.py` imports it; so do
`policy/durations.py` and `memo/visible.py`. The verifier keeps its own written-out copy
(`verify/spans.IGNORABLE_RANGES`), and `tests/test_import_contracts.py` holds `IGNORABLE_RANGES` to be a superset of `unseen.py`'s characters.

#### 4.2.4 Building sections (`ingest/sections.py:build_sections`, line 618)

1. **Running lines.** `running_lines(blocks, title)` finds heading blocks that are page furniture: a heading with a
   page number rising at least 3 times in a row ("Page 3", or words the document also prints unnumbered), plus
   `page_furniture` (PDF only: a heading printed identically on at least 3 pages and on most pages). They become text
   blocks where they stand.
2. **Preamble.** The first section starts with number `""` and heading = the reading's title.
3. **Each heading** closes the current section (`_push`) and opens a new one:
   - `split_heading` takes a stated number: `HEADING_NUMBER` = optional "Section/Clause/Article", digits with dots,
     optional `.` or `)`, then the title.
   - `split_lead_in` labels it. A definition ('"Agreement" means ...', via `terms.defined_at_start`) is labelled by its
     term and the whole sentence is body. A short lead-in title (at most 60 characters and 8 words) before a full stop
     or colon is the label and the rest is body. A short non-sentence line (at most 110 characters) is the label with
     no body. Anything else gets its first 8 words plus "…" as label and all of it as body.
   - Number: a stated number wins; else the Word-printed number (`Block.word_number`); else none. The code can still
     compute a number from levels (`number_computed=True`) when `Block.implicit_number` is True, but no v17 reader
     makes such a heading (`readers.py:984, 1396, 1437, 1444` all pass `implicit_number=False`).
   - A level-2+ heading whose label ends "…" and sits inside its parent's number takes the parent's label (a list item
     styled as a heading).
4. **Text blocks** append as paragraphs. `ParsedSection.text` joins paragraphs with `"\n\n"` (`PARAGRAPH_SEPARATOR`).
5. **Size splits** (`_push`, line 677). A section over `MAX_SECTION_CHARS` (6000) is split at paragraph boundaries into
   parts headed `"<heading> (part N)"` with `part = N`. A single paragraph over 6000 is cut by `split_paragraph`.
   A section that needed only one part keeps its heading and `part = 0`.
6. **Passage-end cuts** (`split_paragraph`, `_cut`). The cut is the last passage end (`.!?;` plus closing quotes, or CJK
   stops) between a quarter of the cap and the cap; else the first one within half a cap past it; else the last space
   inside the cap; else the first space past it; else no cut and the rest stays whole. Every candidate must pass the
   verifier's own edge test, `verify.spans.bounded`: no edge inside a word or a written number. So a part can exceed
   6000 characters.
7. Sections with neither paragraphs nor heading are dropped.

`sections.py` also holds the passage-labelling helpers used after reading: `clause_openings`, `stated_clause_numbers`,
`clause_label`, `clause_label_in` (callers: `application/clause_location.py`, `runs/links.py`, `runs/relations.py`,
`runs/service.py`).

#### 4.2.5 Coverage report (`ingest/coverage.py`)

Each reading lists every part it accounts for, with a status, a count and a note. The interface shows parts with status
`omitted` and a count above 0 as "Not read by this reading: headers (5), footers (3)"
(`src/components/workbench/workspace/DocumentPane.tsx:notRead`; `application/explain_run.py:94` builds the same list).
Probe, `cloud-service-agreement.docx`: `headers omitted 5`, `footers omitted 3`, `tables read 7`.

- DOCX: the 17 fixed parts in `PARTS` order except `format_characters`, then `tracked_changes_total` when any, then
  `format_characters` (added by `readers.read`), then extra parts (`text_boxes`, `symbols`, `bound_controls`,
  `invisible_text`, `other_content`) only when present. Headers, footers, footnotes, endnotes, comments, embedded
  objects and `altChunk` content are `omitted`.
- PDF: `main_body` (count = pages), `tables` (`partial`), `headers`/`footers` (`omitted` with the lines named, or
  `unknown`), `footnotes` (`unknown`), `scanned_pages`, `embedded_objects`, then `columns`, `invisible_text`,
  `image_text`, `rotated_text`, `text_layer`, `unreadable_fonts`, `annotations` when present, then `format_characters`.
- TXT: `main_body` (note names the encoding), then `format_characters`.

`coverage_report(parts, reader_version, source)` wraps the list for storage. It is stored as `Document.coverage_json` at
upload with `source="persisted"`.

#### 4.2.6 Names

`base_name` (line 128): take the last path component (both slash kinds), drop control characters, remove format
characters, strip. If the stem draws nothing and the extension is supported, the name is `document.<ext>`. If nothing
draws, `document`. Over 255 characters (`MAX_NAME`), the stem is cut and a supported extension kept.

The stored `Document.name` is **not** the uploader's name when a workspace uploads: it is `document.docx`/`.pdf`/`.txt`
(`ingest_document.py:152`). The uploader's name lives on its `DocumentAccess.name`. Only uploads with no workspace
(batch, goldens) store the file's own name. `document_names.py` decides which name each workspace sees.

#### 4.2.7 Defined terms (`ingest/terms.py`)

`DEFINES` matches a quoted term (straight, curly, single, guillemets, low-9 quotes; at most 60 characters), up to three
words, then a defining verb ("means", "shall mean", "has/have the meaning", "is to", "are to", "refers to",
"includes"). `term_of` rejects words of construction (`CONSTRUCTION`: "including", "to", "herein", ...), terms with no
letter, and a lower-case term the definition quotes again. The reader uses it only to label a heading that is a
definition (`split_lead_in`). No terms table is written. `runs/links.py` (retrieval) and `families/fingerprint.py` call
`definitions` on stored section text.

#### 4.2.8 What is stored

| Table / place | Written by | Content |
|---|---|---|
| `documents` | `ingest_document` | One row per (sha256, reader version); unique index `ux_documents_sha256_parser` (`models.py:99`). |
| `sections` | `ingest_document` (cascade with the document) | One row per `ParsedSection`, `ordinal` = position. |
| `document_access` | `workspace.grant_document`, via `ingest_document.store` / `_grant` | (workspace, document) grant with the uploader's file name. A document with no grant is curated (readable by all). |
| `<data_dir>/documents/<sha256><ext>` | `keep_original` → `write_durable` | The original bytes. Extension from the media type (`document_suffix`). Older files may sit under a legacy name (`original_path`). |
| `document_versions` | `application/versions.py:declare_supersedes` (separate route) | A workspace's statement that one document supersedes another. Not written at upload. |

### 4.3 File by file

| File | Job | Key names | Called by |
|---|---|---|---|
| `backend/app/ingest/__init__.py` | The reader's front door: run a reader, build sections, enforce output bounds; declares the reader version and its history. | `PARSER_VERSION = "v17"` (113); `MAX_SECTIONS`, `MAX_TEXT_CHARS` (22-23); `MAX_NAME = 255`; `Ingested` (dataclass, 116); `base_name(filename)` (128); `ingest(filename, data) -> Ingested` (150); re-exports `SUPPORTED`, `TooLargeToRead`, `UnsupportedFile`. | `bounded.py` (child), `ingest_document.py`, `trust_run.py`, `evidence_pack.py` (`base_name`), `families/service.py`, `goldens/service.py`, tests. |
| `backend/app/ingest/bounded.py` | Runs `ingest` in a child process bounded by memory and time, at most two at once; owns the handoff folder. | `read_file` (88); `ingest_bounded` (134); `ReadingBusy`; `READ_SECONDS`, `READ_MEMORY_BYTES`, `READINGS_AT_ONCE`, `READ_IN_CHILD`, `HANDOFF_DIR`, `HANDOFF_PREFIX`; `handoff_folder`, `use_handoff_dir`, `release_handoff_dir`. | `ingest_document.py`, `trust_run.py`, `main.py` (lifespan), `retention.py` (sweep), `api/documents.py` (`READINGS_AT_ONCE`). |
| `backend/app/ingest/readers.py` | The three format readers and the type check; DOCX numbering, styles, hiding; lines-to-blocks for PDF/TXT. | `SUPPORTED`, `SUFFIX_OF`; `UnsupportedFile`, `TooLargeToRead` (subclass, 932); `ReadResult` (87); `content_type`, `file_type`, `read` (136); `read_docx` (945), `read_pdf` (1218), `read_txt` (1322); `decode_text`, `shorten_title`, `accepted_text`; `MAX_DOCX_UNPACKED_BYTES`, `MAX_PDF_PAGES`, `MAX_TITLE_CHARS`. | `ingest/__init__.py`, `ingest_document.py` (`file_type`, `read`, `SUFFIX_OF`), `api/documents.py`, `retention.py` (`SUFFIX_OF`). |
| `backend/app/ingest/pdf_layout.py` | A PDF page's text from its own drawing operators, in reading order, with columns and invisible text handled; lines laid out by pypdf's fixed-width code. | `page_text(page) -> PageText` (619); `PageText` (93); `render`, `char_width`; constants `TINY_POINTS`, `MIN_GUTTER_LINES`, `MIN_GUTTER_HEIGHTS`, `MIN_PROSE_WORDS`, `GUARDED`. | `readers.read_pdf`; `coverage.PdfTally` (type only). |
| `backend/app/ingest/word_display.py` | What Word displays where a plain `w:t` walk is wrong: markup compatibility, fields and legacy form fields, symbol fonts, data-bound controls. Reads no file. | `Compatibility` (88), `Fields` (179), `fields_balance` (209), `form_display`, `symbol_font`, `symbol_text`, `in_symbol_font`, `Bindings` (336), `WORD_NAMESPACES`, `REPLACEMENT`. | `readers.py` only. |
| `backend/app/ingest/sections.py` | Blocks to numbered sections; heading tests; running headers/footers; size splits at passage ends; clause-label helpers used later. | `Block` (266), `ParsedSection` (282), `build_sections` (618), `split_heading`, `split_lead_in`, `looks_like_heading` (781), `split_paragraph` (713), `page_edge_furniture` (562), `running_lines`, `page_furniture`; `HEADING_NUMBER`, `MAX_SECTION_CHARS = 6000`, `PARAGRAPH_SEPARATOR`, `PART_HEADING`, `part_heading`; `clause_openings`, `stated_clause_numbers`, `clause_label`, `clause_label_in`. | `ingest/__init__.py`, `readers.py`, `application/clause_location.py`, `runs/links.py`, `runs/relations.py`, `runs/service.py`. |
| `backend/app/ingest/coverage.py` | The coverage model and its per-format builders. | `PARTS` (18 names, 25); `Status` (47); `PartCoverage` (58); `COVERAGE_SCHEMA_VERSION = 1`; `coverage_report` (71); `docx_coverage`, `docx_more_coverage`, `DocxWalkCounts`; `pdf_coverage`, `PdfTally`; `txt_coverage`. | `readers.py`, `ingest/__init__.py`, `ingest_document.py` (`coverage_report`). |
| `backend/app/ingest/invisible.py` | Removes invisible format characters and says whether text shows anything. | `remove_format_characters(text) -> (text, removed)` (48), `visible_text` (56), `has_visible_text` (77), `INSIDE_NUMBERS`; re-exports `IGNORABLE`, `JOINERS`, `MARKS`. | Every reader, `base_name`, `application/review_finding.py`, `save_guidance.py`, `start_run.py`, `visible_input.py`. |
| `backend/app/ingest/terms.py` | The one reader of where a contract defines a term. | `QUOTED`, `DEFINES`, `CONSTRUCTION`, `OPENING_QUOTE`, `term_of`, `definitions`, `defined_at_start`. | `sections.split_lead_in`, `runs/links.py`, `families/fingerprint.py`. |
| `backend/app/application/ingest_document.py` | The upload use case: checks, dedupe, bounded read, rows, durable original, grant, race handling; also where an original lives and how coverage is served. | `ingest_document` (114), `IngestedDocument`, `MAX_UPLOAD_BYTES`, `READINGS_BUSY`, `STORE_BUSY`, `stored_document`, `coverage_of` (72), `original_path`, `reading_name`, `document_suffix`, `keep_original`, `write_durable`, `refuse_if_too_large`, `refuse_unsupported_type`. | `api/documents.py`, `api/body_limit.py` (`MAX_UPLOAD_BYTES`), `batch/service.py`, `goldens/service.py`, `evidence_pack.py`, `explain_run.py`, `trust_run.py`. |
| `backend/app/application/versions.py` | A workspace says document B is the version after A; read the line back. Append-only, per workspace. Unrelated to the reader version. | `declare_supersedes` (36) → `Declared`; `lineage` (83); `is_later_version` (93). | `api/trust.py` (`POST /api/documents/{id}/supersedes`, `GET /api/documents/{id}/versions`), `trust_run.py` (`is_later_version`). |
| `backend/app/document_names.py` | Which name a workspace sees, and which name the model is given, for a shared stored reading. | `UNNAMED`, `display_name`, `display_created`, `prompt_name`, `legacy_prompt_name`, `stored_name_is_a_workspaces`, `run_document_name`, `run_prompt_name`, `run_legacy_prompt_name`. | `api/documents.py`, `api/runs.py`, `api/findings.py`, `api/trust.py`, `evidence_pack.py`, `explain_run.py`, `memo/service.py`, `batch/service.py`, `reconstruct_input.py`, `runs/service.py`. |
| `backend/app/unseen.py` | The single definition of characters a reader does not see but keeps: joiners, direction marks, non-Cf default-ignorables (a regex class body). Sits in the bottom layer. | `JOINERS`, `MARKS`, `IGNORABLE`. | `ingest/invisible.py`, `policy/durations.py`, `memo/visible.py`. |
| `backend/app/hashing.py` | The only module that imports `hashlib`; all identity hashing. | `sha256_bytes`, `sha256_text`, `sha256_file`, `mac_sha256`, `fingerprint(kind, *parts)`, `ALGORITHM`. | `ingest/__init__.py` (document sha256), `bounded.py` (handoff name), `ingest_document.py`, and many others (runs, memo, packs, access). |
| `public/samples/cloud-service-agreement.docx` | The standard sample: Common Paper Cloud Service Agreement v2.1, CC BY 4.0, unmodified. 135,097 bytes, sha256 `cb72dad74b3af676…`. Probe: 11 pages, 123 sections, 3 size-split parts. | n/a | `src/components/workbench/samples.ts`, `backend/app/goldens/set.json` (sha prefix pinned), `tests/test_file_types.py`, `test_reader_boundary.py`, `test_reading_cost.py`, `test_data_audit.py`, scripts. |
| `public/samples/cloud-service-agreement-revised.docx` | The prepared revision for the revision check: one change, §5.3(a) cure period 30 → 10 days. 127,936 bytes, sha256 `dfc76c11ab508223…`. Probe: the only section that differs is `5.3(a)`. | n/a | `src/components/workbench/assistant/RevisionCheck.tsx` (`SAMPLE_REVISION`). No backend test reads it (grep). |
| `public/samples/linen-services-agreement-amended.pdf` | The amended sample: synthetic, fictional parties; Amendment No. 1 replaces clause 7.2. 32,098 bytes, sha256 `4139089d7849ae7d…`. Probe: 4 pages, 16 sections, 4 footer lines left out. | n/a | `samples.ts` (with three questions), `tests/test_amended_sample.py`, `tests/test_identifier_values.py`. |

### 4.4 Data it produces

**`Block`** (`sections.py:266`), reader output, not stored.

| Field | Meaning |
|---|---|
| `kind` | `"heading"` or `"text"`. |
| `text` | The block's text, format characters removed. |
| `level` | Heading level from 1; 0 for text. |
| `implicit_number` | Whether a number may be computed from levels. All v17 headings: False. |
| `word_number` | DOCX: the clause number Word prints, when exact; else None. |
| `page` | PDF: 0-based page of the first line; None otherwise. |

**`ReadResult`** (`readers.py:87`): `blocks`, `pages` (int or None; TXT None), `title`, `tracked_changes` (DOCX),
`hidden_runs` (DOCX: own-hidden + style-hidden, `readers.py:1183`), `coverage` (list of `PartCoverage`),
`format_characters` (count removed), `more_coverage` (extra parts, appended by `read`).

**`ParsedSection`** (`sections.py:282`).

| Field | Meaning |
|---|---|
| `number` | A number the document shows ("12.4", "5.3(a)") or `""`. |
| `heading` | Label: title, defined term, first words + "…", or the reading's title for the preamble. Ends " (part N)" on a size split. |
| `paragraphs` | List of paragraph strings; `.text` joins them with `"\n\n"`. |
| `number_computed` | True only when computed from levels. Not stored. |
| `part` | 1..n for a size split; 0 otherwise (reader v17). |

**`Ingested`** (`ingest/__init__.py:116`): `name` (base_name), `media_type`, `sha256` (of the raw bytes), `pages`,
`sections`, `tracked_changes`, `hidden_runs`, `coverage`. It crosses the process boundary by pickle.

**`documents` row** (`models.py:95`): `id`, `name` (`document.<ext>` for workspace uploads), `media_type`, `sha256`,
`pages`, `parse_ms`, `parser_version` (NULL = the first reader), `tracked_changes`, `hidden_runs`, `coverage_json`
(NULL before 2026-09-29), `created_at`, `size_bytes` (NULL before 2026-10-30).

**`sections` row** (`models.py:123`): `id`, `document_id`, `ordinal`, `number` (String 32), `heading` (String 512),
`text`, `part` (NULL for readings stored before v17; rows are never back-filled).

**Coverage record** (`coverage_report`, stored as JSON, served as `DocumentOut.coverage`):

```json
{
  "schema_version": 1,
  "reader_version": "v17",
  "source": "persisted",
  "parts": [
    {"part": "main_body", "status": "read", "count": 0, "note": "paragraphs and tables of the body, in document order"},
    {"part": "headers", "status": "omitted", "count": 5, "note": "header text is not read"}
  ]
}
```

`status` is one of `read`, `accepted` (tracked insertions kept), `excluded` (left out on purpose, counted), `partial`,
`omitted` (present, not read), `absent` (the file has none), `unknown` (the reader cannot tell). `source` is
`reconstructed` when `coverage_of` rebuilt it from the stored bytes for a current-reader row with no stored coverage.
`coverage_of` returns None when there is no stored coverage and the row is from an older reader or its bytes are gone.

**API shape** (`schemas.py`): `SectionOut {id, number, heading, text, part}`; `DocumentOut {id, name, pages, sha256,
parse_ms, parser_version, tracked_changes, hidden_runs, coverage, created_at, sections, reused}`.

**`document_access` row**: `workspace_id`, `document_id`, `created_at`, `name` (NULL on grants before 2026-10-09).
**`document_versions` row**: `id`, `workspace_id`, `lineage_id`, `document_id`, `supersedes_document_id` (NULL for the
first of a line), `created_at`; unique per (workspace, document).

### 4.5 Versions

#### 4.5.1 The reader version

`PARSER_VERSION = "v17"` (`ingest/__init__.py:113`). It is stored on every document (`documents.parser_version`) and
shown in the API, the run record, the trust manifest and the evidence pack. The comment block above it (lines 25-112)
is the reader's history: what each version changed and what was measured on the corpus.

| Version | Change (short) |
|---|---|
| (null) | python-docx `paragraph.text`. |
| v2-v4 | DOCX accepted view; headings from styles and outline levels; definitions labelled by term; short lead-ins only. |
| v5 | Content controls and nested tables; UTF-16/Windows-1252 text; walls of text split; textless PDF pages counted. |
| v6 | Style-hidden text left out. |
| v7-v8 | TXT/PDF: only stated numbers; numbers that do not continue the numbering are text; lower-case numbered lines are body. Bytes must agree with the type. |
| v9-v10 | Invisible format characters and ignorables removed and counted. |
| v11-v12 | Running headers/footers and page furniture are never headings. |
| v13-v14 | DOCX: a heading carries the number Word prints, or none. |
| v15 | Attachment lines are headings; PDF page-edge furniture left out and counted. |
| v16 | Splits only at passage ends; output bounds; DOCX as Word displays it (`word_display.py`); table grid slots; capitals lines judged on words; PDF read by position (`pdf_layout.py`). |
| v17 | One defined-term reader (`terms.py`); `ParsedSection.part` recorded. |

What a bump means:
- Documents are keyed by (sha256, reader version). After a bump, an upload of bytes read before is **read again** and
  stored as a new row. The old row and its runs stay as they were; rows are immutable.
- `trust_run.py` compares a run's document reader with today's (`runs/versions.compare_version`). For an earlier reader
  it re-reads the original (`current_reading`) to show what changed. `compare_version` reads `v<number>`; any other
  form is "unknown". Keep the form `v<N>` and only count up.
- `goldens/service.py` and `families/service.py` look documents up by the current `PARSER_VERSION`. The goldens runner
  ingests its sample under the current reader (`goldens/set.json`, `document.note`).
- `coverage_of` returns None for older-reader rows that never stored coverage.

#### 4.5.2 The fingerprint test

`backend/tests/test_semantic_versions.py` holds each version to its code. The reader's entry point is
`("ingest/__init__.py", "ingest")`. The test follows every function, class and assignment `ingest` reaches inside
`app/` (the closure), fingerprints its syntax tree without docstrings or comments, and compares with
`RECORDED["reader v17"] = "3a4543713ac44436"` (line 192). Probe: the closure is `ingest/__init__.py`, `readers.py`,
`sections.py`, `pdf_layout.py`, `word_display.py`, `coverage.py`, `invisible.py`, `terms.py`, `unseen.py`,
`hashing.sha256_bytes`, and parts of `verify/spans.py` and `verify/tokens.py` (reached through `split_paragraph` →
`spans.bounded`). Not in it: `bounded.py`, `ingest_document.py`, `versions.py`, `document_names.py`, and
`sections.clause_label`/`clause_label_in`.

When the test fails, decide by hand:
- the reading changed → bump `PARSER_VERSION` and **add** `"reader v18": "<new fingerprint>"` (never remove v17);
- nothing a reading produces changed (a rename, a refactor) → replace the v17 fingerprint.
  Coverage note strings are code in the closure, not docstrings: rewording one moves the fingerprint, and also changes
  the stored coverage of new readings.

Shared code moves several fingerprints at once (probe):
- `sections.py`: `HEADING_NUMBER`, `CLAUSE_TITLE`, `continues_numbering`, `inline_clause`, `clause_openings`,
  `stated_clause_numbers` and their constants are also in the **policy** and **retrieval** closures.
- `terms.py` is in the reader and **retrieval** closures.
- `unseen.IGNORABLE` is in the reader and **policy** closures.
- `document_names.run_prompt_name` and what it reaches (`display_name`, `prompt_name`, `UNNAMED`, ...) are in the
  **input** closure (`input-v1`).
- `verify/spans.py` and `verify/tokens.py` changes move the reader fingerprint as well as the verifier's.

Also on a bump: `docs/STATUS.md:177` must say "reader \`v18\`" (`tests/test_docs_claims.py`), and the history comment
above `PARSER_VERSION` gets a new paragraph with what was measured.

#### 4.5.3 Document versions (lineage) are a different thing

`application/versions.py` records a person's statement that document B supersedes A in one workspace. Rules: both
documents readable by the workspace; not itself; a document has at most one place in one line; repeating the same
statement returns it (200); a different statement about a placed document is `Conflict` (409), which also prevents
cycles. Writes go through `quotas.admit(workspace_open)` under the write lock, retried once on `IntegrityError`.
`is_later_version` walks `supersedes_document_id` upward.

### 4.6 Invariants and gotchas

1. **One document = its bytes + one reader.** Never key a document by name. The type check runs before the dedupe
   lookup, so a known PDF under a `.txt` name is refused, not handed back (`ingest_document.py:104-111`).
2. **What a reader cannot see is left out and counted.** Any new skip must add a count and a coverage part. A part the
   reader does not read must never be reported `read`.
3. **No number the document does not show.** Stated numbers, or Word's printed number when exact, or none. Do not
   reintroduce level-computed numbers.
4. **Parts are cut only at passage ends** and never inside a word or written number (`verify.spans.bounded`). So a
   part may run past 6000 characters, and a paragraph with no cut place stays whole (as "X (part 1)", `part=1`, when
   it alone exceeds the cap).
5. **`part` is data, not heading text.** A document may write "Recitals (part 2)" itself. New code should read
   `Section.part` (NULL = pre-v17; then `_earlier_parts` reads headings strictly). Observed outside this slice:
   `runs/service.py:_part_of` still matches the `" (part N)"` text (`PART_HEADING`), not `part`. Whether that matters
   there is not verified.
6. **`unseen.py` is the single definition** of kept-but-unseen characters. Do not copy it into `ingest`, `policy` or
   `memo`. If you change it, change `verify/spans.IGNORABLE_RANGES` to match (`test_import_contracts.py`).
7. **Only `hashing.py` imports `hashlib`** (`tests/test_hashing.py` scans `app/`).
8. **pypdf private API.** `pdf_layout.py` imports pypdf internals (`_text_extraction._layout_mode`, `page._layout_mode_fonts()`,
   `Font`). Lines 54-57: `from pypdf.generic._font import Font` (6.21+) with fallback `from pypdf._font import Font`
   (6.19). `requirements.lock` pins `pypdf==6.21.2`; `requirements.txt` is unpinned. An environment with 6.19.0 also
   reads the samples (probed). Keep both import paths; test any pypdf upgrade with the PDF tests. The text-layer check reads `font.encoding` because 6.21 removed `_decoded_value`.
9. **`TooLargeToRead` subclasses `UnsupportedFile`.** Catch it first, or a bound becomes a 422 "unreadable" and, in
   `trust_run`, a cached "unreadable" instead of "try later".
10. **No file content in logs.** `readers._read_as` logs only the exception class; the child silences all output.
    `tests/test_reader_logs.py` holds this.
11. **The child returns by pickle.** Anything added to `Ingested`, `ParsedSection` or `PartCoverage` must pickle.
    `bounded.py` bounds resources, not trust: the child inherits the API's environment.
12. **Tests read in-process.** `conftest.py` sets `READ_IN_CHILD = False`. Only `tests/test_reading_cost.py` exercises
    the child. A change that only breaks under spawn/forkserver (an import side effect, an unpicklable field) passes
    most tests.
13. **Windows file handling.** `write_durable` writes `<name>.<8 hex>.part`, fsyncs through an `r+b` handle (Windows
    flushes only through a writable handle), retries `os.replace` five times on `PermissionError`, accepts a file
    already holding the same bytes, else `Busy`. The folder fsync is POSIX only. `ingest_bounded` may fail to unlink
    the handoff file while the child still holds it (logged, swept later). `use_handoff_dir` checks folder ownership
    only where `os.getuid` exists. A Windows child that died before taking its pipe end leaves the pipe open, hence
    `answers.poll()` before `recv()`.
14. **The bytes are on disk before the row**, and the grant is in the same transaction as the row
    (`test_upload_atomicity.py`, `test_upload_race.py`). A damaged original is rewritten by the next upload of the same
    bytes (`keep_original` checks the hash, not just the name).
15. **`coverage_of` reconstruction runs in-process** (`readers.read`, not `bounded.py`), but only for a current-reader
    row with NULL `coverage_json`, which `ingest_document` never writes.
16. **Two concurrency limits stack.** `api/documents.py` has its own `CapacityLimiter(2)` and per-network lock;
    `bounded._slots` is the global one, shared with trust re-reads.
17. **A stale coverage note.** DOCX `automatic_numbering` says "headings are numbered from their outline level". Since
    v14 headings carry Word's printed number. Changing the note moves the reader fingerprint.
18. **Layers.** `app.ingest` is in the services layer (`.importlinter`): it may import `verify`, `hashing`, `unseen`;
    never `application`, `runs`, `policy` or `api`.
19. **Line endings.** All slice `.py` files are LF (`.gitattributes`: `* text=auto eol=lf`). Samples are binary;
    changing a byte changes its sha256, which `goldens/set.json` pins by prefix.

### 4.7 How to make common changes safely

Run the backend tests from `backend/` (section 9 gives the commands). The tests for this slice:

| Area | Tests (`backend/tests/`) |
|---|---|
| Upload use case, rows, races, files | `test_api_flow.py`, `test_uniqueness.py`, `test_upload_atomicity.py`, `test_upload_race.py`, `test_store_files.py`, `test_retention_files.py` (handoff sweep) |
| Type and damaged-file refusals | `test_file_types.py`, `test_reader_boundary.py`, `test_hostile_packages.py`, `test_reader_sweep.py` |
| Bounds and the child | `test_reading_cost.py`, `test_reader_v16_bounds.py`, `test_reader_logs.py` |
| DOCX | `test_ingest.py`, `test_hidden_styles.py`, `test_docx_numbering.py`, `test_reader_typed_headings.py`, `test_reader_study_fixes.py`, `test_reader_v16_docx.py` |
| PDF | `test_pdf_ingest.py`, `test_reader_v15.py`, `test_reader_v16_pdf.py`, `test_running_lines.py` |
| Sections, numbers, headings | `test_sections.py`, `test_section_numbers.py`, `test_reader_v16_headings.py`, `test_reader_references.py`, `test_clause_location.py` |
| Splits and parts | `test_reader_v16_bounds.py`, `test_reader_v17_parts.py`, `test_part_edges.py` |
| Coverage | `test_coverage.py`, `test_docs_claims.py` (part count) |
| Invisible text, names | `test_invisible_characters.py`, `test_reader_names.py`, `test_long_names.py`, `test_visible_input.py`, `test_import_contracts.py` |
| Defined terms | `test_defined_terms.py` |
| Names per workspace | `test_document_names.py`, `test_name_leaks.py` |
| Document versions | `test_version_statements.py`, `test_trust.py` |
| Hashing | `test_hashing.py` |
| Samples | `test_amended_sample.py`, `test_identifier_values.py`, `test_goldens.py`, `test_data_audit.py` |
| Version honesty | `test_semantic_versions.py`, `test_docs_claims.py` |

**Support a new file type.**
1. `readers.py`: add the suffix and media type to `SUPPORTED` (`SUFFIX_OF` follows). Teach `content_type`/`file_type`
   the new signature; note that `.txt` currently means "neither PDF nor zip". Add an `UNREADABLE` message. Dispatch in
   `_read_as`. Write `read_<type>` returning `ReadResult` with blocks, title, pages and a coverage list starting with
   `main_body`. Call `remove_format_characters` where text is first read.
2. Update the refusal text "upload .docx, .pdf or .txt" in `file_type`, the interface's `accept=` lists
   (`src/components/workbench/Workbench.tsx:642`, `RevisionCheck.tsx:300`), and any doc that lists types.
3. Tests: add fixtures to `test_file_types.py`, `test_reader_boundary.py` (damaged bytes never a 500),
   `test_hostile_packages.py`, `test_reading_cost.py` (child equals in-process), `test_coverage.py`.
4. Version: the fingerprint moves. The comment at `ingest/__init__.py:25-26` says bump "whenever the reader changes
   what a file's text is"; a new type changes no stored reading, so this is a judgement. The history has bumped for
   every reader change so far.

**Change how sections are split or headed.**
1. Edit `sections.py` (`_push`, `split_paragraph`, `_cut`, `split_lead_in`, `looks_like_heading`) or
   `readers._blocks_from_lines`. Keep invariants 3-5.
2. Check whether the symbol is shared with the policy or retrieval closures (4.5.2). If so, three version decisions.
3. Tests: the "Sections" and "Splits and parts" rows above, plus `test_clause_location.py`.
4. Bump `PARSER_VERSION`, add the fingerprint, update `docs/STATUS.md`, write the history paragraph with what changed
   on the corpus (the comment block's convention; the corpus is not in the repo).

**Add a coverage part.**
- A part every file of a format must report: add it to `PARTS` (fixed order; `test_coverage.py` checks the order) and
  to the builder. The count "each of eighteen parts" in `docs/STATUS.md:177` must change (`test_docs_claims.py`).
- A part reported only when present: add it to `docx_more_coverage` or the tail of `pdf_coverage`, like
  `invisible_text`. `PARTS` stays as is.
- Use `omitted` with a count for content present and not read: the interface lists exactly those as "Not read by this
  reading". Add a count to `DocxWalkCounts`/`PdfTally` and fill it where the walk meets the content.
- Bump the reader version: the stored coverage of a new reading changes.

**Change what counts as invisible.** Edit `unseen.py` (kept-but-unseen) or `invisible._format_characters` (removed).
Keep `verify/spans.IGNORABLE_RANGES` a superset (`test_import_contracts.py`). This moves the reader and policy
fingerprints. Run `test_invisible_characters.py` and `test_reader_names.py`.

**Change a reading bound.** Output bounds live in `ingest/__init__.py` (`MAX_SECTIONS`, `MAX_TEXT_CHARS`, inside the
reader fingerprint). Process bounds live in `bounded.py` (`READ_SECONDS`, `READ_MEMORY_BYTES`, `READINGS_AT_ONCE`,
outside it). `READ_SECONDS` is tied to `api/documents.py:READING_WAIT_SECONDS` (45 s) to answer within Cloudflare's
100 s. Run `test_reading_cost.py` and `test_reader_v16_bounds.py`.

**Change a sample.** Replacing `cloud-service-agreement.docx` changes its sha256: update `goldens/set.json` and expect
golden, data-audit and file-type tests to move. The revised sample must still differ in exactly the change
`RevisionCheck.tsx` describes. The amended PDF must keep 7.2 replaced in full (`test_amended_sample.py`).

## 5. Answering a question

The run pipeline: from `POST /api/runs` to findings on the page, at commit `865356b`. Paths are relative to
`backend/app/` unless they start with `backend/`, `deploy/` or `docs/`; `file.py:123` is a line at `865356b` (numbers
drift, names do not). Section 5.4 covers all forty files of `runs/`, `retrieval/`, `analysis/`, `verify/`, `policy/`,
`routing/`, `providers/` and `application/start_run.py`, `recover_runs.py`, `wake_model.py`.

The pipeline in one picture:

```
POST /api/runs                                   api/runs.py:create_run           (outside this slice)
  recover_interrupted_runs                       application/recover_runs.py
  start_run                                      application/start_run.py
    clean question, route model, identity options, fingerprint
    quotas.admit(find = active_run, write = new Run row)  -> 200 reused | 202 created
  background: _run_on_own_thread -> _worker -> execute_run       runs/service.py
    reading           sections of the stored reading
    finding_evidence  _retrieve: BM25 (+aliases) -> links -> opening fallback; relations located
    checking          build_user_message -> analyze -> AdmittedProvider -> OllamaProvider (or replay)
    verifying         per quote: verify_evidence -> locate (exact | normalized | casefold | typed)
                      per finding: decide -> check_references -> check_values -> check_conditions
                                   -> [relations] check_replaced -> check_old_value -> check_unhanded
                      across findings: settle_together
    complete | unresolved | failed               _finish -> finished_record
  every stage write -> bus.publish -> GET /api/runs/{id}/events (SSE)
```

Who owns what: the model proposes findings, quotes and a `status_hint`. Code locates every quote (verify), parses
every number it compares (policy), and sets each finding's `status` and `status_source`. A pass is never code's: it is
always recorded as the model's (`model_hint`), with code's reasons attached.

### 5.1 The life of one question

#### Step 1. The request (`api/runs.py:create_run`, line 281; outside this slice)

1. `recover_interrupted_runs(session)` first, so a dead run with the same inputs is failed before the lookup (step 14).
2. `start_run(...)` (step 2). A reused run returns HTTP 200 with `reused: true`; a new one HTTP 202, and
   `_run_on_own_thread` submits `_worker` to `RUN_EXECUTOR` (64 threads, `api/runs.py:250`), not the request pool.
3. `_worker` (`api/runs.py:253`) opens its own session, calls `execute_run(session, run_id, provider_for(run,
   provider))` and always calls `run_ended(run_id)` in `finally`. `provider_for` builds a provider for the run's own
   model when it differs from the default.

#### Step 2. `application/start_run.py:start_run` (line 143)

| Order | What happens | Where |
|---|---|---|
| a | Access. With a workspace: `require_document` / `require_guidance` (application/workspace.py). Without one (goldens, batches: "curated" runs): `session.get`, `NotFound` if absent. | 157-166 |
| b | The question is `visible_text(question).strip()` (ingest/invisible.py removes format characters). No visible character left: `InvalidInput`, no model call. | 168-174 |
| c | `load_prompt(prompt_version)`: the prompt file and its sha256. Default `settings.prompt_version` = `answer-v2` (config.py:95; `deploy/up.ps1` and `deploy/supervise.ps1` also set `answer-v2`). | 175 |
| d | `task_for(guidance is not None)` gives `clause_lookup` or `guidance_comparison`; `router().select(task, model)` picks the model (routing/router.py). | 176-177 |
| e | `now = utcnow()`: one instant for the identity and `created_at`, so the amendment starts in the identity are the ones the run is later assessed against, even across midnight. | 180 |
| f | `identity_options(session, document, decision.model, now)`: `run_options(model)` plus `latest_start_reached` when one of the document's replacement statements has a start already reached. | 119-128 |
| g | `compute_fingerprint(document.id, guidance id, question, prompt.sha256, options, workspace)`: `hashing.fingerprint("run/v1", ...)` with `json.dumps(options, sort_keys=True)`; the workspace joins only for a workspace run. | 135-140 |
| h | A `Run` row is built: `stage="reading"`, provider name, model, task, routing reason, prompt version and hash, `options_json`, document and guidance sha256, fingerprint, workspace, `owner=this_process().render()`. | 184-203 |
| i | `admit(session, run_quotas(workspace, at=now), write, find=lambda: active_run(session, key))` (application/quotas.py). `find` runs first without the lock: a repeat spends no quota. Otherwise, under the write lock: `find` again, quotas counted, then `write()`. | 216 |
| j | `write()` calls `run_started(run.id)` before `session.add(run)`, so no reader ever sees a run of this process that no worker holds. A reused run, or a failed admit, calls `run_ended(run.id)`. | 205-221 |

`run_options(model)` (line 51) is the part of identity that comes from settings:

| Key | When present | Value |
|---|---|---|
| `model`, `temperature`, `seed`, `num_ctx`, `retrieval_k` | always | settings (temperature 0.0, seed 42, num_ctx 16384, retrieval_k 6) |
| `section_window` | when `settings.section_window != 5000` (the default is 6000, so on every new run) | 6000 |
| `retrieval_aliases` | when the alias table is on (default on) | `ALIASES_SHA256[:12]` (`f10b9e3f4919` at 865356b) |
| `model_digest` | when `WORKBENCH_MODEL_DIGEST` is set | first 12 hex chars |
| `retrieval`, `embed_model` | only for a non-BM25 retriever | `hybrid`, `nomic-embed-text` |
| `policy_version`, `verifier_version`, `retrieval_version`, `input_version` | always | `SEMANTIC_VERSIONS` (section 5.5) |
| `latest_start_reached` | added by `identity_options` when a start is reached | ISO date |

`_document_starts` (line 95) caches each document's replacement starts per process (256 documents, a lock per
document so concurrent first questions read it once). `active_run(session, key)` (line 225) is the newest run with that
fingerprint whose stage is not `failed`. The store enforces the same rule with the unique index
`ux_runs_fingerprint_active` over non-failed runs (models.py, `Run.__table_args__`).

#### Step 3. `runs/service.py:execute_run` (line 368), stage `reading`

`execute_run` is wrapped in `@verification_pass()` (verify/spans.py:266): everything the verifier works out about a
text is remembered for this run only, then dropped.

1. `_set_stage(session, run, "reading", input_hash=run.document_sha256)`. `_set_stage` (line 83) checks the transition
   (`runs/transitions.py:assert_transition`), closes the previous stage row as `ok` (or `failed`) with its duration and
   commits that first, sets `run.stage`, adds the new row with `owner`, commits, logs, and publishes a `StageEvent`.
   A terminal stage is opened and closed in the same write.
2. `FrozenOptions.of(run)` (line 269) reads the run's own `options_json`, never the process settings:

| Field | From the recorded options | Refused (`StaleRun`) when |
|---|---|---|
| (versions) | `stale_versions(options)` | any of the four versions is earlier or unknown to this build |
| `aliases` | `retrieval_aliases` present | recorded alias hash differs from today's `ALIASES_SHA256[:12]` |
| `retrieval_k` | `retrieval_k` | missing |
| `retriever` | `retrieval`, default `bm25` | - |
| `embed_model` | `embed_model`, default setting | - |
| `window` | `analysis/service.py:window_of` (5000 when absent) | - |
| `decoding` | `model` (or `run.model`), `temperature`, `seed`, `num_ctx` | - |

3. `provider = bound_to(provider, frozen)` (line 355): `provider.with_options(frozen.decoding)` when the provider has
   it (Admitted, Ollama, Recording do; Replay does not). A `StaleRun` ends the run `failed` / `internal_error`, "ask again".
4. `sections = list(document.sections)` (the stored reading, in ordinal order). `_note_stage` writes the detail
   ("12 pages · 40 sections") and `output_hash = sha256("\x1f".join(section texts))`.

#### Step 4. Stage `finding_evidence`: retrieval (`runs/service.py:_retrieve`, line 289)

`_set_stage(... "finding_evidence", input_hash=sha256(question + "\x1f" + (guidance_sha256 or "")))`, then:

1. Index over `(heading, text)` pairs: `LexicalIndex`, or `HybridIndex` when the run recorded `retrieval=hybrid`.
2. `query` = the question, plus `" " + guidance` when there is guidance; `expand_query(query)` when the run recorded
   the alias table. `candidates = index.search(query, retrieval_k)`.
3. No candidate: the first `k` sections in document order, mode `opening_fallback`, no links. Otherwise ranked sections,
   then `linked(sections, ranked, window)` (runs/links.py) with `because(...)` reasons, mode `lexical_match` or
   `hybrid_match`.

**BM25 (retrieval/lexical.py).** `words(text)` folds quotation marks with the verifier's table (`_FOLD =
spans._QUOTE_MAP`), casefolds, finds `[a-z0-9]+('[a-z]+)?` and drops a possessive `'s`; `tokenize` drops 39 stopwords.
A section's corpus is `tokenize(heading) * 3 + tokenize(text)`. `search` returns, at most `k`, the sections sharing at
least one query word, by `(-score, document index)`: since retrieval-v3 a section BM25Okapi scores 0 or below still
ranks if it shares a word (a word in exactly half the sections has IDF 0); a section sharing none never ranks.

**Aliases (retrieval/aliases.py).** Seven hand-written `ALIAS_GROUPS` (non-compete, uncapped liability, cap on
liability, governing law, termination for convenience, change of control, most favoured nation). A group fires when the
query holds one of its phrases not in `WORDING` (boilerplate such as "at any time", "shall not exceed") and then appends
every token of the group not already in the query. Probe: "Is there a non-compete?" gains "competition noncompete ...
solicit"; "Can we terminate at any time?" is unchanged. `ALIASES_SHA256` hashes the groups and `WORDING`.

**Links (runs/links.py:linked, line 307).** After the ranking, the contract's own pointers are followed:

| Rule | Value |
|---|---|
| Seeds for definitions and references | the top `SEEDS = 3` ranked sections |
| Seeds for amendments | every ranked section (`_changes_of`) |
| Most links added | `MAX_LINKS = 2` |
| Priority | amendment and override 0, amended definition and definition 1, reference 2; then rank, then order found |
| Room | a link is added only while the sum of `min(len(text), window)` over handed sections stays within `len(ranked) * window` |
| Chain | a section added as a link brings its own amendments next (retrieval-v3) |

An amendment is a sentence matching `_AMENDS` whose clause or definition target is resolved by number, by a clause the
text opens, or by the nearest numbered parent; `_CHANGES` separates a change of text ("is hereby amended") from a mere
override ("Notwithstanding Section 8.2"). Definitions come from `ingest/terms.py:definitions`. A reason is recorded per
linked section, for example `the definition of "Business Day", used in §2.7`.

Back in `execute_run` (lines 383-417):

- `by_label = {"sec_{ordinal}": section for section in chosen}`. The handle is the section's document ordinal, so it is
  stable. The prompt lists sections in `chosen` order, which is rank order then links. (The comment at
  `runs/service.py:72` says "document order"; the code hands rank order. Not a behaviour bug: handles are ordinals.)
- `labels`: handle to `§number` (or the heading), used to rewrite the model's prose. `run.candidates_json` (label,
  section id, number, heading, `linked` reason) and `run.retrieval_mode` are set.
- Relations (policy-v11): `relevant(locate_relations(sections, created_at date), chosen ids)` is recorded on
  `run.relations_json` (at most `MAX_RELATIONS = 24`, those touching handed sections first).
- `_note_stage(... "finding_evidence", ...)`: "6 candidate sections and 2 the contract points to from them", plus
  `_retrieval_record`: amendments of a handed section left out for want of room (read only when both link places are
  used, `amendments_left_out`) and the alias groups that fired (`fired_alias_groups`). Opening fallback reads
  "retrieval ranked no section for this question; the opening 6 of 40 were read instead". `output_hash =
  sha256("\x1f".join(chosen ids))`.

#### Step 5. Stage `checking`: the model input (`analysis/service.py`)

`prompt = load_prompt(run.prompt_version)` (the run's version, not today's default), `window = frozen.window`, then
`build_user_message(question, guidance, run_prompt_name(run), [SectionForPrompt(label, number, heading, text)],
window=window)` (line 79). The message is plain text:

```
QUESTION: <question>

LEGAL GUIDANCE: <guidance>            (or "LEGAL GUIDANCE: none supplied")

CONTRACT: <document name as the workspace names it>

SECTIONS (cite by the id in brackets):

[sec_12] 5.1 Termination for convenience
<section text, or its first `window` characters followed by " […]">
...
```

The system message is the prompt file's text. `_set_stage(... "checking", "against guidance" | "against the
question", input_hash=sha256(prompt.sha256 + user_message))`.

#### Step 6. The provider call

`analyze(provider, prompt, user_message)` (step 7) calls `provider.generate_json(system, message, ANALYSIS_SCHEMA)`.
The provider is a stack built by `providers/__init__.py:make_provider`:

```
AdmittedProvider(workload "interactive" | "batch")       providers/admission.py
  └─ OllamaProvider                                       providers/ollama.py   (WORKBENCH_PROVIDER=ollama, default)
     | ReplayProvider(replay file)                        providers/replay.py   (=replay, browser tests)
     | RecordingProvider(OllamaProvider, replay file)     providers/replay.py   (=record)
```

**Admission** (`AdmittedProvider.generate_json`, admission.py:138). `acquire(workload)` blocks until one of
`settings.model_concurrency` slots (default 1) is free; two queues are served 4 interactive to 1 batch
(`INTERACTIVE_TURNS`) and a released slot passes straight to the next waiter. `provider.last` records the wait, service
time and queue depth; `execute_run` turns it into "queued N s behind M" and a `model_ms=... queue_ms=...` log line.

**`OllamaProvider.generate_json`** (ollama.py:386), all inside the one admission slot:

1. `payload = chat_request(system, user, schema)`: `model`, system and user messages, `format = schema` (Ollama
   constrains decoding to it), `stream: false`, `think: false`, `truncate: false`, `shift: false` (`NEVER_CUT`), and
   `options` = temperature, seed, num_ctx (the bound run's, or settings).
2. `deadline = _Deadline(timeout_s)` (600 s default): one monotonic budget for the build check, the clean start, every
   redirect hop and every byte of every reply. `_whole` reads a body chunk by chunk, cuts the connection with a timer
   at the deadline (`_cut` shuts and closes the socket), and refuses replies over `MAX_REPLY_BYTES` (8 MiB).
3. `_check_build(deadline)` when `settings.model_digest` is pinned: `GET /api/tags`, the tag's digest must start with
   the pin, else `ProviderError`.
4. `_start_clean(deadline)`: `POST /api/generate` with raw prompt `"x"`, `num_predict: 1`, the answer's own load
   settings. It leaves the server's single slot holding a prompt that shares no token with the answer, so the answer is
   computed from its first token (docs/CASEBOOK.md case 6). This holds only with `LLAMA_ARG_CACHE_RAM=0`,
   `OLLAMA_NUM_PARALLEL=1` and `WORKBENCH_MODEL_CONCURRENCY=1`.
5. `_send("POST", /api/chat, deadline, payload)`. Redirects are followed only to the same scheme, host and port, at
   most 5 hops; a 303 (Modal's wait URL) is followed with GET.
6. Reading the reply: a 400/413/500 saying the input exceeds the context is `ContextOverflow` (`_overflow`); other HTTP
   errors are `ProviderError(failed_call(...))`, plain words, never the exception's text; the reply must name the model
   asked for (`_answered_by`); `done_reason == "length"` with non-JSON content is `AnswerCut`; empty content is a
   `ProviderError`; with a pinned digest the build is checked again and a change is a `ProviderError`.
7. Returns `Generation(text, prompt_eval_count, eval_count, latency_ms from the clean start, model)`; `_heard()` stamps
   `_last_answer` for the wake-up logic.

**Replay and record** (providers/replay.py). Keyed by `request_key = sha256(system + "\n␞\n" + user)`, `ReplayProvider`
answers only from `settings.replay_file` (default `e2e/replay.json`) and fails loudly for any other request;
`RecordingProvider` passes calls to Ollama and writes each answer under its key. Browser-test markers in the message:
`[[fault:provider]]`, `[[fault:garbage]]`, `[[zzdelay]]` (8 s, removed before keying). Replayed runs are decided as live.

#### Step 7. Schema validation and one retry (`analysis/service.py:analyze`, line 105)

```
rounds = 0; message = user_message
while rounds < 2:
    rounds += 1
    generation, calls = _generate(...)        # one call; on ProviderError (not ContextOverflow) wait 2 s, call once more
    attempts += calls
    try: AnalysisOut.model_validate(json.loads(generation.text)) -> return proposal
    except JSONDecodeError | ValidationError as e:
        message = user_message + "\n\nYour previous answer was not valid (<first 800 chars of e>). Return JSON matching the schema exactly."
return AnalysisResult(proposal=None, ...)      # both rounds invalid
```

| Outcome | Run ends as | `reason` |
|---|---|---|
| Invalid twice | `failed` | `invalid_output` |
| `ProviderError` twice in a round (transport) | `failed` | `provider_error` |
| `ContextOverflow` / `AnswerCut` (not retried: the same prompt is cut the same way) | `failed` | `provider_error` |
| Any other exception | `failed`, reader told "The server failed while answering this question" | `internal_error` |

Output is never repaired. `attempts` counts model calls (at most 4); `rounds` counts validation rounds (1 or 2). When
`rounds == 2` the recorded answer replied to the corrected message, which the record does not keep: the checking
stage's `input_hash` covers the first message only, and `application/reconstruct_input.py` says so.

`execute_run` then stores `raw_output`, token counts, latency and `run.model = generation.model`, and notes the stage:
"model answered in 23 s · attempt 2 · after a rejected first answer · queued 12 s behind 3", with `attempt`, `rounds`
and `output_hash = sha256(generation.text)`.

The schema (`analysis/schema.py`, section 5.4): at most 5 findings, each with 1 to 3 evidence items and a
`status_hint`; `ANALYSIS_SCHEMA` constrains Ollama's decoding, the pydantic `AnalysisOut` validates independently.

#### Step 8. Stage `verifying`: each quote (`runs/service.py:verify_evidence`, line 153)

`_set_stage(... "verifying", input_hash=sha256(generation.text))`. If `insufficient_evidence` is true or there are no
findings: note "no passages to verify", end `unresolved`, reason `insufficient_evidence`, with the product's sentence
naming the sections searched (the model's own note stays in `raw_output`).

Facts read once per run from the whole document (lines 490-500): `printed = stated_clause_numbers(texts)`,
`clause_numbers` (section numbers plus printed), `handed` (number, heading of chosen), `week = business_week(...)`,
`days = day_convention(...)`, `parts = parts_of(sections)` when relations exist.

For each evidence item, `verify_evidence(quote, cited_label, by_label, chosen, window=window)` calls
`locate(quote, section.text, _label(section), window)` on the cited section (`_label` = "<number> <heading>"), then on
every chosen section in order (`relocated:<tier>`), else returns method `none` (section 5.3). For a verified quote,
`execute_run` also records:

| Value | Function | Used by |
|---|---|---|
| `read`: the contract's own characters at the span | `located_text(section, located)` (line 173); for an `unprefixed:` match at offset 0 the stored heading is put in front | every value and period check (policy-v17: never the model's spelling) |
| the sentence(s) around the quote | `reading_of` (joins a clause's run-on parts, line 193) then `runs/status.py:enclosing_sentences` | `decide`, `pass_blockers` |
| sections the sentence points at that were not handed | `status.unseen_references(passage, every_section, handed)` | `decide`, reason text |
| where the quote stands | `(section id, start, end)` | `unshown_conditions` |
| a condition its sentence carries outside it | `status.left_out(whole, start, end)` with `place_in(...)` | `check_conditions` |

Each item becomes an `EvidenceSpan`: `ordinal`, `section_id` (None if no stored section), `cited_section_label` (the
model's handle), `start`/`end` (-1 when unverified), the model's `quote`, `verified`, `method`, `match_count` (how many
bounded places the tier found).

A finding is "all verified" only when it has evidence and every item is verified. One unverified quote withholds the
whole finding.

#### Step 9. The policy chain, per finding (`runs/service.py`, lines 541-585)

| # | Call (runs/status.py) | Acts on | May produce |
|---|---|---|---|
| 1 | `decide(status_hint, observed, required, has guidance, all_verified, quotes=read, guidance, topic, dependencies, passages, week, days)` (line 182) | every finding | any decision (below) |
| 2 | `check_references(decision, labelled conclusion, section numbers, by_label, printed, unresolved handles from all six text fields)` (630) | a pass | `needs_review` / `reference_check` |
| 3 | `check_values(decision, labelled conclusion, read, question, guidance, clause_numbers)` (656) | a pass with quotes | `needs_review` / `position_check` |
| 4 | `check_conditions(decision, unshown_conditions(conditions, shown))` (553) | a pass | `needs_review` / `position_check` |
| 5 | only when relations were recorded: `assess(...)` (runs/relations.py:581) makes this finding's notes | - | notes |
| 6 | `check_replaced(decision, first "replaced" note)` (600) | anything but `unresolved` | `needs_review` / `position_check` |
| 7 | `check_old_value(decision, first "old_value" note)` (610) | a pass | `needs_review` / `position_check` |
| 8 | `check_unhanded(decision, unhanded_amendment(relations, quoted, chosen ids, question))` (620) | a pass | `needs_review` / `position_check` |

`decide` in order (status.py:182-334):

1. Not all verified: `unresolved` / `no_evidence`. Every later check leaves it alone.
2. The model's `observed` states a period no verified quote states (compared by value, "56 days" = "8 weeks"), when the
   quotes state a period or the hint is pass: `needs_review` / `position_check`.
3. `required` states a period the guidance does not: `needs_review` / `position_check`.
4. With guidance, a rule (`policy.durations.parse_rule`) and a period in some quote (`observed_fact`):
   - hint `missing`: stays `missing` / `model_hint`, "code compared no periods" (the quote is the closest provision).
   - any quote period whose words and digits disagree ("sixty (20) days"): `needs_review` / `ambiguous_fact`.
   - a scoped "days" convention under which the quotes meet the guidance differently: `ambiguous_fact`.
   - the quotes state several periods with different outcomes: `ambiguous_fact`.
   - `evaluate(fact, rule, week)` (durations.py:767) is `needs_review` (a shortfall): `model_hint` with the reason if
     another period the guidance's sentence states is met; `ambiguous_fact` if a negation stands beside the period;
     else `needs_review` / `computed_days` with "... ; that the quoted period and the guidance concern the same point
     is the model's reading, not code's" (`SUBJECT_IS_THE_MODELS`).
   - `evaluate` is `pass`: blockers are collected (model asked for review; the guidance states several periods not all
     met; an unread guidance period; `policy.proof.pass_blockers`; a negation). With blockers: the model's hint /
     `model_hint`, "..., but code does not confirm that as a pass: <reasons>". Without: `pass` / `model_hint`, "...;
     code found the day counts consistent, and that the quoted period and the guidance concern the same point is the
     model's reading, not code's".
   - `ambiguous`: `needs_review` / `ambiguous_fact`. `incomparable` with hint pass: `needs_review` / `position_check`.
5. Hint pass with unseen dependencies: `pass` / `model_hint`, "the sentence points at §14.3, which was not handed to the
   model" (`policy.proof.unseen_reason`).
6. Otherwise: the model's hint / `model_hint`, no reason.

`pass_blockers` (policy/proof.py:102) reads only source text: the quotes and the guidance must share at least two
concept stems per guidance period sentence (`same_point`); the quote's operator must match the rule's (a ceiling does
not meet a floor); no negation beside the period; both or neither counted back from an event; no condition word
(`CARVE_OUT`) in the quote's sentence; no other period in the sentence the quote left out; no unseen dependency.

`check_values` lowers a pass when the conclusion gives a redaction mark as its value (`values.redaction_given_as_value`),
states a value no verified quote states (`values.unquoted_values`; the guidance counts only for a comparison, the
question never, the time the question asks at counts, a dotted clause number counts as a pointer), or gives every party
one value the passages give only to some (`values.uniform_party_choices`). The reason says where each value came from.

`check_conditions` lowers a pass when a verified quote's own sentence carries a condition outside the quoted words and no
verified quote of the finding covers that condition's place. Probe: quote "Customer may terminate on 30 days' notice"
from "Except for the first sixty (60) calendar days of the Initial Term, Customer may ..." gives `needs_review` /
`position_check`, "the quote leaves out of its sentence “Except for the first sixty (60) calendar days of the Initial
Term”, and no quote of this finding shows it".

Relations (`runs/relations.py`): `locate_relations` finds two kinds of statement in the contract's own text:
`replaces` (a numbered provision is deleted, replaced, superseded, amended and restated, read as follows, deemed
changed, or a definition stated afresh in an amendment) and `precedence` (an order of precedence for a conflict).
`assess` gives each finding notes with an `effect`:

| Effect | Meaning | Status effect |
|---|---|---|
| `replaced` | a verified quote is text the contract replaced in full, the answer does not follow the replacement, and the question asks about now or names no time | `check_replaced`: `needs_review` / `position_check` |
| `old_value` | the answer quotes the replacement but states only values the replaced wording states | `check_old_value` lowers a pass; else a concern |
| `scoped` | the change is limited ("for the second Contract Year only") | concern only |
| `dated` | the question names a time ("in June 2025") | concern only |
| `precedence` | quoted passages come from parts the contract ranks | concern only |
| `context` | anything else worth showing | none |

`unhanded_amendment` returns a sentence when a verified quote lies in replaced text and the replacing statement's
section was not handed to the model (except for a historical question); `check_unhanded` lowers a pass on it.

`check_conditions`, `check_old_value`, `check_unhanded` and the every-party branch of `check_values` keep the earlier
reason after a semicolon (`_with_earlier`), so "the sentence points at §8..." is not unsaid. `check_references`,
`check_replaced` and the other `check_values` branches replace the reason with their own.

#### Step 10. Across findings (`runs/status.py:settle_together`, line 391)

A pass whose reason starts "the contract provides" gets "..., but code does not confirm that as a pass: <relation>"
when a code shortfall (`computed_days`, `ambiguous_fact`) in another finding bears on it: same section, a clause
referring to the pass's section, or quotes about the same point of the guidance. Only the reason changes.

#### Step 11. What is written

| What | Where | Content |
|---|---|---|
| Findings | `findings` rows | `ordinal`, `topic` (max 255), `conclusion`, `guidance_reference`, `observed`, `required`, `suggested_position`, each through `prose.label_handles` ("sec_12" becomes "§5.1"; a handle naming no handed section becomes "[unidentified section]"); `status`, `status_source`, `status_reason` (the decision's reason, or NULL) |
| Spans, retrieval, model | `evidence_spans`; `candidates_json`, `retrieval_mode`; `raw_output`, tokens, latency, `model` | steps 8, 4, 7 |
| Relations | `run.relations_json` | `Recorded(relations, notes by finding ordinal)`, rewritten with notes when there are any |
| End | `run.note`, `run.error`, `run.reason`, `run.finished_at`, terminal stage row | `_finish` (line 704) |

Stage rows and their hashes (the evidence pack's `verify.py` recomputes each one):

| Stage | `input_hash` | `output_hash` | Detail example |
|---|---|---|---|
| `reading` | `document_sha256` | sha256 of section texts joined by `\x1f` | "12 pages · 40 sections" |
| `finding_evidence` | sha256(question + `\x1f` + guidance sha256 or "") | sha256 of chosen section ids joined by `\x1f` | "6 candidate sections and 1 the contract points to from them" |
| `checking` | sha256(prompt sha256 + user message) | sha256(raw model text); also `attempt`, `rounds` | "model answered in 21 s" |
| `verifying` | sha256(raw model text) | sha256(JSON of every span's section, start, end, verified, method) | "3 of 4 quotes verified · 1 finding withheld" |
| `complete` / `unresolved` | `finished_record(run, stage)` | - | the run's note |
| `failed` | NULL | - | the error; `error_code` = the run reason |

`finished_record` (line 665) hashes, sorted: run id, fingerprint, document, task, provider, model, prompt version and
hash, retrieval mode, candidates, options, final stage, reason, relations, and per finding its id, ordinal, status,
source, reason, relation notes and span match counts. Reviews are not in it; runs finished before 2026-10-30 have none.

How a run ends:

| Condition | Stage | `reason` |
|---|---|---|
| At least one finding fully verified | `complete` | NULL |
| Model said insufficient evidence, no findings, or findings with zero quotes (a backstop) | `unresolved` | `insufficient_evidence` |
| Findings exist, none fully verified | `unresolved` | `citations_unverified` |
| Invalid output twice | `failed` | `invalid_output` |
| Provider failure, overflow, cut answer | `failed` | `provider_error` |
| Stale run, any other exception, recovery | `failed` | `internal_error` |

A complete run shows findings whose status is not `unresolved`; the unresolved ones are listed as `withheld`
(`api/runs.py:run_out`). Once terminal, store triggers refuse any UPDATE or DELETE of the run, its stages, findings,
spans, and the sections and document it read (`db.py:immutability_triggers`). `_fail` rolls back and refreshes first;
if another writer already ended the run, the worker leaves quietly.

#### Step 12. Events to the page

`_set_stage` and `_note_stage` call `bus.publish(StageEvent(run_id, stage, detail))` (runs/events.py: one bus per
process, thread-safe, bound to the event loop at startup). `GET /api/runs/{id}/events` (`api/runs.py:run_events`)
replays stored stage rows as SSE `stage` events with `id:` = row id (a reconnect's `Last-Event-ID` skips seen rows),
sends `queue` with `ahead`, then streams live events. Every 15 s it re-reads the record, so a run ended by another
process still ends the stream; a terminal event carries `final: true`.

#### Step 13. Routing (`routing/router.py`)

`ModelRouter.select(task, requested)`: a requested model, else `settings.routing_policy[task]`, else the default model.
The policy is empty by default, so every task uses `qwen3:8b`; the run records `task` and `routing_reason`.

#### Step 14. When no worker finishes a run (`application/recover_runs.py`)

`recover_interrupted_runs(session)` runs at startup, on every run read, before every question, and at each retention
pass. For each open run it reads the latest stage row's `owner` (or the run's own):

| Case | Action |
|---|---|
| Owner is a process on this host that provably no longer exists (`owner_is_gone`) | fail now: "the server process running the <stage> stage stopped" |
| Owner is this process and no worker holds the run (`is_working` false) | fail now: "the work on this question stopped ... before it could record how it ended" |
| Public workspace, held longer than `queue_ceiling_seconds()` = (public max in flight 8 + 1) × stale window | fail now |
| Stage older than `stale_after_seconds()` = 600 s × 4 calls + 60 s = 2,460 s, owner not alive here | fail: "no progress for N min" |
| Owner alive on this host and holding it | leave it |

`_end_as_failed` writes under the write lock only if the run is still at the stage and latest row it was seen at,
closing the open row, then the run, then adding a `failed` row (the order the triggers allow), and publishes the
`failed` event. A failed run frees its fingerprint, so the same question can be asked again.

#### Side path: waking a sleeping model (`application/wake_model.py`)

`waker.request(allow)` (from `api/model.py`) starts a background `OllamaProvider().wake()` (build check plus the clean
start) when `settings.model_wakeup` is on. It returns `off`, `awake` (a call in flight or an answer within 240 s),
`waking` or `limit` (10 a day, or the caller's bound). Off by default: the laptop's model never sleeps.

### 5.2 The status vocabulary

Finding statuses (`models.py:FindingStatusName`):

| Status | Meaning to a reader | Who can set it |
|---|---|---|
| `pass` | the model's answer, nothing code raised that lowers it | only `model_hint` today (code attaches reasons) |
| `needs_review` | a person should look | the model's hint, or any of code's checks |
| `missing` | the model did not find the point in the sections it was given; shown as "The model did not find this in the sections it was given." | only `model_hint` |
| `unresolved` | withheld: a quote was not found | only `no_evidence` |

`status_source` and the statuses each may decide (`models.py:STATUSES_BY_SOURCE`, line 38). `Decision.__post_init__`
refuses any other pair, and the store has a CHECK constraint built from the same table.

| `status_source` | Allowed statuses | Whose view | Written today by |
|---|---|---|---|
| `model_hint` | pass, needs_review, missing | the model's; code may add a reason | `decide` (pass, missing, hint, blocked pass, shortfall with alternatives), `settle_together` |
| `computed_days` | pass, needs_review | code: the quote's period falls short of the guidance's rule | `decide` (needs_review only; a `pass` here is a pre-policy-v2 record) |
| `confirmed_days` | pass | policy-v2 records only ("confirmed by code") | nothing since policy-v3 |
| `no_evidence` | unresolved | code: a quote was not found, finding withheld | `decide` |
| `reference_check` | needs_review | code: the answer names a section the document lacks, or a handle the model was not given | `check_references` |
| `position_check` | needs_review | code: the evidence shown does not establish the answer (stated period or value not in the quotes, a value from the question or the guidance, one value given to every party, a redaction mark, a left-out condition, replaced text, an incomparable pass, an unhanded amendment) | `decide`, `check_values`, `check_conditions`, `check_replaced`, `check_old_value`, `check_unhanded` |
| `ambiguous_fact` | needs_review | code: the quotes do not state one period (inconsistent words and digits, several periods with different outcomes, a negation beside a shortfall, a scoped "days" convention) | `decide` |

Model's view versus code's decision, as every surface reads it (`runs/account.py:account_of`):

| `decided_by` | When |
|---|---|
| `withheld` | status `unresolved` or source `no_evidence` |
| `code` | source in `DECIDED_BY_CODE` = computed_days, position_check, ambiguous_fact, reference_check |
| `model` | everything else (`model_hint`, and legacy `confirmed_days`) |

`concerns` collects every sentence code wrote against the status ("code does not confirm the pass: ...", an unseen
section, unquoted values, value choices, relation notes with effect in `relations.CONCERNS`). `flagged` is true for any
status other than pass, or a pass with a concern. `runs/status.py:basis` reads from the stored reason whether code
compared a period (`code_compared`) and which unseen-section sentence it wrote, in every wording any policy version used.

Other vocabularies used in the run:

| Name | Values |
|---|---|
| Run stages and reasons | step 11 tables |
| Stage row status | running, ok, failed |
| Retrieval mode | lexical_match, hybrid_match, opening_fallback |
| Span method | exact, normalized, casefold, typed; `unprefixed:<tier>`; `relocated:<method>`; none; `alnum` on records before v5 |
| Relation effect | replaced, scoped, precedence, dated, old_value, context (step 9) |

Transitions (`runs/transitions.py:ALLOWED`): created → reading → finding_evidence → checking → verifying → complete
or unresolved; any open stage → failed; checking → unresolved (older records; the executor now passes verifying).

### 5.3 The verifier in depth (`verify/spans.py`, `verify/tokens.py`)

#### What "verified" means

A quote is verified when `locate(quote, text, label, window)` returns a `Located(start, end, method, count)`: the quote
stands in the first `window` characters of a handed section, under one rung of a fixed ladder, and neither edge of the
span splits a word or a number. `start`/`end` index the original stored text, so the interface highlights the exact
characters. It says nothing about whether the quote supports the conclusion; that is the policy chain's job, and much
of it stays the model's reading.

There is no similarity tier. A 0.994 similarity ratio once hid a changed digit (DECISIONS.md, 2026-09-28).
`verification_pass` (a `ContextVar` memo) keeps per-text work (number positions, quote words, caseless text) for one
run, trust manifest, diff or `locate` call only; nothing about a visitor's text outlives the pass.

#### The ladder (`_tiers`, spans.py:379)

| Tier | Quote and text compared as | Forgives | Never forgives |
|---|---|---|---|
| (guard) | quote with no letter or digit | - | "." alone is never found (v11) |
| `exact` | substrings | nothing | - |
| `normalized` | both through `normalize_with_map`: `_QUOTE_MAP` (curly quotes to straight, en/em/minus dashes to "-", no-break space to space, default-ignorable characters deleted, v11 apostrophe folds), whitespace runs to one space | typography, spacing, invisible characters | letters, digits |
| `casefold` | normalized, then `str.casefold` with an index map (`fold_with_map`, "ß" keeps one index for "ss") | case | a clause letter's case: "(A)" is not "(a)" (v11, `_CLAUSE_LETTER`) |
| `typed` | `tokens.locate_tokens`: token sequences from `tokens.compared` | punctuation, quotation marks, dashes, "1,500" vs "1500" | a digit, precision ("15.00" vs "15"), a sign, parentheses, currency, percent, a space inside a word, a sentence end, a choice mark |

At every tier an occurrence counts only if `bounded(whole, start, end)` holds; `_find_bounded` returns the first bounded
occurrence and how many there are (`count`, stored as `match_count`). An occurrence that starts or ends inside what one
original character folded to ("ﬀ" to "ff") is rejected.

Before the ladder, `_cannot_hold` (line 358) checks that every word of the quote, in canonical caseless form, appears in
the text. It only skips work: no tier changes a letter, so a text missing a word cannot hold the quote
(`tests/test_locate_prefilter.py` holds this).

#### Edges (`bounded`, `_splits`, lines 211-260)

An edge "splits" when, reading the characters a person sees (deleted characters skipped, `_seen`):

- both neighbours belong to a run of letters and digits, where a combining mark or a joiner counts as part of the run
  (v11, `_in_run`, `tokens.marked`): "5 days" is not inside "fifteen (15) days"; "paye" is not inside a decomposed "payé";
- the joint is a digit mark between digits (`joins_digits`): "1,500|,000", "Section 5|.2", "2|/3";
- the edge falls inside a written number (`tokens.written_numbers`) at something written against it (a sign, a
  currency or percent sign, a parenthesis, a unit sign), or anywhere inside a number opened by a sign, parenthesis,
  comparator, plus or leading decimal point, or after the number's first digit. The text's start and end never split.

#### Window, labels, relocation

- **Window.** `locate(..., window=w)` searches `text[:w]` but reads every edge in the whole text (v11): "$1,500" is not
  found where the window cuts "$1,500,000". The window is the run's (`FrozenOptions.window`), the one the prompt carried.
- **Labels** (`strip_label`, line 409). If the ladder fails and the quote may carry the section's label
  (`_may_carry_label`), the label "<number> <heading>" is stripped and the ladder runs again; a hit is
  `unprefixed:<tier>`. The number counts only as written, with its dots, optionally followed by one of `. ) : ]`, then a
  space, never as the whole quote ("15 days" under §1.5 keeps its 15). The heading must be followed by a space or one of
  `.:;)]-–—` (v11), so "8 Supplier" is not stripped from "Supplier's liability". A signed number right after the
  heading keeps its sign ("Fees: -5%" leaves "-5%").
- **Relocation.** `verify_evidence` tries the cited section, then every handed section in order; a quote found
  elsewhere is kept as `relocated:<tier>`. A quote from a section the model was not handed is never verified.

#### Unicode handling

| Rule | Where | Since |
|---|---|---|
| Every Default_Ignorable_Code_Point (soft hyphen, ZWSP to RLM, bidi controls, word joiner, variation selectors, BOM, tags...) is read as absent | `IGNORABLE_RANGES`, `_QUOTE_MAP`, `_DELETED` | v11 (v10 deleted four) |
| Apostrophe forms U+02BC, U+FF07, "`", "´" fold to "'" | `QUOTE_FOLDS_V11` | v11 |
| Curly quotes, typeset dashes, minus sign, no-break space | `_QUOTE_MAP_V10` | before v11 |
| A combining mark or ZWJ/ZWNJ belongs to its word | `tokens.marked`, `whole_words` | v11 |
| Words compared by canonical caseless match, NFC(casefold(NFD(text))) | `tokens.caseless` | v11 |
| Digits joined by typeset fraction slash, ratio colon, fullwidth forms, middle dot are one number | `_JOINED`, `_DIGIT_MARKS_V11` | v11 |
| Edges and number positions read with deleted characters skipped, offsets mapped back | `_seen`, `_read_numbers`, `written_numbers(invisible=...)` | v8 on |

#### Typed tokens (`verify/tokens.py`)

`tokenize` (line 325) reads `_TOKEN`: `section` ("8.1.2", "12.4(a)"), `currency` ("$1,500", "USD 10.00"), `percent`,
`number`, `word` (letters of any script), `punct`. No token starts or ends inside a run of letters and digits (v7).
`canonical_number` keeps digits as written ("15.00" stays "15.00"); a comma is a thousands separator only in thousands
grouping ("1,5" is not 15).

`compared(text)` (line 486) is what the typed tier compares:

1. `signed(...)`: each number joined with what is written against it, read by `_WRITTEN` (v11): a minus sign (any
   typeset dash), accounting parentheses, a currency symbol or ISO 4217 code or "US$", a short label after a sign or
   inside a parenthesis ("-Ksh 5M", "(RM5M)"), a magnitude letter ("$5M", "2.5bn"), a comparator or plus sign ("≥99.9%",
   "+/-5%"), a leading decimal point (".5%"), a unit sign ("%", "‰", "°"). "2/3" and "3:1" are one value.
2. Significant tokens only (punctuation dropped).
3. `BREAK` tokens at each sentence end (`sentence_ends`: ". ! ? …" then a space and a non-lowercase letter, or a tight
   capital between lower-case letters, and every ";"), so a quote cannot join two sentences.
4. `SYMBOL` tokens for choice marks ☐ ☑ ☒ ✓ ✔ ✗ ✘ and U+FFFD, compared as written.
5. `whole_words`: words read through their marks and compared caseless; a clause letter in parentheses keeps its case.

`locate_tokens` (line 543) tries every place the quote's token sequence occurs and keeps those whose offsets are
bounded; it returns the first and the count.

Probe results at 865356b (text: "Customer may terminate on thirty (30) days’ written notice. Fees are $1,500,000 per
year, or -$5M if adjusted."):

| Quote | Result |
|---|---|
| `thirty (30) days’ written notice` | exact |
| `thirty (30) days' written notice` | normalized |
| `THIRTY (30) DAYS' WRITTEN NOTICE` | casefold |
| `terminate on thirty (30) days written notice` | typed |
| `30 days written notice` | not found (the text writes "(30)"; v8 keeps parentheses with the number) |
| `$1,500` | not found (inside "$1,500,000") |
| `$5M` | not found (inside "-$5M") |
| `.` | not found |

#### Versions kept side by side

The workbench runs only the current verifier (`tokens.VERSION = 11`, `spans.VERIFIER_VERSION = "v11"`). Older readings
stay in the code because evidence packs of runs verified under them must be checked as their verifier read them:

| Verifier | What it added | Old reading kept as |
|---|---|---|
| v5 | typed tier replaces letters-and-digits; search bounded to the window; `count` | pack `verify.py` checks `alnum` spans of older records |
| v6 | a space moved inside letters is no longer forgiven ("the rapist" is not "therapist") | pack `typed()` joins neighbouring words for records before v7 |
| v7 | no token ends inside a run of letters and digits; comma only in thousands grouping | pack `TOKEN` pattern and `number()` |
| v8 | no span begins or ends inside a number; signs and parentheses belong to the number | `tokens._WRITTEN_V8`, `_ATTACHED_V8` |
| v9 | amounts with a magnitude letter and any currency are numbers; no edge at a space inside a signed number | `tokens._WRITTEN_V9`, `_ATTACHED`, `SIGN_OPENERS` |
| v10 | a short label after a sign or inside a parenthesis is part of the number | `tokens._WRITTEN_V10`, `spans._QUOTE_MAP_V10` |
| v11 | comparators, plus, leading decimal point, "/" and ":" joins, sentence ends, choice marks, clause-letter case, combining marks and joiners, all default-ignorables, window edges read whole, label stripped only whole | `tokens._WRITTEN`, `SIGN_OPENERS_V11`, `_ATTACHED_V11`, `_QUOTE_MAP` |

`written_numbers`, `signed` and `compared` take a `version` argument (8 to 11) for these readings.

#### Why the evidence pack's `verify.py` mirrors it

Every evidence pack carries a standard-library `verify.py` built from `application/verify_template.txt` by
`application/evidence_pack.py:render_verify_py`. It must reach the workbench's verdict on another machine with no
dependencies, so the verifier's own patterns and tables are copied in as JSON string literals when the pack is built:
`_QUOTE_MAP_V10`, `IGNORABLE_RANGES`, `QUOTE_FOLDS_V11`, `_TOKEN`, `_WRITTEN_V8` to `_WRITTEN`, sign, digit-mark and
attachment sets, `_SENTENCE_END`, `_CLAUSE_LETTER`, `_CHOICE_MARKS`, `_LABEL_ENDS`, and `KNOWN_VERIFIER = 11`. It reads
the run's `options.verifier_version` and checks each span under that verifier; a version newer than it knows exits 2
("NOT CHECKED"). It also recomputes the stage hashes and `finished_record`, rebuilds the model input slices, and maps
the model's raw output to the stored findings with the same handle rules (`prose.HANDLE`). The checker hashes on its
own because only `app/hashing.py` may import `hashlib`. `tests/test_pack_parity.py` holds the two in agreement.

### 5.4 File by file

All paths under `backend/app/`. "Callers" are inside `backend/app` unless named; tests are listed in section 5.6.

#### `analysis/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `analysis/__init__.py` | Empty package marker. | - | - |
| `analysis/schema.py` | The shape the model must return, as JSON Schema for Ollama's constrained decoding and as pydantic models for independent validation. | `StatusHint`, `STATUS_HINTS`; `EvidenceOut` (section_id, quote); `FindingOut` (1-3 evidence); `AnalysisOut` (max 5 findings, `insufficient_evidence`, `note`); `ANALYSIS_SCHEMA` | `analysis/service.py`, `runs/status.py` (`StatusHint`) |
| `analysis/service.py` | Builds the user message, loads the prompt, calls the provider, validates, retries once with the error. Never repairs output. | `MAX_SECTION_CHARS_IN_PROMPT = 5000` (the window of runs that recorded none; must never move); `window_of(options)`; `PROVIDER_RETRY_DELAY_S = 2.0`; `INPUT_VERSION = "input-v1"`; `PromptPackage`; `SectionForPrompt`; `AnalysisResult` (proposal, generation, validation_error, attempts, rounds); `load_prompt`; `build_user_message`; `_generate`; `analyze` | `runs/service.py`, `application/start_run.py`, `application/reconstruct_input.py`, `reverify_run.py`, `explain_run.py`, `evidence_pack.py` (`window_of`), `goldens/`, `scripts/run_goldens.py` |
| `analysis/prompts/answer-v1.md` | System prompt v1: seven rules (verbatim quotes under 400 chars, cite `sec_N`, insufficient evidence, guidance comparison fields, no-guidance hints, topic and conclusion form, at most five findings, JSON only). | sha256 `4430d770...` | `load_prompt("answer-v1")` |
| `analysis/prompts/answer-v2.md` | v1 plus rule 8 (absence is about the sections given: "not found in the sections reviewed", hint `missing`, cite the closest provision) and rule 9 (third person). The default (`config.py:95`, `deploy/up.ps1`). The live process's environment was not inspected. | sha256 `9dbeb12a...` | default prompt |
| `analysis/prompts/answer-v3.md` | v2 plus rule 10 (do not repeat a premise the sections do not show), rule 11 ("no because nothing says so" is an absence), rule 12 (cite printed section numbers, never `sec_N`, in conclusions). Not the default. | sha256 `4a9978b2...` | opt-in |
| `analysis/prompts/answer-v4.md` | Rewrites rule 1 (include a limiting condition in the quote), rule 6 (one to three sentences: value, party, every condition; quote each condition), rule 10 (assumed premises), rule 11 (name the party as the quote does), rule 12 (redaction marks). Not the default. | sha256 `a969ffa8...` | opt-in |
| `analysis/prompts/manifest.json` | sha256 of every prompt file a run has used. A prompt is frozen once used; a change is a new file. | four entries | `tests/test_prompts_frozen.py` |

#### `application/` (three files of this slice)

| File | Job | Key names | Callers |
|---|---|---|---|
| `application/start_run.py` | Starts a run or hands back the identical running or completed run; computes identity; writes the row through quotas. | `FINGERPRINT_KIND = "run/v1"`; `StartedRun(run, created)`; `run_options`; `_document_starts` (per-process cache, 256); `identity_options`; `router`; `compute_fingerprint`; `start_run`; `active_run` | `api/runs.py:create_run`, `batch/service.py`, `goldens/replay.py`, `goldens/service.py` (`identity_options`, `compute_fingerprint`) |
| `application/recover_runs.py` | No run stays open forever and no live run is declared dead. Holds the per-process set of runs workers hold. | `MAX_MODEL_CALLS_PER_RUN = 4`; `STALE_MARGIN_S = 60`; `run_started`, `run_ended`, `is_working`; `stale_after_seconds`; `queue_ceiling_seconds`; `recover_interrupted_runs`; `_end_as_failed` | `api/runs.py`, `main.py` (startup), `application/retention.py`, `application/start_run.py` |
| `application/wake_model.py` | Wakes a hosted model that sleeps, beside the request, bounded per day. Off by default. | `WakeState` (off, awake, waking, limit); `ModelWaker.request`; `waker` | `api/model.py` |

#### `policy/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `policy/__init__.py` | Docstring only: typed legal values and the one policy code evaluates (notice periods). | - | - |
| `policy/durations.py` | Parses periods as contracts write them (digits, words, both, ranges, lists, invisible characters, typeset dashes), reads guidance rules (floor, ceiling, range, alternatives), compares, and places non-converting units on the calendar. | `DurationUnit`, `Operator`, `Duration` (`in_days`), `DurationMention` (readings, ambiguity, in_range); `NUMBER_WORDS`; `seen`, `without_unseen`; `parse_durations` (line 312); `ObservedFact`, `GuidanceRule`; `parse_rule` (635), `stated_rules`, `unread_periods`, `period_sentences`; `stated_periods` (692), `same_period`, `observed_fact`, `negation_beside`; `PolicyEvaluation`, `evaluate` (767: pass, needs_review, ambiguous, incomparable); `BusinessWeek`, `business_week`; `calendar_days` (a month 28-31 days, a year 365-366, N business days at least N + (7 - d)·⌊(N-1)/d⌋); `DayConvention`, `day_convention`, `read_as_the_contract_does`, `periods_as_the_contract_reads` | `runs/status.py`, `runs/service.py`, `runs/values.py`, `policy/proof.py`, `goldens/service.py`, `trust/facts.py` |
| `policy/proof.py` | What code must establish before it may call a comparison consistent; reads source text only, never the model's words. | `CARVE_OUT` (condition words); `concept_stems`; `same_point` (`CONCEPT_WORDS_NEEDED = 2`); `pass_blockers`; `unseen_reason` | `runs/status.py` |

#### `providers/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `providers/__init__.py` | The factory and the one admission controller per process. | `admission = AdmissionController(limit=max(1, model_concurrency))`; `_raw_provider` (ollama, replay, record); `make_provider(name, model, workload)` | `main.py` (startup provider), `api/runs.py:provider_for`, `application/wake_model.py`, `scripts/run_batch.py`, `scripts/run_goldens.py`, `scripts/measure_admission.py` |
| `providers/admission.py` | Bounds calls in flight; two queues served by weighted round robin; records waits. | `Workload`; `INTERACTIVE_TURNS = 4`; `Admission`; `AdmissionController` (`acquire`, `release`, `in_flight`, `depth`, `snapshot`; policy `weighted` or `fifo` for measurement); `AdmittedProvider` (`with_options`, `generate_json`, `last`) | `providers/__init__.py`; `snapshot` is read only by `tests/test_admission.py` |
| `providers/base.py` | The provider protocol and its errors; errors read as plain sentences. | `ProviderError`; `failed_call(what, error)`; `ContextOverflow`; `AnswerCut`; `Generation`; `ModelProvider` protocol (`generate_json`, `healthy`) | every provider, `analysis/service.py`, `runs/service.py`, `retrieval/hybrid.py` |
| `providers/ollama.py` | The live model: one deadline per call, clean start, never-cut request, refusal and cut detection, build pin, same-host redirects, wake-up, health. | `NEVER_CUT`; `MAX_REPLY_BYTES`; `SIZE_REFUSAL_STATUSES`; `_Deadline`; `_cut`, `_whole`; `_overflow`, `_answer_cut`; `last_answer`, `_heard`; `OllamaProvider` (`options`, `with_options`, `_send`, `healthy`, `describe_build`, `_check_build`, `chat_request`, `wake`, `_start_clean`, `_answered_by`, `generate_json`) | `providers/__init__.py`, `application/wake_model.py`, `main.py` (`describe_build` log line) |
| `providers/replay.py` | Record and replay of real model answers for browser tests in CI. | `SEPARATOR`; `FAULT_PROVIDER`, `FAULT_GARBAGE`, `DELAY`, `DELAY_SECONDS = 8`; `RecordedAnswer`; `request_key`; `load_answers`, `save_answers`; `ReplayProvider`; `RecordingProvider` | `providers/__init__.py` |

#### `retrieval/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `retrieval/__init__.py` | Empty package marker. | - | - |
| `retrieval/lexical.py` | BM25 over sections with the heading counted three times; text read as the verifier reads it. | `TOKEN`; `_FOLD = _QUOTE_MAP`; `STOPWORDS`; `HEADING_WEIGHT = 3`; `RETRIEVAL_VERSION = "retrieval-v3"`; `Candidate`; `words`; `tokenize`; `LexicalIndex.search` | `runs/service.py`, `retrieval/hybrid.py`, `retrieval/aliases.py`, `scripts/eval_retrieval.py` |
| `retrieval/aliases.py` | Hand-written concept groups that widen the query; versioned by hash. | `ALIAS_GROUPS` (7); `WORDING`; `ALIASES_SHA256`; `_phrase_in`; `expand_query` | `runs/service.py` (`expand_query`, `fired_alias_groups`, `FrozenOptions`), `application/start_run.py` (hash), `scripts/eval_retrieval.py` |
| `retrieval/hybrid.py` | BM25 fused with Ollama embeddings by reciprocal rank; only when a run recorded `retrieval=hybrid`. Embedding calls go straight to `httpx.post` (600 s timeout): not through admission, the call deadline or the redirect rule. | `RRF_K = 60`; `EMBED_BATCH = 64`; `QUERY_PREFIX`; `MAX_EMBED_CHARS = 2000`; `ollama_embed`; `cosine`; `fuse`; `HybridIndex` | `runs/service.py:_retrieve` |

#### `routing/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `routing/__init__.py` | Docstring only. | - | - |
| `routing/router.py` | Picks a model per task from a measured policy; default for every task today. | `TaskName` (clause_lookup, guidance_comparison); `ModelDecision`; `ModelRouter.select`; `task_for` | `application/start_run.py` |

#### `runs/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `runs/__init__.py` | Empty package marker. | - | - |
| `runs/service.py` | The executor: stages, retrieval, model call, verification, policy chain, record, end. | `SECTION_LABEL`; `_set_stage`, `_note_stage`; `verify_evidence`; `located_text`; `reading_of`, `_run_on_parts`, `place_in`, `_runs_on`, `_part_of`; `StaleRun`; `FrozenOptions`; `_retrieve`; `fired_alias_groups`, `amendments_left_out`, `_retrieval_record`; `bound_to`; `execute_run`; `_fail`; `finished_record`; `_finish` | `api/runs.py:_worker`, `batch/service.py`, `goldens/replay.py`, `application/reverify_run.py` (`verify_evidence`, `FrozenOptions`); `located_text` also by `runs/account.py`, `batch/service.py`, `scripts/score_cuad.py` |
| `runs/status.py` | Code decides the status: `decide` and every later check, the reasons, references, sentences and left-out conditions. Declares `POLICY_VERSION`. | `POLICY_VERSION = "policy-v17"` (history in comments, lines 59-154); `Decision`; `decide`; `SUBJECT_IS_THE_MODELS`; `Basis`, `basis`; `Grounds`, `settle_together`; `REFERENCE`, `references`, `unknown_references`; `ATTACHMENT`; `enclosing_sentences`; `LeftOut`, `left_out`, `left_out_condition`, `Place`, `unshown_conditions`, `MAX_CONDITION_CHARS = 200`; `check_conditions`, `check_replaced`, `check_old_value`, `check_unhanded`, `check_references`, `check_values`; `unseen_references`; `_with_earlier` | `runs/service.py`, `runs/account.py` (`basis`), `runs/links.py` and `runs/relations.py` (`references`, `REFERENCE`, `ATTACHMENT`), `api/runs.py`, `create_memo.py`, `evidence_pack.py` (`basis`) |
| `runs/values.py` | The values an answer states that its quotes do not, compared by value (numbers, words, money, percentages, dates); value choices; uniform party values; redaction marks; question frame times. | `frame_times`; `date_spans`; `NOT_A_QUANTITY`; `wording_values`; `stated_values`; `unquoted_values`; `REDACTION_MARK`, `redaction_given_as_value`; `ValueChoice`, `value_choices`; `UniformChoice`, `uniform_party_choices` | `runs/status.py`, `runs/account.py`, `runs/relations.py`, `api/runs.py`, `schemas.py` |
| `runs/relations.py` | Locates the contract's replacement and precedence statements and says what each means for a finding. | `RelationKind`, `Effect`, `Perspective`, `CONCERNS`; `MAX_RELATIONS = 24`; `Passage`, `Relation`, `Note`, `Recorded`; `_Document`; `_replacements`, `_started`, `_fresh_definitions`, `_definition_in`, `_precedences`; `locate_relations`; `asked_time`, `perspective`; `parts_of`; `assess`; `unhanded_amendment`; `replacement_starts`, `reached_start`, `latest_start_reached`; `relevant`; `dump`, `load` | `runs/service.py`, `application/start_run.py` (starts), `runs/account.py`, `api/runs.py` (`load`) |
| `runs/links.py` | Retrieval-v2/v3 links: definitions, amendments, overrides and references the top ranked sections depend on. | `SEEDS = 3`, `MAX_LINKS = 2`; `LinkKind`, `_PRIORITY`; `_AMENDS`, `_CHANGES`; `Readable`; `Link`, `Amendments`; `_definitions`, `_amending`, `_amendments`, `_opened`, `_resolve`, `_named`; `links_of`; `linked`; `_changes_of`; `because` | `runs/service.py` |
| `runs/prose.py` | Rewrites the model's `sec_N` handles as labels; a handle naming no handed section (or followed by a sub-reference) becomes `[unidentified section]`. | `PARAGRAPH`, `SUB_REFERENCE`, `HANDLE`, `UNRESOLVED`; `unresolved_handles`; `label_handles` | `runs/service.py`; patterns copied into the pack by `evidence_pack.py` |
| `runs/account.py` | One account per finding for every surface: `decided_by`, `concerns`, `flagged`, unquoted values, value choices. Decides nothing. | `notes_of`; `DecidedBy`; `DECIDED_BY_CODE`; `_CHECK_DID`; `NOT_CONFIRMED`; `Account`; `value_checks`; `account_of` | `api/runs.py`, `api/findings.py`, `application/create_memo.py`, `application/evidence_pack.py` |
| `runs/events.py` | In-process fan-out of stage events to SSE subscribers. | `TERMINAL`; `StageEvent`; `EventBus` (`bind_loop`, `subscribe`, `unsubscribe`, `publish`); `bus` | `runs/service.py`, `api/runs.py`, `application/recover_runs.py`, `main.py` |
| `runs/owner.py` | Which process holds a stage, and whether it still exists (host, pid, platform start token). | `ProcessIdentity` (`render`, `parse`); `start_token_of`; `this_process`; `owner_is_alive_here`; `owner_is_gone` | `runs/service.py`, `application/start_run.py`, `application/recover_runs.py` |
| `runs/transitions.py` | The run lifecycle as a table. | `CREATED`; `ALLOWED`; `IllegalTransition`; `assert_transition` | `runs/service.py`; copied into the pack as `TRANSITIONS` |
| `runs/versions.py` | The four semantic versions in one place, and how a recorded version compares with the build's. | `SEMANTIC_VERSIONS`; `Order`; `compare_version`; `stale_versions`; `earlier_versions`; `unknown_versions`; `without_versions` (no caller in `app/`; used by `tests/test_run_identity.py`) | `application/start_run.py`, `runs/service.py`, `application/trust_run.py`, `scripts/status.py` |

#### `verify/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `verify/__init__.py` | Empty package marker. | - | - |
| `verify/spans.py` | Locates a quote in a section's text and returns offsets into the original; the ladder, edges, label stripping, window, per-pass memo. | `VERIFIER_VERSION`; `IGNORABLE_RANGES`, `QUOTE_FOLDS_V11`, `_QUOTE_MAP_V10`, `_QUOTE_MAP`, `_DELETED`, `_INVISIBLE`; `Located`; `normalize_with_map`, `fold_with_map`, `alnum_with_map`; `bounded`, `_splits`; `verification_pass`; `_find_bounded`; `_cannot_hold`; `_tiers`; `strip_label`; `locate` | `runs/service.py`, `retrieval/lexical.py` (`_QUOTE_MAP`), `runs/account.py` (`Located`), `ingest/sections.py`, `trust/compile.py`, `trust/diff.py`, `application/reverify_run.py`, `application/evidence_pack.py` |
| `verify/tokens.py` | Typed tokens and numbers as written, for the typed tier and the edges, with every older reading the packs need. | `Kind`; `Token`; `_TOKEN`; `_MINUS_SIGNS`, `_DIGIT_MARKS(_V11)`, `SIGN_OPENERS(_V11)`, `_ATTACHED(_V8, _V11)`; `_CURRENCY_SYMBOLS`, `_ISO_4217`; `_WRITTEN_V8`, `_WRITTEN_V9`, `_WRITTEN_V10`, `_WRITTEN`; `VERSION = 11`; `_CHOICE_MARKS`, `_CLAUSE_LETTER`, `_SENTENCE_END`; `written_numbers`; `joins_digits`; `attaches`; `canonical_number`; `tokenize`; `signed`; `sentence_ends`; `compared`; `caseless`; `whole_words`; `locate_tokens` | `verify/spans.py`, `runs/values.py` (`tokenize`, `Kind`), `ingest/sections.py`, `application/evidence_pack.py`, `trust/facts.py` (`Kind`, `tokenize`) |

Outside the slice, the pipeline leans on `ingest/sections.py` (`stated_clause_numbers`, `PART_HEADING`,
`PARAGRAPH_SEPARATOR`, `clause_openings`), `ingest/terms.py`, `ingest/invisible.py`, `unseen.py`, `document_names.py`,
`hashing.py`, `models.py`, `db.py` (`write_locked`, triggers), `application/quotas.py` and `application/workspace.py`.

### 5.5 Versions and identity

#### The four semantic versions (`runs/versions.py:SEMANTIC_VERSIONS`, line 26)

| Key in options | Value at 865356b | Declared at | Names |
|---|---|---|---|
| `policy_version` | `policy-v17` | `runs/status.py:155` `POLICY_VERSION` | how a status is decided |
| `verifier_version` | `v13` | `verify/tokens.py` `VERSION`, as `spans.VERIFIER_VERSION = f"v{VERSION}"` | when a quote counts as found |
| `retrieval_version` | `retrieval-v3` | `retrieval/lexical.py:83` `RETRIEVAL_VERSION` | which sections are handed over |
| `input_version` | `input-v1` | `analysis/service.py:40` `INPUT_VERSION` | what the model is handed and how its answer is read |

Each is recorded in every run's options and fingerprint, and changed by hand, never derived from a commit. Hashes carry
the rest: prompt text (`prompt_hash`), alias table (`retrieval_aliases`), model build (`model_digest`, when pinned). The
reader's version (`ingest.PARSER_VERSION`, reader v17) names a document's reading, not a run.

#### `compare_version(recorded, current)` (line 38)

Returns `current`, `earlier` or `unknown`, by the number each version ends in, never by string inequality:

| Recorded | Current | Result | Why |
|---|---|---|---|
| missing or empty | any | `earlier` | a run from before versions were recorded |
| `v11` | `v11` | `current` | equal |
| `v10` | `v11` | `earlier` | same rule, lower number |
| `v12` | `v11` | `unknown` | a newer build wrote it (for example after a rollback) |
| `retrieval-v9`, or an unreadable form | `policy-v17` | `unknown` | another rule's prefix, or no number |

`stale_versions(options)` lists versions that are earlier or unknown; `FrozenOptions.of` refuses to execute such a run.
`earlier_versions` (re-check under today's verifier is possible) and `unknown_versions` (nothing is re-checked) are used
by `application/trust_run.py`. `without_versions` strips the four keys (for records made before 2026-10-02); nothing in
`app/` calls it at 865356b, and `tests/test_run_identity.py` uses it.

#### Reused or asked again

A request is handed an existing run when the fingerprint matches a run whose stage is not `failed`: running,
`complete` or `unresolved`. Anything that changes the fingerprint makes a new run:

| Changes identity | Source |
|---|---|
| document id, guidance id | request |
| question text after invisible characters are removed and it is stripped | request |
| prompt file hash | `load_prompt` |
| model, temperature, seed, num_ctx, retrieval_k, section_window (when not 5000), alias table hash, model digest, retriever and embed model (when not BM25) | `run_options` |
| any of the four semantic versions | `SEMANTIC_VERSIONS` |
| the latest amendment start already reached on the run's day | `identity_options` |
| the workspace (for a workspace run) | `compute_fingerprint` |

A failed run never blocks its fingerprint, so the question can be asked again. A run created under one build and
picked up by a build with other versions or another alias table is failed at execution with "ask again"
(`tests/test_run_identity.py`, `tests/test_version_order.py`).

#### How the code behind each version is fingerprinted

`backend/tests/test_semantic_versions.py` holds each version to the code it names, so a rule cannot change while its
version stays the same:

- `ENTRY_POINTS`: `verifier_version` = `runs/service.py:verify_evidence`; `retrieval_version` =
  `runs/service.py:_retrieve`; `input_version` = `analysis/service.py:build_user_message`, `analyze`,
  `analysis/schema.py:ANALYSIS_SCHEMA`, `load_prompt`, `document_names.py:run_prompt_name`,
  `providers/ollama.py:OllamaProvider.chat_request` and `.generate_json`; `policy_version` =
  `runs/service.py:execute_run`; `parser_version` = `ingest/__init__.py:ingest`.
- `tests/code_closure.py:closure(entries, stop)` parses the app's modules (docstrings removed) and follows every name a
  definition's code uses (a class field's type too; parameters and annotations not) through in-app imports, until
  nothing new is reached. Code reached only through a method call on an object must be named as an entry point.
- `boundary(name)` is that closure, stopping at the other versions' entry points and at `NON_DECIDING` (stage
  recording, logging, the bus, process identity, transitions, `stale_versions`, rows, `settings`, `sha256_text`,
  `ProviderError`, `bound_to`, `fired_alias_groups`, `_retrieval_record`, `finished_record`, ...).
- `fingerprint(name)`: sha256 over each reached definition's `canonical` tree (no positions), first 16 hex characters.
  `RECORDED` maps every version that ever recorded a run to its fingerprint; old entries are never removed.

At 865356b all match (probe: policy-v17 `e139fb7d79be932c`, 372 definitions; v11 `e0c252050f95ddaa`, 107;
retrieval-v3 `272c76e0c6991632`, 86; input-v1 `f3535f0a6d1058e6`, 43; reader v17 `3a4543713ac44436`, 341).
Boundaries overlap, which matters when editing: `spans._QUOTE_MAP` (with `IGNORABLE_RANGES`, `QUOTE_FOLDS_V11`) is in
verifier and retrieval (BM25 folds with it); `status.references`, `REFERENCE`, `ATTACHMENT` in policy and retrieval
(links use them); `aliases.ALIAS_GROUPS`, `WORDING`, `ALIASES_SHA256` in retrieval and policy (via `FrozenOptions`).
The policy boundary also holds `located_text`, `reading_of`, `place_in`, `window_of`, `MAX_SECTION_CHARS_IN_PROMPT`,
`runs/status.py`, most of `runs/values.py` and `runs/relations.py`, `runs/prose.py` and `policy/`; the input boundary
holds `NEVER_CUT`, `_Deadline`, `_overflow`, `_answer_cut` and `PROVIDER_RETRY_DELAY_S`.

When the test fails, a person decides: the rule changed (bump the version where it is declared and add the new
version and fingerprint to `RECORDED`), or it did not (a rename, a reworded reason, a refactor: replace the current
version's fingerprint). The comments in `RECORDED` record that some versions were replaced before release (v11,
retrieval-v3, policy-v10, policy-v11) and others bumped once released. Other guards in the same file: every version
has entry points; no two versions share a fingerprint; every `NON_DECIDING` symbol is reached by the executor; the
stress test's planted edits each fall inside some boundary; comments and layout never move a fingerprint.

### 5.6 Invariants and safe change

#### Invariants an agent must not break

| # | Invariant | Enforced in | Tests (in `backend/tests/`) |
|---|---|---|---|
| 1 | The model never decides a code-owned status. A pass is always `model_hint`; code may lower it, never raise it. `confirmed_days` is never written. `missing` comes only from the model. | `runs/status.py`, `STATUSES_BY_SOURCE` | `test_pass_gate.py`, `test_pass_blockers_named.py`, `test_policy_rules.py` |
| 2 | A finding with any unverified quote is `unresolved` / `no_evidence` and stays so through every later check. | `decide`, each `check_*` | `test_withheld_stays_withheld.py`, `test_verify_evidence.py` |
| 3 | Checks read the contract's characters at a verified span (`located_text`), never the model's spelling. | `runs/service.py`, `runs/account.py` | `test_located_text.py` |
| 4 | The verifier never says "found" when the text is not there: no similarity tier, bounded edges, window searched with edges read whole, offsets into the original. | `verify/` | `test_spans.py`, `test_spans_properties.py`, `test_tokens.py`, `test_verifier_v7.py`, `test_verifier_v8.py`, `test_verifier_v9.py`, `test_verifier_v11.py`, `test_verifier_v12.py`, `test_verifier_v13.py`, `test_locate_prefilter.py`, `test_invisible_characters.py` |
| 5 | A run executes from its own recorded options, never the process settings; a run under other versions or another alias table is not executed. | `FrozenOptions.of`, `bound_to` | `test_run_identity.py`, `test_version_order.py`, `test_section_window.py`, `test_replay_window.py` |
| 6 | Identity carries every input and rule that shapes the answer; a decision change without a version decision fails the build. | `start_run.py`, `versions.py` | `test_semantic_versions.py`, `test_run_identity.py`, `test_run_dates.py`, `test_uniqueness.py` |
| 7 | Status and source pairs stay inside `STATUSES_BY_SOURCE`. | `Decision.__post_init__`, store CHECK | `test_store_schema.py`, `test_pass_gate.py` |
| 8 | Stages move only along `ALLOWED`; a finished run is immutable; terminal rows are written in one write. | `transitions.py`, `_set_stage`, `db.py` triggers | `test_transitions.py`, `test_run_endings.py`, `test_run_invariants_stateful.py` |
| 9 | A used prompt file never changes. | `prompts/manifest.json` | `test_prompts_frozen.py` |
| 10 | The model input is never cut: `truncate:false`, `shift:false`; overflow and cut answers fail the run and are not retried. | `providers/ollama.py`, `analyze` | `test_model_saw.py`, `test_model_transport.py` |
| 11 | Clean start and answer share one admission slot; every answer is computed from token 0 (with the documented server settings). | `AdmittedProvider`, `_start_clean` | `test_model_from_token_zero.py`, `test_admission.py`, `test_model_queue.py` |
| 12 | A reader never sees an exception's text or the endpoint address. | `failed_call`, `ProviderError` messages, `_fail` | `test_failure_words.py` |
| 13 | Links never grow the worst-case prompt beyond `k` full windows. | `links.linked` | `test_retrieval_links.py` |
| 14 | A located relation is a fact about the text, not a ruling; only `replaced`, `old_value` (on a pass) and an unhanded amendment (on a pass) change a status. | `relations.assess`, `check_*` | `test_relations*.py`, `test_policy_v16.py`, `test_unhanded_amendment.py` |
| 15 | A run is held before its row commits and released when its worker ends; recovery fails only runs nobody answers. | `start_run.write`, `_worker`, `recover_runs.py` | `test_run_liveness.py`, `test_run_ceiling.py`, `test_owner.py`, `test_liveness.py` |
| 16 | The pack's `verify.py` reaches the workbench's verdict for every recorded verifier. | `evidence_pack.render_verify_py`, `verify_template.txt` | `test_pack_parity.py`, `test_evidence_pack.py`, `test_pack_binding.py` |

#### Recipe: add a policy check

1. Write `check_<name>(decision: Decision, ...) -> Decision` in `runs/status.py`. Act only on `decision.status ==
   "pass"` unless the rule must reach other statuses (only `check_replaced` does). Return `Decision("needs_review",
   "position_check", _with_earlier(reason, decision))`. Read source text only (verified spans via `located_text`,
   guidance, the document), never `observed`, `required` or `topic` as evidence.
2. Wire it into the per-finding chain in `execute_run` (lines 541-585), before `settle_together`; compute any
   document-wide fact once, beside `week` and `days` (lines 490-500).
3. Bump `POLICY_VERSION` to `policy-v18` (v17 is released), add its history comment, and add `"policy-v18":
   "<fingerprint>"` to `RECORDED` (the failing test prints it). Never edit the `"policy-v17"` entry.
4. Prefer `position_check`. A new `status_source` is a wider change: `models.py` (`StatusSourceName`,
   `STATUSES_BY_SOURCE`), the store CHECK and its rebuild in `db.py`, `runs/account.py` (`DECIDED_BY_CODE`,
   `_CHECK_DID`), `schemas.py`, the interface, `verify_template.txt`. A new field in `finished_record` must be mirrored
   in `verify_template.txt` (`record_of`) or every new pack fails.
5. Tests: a new file for the rule and its controls, then `test_semantic_versions.py`, `test_pass_gate.py`,
   `test_withheld_stays_withheld.py`, `test_finding_account.py`, `test_unseen_disclosure.py`, `test_run_identity.py`,
   `test_evidence_pack.py`, `test_pack_binding.py`. DECISIONS.md records each past bump with a replay over stored
   findings.

#### Recipe: change retrieval

1. Where: ranking and tokens in `retrieval/lexical.py`, query widening in `retrieval/aliases.py`, the contract's
   pointers in `runs/links.py`, fallback and order in `runs/service.py:_retrieve`. Bump `RETRIEVAL_VERSION` when the
   handed sections can change; record the fingerprint.
2. Edits to `ALIAS_GROUPS` or `WORDING` change `ALIASES_SHA256` (new identity; queued runs refused as stale) and also
   move the policy fingerprint; decide "rule did not change" for the policy and replace it, unless it did. Edits to
   `status.references`, `REFERENCE` or `ATTACHMENT` move retrieval and policy; `spans._QUOTE_MAP` moves retrieval and
   verifier.
3. Changed candidates change the user message, so the browser replay file must be re-recorded
   (`WORKBENCH_PROVIDER=record` against Ollama).
4. Measure first (`scripts/eval_retrieval.py`, docs/RETRIEVAL.md). Tests: `test_lexical.py`, `test_aliases.py`,
   `test_retrieval_links.py`, `test_retrieval_record.py`, `test_retrieval_and_status.py`, `test_absence_wording.py`,
   `test_model_saw.py`, `test_defined_terms.py`, `test_semantic_versions.py`.

#### Recipe: change the prompt

Add a new file `analysis/prompts/answer-vN.md` (never edit a used one) and its sha256 to `manifest.json`
(`test_prompts_frozen.py`). Select it with `WORKBENCH_PROMPT_VERSION` (config default `answer-v2`; `deploy/up.ps1` and
`deploy/supervise.ps1` set it too). The prompt hash is in the identity, so prompt text alone needs no version bump.
Re-record the replay file and re-run the goldens (`scripts/run_goldens.py`) before switching the default.

#### Recipe: change what the model is handed or how its answer is read

`build_user_message`, `ANALYSIS_SCHEMA` and the pydantic models, the retry note in `analyze`, `run_prompt_name`,
`OllamaProvider.chat_request`, the reply reading in `generate_json`: bump `INPUT_VERSION` and record it.
`MAX_SECTION_CHARS_IN_PROMPT` must never move (it is how old runs are read back); change the window through
`WORKBENCH_SECTION_WINDOW`, which is recorded per run. Keep `application/reconstruct_input.py` able to rebuild the
message from the record, and the pack's context-slice check (`verify.py` check 12) passing. Tests: `test_reconstruct_input.py`,
`test_retry_provenance.py`, `test_model_saw.py`, `test_model_transport.py`, `test_section_window.py`,
`test_replay_provider.py`, `test_semantic_versions.py`.

#### Recipe: change the verifier

1. Edit `verify/spans.py` or `verify/tokens.py`; bump `tokens.VERSION` (`VERIFIER_VERSION` follows) whenever a quote
   could be found or refused differently, and record the fingerprint. A `_QUOTE_MAP` change also moves retrieval.
2. Keep the previous reading under a versioned name (`_WRITTEN_V11`, ...) and pass `version` through
   `written_numbers`, `signed`, `compared`, so packs of old runs still check as their verifier read them.
3. Mirror the change in `application/verify_template.txt` and `evidence_pack.render_verify_py` (`KNOWN_VERIFIER` follows
   `tokens.VERSION`). Replay stored spans before release, as DECISIONS.md shows for each past bump.
4. Tests: `test_spans.py`, `test_spans_properties.py`, `test_tokens.py`, `test_verifier_v7.py`, `test_verifier_v8.py`,
   `test_verifier_v9.py`, `test_verifier_v11.py`, `test_verify_evidence.py`, `test_locate_prefilter.py`,
   `test_located_text.py`, `test_invisible_characters.py`, `test_pack_parity.py`, `test_evidence_pack.py`,
   `test_version_order.py`, `test_trust.py` (the trust layer re-checks earlier-verifier spans), `test_semantic_versions.py`.

#### Recipe: change the provider or the queue

Admission, deadlines and redirects are in `providers/`. `OllamaProvider.chat_request` and `generate_json` are inside the
input boundary: any change there needs an `input_version` decision. The clean start relies on concurrency 1 and the
server's prompt cache being off; raising `WORKBENCH_MODEL_CONCURRENCY` breaks invariant 11. `MAX_MODEL_CALLS_PER_RUN`
in `recover_runs.py` must match the most calls `analyze` can make, or live runs are declared dead. Tests:
`test_model_transport.py`, `test_model_from_token_zero.py`, `test_admission.py`, `test_model_queue.py`,
`test_model_endpoint.py`, `test_model_wake.py`, `test_replay_provider.py`, `test_run_liveness.py`.

#### Other tests that cover this slice

`test_durations.py`, `test_periods_as_written.py`, `test_policy_v10_calendar.py`, `test_scoped_day_convention.py`,
`test_guidance_polarity.py`, `test_condition_words.py`, `test_left_out_conditions.py`, `test_unquoted_values.py`,
`test_values_from_the_guidance.py`, `test_value_support.py`, `test_value_choices.py`, `test_uniform_party_values.py`,
`test_identifier_values.py`, `test_reference_check.py`, `test_prose.py`, `test_source_handles.py`,
`test_relations.py`, `test_relations_cost.py`, `test_relations_definitions.py`, `test_relations_oracle.py`,
`test_relations_stance.py`, `test_relations_surfaces.py`, `test_part_edges.py`, `test_stream_resume.py`,
`test_failure_matrix.py`, `test_question_input.py`, `test_explanation.py`, `test_goldens.py`, `test_api_flow.py`.

## 6. Records, reviews and proofs

This chapter covers what a reader can check after a run has finished, and the measurement tools built on the same
record. Slice: `backend/app/trust/`, `backend/app/memo/`, `backend/app/goldens/`, `backend/app/batch/`,
`backend/app/families/`, and the use cases in `backend/app/application/` other than ingest, versions, start, recovery,
wake, workspace, quotas and retention (chapters 4, 5 and 7 own those).

One rule runs through every file here: **a finished run is immutable, and everything in this chapter is derived from
it.** Nothing here calls the model. Nothing here changes a run, a finding or a span. A review is a new row beside a
finding, never an edit of it. The trust manifest and the trust diff are worked out on demand and never stored. The memo
and the evidence pack are projections of the record into a document and a zip.

Paths below are relative to `backend/app/` unless they start with `backend/`, `docs/` or `scripts/`.

### 6.1 What a reader can check, and how

| Question a reader asks | Where the answer comes from | Route or tool |
|---|---|---|
| What did the run do, stage by stage? | `run_stages` rows with input and output hashes (written by `runs/service.py`, chapter 5) | `GET /api/runs/{id}/detail` |
| Who decided this finding's status, and what did code raise? | `runs/account.py:account_of` (chapter 5), read by memo, pack and card | card, memo "Why flagged", pack `findings.json` |
| What does a person say about it? | `finding_reviews` rows (`application/review_finding.py`) | `POST /api/findings/{id}/review` |
| A document I can send | `application/create_memo.py` + `memo/service.py` | `POST /api/memos`, `GET /api/memos/{id}/html`, `/docx` |
| Can I check the evidence without Verity? | `application/evidence_pack.py` + `verify_template.txt` | `GET /api/runs/{id}/evidence-pack` |
| What does each finding stand on? | `trust/compile.py` via `application/trust_run.py:manifest_of` | `GET /api/runs/{id}/trust` |
| What does a revised contract do to it? | `trust/diff.py` via `application/trust_run.py:diff_with` | `GET /api/runs/{id}/trust/diff?documentId=` |
| Why this answer? | `application/explain_run.py` | `GET /api/runs/{id}/explanation` |
| Exactly what did the model see? | `application/reconstruct_input.py` | inside the explanation and the pack; `backend/scripts/reconstruct_inputs.py` |
| Would today's verifier find the same quotes? | `application/reverify_run.py` | `backend/scripts/reverify.py` only (no route) |
| How often are quotes found at all? | `application/citation_record.py` | `GET /api/engineering/citations` |

#### 6.1.1 The run record (what the rest of this chapter reads)

The run record is written by `runs/service.py` (chapter 5). Each stage row carries the hash of what the stage read
(`input_hash`) and what it produced (`output_hash`). This chapter recomputes them; it never writes them.

| Stage | `input_hash` | `output_hash` |
|---|---|---|
| `reading` | the document's sha256 | sha256 of every section text joined by `\x1f`, in ordinal order |
| `finding_evidence` | sha256 of `question + "\x1f" + (guidance_sha256 or "")` | sha256 of the chosen section ids joined by `\x1f` |
| `checking` | sha256 of `prompt.sha256 + user_message` (the first round's message) | sha256 of the model's answer text (`raw_output`) |
| `verifying` | sha256 of the model's answer text | sha256 of `json.dumps([[section_id, start, end, verified, method], ...], sort_keys=True)` over every span in finding order |
| `complete` / `unresolved` | `runs/service.py:finished_record`: sha256 of the record the run finished on (each finding's id, ordinal, status, status source and reason, relations, match counts; the run's relations, options, candidates, identity, model, prompt, retrieval mode, stage, reason). Only runs finished on or after 2026-10-30 have it | none |
| `failed` | none | none |

Stage order is `created → reading → finding_evidence → checking → verifying → complete|unresolved`, with `failed`
reachable from any non-terminal stage (`runs/transitions.py:ALLOWED`). Reviews are not in `finished_record`: they come
later, as rows of their own.

#### 6.1.2 The account of a finding (how this slice uses it)

`runs/account.py:account_of(finding, clause_numbers)` belongs to chapter 5. It returns an `Account` with `decided_by`
(`"code"`, `"model"` or `"withheld"`), `concerns` (sentences code wrote against the status), and `flagged` (a status
other than pass, or a pass with a concern). This slice is one of its main readers:

| Reader | What it takes from the account |
|---|---|
| `application/create_memo.py:create_memo` | `flagged` decides which findings are listed under "Flagged by automated checks"; `"; ".join(concerns)` is the "Why flagged." text |
| `application/evidence_pack.py:build_evidence_pack` | `decided_by`, `flagged`, `concerns` copied into `findings.json` (printed UNCHECKED by `verify.py`) |

Both pass `ClauseLocator(document.sections).clause_numbers` for every finding except a `missing` one, which gets an
empty set. `runs/account.py:notes_of` supplies the relation notes; the memo prints only those with
`effect == "context"` under "The contract on this provision (located by code).", because concerns already appear under
"Why flagged".

#### 6.1.3 Reviews: confirm, dismiss, clear

File: `application/review_finding.py`. Route: `POST /api/findings/{finding_id}/review` (`api/findings.py`), body
`{verdict, reviewer, note?, basedOn?}` (JSON is camelCase on the wire).

- **Appended, never edited.** Each call that changes the state adds one `FindingReview` row. The latest row is the
  state. `verdict` is one of `confirmed`, `dismissed`, `cleared` (`models.py:ReviewVerdictName`). `cleared` returns the
  finding to unreviewed; `Finding.review` (`models.py`) returns `None` when the latest row is `cleared`.
- **Who may review.** Only a finding shown as an answer: `status != "unresolved"` and run stage `complete`, else
  `Conflict` (409). The route also calls `application/workspace.py:require_own_run`: a curated run (no workspace:
  goldens, batches) is `Forbidden` ("This is a curated record. It is read only"), and another workspace's run is 404.
- **Reviewer name.** Passed through `ingest/invisible.py:visible_text` and stripped. If `has_visible_text` is false
  (spaces, zero-width characters, a lone joiner), `InvalidInput` and nothing is written. The note gets the same
  cleaning and becomes `None` when it shows nothing. Max lengths: reviewer 80, note 2000 (`schemas.py:ReviewIn`).
- **Repeats write nothing.** Same `(verdict, reviewer, note)` as the latest row returns `created=False` (route answers
  200 instead of 201). `cleared` on an unreviewed finding also writes nothing.
- **Out-of-date tab refusal.** The client sends `basedOn`, the `latestReviewId` it was shown. `latest_review_id(finding)`
  is `len(finding.reviews)`: the finding's own count of review rows, cleared rows included, 0 when none. It is a
  per-finding count, not the store-wide row id (the row id moved with other visitors' decisions). If `basedOn` differs
  from the current count, `Conflict("This finding was … after you opened it …")` and nothing is written. Repeating the
  current decision from a stale tab is not a conflict (the repeat check runs first).
- **Concurrency.** The read is committed, then every check and the insert run inside `db.write_locked(session)`, one
  transaction. A lock not had in time is refused as busy with nothing written.
- **`access_subject`.** Whenever the gate is on, the session's subject (an invite's, or a public visitor's `anon-…`) is
  recorded beside the typed name. The typed name is what is shown; it is not an identity.
- `review_out(review)` is the one mapping to `ReviewOut`; it returns `None` for no review or a cleared one.

#### 6.1.4 The review memo (HTML and DOCX)

Files: `application/create_memo.py` (identity, storage, atomic write), `memo/service.py` (rendering),
`memo/visible.py` (display of invisible characters). Routes (`api/memos.py`): `POST /api/memos {runId}` returns 201
with a new memo or 200 with the one already written; `GET /api/memos/{id}/html` serves the stored HTML under a strict
Content-Security-Policy (`default-src 'none'; style-src 'unsafe-inline'; …`); `GET /api/memos/{id}/docx` serves the
file, 404 `memo file` when the row exists and the file does not.

**Preconditions.** Run stage must be `complete` (else 409). Findings with status `unresolved` are not printed as
findings; they are listed under "Withheld from the findings" with the model's sentence labelled as the model's and
with no quotes (every quote in a memo was found in the document).

**Identity: run, review head, content hash.** One memo per `(run_id, review_head, content_sha256)`, enforced by the
unique index `ux_memos_run_review_content` (`models.py:Memo`).

| Key part | Defined in | What it is |
|---|---|---|
| `review_head` | `create_memo.py:review_head` | sha256 of `"\x1f".join(f"{finding.id}:{latest review row id or ''}")` in finding order. Uses row ids (not the per-finding count). A cleared row counts |
| `content_sha256` | `create_memo.py:content_key` | sha256 of `f"{DOCX_LAYOUT}\x1f{html}"` where the HTML is rendered with the fixed date string `KEY_DATE = "the day it is written"` |

So a review after a memo, a change to memo wording, a change to what `runs/account.py` raises, a change to clause
labels, or a bump of `memo/service.py:DOCX_LAYOUT` all make the next request write a new memo. The earlier memo stays
and is still served by its id. A memo written before `content_sha256` existed (NULL) is never handed back as the
answer to a new request. The date a memo is asked for is not part of what it says.

**Atomic write order** (`create_memo.py:create_memo`). DOCX is written to `data_dir/memos/pending/<uuid>/`, moved to
`data_dir/memos/memo-<run>-<head[:8]>-<token[:8]>.docx`, then the row is committed. On `IntegrityError` (a concurrent
first request won) the loser deletes its own file and returns the winner's row. On any other failure the file is
deleted. Worst case after a crash: a file with no row. `memo_file(memo)` reads the file from today's
`settings.data_dir / "memos"` under the stored file name, so a copied or restored store still serves its memos.

**What the memo says** (`memo/service.py:memo_html`, `memo_docx`; both share the same parts):

| Part | Rule |
|---|---|
| Header table | Agreement name (`document_names.run_document_name`), date, question, guidance text or "none supplied", "Sections read" (`reading_line`: how many of how many sections, how they were chosen, and "Nothing in this memo is a statement about the other sections.") |
| "Flagged by automated checks (N)" | `memo_flags`: findings whose account is flagged, with the joined concerns, then each withheld proposal with its concerns or `WITHHELD_REASON`. With none: `NO_FLAGS` ("No automated check flagged a finding. The findings below are the model's answers: …") |
| Per finding heading | `topic · status_label(status, has_guidance, status_source)`. A pass is "Model's answer" without guidance, "Within guidance (confirmed by code)" for `confirmed_days` (records made under policy-v2 only), "Within guidance" for `computed_days`, otherwise "Within guidance (model's view)". `missing` reads "Not found in the sections read (model's view)" |
| Body | `shown_conclusion`; `withheld_conclusion` (if any) as "The model also wrote" with `WITHHELD_NOTE`; each span as "Observed language" (or "Closest provision read" for `missing`) with a numbered link to Sources |
| "Not shown to the model." | when `runs/status.py:basis(...).unseen` names sections the quote's sentence points at that the model was not given |
| Model's reference to the guidance | `guidance_line`: says "found in the guidance" only when the reference is the guidance's own words (case, spacing, quote marks aside) |
| "The model's reading." | `observed` / `required` as the model's words |
| "Why flagged." | the account's concerns |
| Suggested position | only beside a `needs_review` finding (`_suggests`) |
| Person | "Reviewed. Confirmed by X on 28 September 2026: note" or "Person. Not reviewed by a person." |
| Sources table | number, section title (clause label first when the text names one: "13.2 Governing Law · within §13 General"), "found in the document text · method · characters a to b", deep link `{app_url}/?document=…&run=…&finding=…` |
| Footer | run id, review head prefix, model, prompt version and hash prefix, and the sentence that verification covers quotes, not conclusions |

The DOCX also carries core properties and a custom-properties part (`docProps/custom.xml`) with `workbench_run_id`,
fingerprint, document id and sha256, guidance sha256, model, prompt version and hash, citations verified "a of b",
review head, generated-at time and workbench link. Citations are internal hyperlinks to bookmarks `src_N`.

**Invisible characters.** Every string from the record passes through `memo/visible.py`: `shown_html` (HTML: escaped,
each hidden character a dashed `<span class='invisible'>U+XXXX</span>`) or `shown` (DOCX and the pack README:
`[U+XXXX]`). `memo/service.py:xml_safe` applies `shown` and then strips characters XML 1.0 cannot carry. The record
itself is never changed. Which characters are named: format characters (category Cf) other than the joiners and
direction marks text needs, plus shaping characters between two ASCII letters or digits (`memo/visible.py:_hidden`).

#### 6.1.5 The evidence pack

File: `application/evidence_pack.py:build_evidence_pack(session, run_id)`. Route: `GET /api/runs/{id}/evidence-pack`
(`api/runs.py`), a few built at once (`packs_building` semaphore, `Busy` with retry-after 5 s), counted against the
pack download limit only when built. Filename `evidence-<run_id>.zip`. Works for a run at any stage.

**Files in the zip** (written in this order):

| File | When present | Content |
|---|---|---|
| `README.txt` | always | `README_TXT`, plus `INVISIBLE_HEAD` and a line per model string that holds invisible characters (`readme_text`) |
| `run.json` | always | the run record; shape in 6.4.3 |
| `sections.json` | always | `[{id, ordinal, number, heading, text}]` as stored; `json.dumps(…, ensure_ascii=False, indent=1)`; its sha256 is `run.json:sections_sha256` |
| `findings.json` | always | every finding, withheld ones included; shape in 6.4.3 |
| `relations.json` | run has `relations_json` (policy-v11 on) | `[asdict(r) for r in relations]` from `runs/relations.py` |
| `verify.py` | always | `render_verify_py()`: `verify_template.txt` with workbench constants substituted |
| `model_output.txt` | `run.raw_output is not None` | the model's answer exactly as recorded |
| `document/<name>` | original bytes still on disk | original upload; name made portable by `pack_name` (Windows-illegal characters to `_`, reserved device names prefixed `_`) |
| `model_input/system.txt`, `model_input/user.txt` | `reconstruct_input(...).answered` | the rebuilt messages of the recorded answer |
| `guidance.txt` | run had guidance | guidance text |

**`verify.py`.** A standard-library Python 3 script (`python3 verify.py`). The template lives in a `.txt` file so that
"only `app/hashing.py` imports hashlib" stays enforceable by grep. `render_verify_py` replaces about thirty
`__PLACEHOLDER__` names with JSON string literals copied from the workbench: the quote normalisation map
(`verify/spans._QUOTE_MAP_V10`), `IGNORABLE_RANGES`, the typed-token patterns of verifier v7 to v11
(`verify/tokens.py`), `KNOWN_VERIFIER = tokens.VERSION` (11 at 865356b), the transition table, the legacy window
(`MAX_SECTION_CHARS_IN_PROMPT`), the handle-to-label patterns of `runs/prose.py`, `NOT_FOUND_CONCLUSION`, and
`README_SHA256 = sha256(README_TXT)`. Output lines start with `PASS`, `FAIL`, `UNCHECKED`, `NOTE`, `WITHHELD` or
`NOT CHECKED`.

What `verify.py:check` does, in order (`verify_template.txt:725` onward):

1. **Verifier gate.** `options.verifier_version` read as `v<N>`. A name it cannot read, or `N > KNOWN_VERIFIER`:
   prints `NOT CHECKED … Check the pack with the verify.py of a Verity build that knows …` and **exits 2**. Nothing,
   not even a hash, is judged. A run with no recorded version is version 0.
2. **Stage rows.** `run.json:stages` must be a path through the transition table from `created`, end at `run.stage`,
   have no repeated stage, and carry no hash on a row that never writes one. A `run.json` with a `run_id` and no
   `stages` is a FAIL. One with neither (hand-made, as in tests) is checked file against file, with an UNCHECKED line.
3. **Copies agree.** `sections_text_sha256_recorded`, `model_input.input_sha256_recorded` and
   `model_output.sha256_recorded` must equal the matching stage-row hashes.
4. **Reading.** `document.sha256` equals the reading input hash; the document file hashes to it (absent file:
   UNCHECKED); `sections.json` hashes to `sections_sha256`; section texts joined by `\x1f` hash to the reading output.
5. **Guidance.** `guidance.txt` hashes to `guidance_sha256`; a recorded guidance hash with no file is a FAIL.
6. **Finding evidence.** question + guidance hash; candidate ids in order; each candidate's number and heading match
   `sections.json`; the window and `retrieval.requested_k` repeated in `run.json` equal the options'.
7. **Checking input.** When the model input files are present: `sha256(sha256(system) + user)` equals the checking
   input hash; `sha256(system)` equals `prompt_hash`; `user.txt` starts with
   `QUESTION: …\n\nLEGAL GUIDANCE: …\n\nCONTRACT: `. `reconstructable` must agree with whether the files are there.
8. **Checking output.** `model_output.txt` bytes hash to the checking output hash and the verifying input hash.
9. **Finding words.** `findings.json` has as many findings as the answer proposes; each finding's topic (cut to 255),
   conclusion, model fields, `shown_conclusion` and each span's ordinal, quote and cited handle equal the answer with
   `sec_N` handles written as section labels (`label_handles`, a mirror of `runs/prose.label_handles`).
10. **Verifying output.** The located-span hash over `[section_id, start, end, verified, method]`.
11. **Finished record.** For a run whose last stage is `complete` or `unresolved`: `record_of(run, findings,
    relations)` (a mirror of `runs/service.py:finished_record`) equals that row's input hash. A run finished before
    2026-10-30 has no such hash: its statuses, relations and options are printed UNCHECKED ("the pack's word only").
12. **Context slices.** Recomputed from candidates, sections and window; must equal `run.json:context_slices` and
    `retrieval.returned`; each slice hashes as recorded and appears verbatim in `user.txt`.
13. **Spans.** For each span: unverified → `WITHHELD` line, nothing asserted. Verified → the stored section text at
    `[start:end]` must match the quote under the span's own tier (`same()`: `exact`, `normalized`, `casefold`,
    `alnum`, `typed`, and `unprefixed:` label stripping), read **as the verifier version the run recorded** read it
    (v5 window, v7 typed tokens, v8 edges and signed numbers, v9 currencies and magnitudes, v10 labels in numbers, v11
    joiners, sentence ends and clause letters). From v5 a span ending beyond the run's window fails. A v8+ span needs
    Python 3.11 (else FAIL, never an unchecked PASS). A span with characters this Python's Unicode does not know fails
    when the pack's Unicode version differs.
14. **NOTE** for each verified span beyond the slice the model was shown.
15. **Relations.** Each end (`statement`, `replaced`, `replacement`) of each relation: the stored section text at its
    offsets equals its `text`. A PASS says the words are there, not their legal effect.
16. **Reviews.** If `review_head` equals the hash of "no reviews" (`"\x1f".join(f"{id}:")`), every `review` in
    `findings.json` must be null (an invented review fails). Otherwise UNCHECKED: no hash covers what a review says.
17. **README.** `README.txt` must hash to `README_SHA256`.
18. **UNCHECKED** lists: times, document name, parser version, coverage, workbench link, the `verifier` block,
    `relations_note`, model call counts, `stages.attempt`/`rounds`; and in `findings.json` `decided_by`, `flagged`,
    `concerns`, `code_compared`, `unseen_reason`, `spans.clause_label` (worked out by the build that made the pack).

Exit 0 when no check failed, 1 when one did, 2 for an unknown verifier. A malformed file (missing key, bad JSON) is a
named FAIL, never a traceback (`main`). The pack is not signed: `verify.py` shows the files agree with each other and
with the stage hashes in `run.json`. To check `run.json` itself, compare its stage rows with
`GET /api/runs/{id}/detail`.

**Known gap (found while writing this chapter, by a pure-Python probe, not by an end-to-end run).** `readme_text`
appends an "invisible characters" section to `README.txt` when any model string holds such characters, but
`verify.py` compares `README.txt` with the hash of the fixed `README_TXT` (step 17). For such a pack the README check
should print `FAIL README.txt …` and the script exit 1, on an untouched pack. Probe: the embedded `README_SHA256`
equals `sha256(readme_text(...))` for an honest finding and differs for a topic holding `U+202E`.
`backend/tests/test_memo_display.py` checks the README text of a hostile run but does not run `verify.py` on it.

#### 6.1.6 The trust layer

Files: `trust/model.py` (values), `trust/facts.py` (typed values in a quote), `trust/compile.py` (record → manifest),
`application/trust_run.py` (use case, caching, re-reading). Route `GET /api/runs/{id}/trust` (`api/trust.py`), only
for a run in a terminal stage (else 409). The manifest is derived every time it is asked for (with a short cache) and
never stored. `TRUST_VERSION = "trust-v1"` (`trust/model.py:35`).

**Obligations.** For each finding, for each span, `compile.py:span_obligations` and the two code obligations:

| Need | Established when | Depends on |
|---|---|---|
| `quote_exists` | the record says the span verified, with a section and offsets (the record's own answer; not re-decided) | that one section (`On.SECTION`, the section key) |
| `quote_unique` | the quote stands in exactly one place across all sections, counted with `verify/spans.py:locate` | every section (`On.DOCUMENT`) |
| `fact_matches#n` | one per typed value in the quote (`facts_in`): durations (`policy/durations`), money and percent (`verify/tokens`), dates (month-name or ISO, real calendar dates only). Always established at compile time | the quoted span (`On.SPAN`) |
| `reader_compatible` | the document was read by today's reader (`PARSER_VERSION`); or by an earlier one and every located quote also stands in today's reading of the same bytes | code (`On.CODE`) and the spans |
| `rules_compatible` | decided under today's semantic versions; or under earlier ones and today's verifier still finds each located quote in the section the record named | code and the spans |

Obligation ids are `"<finding ordinal>.<span ordinal>/<need>[#n]"` for span needs and `"<finding ordinal>/<need>"` for
the code needs.

**Standings and trust states.** `Standing`: `established`, `not_established` (with a reason), `contradicted`.
`trust/model.py:derive` turns obligations into a `TrustState`, and nothing else does:

| State | Rule |
|---|---|
| `unsupported` | no `quote_exists` obligation at all, any `quote_exists` not established, or anything `contradicted` |
| `needs_review` | quotes stand, and some other obligation is not established (a quote standing twice, a reader that reads the text differently, …) |
| `supported` | every obligation established |

The trust state never changes the recorded status; `FindingProof.recorded_status` carries the status as recorded.

**Reader compatibility.** When the run's document was read by an earlier reader, `trust_run.py:current_reading`
gets today's reading: a stored document with the same sha256 read by the current reader, else the original bytes read
again on a single background thread (`_read_again`). A request waits `REREAD_WAIT_SECONDS = 2.0`; if the reading is
not ready, the obligation says "could not be read again" and the manifest is not cached. Readings are kept 600 s,
at most 32, and dropped by every retention pass (`forget_readings`). A damaged original (hash mismatch) or a refusal at
a reading bound is "not now", never remembered as unreadable.

**Rules compatibility and unknown rules.** `runs/versions.py:compare_version` classifies each recorded version as
`current`, `earlier` or `unknown` by its number. `earlier_versions` feed `stale_rules`; `unknown_versions` plus an
unknown reader feed `unknown_rules` (`trust_run.py:unknown_to_this_build`). With unknown rules (as after a rollback):
- `rules_compatible` is `not_established`: "recorded under rules this build does not know …; not re-checked here".
- `quote_unique` and `reader_compatible` are replaced by `_not_judged`: not established, "not judged here". This build's
  verifier and reader do not judge records made by newer ones.
- No re-reading is attempted for an unknown reader.
- The trust diff is refused (`later_version` raises `Conflict`).

**Manifest identity and cache.** `TrustManifest.manifest_id` is the first 16 hex of a fingerprint over the whole
manifest as JSON. `snapshot_hash(reader_version, sections)` is the identity of one reading: reader version and every
section's number, heading and text hash, in order; the file name is no part of it. `manifest_of` caches by
`(run.id, document_sha256, PARSER_VERSION, TRUST_VERSION, SEMANTIC_VERSIONS)`, at most `MANIFESTS_KEPT = 64`, 600 s,
one computation per key at a time, cleared by `forget_readings`. The API counts each trust read as a document read
and lets only a few build at once (`api/access.trust_reads_building`, `Busy` otherwise).

#### 6.1.7 The revision diff

File: `trust/diff.py:trust_diff(manifest, old_sections, new_sections, new_reader_version)`, through
`application/trust_run.py:later_version` and `diff_with`. Route `GET /api/runs/{id}/trust/diff?documentId=<later>`.

**Precondition.** The later document must be the run's own document or recorded as a later version of it in the same
workspace (`application/versions.py:is_later_version`, chapter 7; recorded with
`POST /api/documents/{id}/supersedes`). Otherwise 409 "Record it as one first." Calling a finding stale is a
statement about the same contract, so it is made only where a person said it is the same contract. Refused also for a
run under unknown rules. Both checks run before anything is built.

**Section alignment** (`align`). Sections are compared by content, never by position or id. An old section whose key
(label + text hash) appears in the new version is identical. The rest are paired in four passes, strongest first, each
new section taken once:
1. same text under another label (renumbered or retitled);
2. same number and normalised heading, only when unique on both sides;
3. same normalised heading, only when unique on both sides;
4. by wording: Jaccard over 4-word shingles `>= SAME_SECTION (0.5)`, best pairs first, each old section compared only
   with new ones within `WORDING_BAND = 32` places of its scaled position, stopping at `MAX_WORDING_COMPARISONS =
   200_000` pairs or `MAX_WORDING_SHINGLES = 40_000_000` shingles read. `SectionChanges.not_compared` counts removed
   sections the budget never reached.

A number alone never pairs sections (inserting a clause shifts every later number). Unpaired old sections are
`removed`; unpaired new ones `added`.

**Obligations taken forward:**

| Need | What happens |
|---|---|
| `quote_exists` | Cited section identical in the revision: untouched. Else look in the counterpart (`held`), then anywhere (`relocated`, "where they were not cited"). Not found: if the 40 characters recorded on each side (`CONTEXT_CHARS`) still mark one place, the passage now there is read and the obligation is `contradicted` ("the cited passage in X now reads: …", cut to `SHOWN_PASSAGE = 240`); otherwise not established |
| `quote_unique` | Recounted. Sections carried over unchanged contribute the count they had; only sections whose content is new are searched (`sections_searched + sections_reused == sections_total`, enforced in `TrustDiff.__post_init__`) |
| `fact_matches` | Quote still found: established. Passage changed: values of the same kind re-parsed; the old value still there keeps it established; exactly one different value is `contradicted` ("15 calendar days → 30 calendar days: …"); otherwise not established |
| `reader_compatible`, `rules_compatible` | Untouched (they depend on code, not the document) |

Same snapshot (`to_snapshot == manifest.snapshot_hash`) means nothing is re-asked.

**Finding verdicts.** `stale` when any obligation's standing changed or the derived state changed; else `revalidated`
when a non-uniqueness obligation was re-answered (a cited section changed around the quote and it was found again);
else `unchanged`. A stale finding is not wrong; it is no longer shown to be supported by the document in front of the
reader. Nothing is written by a diff.

#### 6.1.8 "Why this answer" (explanation)

File: `application/explain_run.py:explain_run`. Route `GET /api/runs/{id}/explanation`. A read-only projection of
the record in six layers: the reading (document, reader version, pages, sections, tracked changes, hidden runs,
coverage and what was not read, the recorded sections hash); retrieval (candidates in rank order with their slice
start, end and truncation, and `linked` for sections retrieval-v2 added by reference); the reconstruction (6.1.9);
the model's proposals; per finding the `SourceMatch` list; and the recorded policy evaluation.

Rules it keeps:
- Proposals come only from `raw_output` parsed as `analysis/schema.AnalysisOut`, correlated by `Finding.ordinal`.
  Unparseable output, or a count that does not line up with the findings, gives
  `PROPOSAL_NOT_RECONSTRUCTABLE` and no proposals, never a guess.
- `inside_model_visible_context` is decided by the span's offsets against the reconstructed `ContextSlice` for its
  section, not by a constant. `None` for an unverified span or when slices could not be rebuilt.
- Nothing is recomputed and presented as what the run established. The status, source and reason are the recorded
  ones; `SOURCE_SUMMARIES` gives one fixed sentence per status source; `deterministic` is true for
  `DETERMINISTIC_SOURCES = {computed_days, position_check, ambiguous_fact, reference_check}`.
- `queue_note` is the `queued N s behind M` text from the checking stage detail, if any.
- `reproducibility` names ids, hashes, `input_matches` and the pack path.

#### 6.1.9 Reconstructing the model input

File: `application/reconstruct_input.py:reconstruct_input(session, run_id) -> Reconstruction`. Rebuilds the system
message (the prompt file `analysis/prompts/<version>.md` via `load_prompt`) and the user message
(`analysis/service.build_user_message`) from the question, guidance, document name, candidates and window, then hashes
`prompt.sha256 + user` and compares with the checking stage's `input_hash`.

| Outcome | `problem` / `answer_problem` |
|---|---|
| no checking stage | "the run never reached the model" |
| prompt file gone, or its hash differs from `run.prompt_hash` | reported, never repaired |
| a candidate section gone, or `candidates_json` invalid | reported |
| no recorded input hash (runs before 2026-09-28) | `NO_RECORDED_HASH`; not called a mismatch |
| hash differs | "the reconstructed input does not hash to what the checking stage recorded" |
| answer came from validation round 2+ | `later_round(n)`: the first message is what the hash covers; the recorded answer's own input (first message plus a rejection note) was not kept |
| rounds not recorded and calls ambiguous | `rounds_not_recorded(calls)` |

`matches` is the hash check alone; `answered` is `matches` and no `answer_problem`. Only `answered` messages go into
the pack. `validation_rounds` reads `rounds` when recorded, else infers from `attempt` using the frozen constants
`_ROUNDS_BEFORE_RECORDED = 2` and `_CALLS_PER_ROUND_BEFORE_RECORDED = 2` (must never move: they decide how old rows
read). A run recorded before 2026-10-30 may have been given its stored file name; when the first hash misses and the
legacy name differs, the message is rebuilt with `run_legacy_prompt_name` and kept if it matches. Each `ContextSlice`
is `(label, section_id, rank, start=0, end=min(len, window), truncated, sha256 of text[:end])`.

#### 6.1.10 Guidance saving

File: `application/save_guidance.py`. Route `POST /api/guidance` (`api/guidance.py`). Guidance is content-addressed:
the text is cleaned with `visible_text`, stripped, refused with `InvalidInput` when it shows nothing, and keyed by
`sha256_text(text)`. The same words reuse one row, so a run's fingerprint (which carries the guidance id) is stable.
`stored_guidance(session, sha256, workspace)` returns the workspace's own row, or a curated one (no workspace) for a
non-public workspace; a public workspace only ever uses its own. Writes go through `quotas.admit` under the write lock
and only while the workspace is open (`quotas.workspace_open`), so guidance cannot outlive a purged workspace. The
goldens use `source="golden"`.

#### 6.1.11 Re-verification

File: `application/reverify_run.py:reverify_run`. Script only: `backend/scripts/reverify.py <run_id>… | --withheld |
--all`. Parses the stored `raw_output`, re-runs `runs/service.verify_evidence` (the same function execution uses) for
every proposed quote against the run's candidate sections and the run's recorded window, and compares with the stored
spans. Each `SpanReplay.change` is `gained`, `lost`, `moved` (verified under another method) or `same`. Nothing is
written. It reads options from the record, not `FrozenOptions.of(run)`, because replaying runs made under older rules
is its purpose. This is how a verifier change is measured against the record before it is kept.

#### 6.1.12 The citation record

File: `application/citation_record.py:citation_record(session, workspace)`. Route `GET /api/engineering/citations`.
Over runs at `complete` or `unresolved` (all runs when `workspace` is None; otherwise `workspace.visible_runs`): runs
by stage, findings and withheld findings, spans, verified spans by method (largest first), first and last run time.

### 6.2 Goldens, batch and families

All three run the product's own use cases (`start_run`, `execute_run`) so their runs are ordinary runs: same
fingerprint, same record, same verification. Their runs have no workspace (curated: readable by every workspace,
changed by none). Their routes are mounted with `api/access.owner_only`, which answers 404 to a public workspace.

#### 6.2.1 Goldens

**What.** `goldens/set.json`: 44 fixed questions about the bundled sample (`public/samples/cloud-service-agreement.docx`,
sha256 prefix `cb72dad74b3af676`, Common Paper CSA, CC BY 4.0). 38 `present`, 6 `absent`; 11 categories
(`direct_extraction` 8, `absence` 5, `cross_reference` 5, `multi_section` 5, `negation` 4, `defined_term` 4,
`guidance_comparison` 4, `amendment_conflict` 3, `ambiguous` 2, `numeric_precision` 2, `adversarial` 2); 4 carry
guidance. Each golden: `id`, `category`, `question`, `kind`, `sections` (numbers), `why`, optional `guidance`,
`status` (`pass` or `needs_review`, only with guidance), `expected_value` (exactly one period).

**Anchors.** Sections are named by text, not number: `anchors` maps a section number to `section_anchor(text)` = the
first 16 hex of sha256 of the casefolded, whitespace-collapsed text under today's reader. `earlier_anchors` holds the
same sections as earlier readers read them where the text differs. A reader that renumbers a section (v14 made 5.3.1
into 5.3(a)) does not change what a recording cited. A section with no text has no anchor and is matched by number.

**Judging** (`goldens/service.py:judge(golden, run) -> Verdict`), code only:
- No run: `missing`. Failed run: `fail`. Not terminal: `missing`.
- `absent`: pass when the run is `unresolved` or no finding asserts (`pass`/`needs_review`); else fail.
- `present`: an `unresolved` run fails. Carriers are asserting findings with a verified span in a section the golden
  names (`_named`, by anchor, else by number). With `status`: every carrier must have it (a clause decided both ways
  fails). With `expected_value`: some carrier's `conclusion` or `observed` must state that period. A pass carried only
  by a finding code lowered (`LOWERED_BY_CODE = {position_check, reference_check, ambiguous_fact}`) is still a pass,
  with `lowered` set and `LOWERED_NOTE` in `because`.

**Finding recordings** (`recordings`). Runs are grouped by what they stored (document, question, guidance, prompt
hash, model, options), never by today's fingerprint, so a recording made under older versions is still found.
`best_recording` picks the most complete, then one under today's identity, then the latest. `Recording.label()` names
prompt, model, reader, rules, k, window, alias table and dates.

**Report** (`goldens/service.py:report`, `GET /api/engineering/goldens`): for each prompt file, its best recording,
per-golden verdicts, passes of recorded, mean latency, counts by category, and a comparison of the last two prompt
versions only when recorded on one reading under the same options. `compare_models` compares two models on one prompt
(used by `--compare-models`).

**Replay** (`goldens/replay.py`). `recordings/6c.json` is a committed recording: Recording 6c, `answer-v2`,
`qwen3:8b`, reader v5, 2026-10-01, with each golden's `raw_output`, `as_recorded` (37 of 44 under the judge of its
day) and `replayed` (what today's code gives: 37 of 44, fails g08 g11 g12 g26 g30 g35 g42, lowered g14 g28 g38 g43).
`replay()` feeds each recorded answer back through `start_run` + `execute_run` with a `RecordedAnswers` provider (it
answers by the `QUESTION:` line and refuses anything else), on today's reading, and judges. It refuses when the
prompt file's hash is not the recording's. A replay makes runs under today's identity from answers to other rules, so
it must run in a store of its own (the test's, or the temporary data dir `run_goldens.py --replay` creates).

`backend/scripts/run_goldens.py`: run the set (default prompt and model, or `--prompt`, `--model`, `--only gNN`),
`--report`, `--compare-models A B`, `--record <file> --prompt <v>`, `--replay <file> [--write]` (writes the
`replayed` block that `backend/tests/test_goldens.py` holds and `docs/STATUS.md` quotes;
`backend/tests/test_docs_claims.py` checks STATUS against it).

#### 6.2.2 Batch extraction

**What.** One task (a set of field questions) over a corpus of files; each (document, field) is one ordinary run.
`batch/tasks/core-fields.json` (governing law, termination, liability cap) and `batch/tasks/cuad-clauses.json` (seven
questions mapped one-to-one to CUAD v1 categories via `cuad_category`).

**Running** (`batch/service.py:run_batch`). Ingests every `.docx/.pdf/.txt` in the corpus directories (same bytes are
one document), writes a `Batch` row (task name and sha256, corpus label, model, prompt version, concurrency, counts),
then in a thread pool of `concurrency` workers calls `start_run` and, if new, `execute_run`, writing a `BatchItem`
(batch, document, field, run, `reused`, `wall_ms`). Existing runs are reused. Script: `backend/scripts/run_batch.py
--corpus <dir> --task <name> [--concurrency N] [--label L]` or `--report <batch_id>`.

**Value of a run** (`value_for`): `failed`; `withheld` (unresolved with `citations_unverified`) or `not_found`
(other unresolved); `in_progress`; `answered` with the answer finding's conclusion, status, citation (`§number` or
heading of the first located span) and method; `not_found` with the product's sentence when a finding is `missing`;
else `withheld`. The answer finding is `cuad_match.answer_index`: the first finding, in run order, with status `pass`
or `needs_review` and at least one verified quote with located text.

**Report** (`report`, `GET /api/batches/{id}`, also `/api/batches/{id}/values.csv` with formula-leading cells
escaped): distinct (document, field) pairs; runs created (began after the batch) vs reused; wall minutes; documents
and values per minute; p50/p95/mean model latency over created runs; failed runs by reason; findings, withheld,
spans, verified spans; retries (checking `attempt > 1`).

**CUAD scoring** (`batch/cuad_match.py`, pre-registered in `docs/CUAD.md`). `hits(located, experts)`: after
casefolding and collapsing whitespace, one contains the other, or token Jaccard `>= JACCARD (0.5)`.
`retrieved_carries(section, expert)`: the expert span is contained or 80% of its tokens are in the section
(`RETRIEVED_COVERAGE`; also used by `backend/scripts/eval_retrieval.py`). `outcome(value, texts, experts)` maps to the
closed set `correct`, `cited elsewhere`, `missed`, `correct absence`, `asserted where experts found none`, `failed`,
`in progress`, `not run`; the last three are `UNFINISHED` (a miss for recall; a recording with any gets no verdict).
The batch report, `backend/scripts/score_cuad.py` and the SkillOpt rollout all score the same finding through
`answer_index`.

Data: `batch/corpora/cuad-30.json` (source zip and sha256, selection rule: 10,000 to 150,000 characters, sorted by
title, every k-th of 404 eligible, first 30; seven categories; 30 contracts with file, title, chars, sha256),
`batch/corpora/cuad-30-labels.json` (per contract title, per category, the experts' spans; an empty list means none),
`batch/corpora/cuad-skillopt.json` (30 disjoint contracts, same rule with offset 6, train/validation/test splits; read
by `research/skillopt/build_data.py`, `backend/scripts/eval_retrieval.py` and `data_audit.py`), and
`batch/recordings/cuad-30-51398ed416634c15.json` (batch `51398ed416634c15`, `cuad-clauses` on `cuad-30`, `qwen3:8b`,
210 pairs, each with sha256, field, run id, value, findings as `[status, located texts]`, citation, method, latency,
reused). `backend/tests/test_docs_claims.py` checks that `docs/CUAD.md`'s table is what `score_cuad.py` prints for
this recording. `backend/scripts/cuad_corpus.py` regenerates the corpora files from `data/cuad/data.zip`.

#### 6.2.3 Families

**What.** Which documents of a labelled corpus belong together (a contract and its schedules, siblings from one
template), from structure alone, measured against hand labels. No model.

**How** (`families/fingerprint.py`). Three set views per document: normalised headings (numbering and punctuation
stripped, lower case), defined capitalised terms (`ingest/terms.definitions`), and word 5-gram shingles. Exact
Jaccard per view, combined with fixed `WEIGHTS = {shingles: 0.5, headings: 0.25, terms: 0.25}`.
`families/service.py:cluster` is single linkage at a threshold (union-find); `evaluate` is pairwise precision, recall
and F1 against a label set; `report` adds a sweep of thresholds 0.05 to 0.95 and the 15 most similar pairs.
`DEFAULT_THRESHOLD = 0.15`, the highest threshold where the `template` label set keeps precision 1.0 on the public
corpus.

**Labels** (`families/labels.json`): documents named by the first 16 hex of their sha256 (CP01 is the bundled
sample); two sets, `suite` (strict: same contract suite) and `template` (adds the eight Common Paper agreements as one
family). Only documents read by the current reader count (`labeled_documents`). Fingerprints are cached per document
id in `_FINGERPRINTS` (documents are immutable). Route `GET /api/engineering/families?threshold=` (owner only);
script `backend/scripts/cluster_corpus.py --corpus <dir> … [--threshold t]`, which ingests via
`batch/service.ingest_corpus`.

### 6.3 File-by-file reference

#### `backend/app/trust/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `trust/__init__.py` | Package docstring only. | none | none |
| `trust/model.py` | Frozen values of the trust layer and the one rule from obligations to a state. | `TRUST_VERSION` (`"trust-v1"`, :35); `CONTEXT_CHARS = 40`; `Need`, `Standing`, `TrustState`, `On`, `FactKind` (StrEnums); `Dependency`, `Fact`, `SectionText` (`label`, `content_hash`, `key`, `name`), `Occurrences`, `Evidence`, `Obligation`, `FindingProof`, `TrustManifest` (`manifest_id`, `counts`); `derive` (:173); `snapshot_hash` (:212) | `trust/compile.py`, `trust/diff.py`, `application/trust_run.py`, `api/trust.py` |
| `trust/facts.py` | Typed values a passage states: durations, money, percent, dates. | `facts_in(text)` (:47); `_dates` (calendar-valid dates only) | `trust/compile.py`, `trust/diff.py` |
| `trust/compile.py` | Record values to a `TrustManifest`; reads no database. | `SpanRecord`, `FindingRecord`; `count_places`; `unique_obligation` (the one uniqueness rule, shared with the diff); `evidence_of`; `span_obligations`; `reader_obligation`; `rules_obligation`; `_JUDGED_BY_THIS_BUILD`, `_not_judged`; `compile_manifest` (:232, a `verification_pass`) | `application/trust_run.py` |
| `trust/diff.py` | Takes a manifest to a revised document: alignment, re-asking each obligation, finding verdicts. | `Verdict`; `ObligationChange`, `FindingChange`, `SectionChanges`, `TrustDiff` (checks its own section accounting); `align` (:157); `passage_now`; `find_again`; `_fact_after`; `trust_diff` (:301); constants `SHOWN_PASSAGE`, `SHINGLE_WORDS = 4`, `SAME_SECTION = 0.5`, `WORDING_BAND`, `MAX_WORDING_COMPARISONS`, `MAX_WORDING_SHINGLES` | `application/trust_run.py`, `api/trust.py` (type) |

#### `backend/app/memo/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `memo/__init__.py` | Empty package marker (one line). | none | none |
| `memo/service.py` | Renders the memo as HTML and DOCX from findings and what the caller worked out. | `memo_html` (:271), `memo_docx` (:483); `memo_flags`, `flags_of`, `flag_reason`; `status_label`; `reading_line`; `guidance_line`, `in_guidance`; `model_reading`; `xml_safe`; `deep_link`; constants `STATUS_LABELS`, `FLAGS_HEAD`, `NO_FLAGS`, `NOT_REVIEWED`, `DECIDED_BY_CODE`, `WITHHELD_HEAD`, `WITHHELD_LEDE`, `WITHHELD_REASON`, `RELATED_HEAD`, `WITHHELD_NOTE`, `UNSEEN_HEAD`, `DOCX_LAYOUT = "docx-1"` (:191), `AUTHOR` | `application/create_memo.py` |
| `memo/visible.py` | The one display primitive for strings from the record: names invisible characters instead of letting them act. Same rule as `src/lib/text.ts revealInvisible`. | `shown` (plain, `[U+XXXX]`), `shown_html` (marked span), `_hidden`, `_pieces` | `memo/service.py`, `application/evidence_pack.py` |

#### `backend/app/application/` (this chapter's files)

| File | Job | Key names | Callers |
|---|---|---|---|
| `application/__init__.py` | Package docstring: use cases are functions over a session; no HTTP, no direct model call. | none | none |
| `application/trust_run.py` | Use cases for the trust manifest and the diff; re-reading with today's reader; caches. | `sections_of`, `document_snapshot`, `current_reading`, `manifest_of` (:151), `_work_out`, `unknown_to_this_build`, `later_version` (:236), `diff_with` (:250), `forget_readings` (:110); `REREAD_WAIT_SECONDS`, `READING_KEPT_SECONDS`, `MANIFESTS_KEPT` | `api/trust.py`; `application/retention.py` (`forget_readings`); `backend/scripts/trust_faults.py` (mutates it) |
| `application/evidence_pack.py` | Builds the evidence zip and renders `verify.py`. | `build_evidence_pack` (:219), `render_verify_py` (:54), `readme_text`, `pack_name`, `EvidencePack`; `README_TXT`, `INVISIBLE_HEAD`, `QUOTE_MAP`, `VERIFY_PY` | `api/runs.py` (`/evidence-pack`) |
| `application/verify_template.txt` | Source of the pack's standalone checker, with `__NAME__` placeholders. 1032 lines. | `main`, `check` (:725), `same` (tier ladder), `typed_tokens`, `edges_hold`, `record_of` (mirror of `finished_record`), `located`, `slices_of`, `label_handles`, `differences`, `verifier_number` | read by `evidence_pack.py` at import |
| `application/create_memo.py` | Memo identity, lookup and atomic write. | `create_memo` (:62), `review_head` (:32), `content_key` (:42), `KEY_DATE`, `stored_memo`, `memo_file`, `CreatedMemo` | `api/memos.py`; `api/runs.py` (`review_head` in `RunOut`); `evidence_pack.py` (`review_head`) |
| `application/explain_run.py` | "Why this answer": read-only projection of the record. | `explain_run` (:198), `_reading`, `_proposals`, `_inside`, `_findings`, `_queue_note`; `SOURCE_SUMMARIES`, `DETERMINISTIC_SOURCES`, `PROPOSAL_NOT_RECONSTRUCTABLE` | `api/runs.py` (`/explanation`) |
| `application/reconstruct_input.py` | Rebuilds the model's messages from the record and checks them against the recorded hash. | `reconstruct_input` (:145), `Reconstruction` (`matches`, `answered`, `answered_problem`), `ContextSlice`, `context_slice`, `validation_rounds`, `later_round`, `rounds_not_recorded`, `NO_RECORDED_HASH` | `explain_run.py`, `evidence_pack.py`, `backend/scripts/reconstruct_inputs.py`, `backend/scripts/export_break_record.py` |
| `application/visible_input.py` | Re-exports `has_visible_text` from `ingest/invisible.py` (moved there 2026-10-30). | `has_visible_text` | `review_finding.py`, `save_guidance.py`, `start_run.py` |
| `application/citation_record.py` | Counts verifier outcomes across finished runs. | `citation_record`, `ANSWERED` | `api/engineering.py` (`/citations`) |
| `application/clause_location.py` | Names the clause a verified passage sits in, read from stored section text; caches clause numbers per reading. | `ClauseLocator` (`label`, `clause_numbers`), `clause_numbers_by_document`, `_CLAUSE_NUMBERS_CACHED = 256` | `api/runs.py`, `api/findings.py`, `create_memo.py`, `evidence_pack.py`; cache cleared by `retention.py` |
| `application/review_finding.py` | Records a person's decision; stale-tab refusal; single-transaction write. | `review_finding` (:44), `latest_review_id` (:36), `review_out` (:22), `Reviewed` | `api/findings.py`, `api/runs.py`, `explain_run.py` |
| `application/reverify_run.py` | Re-verifies a run's stored answer with today's verifier; reports changes, writes nothing. | `reverify_run`, `SpanReplay` (`change`), `Replay` (`gained`, `lost`) | `backend/scripts/reverify.py` |
| `application/save_guidance.py` | Content-addressed guidance rows. | `save_guidance`, `stored_guidance`, `SavedGuidance` | `api/guidance.py`, `goldens/replay.py`, `goldens/service.py` (`stored_guidance`), `backend/scripts/run_goldens.py` |

#### `backend/app/goldens/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `goldens/__init__.py` | Package docstring; the keep-or-drop rule is in `docs/GOLDENS.md`. | none | none |
| `goldens/set.json` | The 44 goldens, categories, rules, anchors. Its sha256 ties every result to the questions. | `document`, `rules`, `categories`, `anchor_rule`, `anchors`, `earlier_anchors_rule`, `earlier_anchors`, `goldens` | `goldens/service.py:load_set`; also read directly by `backend/scripts/eval_retrieval.py`, `data_audit.py`, `domain_review_pack.py`, `load_envelope.py` |
| `goldens/service.py` | Loads the set, finds recordings, judges, compares, reports. | `load_set`, `section_anchor`, `judge` (:351), `recordings` (:251), `best_recording`, `run_for`, `compare`, `compare_models`, `report` (:532), `Golden`, `GoldenSet`, `Verdict`, `Recording`, `LOWERED_BY_CODE`, `LOWERED_NOTE` | `api/engineering.py` (`/goldens`), `goldens/replay.py`, `backend/scripts/run_goldens.py` |
| `goldens/replay.py` | Replays a committed recording through today's code without a model. | `replay`, `RecordedAnswers`, `load_recording`, `record`, `outcome_counts`, `CommittedRecording`, `RECORDINGS_DIR` | `backend/scripts/run_goldens.py`, `backend/tests/test_goldens.py` |
| `goldens/recordings/6c.json` | Recording 6c: answers, `as_recorded`, `replayed`. | `recording`, `label`, `model`, `prompt_version`, `prompt_hash`, `document_sha256`, `options`, `set_sha256`, `as_recorded`, `answers`, `replayed` | `replay.py`, `backend/tests/test_goldens.py`, `backend/tests/test_docs_claims.py` |

#### `backend/app/batch/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `batch/__init__.py` | Package docstring (`docs/BATCH.md`). | none | none |
| `batch/service.py` | Runs a task over a corpus and reports it. | `run_batch`, `load_task`, `corpus_files`, `ingest_corpus`, `value_for`, `answer_of`, `located_texts`, `summary`, `report`, `list_batches`, `Task`, `Field`, `TASKS_DIR` | `api/batches.py`, `backend/scripts/run_batch.py`, `score_cuad.py`, `cluster_corpus.py` (`ingest_corpus`) |
| `batch/cuad_match.py` | Matching and scoring rules shared by the batch, the CUAD scorer and the SkillOpt rollout. | `hits`, `retrieved_carries`, `answer_index`, `answered_texts`, `outcome`, `JACCARD`, `RETRIEVED_COVERAGE`, `ANSWERING`, `Outcome`, `OUTCOMES`, `UNFINISHED` | `batch/service.py`, `backend/scripts/score_cuad.py`, `eval_retrieval.py`, `research/skillopt/workbench_env/rollout.py` (per the module docstring; not opened) |
| `batch/tasks/core-fields.json` | Three repository-review questions. | `name`, `description`, `fields[{key,label,question}]` | `load_task` |
| `batch/tasks/cuad-clauses.json` | Seven CUAD-mapped questions. | as above plus `cuad_category` | `load_task`, `score_cuad.py` |
| `batch/corpora/cuad-30.json` | CUAD-30 manifest. | `source`, `selection`, `categories`, `contracts` | `score_cuad.py`, `eval_retrieval.py`, `data_audit.py`; written by `cuad_corpus.py` |
| `batch/corpora/cuad-30-labels.json` | Experts' spans per contract and category. | `{title: {category: [span, …]}}` | `score_cuad.py` (`LABELS`), `eval_retrieval.py` (also hashed into its corpus fingerprint) |
| `batch/corpora/cuad-skillopt.json` | 30 disjoint CUAD contracts with splits. | `source`, `selection`, `splits`, `categories`, `contracts` | `research/skillopt/build_data.py`, `eval_retrieval.py`, `data_audit.py` |
| `batch/recordings/cuad-30-51398ed416634c15.json` | Committed CUAD-30 batch result, 210 pairs. | `batch`, `task`, `corpus`, `model`, `finished_at`, `pairs` | `score_cuad.py`, `backend/tests/test_docs_claims.py` |

#### `backend/app/families/`

| File | Job | Key names | Callers |
|---|---|---|---|
| `families/__init__.py` | Package docstring (`docs/FAMILIES.md`). | none | none |
| `families/fingerprint.py` | Structural fingerprint and similarity of a document. | `Fingerprint`, `Similarity` (`combined`), `fingerprint`, `similarity`, `jaccard`, `shingles`, `normalise_heading`, `defined_terms`, `WEIGHTS`, `SHINGLE_WORDS = 5` | `families/service.py` |
| `families/service.py` | Clustering and evaluation against labels. | `report`, `cluster`, `evaluate`, `pairwise`, `load_labels`, `labeled_documents`, `cached_fingerprint`, `DEFAULT_THRESHOLD = 0.15`, `SWEEP`, `Labels`, `LabelSet` | `api/engineering.py` (`/families`), `backend/scripts/cluster_corpus.py` |
| `families/labels.json` | Hand labels for the public corpus. | `note`, `sets.suite`, `sets.template`, `documents` | `load_labels`; `data_audit.py` |

### 6.4 Data shapes

#### 6.4.1 Trust

```
TrustManifest
  run_id, document_id, document_sha256, snapshot_hash, reader_version
  rule_versions: tuple[(name, version)]   # policy_version, verifier_version, retrieval_version, input_version
  findings: tuple[FindingProof]
  trust_version = "trust-v1"
  manifest_id (property, 16 hex), counts() -> {supported, needs_review, unsupported}

FindingProof: finding_id, ordinal, topic, recorded_status, state: TrustState, evidence: tuple[Evidence], obligations
Evidence: span, quote, cited_label, section_key ("" = not located), section_number, section_heading, section_name,
          start, end (-1 = not located), method, before, after (40 chars each), occurrences: tuple[Occurrences]
          located (property), places (property: total count)
Occurrences: section_key, count
Obligation: obligation_id, need: Need, standing: Standing, reason, depends_on: tuple[Dependency], span: int|None,
            fact: Fact|None
Dependency: on: On (section|document|span|code), ref
Fact: kind (duration|money|percent|date), value (normal form), surface (as written)
Need: quote_exists | quote_unique | fact_matches | reader_compatible | rules_compatible
Standing: established | not_established | contradicted
TrustState: supported | needs_review | unsupported
```

API (`api/trust.py:manifest_out`, camelCase on the wire): `manifestId, trustVersion, runId, documentId,
documentSha256, snapshotHash, readerVersion, ruleVersions{}, counts{}, findings[{findingId, ordinal, topic,
recordedStatus, state, evidence[{span, quote, located, section, start, end, method, places}], obligations[{id, need,
standing, reason, dependsOn[{on, ref}], span, fact{kind, value, surface}|null}]}]`.

Diff (`diff_out`): `manifestId, runId, fromDocumentId, toDocumentId, fromSnapshot, toSnapshot, sections{identical,
changed[], removed[], added[], notCompared}, sectionsTotal, sectionsSearched, sectionsReused, counts{unchanged,
revalidated, stale}, findings[{findingId, ordinal, topic, before, after, verdict, why[], obligations[{id, need,
before, after, verdict, reason, placesBefore, placesAfter}]}]`. Obligation verdicts: `untouched`, `held`, `relocated`,
`changed`; finding verdicts: `unchanged`, `revalidated`, `stale`.

#### 6.4.2 Memo and review rows

| Table / column | Meaning |
|---|---|
| `memos.id` | memo id: 16 hex characters in a VARCHAR(32) |
| `memos.run_id` | the run |
| `memos.review_head` | `create_memo.review_head(run)` at write time |
| `memos.content_sha256` | `content_key(html with KEY_DATE)`; NULL on memos written before 2026-10-30 |
| `memos.docx_path` | path written to; only its file name is used now (`memo_file`) |
| `memos.docx_sha256` | sha256 of the DOCX file |
| `memos.html` | the HTML as served |
| `memos.created_at` | UTC |
| unique index | `ux_memos_run_review_content (run_id, review_head, content_sha256)` |
| `finding_reviews.id` | autoincrement row id (used in `review_head`) |
| `finding_reviews.finding_id` | FK, cascade delete |
| `finding_reviews.verdict` | `confirmed` / `dismissed` / `cleared` (check constraint) |
| `finding_reviews.reviewer` | typed name, max 80 |
| `finding_reviews.note` | optional |
| `finding_reviews.created_at` | UTC; the memo shows it converted to the server's local date |
| `finding_reviews.access_subject` | the session's subject (invite or `anon-…`) when the gate was on, else NULL |

API: `MemoOut {id, runId, docxUrl, htmlUrl, docxSha256, reviewHead}`. `FindingReviewOut {findingId, review:
{verdict, reviewer, note, at, accessSubject} | null, latestReviewId}`.

#### 6.4.3 Evidence pack JSON

`run.json`:

```
run_id, fingerprint, question, stage, reason, task
document: {id, name, sha256, parser_version, parse_coverage, file ("document/<name>" | null)}
sections_sha256                    # of sections.json bytes
sections_text_sha256_recorded      # reading stage output_hash
guidance_sha256, guidance_file ("guidance.txt" | null)
review_head
model_input: {input_sha256_recorded, reconstructable, problem, system_file, user_file,
              prompt_window_chars, model_calls, validation_rounds}
model_output: {file ("model_output.txt" | null), sha256_recorded}
context_slices: [{label, section_id, rank, start, end, truncated, sha256}]
candidates: [...]                  # candidates_json as recorded (label, section_id, number, heading, linked …)
stages: [{stage, input_hash, output_hash, attempt, rounds}]   # in row-id order
retrieval: {mode, requested_k, returned}
provider, model, prompt_version, prompt_hash, options
created_at, finished_at, packed_at
verifier: {describes, version, ladder, label_stripping, boundary, window_chars, unicode}
workbench_link
relations_file ("relations.json" | null), relations_note
```

`findings.json` (one object per finding, withheld included):

```
id, ordinal, topic, status, status_source, status_reason
code_compared, unseen_reason          # runs/status.basis
conclusion, shown_conclusion
decided_by, flagged, concerns         # runs/account.account_of
model: {observed, required, guidance_reference, suggested_position}
review: {verdict, reviewer, note, at} | null      # current review; cleared reads as null
relations: [{relation, effect, sentence}]
spans: [{ordinal, section_id, cited_label, start, end, quote, verified, method, match_count, clause_label}]
```

`sections.json`: `[{id, ordinal, number, heading, text}]`. `relations.json`: the dataclasses of `runs/relations.py`
(chapter 5); `verify.py` reads `kind` and, for each of `statement`, `replaced`, `replacement`, an object with
`section_id`, `start`, `end`, `text`, `label`.

#### 6.4.4 Goldens and batch

`Verdict(outcome: pass|fail|missing, because, statuses, cited ("5.3.1 exact", "sec_9 not found"), lowered)`.
`BatchValue {runId, outcome: answered|not_found|withheld|failed|in_progress, value, status, citation, method, reason}`.
`Batch` / `BatchItem` rows are defined in `models.py` (chapter 7).

### 6.5 Invariants and how to change things safely

| Invariant | Where it is enforced | Tests |
|---|---|---|
| Nothing in this chapter writes to a run, finding or span | by construction; `models.py` immutability triggers (chapter 7) | `test_trust.py`, `test_explanation.py`, `test_reconstruct_input.py`, `test_replay_window.py` |
| A review never edits; latest row is the state; stale `basedOn` writes nothing | `review_finding.py` | `test_review_concurrency.py`, `test_workspaces.py`, `test_visible_input.py` |
| A memo is keyed by run, review head and what it says | `create_memo.py`, unique index | `test_memo_identity.py`, `test_memo_revisions.py` |
| A memo's file exists before its row; a failed write leaves no row | `create_memo.py` | `test_memo_atomicity.py` |
| Every quote in a memo was found; withheld proposals are listed, not printed as findings | `create_memo.py`, `memo/service.py` | `test_acceptance_memo_withheld.py`, `test_absence_wording.py`, `test_memo_restraint.py`, `test_memo_docx.py` |
| A memo and the pack never let invisible characters act | `memo/visible.py`, `xml_safe` | `test_memo_display.py`, `test_invisible_characters.py` |
| Memo, pack and card read one account | `runs/account.py` | `test_finding_account.py`, `test_relations_surfaces.py`, `test_post_pilot_repair.py` |
| Every pack field is checked by `verify.py` or printed UNCHECKED; every file edited alone fails | `evidence_pack.py`, `verify_template.txt` | `test_pack_binding.py` |
| `verify.py` reads each span as its own verifier version read it | `render_verify_py`, `verify_template.txt:same` | `test_pack_parity.py`, `test_verifier_v7.py`, `test_verifier_v8.py`, `test_verifier_v9.py` |
| An unknown verifier is NOT CHECKED, exit 2 | `verify_template.txt:check` | `test_pack_binding.py` (`…verifier_the_checker_does_not_know_is_not_checked`) |
| The rebuilt input is reported, never repaired | `reconstruct_input.py` | `test_reconstruct_input.py`, `test_retry_provenance.py`, `test_name_leaks.py`, `test_prompts_frozen.py`, `test_section_window.py` |
| A trust state comes only from `derive` | `trust/model.py` | `test_trust.py` |
| Unknown rules are not judged by this build | `trust/compile.py:_not_judged`, `trust_run.later_version` | `test_version_order.py` |
| A diff is only of a recorded later version | `trust_run.later_version` | `test_trust.py`; fault in `backend/scripts/trust_faults.py` |
| Alignment cost grows linearly, and says what it did not compare | `trust/diff.py:align` | `test_trust_align_bounds.py` |
| A reading refused under load is not remembered | `trust_run._read_again` | `test_reading_cost.py` |
| A golden is judged by the text it cited, not its number | `goldens/service.py:_named`, anchors | `test_goldens.py` |
| The published golden figure is the replay of Recording 6c | `goldens/replay.py`, `6c.json:replayed` | `test_goldens.py`, `test_docs_claims.py` |
| The batch value and the CUAD score use the same finding | `cuad_match.answer_index` | `test_cuad_score.py`, `test_batch.py` |
| Families are deterministic and measured against labels | `families/` | `test_families.py` |

**Recipes.**

- **Add a field to the evidence pack.** Decide first which recorded hash covers it. If one does, add its
  recomputation to `verify_template.txt:check` (and, if it is part of the finished record, to both
  `runs/service.py:finished_record` and `verify_template.txt:record_of`, kept identical). If none does, add it to an
  `unchecked(...)` line with the reason. Update `README_TXT` (its hash is embedded in `verify.py`, so the README check
  follows automatically). Run `backend/tests/test_pack_binding.py`: its "every field edited alone fails or is named
  unchecked" test is the gate. A field that is neither bound nor printed UNCHECKED is a defect.
- **Add a constant `verify.py` needs from the workbench.** Add a `__NAME__` placeholder in the template and the entry
  in `render_verify_py:embedded`. The value is double JSON-encoded; decode it with `json.loads(__NAME__)` in the
  template. Do not import workbench code into the template: it must run with the standard library alone.
- **Bump the verifier version** (chapter 5). The pack must learn the new reading: `KNOWN_VERIFIER` follows
  `tokens.VERSION` automatically, but `same()`, `typed_tokens` and `edges_hold` in the template must reproduce the new
  rules under a `version >= N` branch, keeping every earlier branch unchanged. `test_pack_parity.py` compares the pack
  with the workbench. Until that is done, a pack of a new run would be judged by older rules.
- **Change memo wording or layout.** HTML wording needs nothing else: the content key is what the HTML says, so the
  next request writes a new memo. A change visible only in the DOCX must bump `memo/service.py:DOCX_LAYOUT`, or stored
  memos will keep being served. Every string from the record must pass through `shown_html` (HTML) or `xml_safe`
  (DOCX). Note that `settings.app_url` (deep links) and the server's local time zone (review dates) are part of the
  rendered HTML and therefore of the key. Tests: `test_memo_identity.py`, `test_memo_display.py`, `test_memo_docx.py`,
  `test_memo_restraint.py`.
- **Change what code flags.** Change `runs/account.py` (chapter 5), not the memo. The memo, the pack and the card read
  it. `memo/service.py:flag_reason` is only the fallback for a caller with no accounts.
- **Change trust rules.** Any change to what an obligation means, how a state is derived, or the alignment must bump
  `trust/model.py:TRUST_VERSION`: it is part of the manifest cache key in `trust_run.manifest_of`, and the manifest id
  covers it. Keep `unique_obligation` the single uniqueness rule for compile and diff. Run `backend/tests/test_trust.py`
  and `backend/scripts/trust_faults.py` (the release gate runs it; it injects one fault at a time into `app/trust` and
  `trust_run.py` and exits non-zero if a fault goes unnoticed).
- **Change the reader or the semantic versions.** The trust layer reads them through `PARSER_VERSION` and
  `runs/versions.SEMANTIC_VERSIONS`; both are in the manifest cache key, so no manual cache work is needed. Retention
  clears the caches in any case (`retention.py` calls `trust_run.forget_readings` and clears `clause_location`'s
  cache).
- **Change a review rule.** Keep the write inside `write_locked`. Keep `latest_review_id` a per-finding count (the
  interface sends it back as `basedOn`) and `review_head` on row ids (memo identity). `test_review_concurrency.py`.
- **Change the golden set.** Edit `goldens/set.json`; anchors must be the text anchors of today's reading. A relabel
  changes `set_sha256`. Re-run `run_goldens.py --replay app/goldens/recordings/6c.json --write` in its own temporary
  store and update `docs/STATUS.md`; `test_goldens.py` and `test_docs_claims.py` hold both.
- **Change the CUAD rule.** It is pre-registered in `docs/CUAD.md`. Change `cuad_match.py` only with the document;
  `test_docs_claims.py` fails when the scored table moves.
- **Change reconstruct_input.** Never move `_ROUNDS_BEFORE_RECORDED` or `_CALLS_PER_ROUND_BEFORE_RECORDED`. A change
  to `analysis/service.build_user_message` changes every rebuilt input; old runs must still rebuild to their recorded
  hash (`test_reconstruct_input.py`, `test_prompts_frozen.py`).

**Not verified in this chapter.** The exact fields of `relations.json` beyond what `verify.py` reads;
`research/skillopt/workbench_env/rollout.py`
(outside the backend, named only from the `cuad_match.py` docstring); the README hash failure in 6.1.5 was shown by a
hash probe, not by running `verify.py` on a real hostile pack.

## 7. The API, access and the store

This chapter covers the HTTP surface (`backend/app/api/`), how the process starts (`main.py`, `serving.py`), who may
reach what (sessions, workspaces, limits, quotas), the settings (`config.py`), and the SQLite store (`models.py`,
`db.py`, `application/workspace.py`, `application/quotas.py`, `application/retention.py`). Paths are relative to the
repository root; `file.py:123` is a line at commit `865356b`. Where something was not checked, the text says
"not verified".

### 7.1 How the API starts

**Entry point.** uvicorn runs `app.main:app`, the object `create_app()` returns at import (`backend/app/main.py:254`).
The deployment starts it as `uvicorn app.main:app --host 127.0.0.1 --port <port> --loop
app.serving:ResilientProactorEventLoop --no-access-log` (`deploy/supervise.ps1:206`; `deploy/up.ps1:59` is the same
without `--no-access-log`).

**What happens at import, before any request:**

1. `app.config` builds `settings = Settings()` once. Every default is read from `os.environ` when the module is first
   imported (`config.py:37-155`). Changing an environment variable later changes nothing; tests patch
   `config.settings` attributes or start a fresh interpreter (`tests/test_access.py:251`).
2. `app.db` builds `engine = make_engine()` and `SessionLocal` (`db.py:111-112`). Reading `settings.sqlite_url`
   creates the data directory if it is missing (`config.py:174-178`).
3. `app.main` calls `log_sink.configure(...)` (`main.py:39`): every logger, uvicorn's included, goes through one
   bounded handler (section 7.7, `log_sink.py`).
4. `create_app()` calls `access.check_configuration()` first (`main.py:131`). It raises `RuntimeError`, and the process
   does not start, when `WORKBENCH_ACCESS_SECRET` is set but shorter than 32 characters, or when
   `WORKBENCH_ACCESS_REQUIRED` is on and the secret is empty (`api/access.py:89-95`).

**The lifespan** (`main.py:108-129`) runs once when the server starts, in this order:

| Step | Code | What it does | Fails how |
|---|---|---|---|
| 1 | `init_db()` | `create_all`, then `ensure_columns`, `ensure_checks`, `ensure_immutability` (7.5) | `StoreDrift` if stored rows break a declared CHECK; start aborted |
| 2 | `bounded.use_handoff_dir(bounded.handoff_folder(settings.data_dir))` | Picks the temp folder where file readings hand bytes to a child process (`verity-readings-<16 hex>` in the system temp folder); deletes files a stopped process left; logs how many | `RuntimeError` on POSIX if the folder is not this user's alone |
| 3 | `refuse_a_store_with_owner_records()` (only when `anonymous_sessions`) | Counts runs whose `workspace_id` is NULL or not `pw-%`, documents with no `document_access` row (curated), and access rows not `pw-%`. Any count above 0 stops the start | `RuntimeError`: a misplaced `WORKBENCH_DATA_DIR` must never show the owner's record to the public |
| 4 | `recover_interrupted_runs(session)` | Fails runs no process is answering any more (chapter 5); logs `recovered_runs=N` | |
| 5 | `bus.bind_loop(asyncio.get_running_loop())` | Lets run workers on other threads publish stage events to the event loop (`runs/events.py`) | |
| 6 | `app.state.provider = provider or make_provider()` | The model provider every route uses (`api/deps.py:get_provider`) | |
| 7 | task `_log_model_build` | Logs one `model_build ...` line, read off the event loop, so a slow model server never delays the start | |
| 8 | task `_retain_hourly` (only when `anonymous_sessions`) | Retention: purge ended visitor workspaces, then `forget_process_state()` and `access.prune_windows()` (always, even after a failed purge), then the orphan-file sweep, then sleep 3,600 s. Each step catches and logs its own exception, so a failed pass never stops the API (`main.py:69-86`) | logged `retention pass failed` / `retention sweep failed` |

At shutdown the two tasks are cancelled and `bounded.release_handoff_dir()` removes the empty handoff folder.

**Middleware.** Starlette wraps user middleware so the last one added is the outermost. The resulting order, outermost
first (confirmed with a probe of `app.user_middleware`):

| Order | Middleware | Job |
|---|---|---|
| 1 | `request_log` (`main.py:192`, an `@app.middleware("http")` function) | Takes `X-Request-ID` only if it matches `[A-Za-z0-9-]{1,64}`, else makes a 12-hex id; echoes it back; adds `Cache-Control: no-store` to every `/api` answer that set none; adds the four `SECURITY_HEADERS` with `setdefault`; logs one line per request (`request_id method path status duration_ms`) except `/api/health`; 4xx lines carry a `shape` so floods are thinned (7.7); an unhandled exception is logged with status 500 and re-raised |
| 2 | `CORSMiddleware` | `allow_origins=settings.cors_origins` (never `*`), all methods and headers, `allow_credentials=True` so the cookie works when interface and API are on two ports (laptop). Through the tunnel they are one origin |
| 3 | `InFlightMiddleware` (`api/in_flight.py`) | Public store only: bounds requests in flight per network and open event streams (7.3) |
| 4 | `BodyLimitMiddleware` (`api/body_limit.py`) | Every store: bounds every body by declared and received length; for uploads, asks the gate and the pause at the door, bounds uploads per network, the spool and the sending rate (7.3) |
| 5 | `GZipMiddleware(minimum_size=1024, compresslevel=6)` | Compresses answers over 1 KB; Starlette leaves `text/event-stream` alone |

`SECURITY_HEADERS` (`main.py:99`): `Strict-Transport-Security: max-age=31536000`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `Content-Security-Policy: frame-ancestors 'none'`. They are set by
the app because the Cloudflare Tunnel sets none.

**Exception handlers** (`main.py:153-190`):

- `WorkbenchError` (every typed error, 7.3) becomes `{"detail": "<sentence>"}` with the class's `status_code` and
  `Retry-After` when the error has `retry_after`. A 429 or 503 also writes one `refused path=... status=... kind=<class>
  detail=...` warning line.
- `IntegrityError` whose message is the store's workspace guard (`db.refused_as_not_open`) becomes
  `AccessRequired(VISIT_ENDED)`, 401. Any other `IntegrityError` is re-raised and becomes a 500.
- `BodyRefused` raised while FastAPI reads a body is answered as an `HTTPException`, with the same refusal log line.

**Router mounting** (`main.py:237-250`). This is the one place access is attached, so a route added to an existing
router inherits its router's guard. `tests/test_access.py:55` walks every path in the app's OpenAPI document and
expects 401 without a session for all but the open set.

| Router | Mounted with | Meaning |
|---|---|---|
| `health.router`, `access.router`, `engineering.public_router` | nothing | open |
| `documents.router`, `engineering.router`, `model.router` | `gate` = `Depends(access.require_access)` | session required |
| `guidance.router`, `findings.router`, `memos.router`, `trust.router` | `gate` + `Depends(access.limit_public_writes)` | session; non-GET writes from a public workspace are bounded |
| `batches.router` | `gate` + `Depends(access.owner_only)` | session; a public workspace gets 404 |
| `runs.router` | `gate` + `Depends(access.limit_run_starts)` | session; `POST` is rate-bounded |

**Why `serving.py` exists.** Windows' default proactor loop closes its listening socket when one `accept` fails, and a
client that resets its connection during accept fails it with WinError 64 (`ERROR_NETNAME_DELETED`). The process then
stays up and answers no one; the supervisor restarted a silent API 18 times between 2026-10-09 and 2026-10-11. The
selector loop avoids that but caps a process at 512 sockets. `ResilientProactorEventLoop` (`serving.py:74`) is the
CPython 3.13 proactor with three changes: an accept that failed because of the client (`ConnectionError`, WinError 64
or 1236) is retried (after `RETRY_PAUSE_SECONDS = 0.5` when the accept failed to start); the retries are logged as one
line per `REPORT_EVERY_SECONDS = 60`; and `ResilientSocketTransport` finishes closing a connection whose `shutdown()`
raised a client-caused error instead of leaving the socket to the finaliser. TLS transports keep CPython's behaviour
(the deployment serves plain HTTP on loopback). On non-Windows platforms the module defines only `client_caused` and the
constants. Tests: `tests/test_accept_resets.py` (it also pins the copied CPython code).

### 7.2 Every HTTP route

34 operations, all under `/api`, all listed in `openapi.json`. Wire names are camelCase (`schemas.ApiModel` uses
`alias_generator=to_camel`); Python names are snake_case. Every error body is `ErrorOut {detail}`: a sentence from the
API, or FastAPI's validation list (422). The access column uses: **open**; **gate** (session when the gate is on, and a
same-origin `Origin` for non-GET); **+writes** (`limit_public_writes`); **+owner** (`owner_only`); **+runs**
(`limit_run_starts`). Limits named here are defined in 7.3.

FastAPI's built-in `/openapi.json`, `/docs`, `/docs/oauth2-redirect` and `/redoc` are also served by the app (the app is
created with FastAPI's defaults). They are not under `/api`, not gated, and not in the paths of `openapi.json`. Whether
the edge forwards them to the API is not verified here (chapter 8 and 9 own the interface's routing and the tunnel).

**`api/access.py`** (prefix `/api/access`, open)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `GET /api/access` | Is the gate on, and is this browser through it | none | 200 `AccessOut {required, entered, subject, anonymous, retentionDays}`; `subject` is null for an anonymous session | open | `_out(current_session(...))` |
| `POST /api/access/session` | Exchange an invite for a session cookie | `InviteIn {invite}` (1–4096 chars; the token or the whole link, text after `invite=` is used); query `replace` (bool, default false) | 200 `AccessOut` + `Set-Cookie`; 403 in the public store ("invite does not apply") or from another origin; 422 invalid or expired invite; 409 when the browser holds another reader's working session and `replace` is false; 429 after 10 tries in 10 min per network | open | `verify`, `mint` |
| `POST /api/access/visit` | Give a browser with no session its own anonymous session and a new `pw-` workspace | none | 200 `AccessOut` + `Set-Cookie`; an existing working session is returned unrenewed and no cookie is set; 403 when the gate or anonymous sessions are off, or another origin; 429 after 20 new visits an hour per network | open | inserts `VisitorWorkspace`, `mint` |

**`api/health.py`** (prefix `/api`)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `GET /api/health` | Liveness, store state, model state | none | always 200 `HealthOut {ok, provider, model, detail, access, modelLocation, modelHost, fault}` (semantics in 7.3) | open; never counted at the door; never request-logged; `async`, so it uses no request thread | `storage_problem`, `_probe_off_the_loop` |

**`api/engineering.py`** (prefix `/api/engineering`)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `GET /api/engineering/contract-state` | The recorded contract-state experiment the `/state` page shows | none | 200 `ContractStateOut` (`available=false` with a `detail` when the file is missing, unreadable or not schema `contract-state/2`; `sha256Verified` from the record's own hash) | open (`public_router`) | `load_contract_state`, cached by (path, mtime, size) |
| `GET /api/engineering/experiments` | The experiments board from `results.json` | none | 200 `ExperimentsOut` | gate | `load_experiments(results_path())` |
| `GET /api/engineering/citations` | How often quotes were found, by method, over runs this workspace may read | none | 200 `CitationRecordOut` | gate | `application/citation_record.py:citation_record` |
| `GET /api/engineering/families` | Structural families of the labelled corpus | query `threshold` float 0–1, default 0.15 | 200 `FamiliesOut` | gate +owner (route-level) | `families/service.py:report` |
| `GET /api/engineering/goldens` | Golden set with runs and verdicts per prompt version | none | 200 `GoldensOut` | gate +owner (route-level) | `goldens/service.py:report` |

**`api/documents.py`** (prefix `/api/documents`, gate)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `POST /api/documents` | Upload a contract | multipart `file` | 201 `DocumentOut` (new to this workspace); 200 with `reused=true` when the workspace already holds these bytes; 408 body stalled; 413 over 25 MB; 422 unsupported or unreadable; 429 quota or window; 503 pause, disk, busy store, readings busy | gate; door checks; `admit_upload` | `application/ingest_document.py:ingest_document`, run on a thread after `reading_turn` |
| `GET /api/documents` | This workspace's documents (plus curated ones outside the public store), with section, finding and reviewed counts and last run time | none | 200 `list[DocumentSummary]` | gate | queries over `visible_documents`, `visible_runs` |
| `GET /api/documents/{document_id}` | One document with its sections and coverage | path | 200 `DocumentOut`; 404; 429 (public: 240 views an hour per network) | gate + `limit_document_reads` | `workspace.require_document`, `to_document_out` |

**`api/trust.py`** (prefix `/api`, gate +writes; `limit_public_writes` lets GET, HEAD and OPTIONS through)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `GET /api/runs/{run_id}/trust` | What each finding of a finished run stands on | path | 200 `TrustManifestOut`; 404; 409 run not finished; 429; 503 when two trust reads are already being built | gate; `_trust_read` (2 at once; counts as a contract view in the public store) | `application/trust_run.py:manifest_of` |
| `GET /api/runs/{run_id}/trust/diff` | What a later version does to this run's findings | path; query `documentId` (required) | 200 `TrustDiffOut`; 409 not recorded as a later version, or rules unknown to this build | same | `trust_run.later_version`, `trust_run.diff_with` |
| `POST /api/documents/{document_id}/supersedes` | Say this document is the version after another | `SupersedesIn {previousDocumentId}` (1–32 chars) | 201 / 200 (already said) `DocumentVersionOut`; 409 already in a line; 422 supersedes itself | gate +writes | `application/versions.py:declare_supersedes` |
| `GET /api/documents/{document_id}/versions` | The line of versions in this workspace, oldest first | path | 200 `list[DocumentVersionOut]`, empty when in none | gate | `versions.lineage` |

**`api/runs.py`** (prefix `/api/runs`, gate +runs; `limit_run_starts` acts on POST only)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `POST /api/runs` | Ask a question of a document | `RunIn {documentId, guidanceId?, question}` (question 1–2000 chars) | 202 `RunOut` (new; a worker starts on `RUN_EXECUTOR`); 200 `RunOut` with `reused=true` for this workspace's running or completed run with the same inputs; 404 document or guidance; 422 empty question; 429; 503 | gate +runs | `recover_interrupted_runs`, then `application/start_run.py:start_run`; worker `runs/service.py:execute_run` |
| `GET /api/runs` | This workspace's runs (plus curated ones outside the public store), newest 200 | none | 200 `list[RunSummary]` | gate | query over `visible_runs` |
| `GET /api/runs/{run_id}` | A run: shown findings, withheld findings, stage, `ahead` (runs before it still open) | path | 200 `RunOut`; 404 | gate | `require_run`, `run_out` |
| `GET /api/runs/{run_id}/detail` | The full record: stages, candidates, raw output, tokens, hashes | path | 200 `RunDetail`; 404 | gate | `run_detail` |
| `GET /api/runs/{run_id}/explanation` | Why this answer, from the record only | path | 200 `RunExplanation`; 404 | gate | `application/explain_run.py:explain_run` |
| `GET /api/runs/{run_id}/evidence-pack` | Zip with the original, sections, record, spans and `verify.py` | path | 200 `application/zip` attachment; 404; 429 (public: 30 an hour per network); 503 when two packs are being built | gate | `application/evidence_pack.py:build_evidence_pack` |
| `GET /api/runs/{run_id}/events` | Server-sent events of the run's stages until it ends | path; `Last-Event-ID` header or `?after=<stage id>` to resume | 200 `text/event-stream` with events `stage` (stored rows carry `id:`), `queue {ahead}` (also the 15 s heartbeat), `error`; 404 before subscribing; 429 when too many streams are open (public) | gate; stream bounds at the door | `bus.subscribe`, `_in_the_record` |

The list, run, detail and explanation reads and `POST /api/runs` call `recover_interrupted_runs` first. Runs execute on
`RUN_EXECUTOR` (64 threads, `runs.py:250`), not the request pool. `create_run` commits the request session before
returning so the pooled connection is released while the background task runs.

**`api/findings.py`** (prefix `/api/findings`, gate +writes)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `POST /api/findings/{finding_id}/review` | Record a person's verdict | `ReviewIn {verdict: confirmed\|dismissed\|cleared, reviewer (1–80), note? (≤2000), basedOn? (≥0)}` | 201 when the state changed, 200 when repeated, `FindingReviewOut`; 403 curated run; 404; 409 reviewed since `basedOn`, or not reviewable; 422 | gate +writes | `require_finding`, `require_own_run`, `application/review_finding.py:review_finding` (records the session subject as `access_subject`) |
| `GET /api/findings` | Findings of complete runs this workspace may read, at most 500 | query `documentId` (optional) | 200 `list[FindingRecord]` | gate | one query with `visible_runs` |

**`api/guidance.py`** (prefix `/api/guidance`, gate +writes)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `POST /api/guidance` | Save guidance text | `GuidanceIn {text}` (1–20,000 chars) | 201 new / 200 held `GuidanceOut`; 422 blank | gate +writes | `application/save_guidance.py:save_guidance` |
| `GET /api/guidance/{guidance_id}` | Read guidance | path | 200 `GuidanceOut`; 404 | gate | `workspace.require_guidance` |

**`api/memos.py`** (prefix `/api/memos`, gate +writes)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `POST /api/memos` | Write a memo for the run's current review state | `MemoIn {runId}` | 201 new / 200 held `MemoOut {docxUrl, htmlUrl, docxSha256, reviewHead}`; 404; 409 run not complete | gate +writes; read access only (`require_run`), not ownership | `application/create_memo.py:create_memo` |
| `GET /api/memos/{memo_id}/html` | The memo page | path | 200 `text/html` with `MEMO_POLICY` CSP; 404 | gate | `workspace.require_memo` |
| `GET /api/memos/{memo_id}/docx` | The memo as Word | path | 200 DOCX attachment `review-memo-<run>.docx`; 404 when the row exists but the file is not in this store | gate | `require_memo`, `create_memo.memo_file` |

**`api/model.py`** (prefix `/api/model`, gate)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `POST /api/model/wake` | Wake a sleeping hosted model ahead of a question | none | 200 `ModelWakeOut {state: off\|awake\|waking\|limit}`; `off` when paused, `limit` when the reader's run quotas would refuse | gate (same-origin) | `application/wake_model.py:waker.request`, at most 3 wakes an hour per network |

**`api/batches.py`** (prefix `/api/batches`, gate +owner)

| Method and path | Purpose | Input | Answer | Access | Main call |
|---|---|---|---|---|---|
| `GET /api/batches` | Batch extraction runs | none | 200 `list[BatchSummary]` | gate +owner | `batch/service.py:list_batches` |
| `GET /api/batches/{batch_id}` | One batch's report | path | 200 `BatchOut`; 404 | gate +owner | `batch/service.py:report` |
| `GET /api/batches/{batch_id}/values.csv` | One row per document and field | path | 200 `text/csv` attachment; every cell through `spreadsheet_cell` (a leading `= + - @`, tab or CR gets an apostrophe) | gate +owner | `report`, `spreadsheet_cell` |

Batches are started only from the command line (`backend/scripts/run_batch.py`).

**How responses are declared.** `api/contract.py` builds every `responses=` value from the error classes:
`GATED` (401, 403, 503), `WRITES` (429, 503, 413), `INVALID` (422), `FOUND` (404), `CONFLICT` (409),
`held_or_created(Model)` (the 200 of a create-or-hold route), `media(type, ...)` (non-JSON 200s). The description of
each status is the error class's docstring. `openapi.json` is generated by `backend/scripts/export_openapi.py` and must
equal `create_app().openapi()` (`tests/test_api_contract.py:146`); the interface's types are generated from it with
`npm run api:types` (`package.json`).

### 7.3 Access and security

#### Three modes

| Mode | Settings | Who gets in | Workspace id |
|---|---|---|---|
| Gate off | `WORKBENCH_ACCESS_SECRET` empty | everyone | `open`, one shared workspace (laptop, tests, browser flows) |
| Invite gate | secret set, anonymous off | a browser that exchanged a signed invite for a session | `ws-` + 16 hex |
| Public anonymous (the live demo) | secret set and `WORKBENCH_ANONYMOUS_SESSIONS=1` | any browser, via `POST /api/access/visit`; invites are refused (403) | `pw-` + 16 hex |

`deploy/supervise.ps1:186-195` sets `WORKBENCH_ACCESS_REQUIRED=1` always, and, when started with a public data folder,
`WORKBENCH_ANONYMOUS_SESSIONS=1` and `WORKBENCH_MAX_RUNS_PER_DAY=200`. The running process's environment is not
verified here.

#### Tokens and the cookie

- Token format (`access.py:106`): `v1.<claims>.<mac>`. `claims` is base64url (no padding) of sorted-key JSON
  `{sub, aud, iat, exp}`; `mac` is hex HMAC-SHA256 of `v1.<claims>` under `WORKBENCH_ACCESS_SECRET`
  (`hashing.mac_sha256`). Audiences: `verity-invite`, `verity-session`. Nothing is stored server-side for an invite
  session.
- `verify` (`access.py:113`) returns `None`, without saying why, for: empty, over 1,024 chars, wrong version, bad MAC
  (`hmac.compare_digest`), bad JSON, wrong types, wrong audience, expired, subject in `WORKBENCH_ACCESS_REVOKED`, or an
  invite issued more than 60 s in the future (`models.CLOCK_SKEW`). A session is never refused for a future `iat`, so a
  clock step back does not close open visits.
- Cookie: `__Host-verity_session`, `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, no `Domain` (what the `__Host-`
  prefix requires). Life: `access_session_days` (7) for an invite session; `anonymous_retention_days` (7) for a visit.
- Invites are minted by `backend/scripts/access.py`. Changing the secret ends every invite and session at once.

#### What `require_access` does (`access.py:169`)

1. Gate off: `request.state.workspace = "open"`, pass.
2. No valid session, or `_session_serves_here(subject)` is false: `AccessRequired` 401 "This is a private preview...".
   In the public store only `anon-` subjects serve; an `anon-` subject serves only while its `visitor_workspaces` row
   exists and `expires_at` is in the future (one store read per gated request, `access.py:392`).
3. A non-GET/HEAD/OPTIONS request whose `Origin` header is present and not `app_url` or one of `cors_origins`:
   `Forbidden` 403. A request with no `Origin` passes this check; the `SameSite=Strict` cookie is the first lock.
4. Sets `request.state.subject` and `request.state.workspace = workspace_for(subject)`: prefix (`pw-` for `anon-`
   subjects, else `ws-`) + first 16 hex of `HMAC(secret, "workspace:<subject>")`. Opaque, stable, never chosen by the
   client. The typed reviewer name is never an identity.

Route code gets the workspace through `Depends(current_workspace)`.

#### Workspace isolation (`application/workspace.py`, the one place the rule lives)

| Record | Readable by workspace W when |
|---|---|
| document | W holds a `document_access` row for it; or, if W is not public, no workspace holds one (curated) |
| run | `run.workspace_id == W`; or it is NULL (curated) and W is not public |
| guidance | same rule as a run |
| finding, memo, event stream | follow their run |

- A record W may not read answers exactly like a missing one: `NotFound` 404, same sentence (`require_document`,
  `require_run`, `require_guidance`, `require_finding`, `require_memo`).
- A change to a run or anything under it needs `require_own_run`: a curated run answers `Forbidden` 403; another
  workspace's run answers 404.
- Lists filter with `visible_runs(W)` and `visible_documents(W)`. A public workspace sees only its own rows, never
  curated ones.
- Documents are deduplicated by (sha256, reader version) across workspaces; who may read one is the `document_access`
  relation, which also carries the name this workspace gave the file. Run identity includes the workspace, so one
  workspace's question never hands back another's run (chapter 5).

#### Limits, in the order a request meets them

Door limits (middleware; every store unless noted):

| Limit | Value | Keyed by | Refusal |
|---|---|---|---|
| Upload body (`POST /api/documents`) | 25 MiB file + 1 MiB form = 26 MiB, declared or received | request | 413 "file larger than 25 MB" |
| Any other body | 1 MiB (`JSON_REQUEST_LIMIT`) | request | 413 "request body larger than 1 MB" |
| Upload headers check before reading | gate, `public.paused`, public disk floor | request | 401 / 403 / 503 |
| Uploads in flight | 2 per network (`UPLOADS_PER_NETWORK`) | network | 503, Retry-After 5 |
| Upload spool | 384 MiB of received upload bytes, all uploads (`SPOOL_BUDGET`) | process | 503, Retry-After 5 |
| Upload sending rate | no wait over 30 s; after 10 s, at least 32 KiB/s on average | request | 408 |
| Requests in flight (public store only) | `public_requests_per_network` = 8; one past it waits up to 2 s | network | 503, Retry-After 2 |
| Event streams (public store only) | 4 per workspace, 16 per network | workspace, network | 429, Retry-After 30 (the interface then polls) |

A "network" is `access.client_network`: the `CF-Connecting-IP` address (or the socket's), an IPv4 address itself, an
IPv6 address's /64, an IPv4-mapped IPv6 as IPv4. Every per-network bound uses it.

Route-level windows (`access.SlidingWindow`; in process memory, forgotten on restart; pruned at each retention pass):

| Window | Limit | Keyed by | Stores |
|---|---|---|---|
| Invite exchange | 10 per 10 min | network | gate on |
| Run starts | `run_start_limit` = 20 per 10 min (captured at import as `RUN_LIMIT`) | session subject, else network | all |
| New visits | 20 per hour | network | public |
| Uploads | 30 per hour | network | public |
| Questions | 30 per hour | network | public |
| Other writes (reviews, memos, guidance, version statements) | 60 per hour per workspace and 120 per hour per network | workspace; network | public |
| Evidence packs | 30 per hour (counted only for a pack actually built) | network | public |
| Contract views (`GET /api/documents/{id}`, trust reads) | 240 per hour | network | public |
| Model wake-ups | 3 per hour (`api/model.py:23`) | network | where wake-ups are on |

Each window refusal is `TooManyRequests` 429 with a sentence and Retry-After.

Process-wide concurrency (every store): readings 2 at once (`ingest/bounded.py:READINGS_AT_ONCE`), one per network at
a time, an upload waits at most 45 s for its turn (503 "Other contracts are being read...", Retry-After 30); evidence
packs 2 at once and trust reads 2 at once, refused at once with 503 Retry-After 5.

Switches: a file named `public.paused` in the data directory, read on every request, pauses uploads and run starts in
every store and public writes (503 `Paused`); reading still works. In the public store, free disk below
`public_min_free_bytes` (2 GiB) pauses uploads and public writes the same way.

Store-counted quotas (`application/quotas.py`, decided under the write lock, 7.5):

| Quota | Default (setting) | Counts | Refusal |
|---|---|---|---|
| Public workspace is open | registered and not expired | `visitor_workspaces` row | 401 `VISIT_ENDED` |
| Documents a public workspace holds | 10 (`WORKBENCH_ANONYMOUS_MAX_DOCUMENTS`) | its grants | 429, Retry-After 3600 |
| Uploads per UTC day, all public workspaces | 300 (`..._MAX_UPLOADS_PER_DAY`) | public grants made that day | 429 until 00:00 UTC |
| New bytes per UTC day, all public workspaces | 1 GiB (`..._MAX_UPLOAD_BYTES_PER_DAY`; 0 = none) | `documents.size_bytes` of documents stored that day that a public workspace holds, plus this one; re-uploads of held bytes cost nothing | 429 until 00:00 UTC |
| Questions in flight, one public workspace | 2 (`..._MAX_RUNS_IN_FLIGHT`) | its non-terminal runs | 429, Retry-After 30 |
| Questions in flight, all public workspaces | 8 (`WORKBENCH_PUBLIC_MAX_RUNS_IN_FLIGHT`) | non-terminal `pw-%` runs | 503 `Busy`, Retry-After 60 |
| Questions per UTC day, one public workspace | 30 (`..._MAX_RUNS_PER_DAY`) | its runs created that day | 429 until 00:00 UTC |
| New runs per UTC day, all readers | `WORKBENCH_MAX_RUNS_PER_DAY` (0 = no ceiling; 200 in the public deployment) | runs with a workspace created that day; scripts' runs (no workspace) are not counted | 429 until 00:00 UTC |
| Model wake-ups per UTC day | 10 (`WORKBENCH_MODEL_WAKEUPS_PER_DAY`) | in memory, `wake_model.py` | `state: limit` |

A daily run quota counts the day of the run's own `created_at` instant, not the clock at count time
(`run_quotas(at=now)`), so a burst across midnight cannot slip past.

#### Upload limits in one place

25 MiB per file (`application/ingest_document.py:33`, checked on the declared size and again on the bytes); 26 MiB per
request at the door; 2 in flight per network; 384 MiB spool; 32 KiB/s minimum average rate; one reading per network and
two in all; 45 s wait for a reading; 10 documents per public workspace; 300 uploads and 1 GiB a day across the public
store; 30 uploads an hour per network.

#### Content Security Policy

The API sets `Content-Security-Policy: frame-ancestors 'none'` on every response that has no policy of its own. The memo
page sets `MEMO_POLICY` (`api/memos.py:47`): `default-src 'none'; style-src 'unsafe-inline'; base-uri 'none';
form-action 'none'; frame-ancestors 'none'`, so a memo built from contract text runs and loads nothing. The interface's
own page policy, with its per-request nonce, is set by the Next.js side (chapter 8).

#### Health (`GET /api/health`)

- `storage_problem()` (`health.py:27`) returns a sentence or `None`, in this order: a fault the engine met
  (`db.store_fault()`, 7.5); data directory missing; any of `data_dir`, `workbench.db`, `documents/`, `memos/` not
  writable; free space below the floor (2 GiB in the public store, else `MIN_FREE_BYTES` = 256 MiB). No sizes or error
  names are published.
- Gate on and no valid session: `ok = (no store problem)`, `provider` and `model` blank, `access: "required"`,
  `detail` the store problem or "private preview: an invite is needed", `fault: "store"` or `""`. The model is never
  asked for a visitor without a session.
- Otherwise: if `health_probes_model`, the provider's `healthy()` is asked on one dedicated thread, at most once per
  10 s per provider (`HEALTH_PROBE_TTL_S`); else `ok=true` with "checked before every answer, not by health". A store
  problem overrides: `ok=false`, `fault="store"`. A model failure alone gives `fault="model"`. `access` is `entered` or
  `off`.
- `modelLocation` is `server` when the Ollama URL host is loopback or `WORKBENCH_MODEL_ON_SERVER` is set, else `hosted`
  with `modelHost`.
- The handler is `async` and touches no request thread, so a full thread pool cannot make the supervisor's probe fail
  (`tests/test_liveness.py`).

#### Error classes (`backend/app/errors.py`)

| Class | HTTP | Raised for |
|---|---|---|
| `WorkbenchError` | 500 | base class |
| `NotFound(kind, id)` | 404 | missing, or not readable by this workspace (same answer); also `owner_only` for a public workspace |
| `Conflict` | 409 | valid request, record in the wrong state (stale review, run not finished, version already placed) |
| `InvalidInput` | 422 | unusable input (unsupported file, blank question or guidance, bad invite) |
| `TooLarge` | 413 | file over 25 MB |
| `Busy(msg, retry_after)` | 503 | write lock not had in 30 s, readings busy, packs or trust reads busy, public queue full |
| `Paused` | 503 | `public.paused` present, or public disk below its floor |
| `AccessRequired` | 401 | no valid session; a visit that has ended |
| `Forbidden` | 403 | another origin; a curated record a request would change; invite or visit in the wrong mode |
| `TooManyRequests(msg, retry_after)` | 429 | any window or quota (Retry-After required) |

Outside `errors.py`: `BodyTooLarge` 413, `BodyStalled` 408 and `SpoolFull` 503 (`api/body_limit.py`), and the door's
direct answers 503 `UploadsPerNetwork`, 503 `RequestsPerNetwork`, 429 `StreamsOpen`. FastAPI's own validation errors
are 422 with a list `detail`. Routes never catch broadly and never invent status codes.

### 7.4 Configuration (`backend/app/config.py`)

All values come from the environment once, at import. Booleans marked "1/true/yes" are on only for those words
(case-insensitive); `WORKBENCH_HEALTH_PROBES_MODEL` is on unless `0`, `false` or `no`. An empty value for an integer
setting stops the start, except the three noted as "empty = 0".

| Setting | Environment variable | Default | Meaning |
|---|---|---|---|
| `data_dir` | `WORKBENCH_DATA_DIR` | `backend/data` | The store's folder: `workbench.db`, `documents/`, `memos/`, `public.paused` |
| `database_url` | `WORKBENCH_DATABASE_URL` | empty (then `sqlite:///<data_dir>/workbench.db`) | Override the database URL |
| `provider` | `WORKBENCH_PROVIDER` | `ollama` | Model provider name (`providers.make_provider`) |
| `model` | `WORKBENCH_MODEL` | `qwen3:8b` | Default model tag |
| `ollama_url` | `WORKBENCH_OLLAMA_URL` | `http://127.0.0.1:11434` | Model endpoint (an IP, not `localhost`, to avoid a 2 s IPv6 wait on Windows) |
| `ollama_headers` | `WORKBENCH_OLLAMA_HEADERS` | `{}` | JSON object of header names to strings for an authenticating proxy; anything else stops the start; never printed |
| `model_digest` | `WORKBENCH_MODEL_DIGEST` | empty | When set, every answer first checks the endpoint's tag is this build |
| `model_host` | `WORKBENCH_MODEL_HOST` | empty | Words naming where a hosted model runs, shown to readers |
| `model_on_server` | `WORKBENCH_MODEL_ON_SERVER` | off (1/true/yes) | The endpoint is another container on this machine |
| `max_runs_per_day` | `WORKBENCH_MAX_RUNS_PER_DAY` | 0 (empty = 0) | Ceiling on new runs per UTC day, all readers; 0 = none |
| `health_probes_model` | `WORKBENCH_HEALTH_PROBES_MODEL` | on | Whether health asks the model |
| `model_wakeup` | `WORKBENCH_MODEL_WAKEUP` | off (1/true/yes) | Wake a sleeping hosted model on upload or question |
| `model_wakeups_per_day` | `WORKBENCH_MODEL_WAKEUPS_PER_DAY` | 10 (empty = 0) | Wake-ups per UTC day, all readers |
| `model_awake_s` | `WORKBENCH_MODEL_AWAKE_S` | 240 (empty = 0) | Seconds a model counts as awake after it last answered or woke |
| `temperature` | none | 0.0 | Decoding temperature |
| `seed` | none | 42 | Decoding seed |
| `num_ctx` | none | 16384 | Model context length |
| `model_timeout_s` | none | 600.0 | Per model call; also sets the staleness window (chapter 5) |
| `model_concurrency` | `WORKBENCH_MODEL_CONCURRENCY` | 1 | Model calls in flight per process (`providers/admission.py`) |
| `run_start_limit` | `WORKBENCH_RUN_START_LIMIT` | 20 | Runs one reader may start in 10 minutes; the browser flows raise it |
| `retrieval_k` | `WORKBENCH_RETRIEVAL_K` | 6 | Sections handed to the model; part of a run's identity |
| `section_window` | `WORKBENCH_SECTION_WINDOW` | 6000 | Characters of each handed section; part of a run's identity |
| `retrieval` | `WORKBENCH_RETRIEVAL` | `bm25` | `bm25` or `hybrid` |
| `retrieval_aliases` | `WORKBENCH_RETRIEVAL_ALIASES` | on (1/true/yes) | Join the legal alias table to the retrieval query |
| `embed_model` | `WORKBENCH_EMBED_MODEL` | `nomic-embed-text` | Embedding model for `hybrid` |
| `prompt_version` | `WORKBENCH_PROMPT_VERSION` | `answer-v2` | Prompt version |
| `routing_policy` | `WORKBENCH_ROUTING_POLICY` | `{}` | JSON task-to-model overrides |
| `replay_file` | `WORKBENCH_REPLAY_FILE` | `e2e/replay.json` | Recorded answers for the replay provider |
| `cors_origins` | `WORKBENCH_CORS_ORIGINS` | `http://localhost:3900,http://127.0.0.1:3900` | Comma list; CORS and the same-origin check |
| `app_url` | `WORKBENCH_APP_URL` | `http://localhost:3900` | The interface's origin; links in memos and packs; same-origin check |
| `access_secret` | `WORKBENCH_ACCESS_SECRET` | empty | Signs invites and sessions; empty = gate off; at least 32 chars; never printed |
| `access_session_days` | `WORKBENCH_ACCESS_SESSION_DAYS` | 7 | Life of an invite session |
| `access_required` | `WORKBENCH_ACCESS_REQUIRED` | off (1/true/yes) | Refuse to start without a secret |
| `access_revoked` | `WORKBENCH_ACCESS_REVOKED` | empty | Comma list of invite subjects whose invites and sessions open nothing |
| `anonymous_sessions` | `WORKBENCH_ANONYMOUS_SESSIONS` | off (1/true/yes) | Public mode: visits, `pw-` workspaces, retention, door bounds, owner-record refusal |
| `anonymous_retention_days` | `WORKBENCH_ANONYMOUS_RETENTION_DAYS` | 7 | Life of a visit's session and workspace |
| `anonymous_max_documents` | `WORKBENCH_ANONYMOUS_MAX_DOCUMENTS` | 10 | Documents per public workspace |
| `anonymous_max_runs_per_day` | `WORKBENCH_ANONYMOUS_MAX_RUNS_PER_DAY` | 30 | Questions per public workspace per UTC day |
| `anonymous_max_runs_in_flight` | `WORKBENCH_ANONYMOUS_MAX_RUNS_IN_FLIGHT` | 2 | Open questions per public workspace |
| `public_max_runs_in_flight` | `WORKBENCH_PUBLIC_MAX_RUNS_IN_FLIGHT` | 8 | Open questions, all public workspaces; also sets the public run ceiling in recovery |
| `anonymous_max_uploads_per_day` | `WORKBENCH_ANONYMOUS_MAX_UPLOADS_PER_DAY` | 300 | Public uploads per UTC day |
| `anonymous_max_upload_bytes_per_day` | `WORKBENCH_ANONYMOUS_MAX_UPLOAD_BYTES_PER_DAY` | 1073741824 | Public new bytes per UTC day; 0 = none |
| `public_requests_per_network` | `WORKBENCH_PUBLIC_REQUESTS_PER_NETWORK` | 8 | Requests in flight per network (public) |
| `public_streams_per_workspace` | `WORKBENCH_PUBLIC_STREAMS_PER_WORKSPACE` | 4 | Open event streams per workspace (public) |
| `public_streams_per_network` | `WORKBENCH_PUBLIC_STREAMS_PER_NETWORK` | 16 | Open event streams per network (public) |
| `public_min_free_bytes` | `WORKBENCH_PUBLIC_MIN_FREE_BYTES` | 2147483648 | Free-space floor of the public store; also the log's floor in public mode |
| `log_dir` | `WORKBENCH_LOG_DIR` | unset (standard error) | Folder of log segments |
| `log_segment_bytes` | `WORKBENCH_LOG_SEGMENT_BYTES` | 10485760 | One segment's size |
| `log_keep_bytes` | `WORKBENCH_LOG_KEEP_BYTES` | 209715200 | All segments together |
| `experiments_results` | `WORKBENCH_EXPERIMENTS_RESULTS` | unset (sibling checkout's `docs/results.json`) | Source of `/api/engineering/experiments` |
| `experiments_url` | `WORKBENCH_EXPERIMENTS_URL` | unset | Published page the experiment links lead to |
| `contract_state` | `WORKBENCH_CONTRACT_STATE` | unset (sibling checkout's `contract-state.json`) | Source of `/api/engineering/contract-state` |

Validator `_one_place_for_the_model` (`config.py:157`): setting both `WORKBENCH_MODEL_ON_SERVER` and
`WORKBENCH_MODEL_HOST` stops the start; `WORKBENCH_MODEL_ON_SERVER` with an Ollama host that is not loopback or a bare
service name (`[a-z][a-z0-9_-]{0,62}`) stops the start. `config.py` reads only `os.environ`; it does not load a `.env`
file.

### 7.5 The store

SQLite through SQLAlchemy 2 (`backend/app/db.py`). One file, `<data_dir>/workbench.db`, in WAL mode, plus files beside
it: originals at `documents/<sha256><suffix>`, memos at `memos/<name>.docx`, memo drafts in `memos/pending/<token>/`.

#### Engine (`db.make_engine`, `db.py:73`)

- `NullPool`: a SQLite connection is opened per session. A run holds its session for its whole life, and a fixed pool
  of 15 ran dry under load.
- `timeout=30`: a writer waits up to 30 s for another writer's lock.
- `hide_parameters=True`: an error message never prints bound values (contract text).
- On every connection: `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, `PRAGMA secure_delete=ON` (deleted bytes are
  overwritten, part of the retention promise).
- Fault tracking: a `handle_error` listener records SQLite error names. `SQLITE_CORRUPT` and `SQLITE_NOTADB` stay
  recorded until the process restarts; `SQLITE_IOERR`, `SQLITE_READONLY`, `SQLITE_FULL`, `SQLITE_CANTOPEN` clear at the
  next successful commit. Lock contention is not a fault. `store_fault()` feeds health and `backend/scripts/status.py`.

#### Tables (`backend/app/models.py`)

Ids: `new_id()` is the first 16 hex of a UUID4 for string keys; integer keys autoincrement. Times are
`DateTime(timezone=True)`; SQLite keeps naive UTC text (`YYYY-MM-DD HH:MM:SS.ffffff`), `models.as_utc` adds UTC back and
`models.iso` writes ISO 8601 with offset. "NN" = NOT NULL. Columns added after a table first existed are nullable, and
NULL means "recorded before this field existed".

**`documents`** (`models.py:95`): one reading of one set of bytes, shared by every workspace that uploads them.
Unique index `ux_documents_sha256_parser (sha256, parser_version)`; index on `sha256`. ORM cascade to `sections`.

| Column | Type | NN | Meaning |
|---|---|---|---|
| `id` | VARCHAR(32) PK | yes | |
| `name` | VARCHAR(255) | yes | first uploader's file name (workspace names live on `document_access.name`) |
| `media_type` | VARCHAR(64) | yes | type the bytes were checked as |
| `sha256` | VARCHAR(64) | yes | hash of the original bytes; names the file in `documents/` |
| `pages`, `parse_ms` | INTEGER, FLOAT | no | page count; reading time |
| `parser_version` | VARCHAR(16) | no | reader version (NULL = first reader) |
| `tracked_changes`, `hidden_runs` | INTEGER | no | DOCX revisions and hidden runs left out |
| `coverage_json` | TEXT | no | what the reading did with each part of the file |
| `created_at` | DATETIME | yes | |
| `size_bytes` | INTEGER | no | file size, for the daily byte quota (NULL before 2026-10-30) |

**`sections`** (`models.py:123`): FK `document_id` → `documents.id` ON DELETE CASCADE, indexed.

| Column | Type | NN | Meaning |
|---|---|---|---|
| `id` | VARCHAR(32) PK | yes | |
| `document_id` | VARCHAR(32) | yes | |
| `ordinal` | INTEGER | yes | order in the document |
| `number`, `heading` | VARCHAR(32), VARCHAR(512) | yes | clause number and heading as read (may be empty) |
| `text` | TEXT | yes | the section text quotes are found in |
| `part` | INTEGER | no | which split part (from 1), 0 if not split, NULL before reader v17 |

**`document_access`** (`models.py:141`): who may read a document. PK (`workspace_id`, `document_id`); FK `document_id`
ON DELETE CASCADE, indexed. A document with no row here is curated. Columns: `workspace_id` VARCHAR(32), `document_id`
VARCHAR(32), `created_at` DATETIME NN, `name` VARCHAR(255) nullable (the name this workspace gave the file).

**`visitor_workspaces`** (`models.py:156`): workspaces anonymous visits made. Retention deletes exactly these, once
ended. Columns: `workspace_id` VARCHAR(32) PK, `created_at` DATETIME NN (indexed), `expires_at` DATETIME NN (indexed).

**`document_versions`** (`models.py:167`): a workspace's statement that a document is a version in a line. Appended,
never edited. Unique index `(workspace_id, document_id)`; indexes on `workspace_id`, `lineage_id`, `document_id`. Both
document columns are FKs to `documents.id` with no cascade.

| Column | Type | NN | Meaning |
|---|---|---|---|
| `id` | INTEGER PK | yes | |
| `workspace_id` | VARCHAR(32) | yes | |
| `lineage_id` | VARCHAR(32) | yes | names the line |
| `document_id` | VARCHAR(32) | yes | this version |
| `supersedes_document_id` | VARCHAR(32) | no | the version before (NULL for the first) |
| `created_at` | DATETIME | yes | |

**`guidance`** (`models.py:189`): indexes on `sha256` and `workspace_id`. Columns: `id` PK, `text` TEXT NN, `sha256`
VARCHAR(64) NN, `source` VARCHAR(32) NN (default `pasted`), `created_at` NN, `workspace_id` VARCHAR(32) nullable (NULL =
curated).

**`runs`** (`models.py:201`): one question asked of one document. Partial unique index `ux_runs_fingerprint_active` on
`fingerprint` where `stage != 'failed'` (one running or completed run per input set; failed runs stay retryable).
CHECKs `ck_runs_stage`, `ck_runs_reason`. FKs `document_id` → documents, `guidance_id` → guidance (no cascade).
Indexes on `document_id`, `workspace_id`. ORM cascade to `stages` and `findings`.

| Column | Type | NN | Meaning |
|---|---|---|---|
| `id` | VARCHAR(32) PK | yes | |
| `document_id`, `guidance_id` | VARCHAR(32) | yes, no | inputs |
| `question` | TEXT | yes | |
| `stage` | VARCHAR(32) | yes | `RUN_STAGES` (default `reading`) |
| `provider`, `model` | VARCHAR(32), VARCHAR(128) | yes | who answered |
| `task`, `routing_reason` | VARCHAR(32), VARCHAR(255) | no | routing decision |
| `prompt_version`, `prompt_hash` | VARCHAR(64) | yes | |
| `options_json` | TEXT | yes | options (`retrieval_k`, window, ...) as JSON |
| `document_sha256`, `guidance_sha256` | VARCHAR(64) | yes, no | input hashes |
| `candidates_json` | TEXT | yes | sections handed to the model |
| `relations_json` | TEXT | no | located relations between provisions (policy-v11 on) |
| `retrieval_mode` | VARCHAR(32) | no | `RETRIEVAL_MODES` (not CHECKed) |
| `workspace_id` | VARCHAR(32) | no | owner workspace; NULL = curated (goldens, batches, pre-2026-10-02) |
| `raw_output` | TEXT | no | model output as received |
| `input_tokens`, `output_tokens`, `latency_ms` | INTEGER, INTEGER, FLOAT | no | |
| `note`, `error` | TEXT | no | |
| `reason` | VARCHAR(32) | no | `RUN_REASONS`; NULL on a complete run |
| `fingerprint` | VARCHAR(64) | no | identity of the inputs (chapter 5) |
| `created_at`, `finished_at` | DATETIME | yes, no | |
| `owner` | VARCHAR(128) | no | process that made it (host, pid, start) for recovery |

**`run_stages`** (`models.py:259`): FK `run_id` ON DELETE CASCADE, indexed. Columns: `id` INTEGER PK; `run_id` NN;
`stage` VARCHAR(32) NN; `at` DATETIME NN; `detail` TEXT; `completed_at` DATETIME; `duration_ms` FLOAT; `status`
VARCHAR(16) (`STAGE_STATUSES`, not CHECKed); `attempt` INTEGER (model calls); `rounds` INTEGER (validation rounds);
`input_hash`, `output_hash` VARCHAR(64); `error_code` VARCHAR(32); `owner` VARCHAR(128). The stage row id is the
`id:` of the event stream.

**`findings`** (`models.py:290`): FK `run_id` ON DELETE CASCADE, indexed. CHECKs `ck_findings_status`,
`ck_findings_status_source`. ORM cascade to `spans` and `reviews`. Properties: `shown_conclusion` (the fixed
`NOT_FOUND_CONCLUSION` sentence for `missing`), `withheld_conclusion`, `review` (latest review unless `cleared`).

| Column | Type | NN | Meaning |
|---|---|---|---|
| `id` | VARCHAR(32) PK | yes | |
| `run_id` | VARCHAR(32) | yes | |
| `ordinal` | INTEGER | yes | order in the run |
| `topic` | VARCHAR(255) | yes | |
| `status`, `status_source` | VARCHAR(32) | yes | pair limited by `STATUSES_BY_SOURCE` |
| `status_reason` | TEXT | no | the policy's sentence for a computed status |
| `conclusion` | TEXT | yes | the model's sentence, as recorded |
| `guidance_reference`, `observed`, `required` | VARCHAR(255) | no | |
| `suggested_position` | TEXT | no | |

**`evidence_spans`** (`models.py:336`): FK `finding_id` ON DELETE CASCADE (indexed); FK `section_id` → sections (no
cascade). Columns: `id` PK; `finding_id` NN; `ordinal` INTEGER NN; `section_id` nullable; `cited_section_label`
VARCHAR(32) NN; `start`, `end` INTEGER NN (default -1); `quote` TEXT NN; `verified` BOOLEAN NN; `method` VARCHAR(32) NN
(default `none`); `match_count` INTEGER nullable.

**`finding_reviews`** (`models.py:356`): appended, never edited; the latest row is the state. FK `finding_id` ON DELETE
CASCADE, indexed. CHECK `ck_finding_reviews_verdict`. Columns: `id` INTEGER PK; `finding_id` NN; `verdict` VARCHAR(16)
NN; `reviewer` VARCHAR(80) NN (typed name); `note` TEXT; `created_at` NN; `access_subject` VARCHAR(80) nullable (the
session subject, recorded beside the typed name).

**`batches`** (`models.py:378`): columns `id` PK, `task` VARCHAR(64), `task_sha256` VARCHAR(64), `corpus`
VARCHAR(255), `model` VARCHAR(128), `prompt_version` VARCHAR(64), `concurrency`, `documents`, `requested` INTEGER (all
NN), `started_at` NN, `finished_at` nullable. Numbers are computed from the runs, never stored.

**`batch_items`** (`models.py:399`): FK `batch_id` ON DELETE CASCADE; FKs `document_id`, `run_id` (no cascade); all
three indexed. Columns `id` INTEGER PK, `field` VARCHAR(64) NN, `reused` BOOLEAN NN, `wall_ms` FLOAT.

**`memos`** (`models.py:416`): unique index `ux_memos_run_review_content (run_id, review_head, content_sha256)`; FK
`run_id` (no cascade), indexed. Columns: `id` PK; `run_id` NN; `review_head` VARCHAR(64) (hash of the latest review
rows); `content_sha256` VARCHAR(64) (hash of what the memo says, NULL before it was kept); `docx_path` VARCHAR(512) NN;
`docx_sha256` VARCHAR(64) NN; `html` TEXT NN; `created_at` NN.

#### Vocabularies (declared once as `Literal` types in `models.py:22-58`, shared by ORM, schemas and run code)

| Name | Values | Enforced in the store by |
|---|---|---|
| `RUN_STAGES` | reading, finding_evidence, checking, verifying, complete, unresolved, failed | `ck_runs_stage` |
| `TERMINAL_STAGES` | complete, unresolved, failed | immutability triggers |
| `RUN_REASONS` | insufficient_evidence, citations_unverified, invalid_output, provider_error, internal_error | `ck_runs_reason` (or NULL) |
| `FINDING_STATUSES` | pass, needs_review, missing, unresolved | `ck_findings_status` |
| `STATUS_SOURCES` / `STATUSES_BY_SOURCE` | computed_days: pass, needs_review; confirmed_days: pass; model_hint: pass, needs_review, missing; no_evidence: unresolved; reference_check, position_check, ambiguous_fact: needs_review | `ck_findings_status_source` |
| `REVIEW_VERDICTS` | confirmed, dismissed, cleared | `ck_finding_reviews_verdict` |
| `STAGE_STATUSES` | running, ok, failed | code only |
| `RETRIEVAL_MODES` | lexical_match, hybrid_match, opening_fallback | code only |

#### Triggers (`db.py:305-384`)

- **Immutability** (`immutability_triggers`): `trg_<table>_no_update_when_finished` and `..._no_delete_when_finished`,
  `BEFORE UPDATE/DELETE`, `RAISE(ABORT, 'a finished run is immutable (<table>)')`, on `runs` (own stage terminal),
  `run_stages` and `findings` (their run terminal), `evidence_spans` (their finding's run terminal), and `sections` and
  `documents` (read by any terminal run). Reviews and memos are separate rows, so adjudication never edits the record.
- **Workspace guards** (`workspace_guards`): `trg_<table>_only_open_workspaces`, `BEFORE INSERT`, refuses a row whose
  `workspace_id LIKE 'pw-%'` and is not in `visitor_workspaces`. Applied to every table with a `workspace_id` column
  except `visitor_workspaces`, read off the models (today: `document_access`, `document_versions`, `guidance`, `runs`).
  The message contains `a public workspace that is not open takes no row`, which `main.store_refused` maps to 401.
- Both sets are SQLite-only. `db.py` cannot import `application.workspace.PUBLIC_PREFIX` (layering), so it repeats it
  as `PUBLIC_WORKSPACE_LIKE = "pw-%"`.

#### `init_db` (`db.py:115`)

1. `Base.metadata.create_all`: creates missing tables with their indexes, CHECKs and keys.
2. `ensure_columns`: for each existing table, `ALTER TABLE ... ADD COLUMN "<name>" <type>` for every model column
   missing (type only: no NOT NULL, no default); `CREATE INDEX IF NOT EXISTS` for every declared index; drops
   `SUPERSEDED_INDEXES` (`ux_memos_run_id`, `ux_memos_run_review` on `memos`). Additive only.
3. `ensure_checks`: compares each table's named CHECK bodies (whitespace-normalised, `check_bodies`) with a fresh
   in-memory store built from the models (`declared_tables`). A table that differs is rebuilt by `_rebuild`; a store
   that matches is only read.
4. `ensure_immutability`: creates both trigger sets (`IF NOT EXISTS`).

`_rebuild(table)` (`db.py:227`) follows SQLite's documented 12-step procedure in one `BEGIN IMMEDIATE` transaction with
foreign keys off: it first checks every row against the declared CHECKs and NOT NULLs and refuses (`StoreDrift`, start
aborted, nothing changed, up to 20 ids named) if any fails, or if the stored table has columns the models no longer
declare; it records row counts of every table and existing dangling references; drops all triggers; creates
`<table>__rebuilt` from the declared statement; copies the columns; drops and renames; recreates the table's indexes and
all triggers; and rolls back if any row count changed or a new dangling reference appeared. No backup file is written
(a copy of the public store would outlive retention). `describe_store` gives a whole-schema description used by
`tests/test_store_schema.py` to compare an upgraded store with a fresh one.

#### `write_locked(session)` (`db.py:388`)

Begins the session's next transaction with `BEGIN IMMEDIATE`, so nothing else can write between what is read inside and
the commit. Commits on exit, rolls back on any exception. Raises `RuntimeError` if the session already has an uncommitted
write, `NotImplementedError` on a non-SQLite database, and `Busy` 503 (Retry-After 5) if the lock is not had within the
30 s busy wait. Callers: `quotas.admit`, `recover_runs`, `review_finding`. Read and parse before it, never inside.

`quotas.admit(session, quotas, create, find)` (`application/quotas.py:249`) is the only way a quota-limited row is
written: `find` and the quotas are asked once without the lock (a repeat or an obvious refusal never waits), then under
`write_locked`: `find` again, every quota counted again, `create`, commit. It returns `(row, created)`. Callers:
`ingest_document` (the document and the grant), `start_run`, `save_guidance`, `versions.declare_supersedes`.

#### Retention (`application/retention.py`; public store only)

Runs at start and then hourly (7.1). One pass of `purge_expired_workspaces`:

1. `recover_interrupted_runs` (a run nobody reads again must still end).
2. `_reanchor`: a visit whose `created_at` is more than 60 s after now (the clock ran ahead or stepped back) is moved to
   begin now, keeping its own length of life; logged.
3. Candidates: workspaces in `visitor_workspaces` with `expires_at <= now`, plus `pw-` ids found in any workspace table
   but not registered (left by an earlier failure), the unregistered first.
4. `_purge_workspace`, in short transactions under `BEGIN IMMEDIATE` (`_locked`), each followed by a pause of 0.05–1 s
   (at least as long as the lock was held) so other writers get in:
   - Skip if the workspace is not ended after all, or has a run not in a terminal stage.
   - Transaction 1: if it has runs, drop the immutability triggers, delete the evidence spans and reviews of its
     findings, then its `memos`, `batch_items`, `findings`, `run_stages`, `runs`, and recreate the same triggers; in
     every case delete its `guidance` and `document_versions`. A failure rolls back rows and triggers together.
   - Memo files of those runs are unlinked by file name.
   - One transaction per document the workspace held or named in a version statement: delete its grant; if nothing else
     uses the document (another grant, a run, a version statement, a batch item), delete its `sections` and `documents`
     row, and unlink the original if no `documents` row still names the same sha256 (decided under the same lock an
     upload uses to decide reuse).
   - Last transaction: remaining grants, then the `visitor_workspaces` row (the resume key: a stopped pass is finished
     by the next).
5. `_checkpoint`: `PRAGMA wal_checkpoint(TRUNCATE)` with `busy_timeout` 0 so it never blocks writers; `checkpointed`
   is false if a reader held it up, and the next pass retries. With `secure_delete`, this is what removes deleted bytes
   from the WAL file.

Then `forget_process_state()` drops process caches derived from documents (trust re-readings, clause numbers, run start
records, `runs.links._use_of`, `re.purge()`), and `access.prune_windows()` drops sliding-window keys past their window.
Then `sweep_orphaned_files` removes, after a 1 h grace, files no row names: `documents/*.part`, `documents/<hash>.*`
with no row (decided again under the lock), `memos/*` not named by a memo row, abandoned `memos/pending/<token>/`
drafts, and `verity-reading-*` handoff files. A file counts as abandoned when this process has seen it unchanged for the
grace by its monotonic clock, or when its mtime is past the grace and the wall clock has not stepped more than 5 minutes
since the process started. A file the system refuses to delete (Windows holds open files) is kept, counted and logged;
the pass continues. An owner store lists no visitor workspaces, so retention can delete nothing there.

### 7.6 Layering (`backend/.importlinter`)

`lint-imports` (run from `backend/`) checks three contracts:

| Contract | Type | Rule |
|---|---|---|
| `verifier-is-pure` | forbidden | `app.verify` may import no other top-level module of `app`. `tests/test_import_contracts.py` checks that the forbidden list is exactly every other top-level module, and that `app/verify/*.py` imports only a fixed set of pure standard-library modules and calls no `open`, `eval`, `exec`, `compile`, `__import__`, `input`, `breakpoint` |
| `providers-know-nothing` | forbidden | `app.providers` may not import `verify`, `runs`, `models`, `db`, `api`, `application`, `analysis`, `retrieval`, `ingest` |
| `layers` | layers | higher layers may import lower ones; nothing imports upward |

The layers, top to bottom:

1. `app.api`
2. `app.batch | app.goldens | app.families`
3. `app.application`
4. `app.runs | app.routing | app.trust`
5. `app.analysis | app.retrieval | app.ingest | app.memo | app.policy`
6. `app.verify`
7. `app.providers`
8. `app.document_names : app.models : app.db : app.schemas : app.config : app.hashing : app.errors : app.unseen : app.log_sink`

In import-linter's syntax, `|` separates independent siblings (they may not import each other) and `:` separates
siblings that may import each other. So `api` may call anything; an `application` module may use `runs`, `ingest`, the
leaf modules and other `application` modules, but never `api` or `batch`; the leaf modules may import one another
(`models` imports `db`; `db` imports `config` and `errors`; `schemas` imports `models`) but nothing above them.
`app.main` (the composition root) and `app.serving` (imports nothing of the app) sit in no layer; the test's `EXEMPT`
table names them with their reasons, and any other module outside the layers fails the test.

### 7.7 File by file

| File | Job | Key names | Called by |
|---|---|---|---|
| `backend/app/__init__.py` | Empty package marker | none | |
| `backend/app/main.py` | Composition root: logging, lifespan, middleware, handlers, router mounting | `create_app`, `app`, `refuse_a_store_with_owner_records`, `_retain_hourly`, `_log_model_build`, `SECURITY_HEADERS` | uvicorn (`app.main:app`); `tests/conftest.py`; `backend/scripts/export_openapi.py` |
| `backend/app/serving.py` | The Windows event loop that survives client-reset accepts | `ResilientProactorEventLoop`, `ResilientSocketTransport`, `client_caused`, `ERROR_NETNAME_DELETED`, `ERROR_CONNECTION_ABORTED`, `REPORT_EVERY_SECONDS`, `RETRY_PAUSE_SECONDS` | uvicorn `--loop` in `deploy/supervise.ps1`, `deploy/up.ps1`; `tests/test_accept_resets.py` |
| `backend/app/config.py` | Every runtime setting, read once from the environment | `Settings`, `settings`, `json_headers`, `BACKEND_DIR`, `DEFAULT_OLLAMA_URL`, `SERVICE_NAME`, `Settings.sqlite_url` | nearly every module |
| `backend/app/errors.py` | Typed failures; each class carries its HTTP status | `WorkbenchError`, `NotFound`, `Conflict`, `InvalidInput`, `TooLarge`, `Busy`, `Paused`, `AccessRequired`, `Forbidden`, `TooManyRequests` | application and api modules; `main.workbench_error`; `api/contract.py` |
| `backend/app/log_sink.py` | One bounded log handler for every logger: lines cut at 2,000 chars (tracebacks 16,000), line breaks escaped, floods of a `shape` kept at 60 a minute with a count of what was left out, segments of `log_segment_bytes` with the oldest deleted past `log_keep_bytes`, lines below the disk floor dropped and counted | `configure`, `make_handler`, `BoundedFormatter`, `FloodShaping`, `SegmentedFileHandler`, `MESSAGE_CHARS`, `TRACE_CHARS`, `SHAPED_PER_MINUTE` | `main.py` at import; `tests/test_log_bounds.py` |
| `backend/app/schemas.py` | Every API shape (pydantic, camelCase on the wire). Groups: documents (`SectionOut`, `CoverageReport`, `DocumentOut`, `DocumentSummary`, lines 37-100), guidance and reviews (102-139), runs and findings (`RunIn`, `FindingOut`, `RunOut`, `RunSummary`, `FindingRecord`, `StageOut`, `CandidateOut`, `RunDetail`, 141-403), batches (405-464), memos (466-478), `HealthOut`, `ModelWakeOut`, `InviteIn`, `AccessOut` (480-519), citations, families, experiments, goldens (521-708), contract state `State*` (710-897), explanation (899-1049), trust and versions (1051-1173) | `ApiModel`, `ErrorOut`, `added_later` (marks fields a client must not require) | api routers; application modules that build outputs; `openapi.json` |
| `backend/app/models.py` | Tables, vocabularies, time helpers | the 14 table classes, `RUN_STAGES`, `TERMINAL_STAGES`, `FINDING_STATUSES`, `RUN_REASONS`, `STATUSES_BY_SOURCE`, `REVIEW_VERDICTS`, `STAGE_STATUSES`, `RETRIEVAL_MODES`, `NOT_FOUND_CONCLUSION`, `new_id`, `utcnow`, `as_utc`, `iso`, `CLOCK_SKEW`, `issued_in_future` | everything that touches the store |
| `backend/app/db.py` | Engine, sessions, schema upkeep, triggers, the write lock, fault tracking | `make_engine`, `engine`, `SessionLocal`, `get_session`, `session_scope`, `init_db`, `ensure_columns`, `ensure_checks`, `_rebuild`, `StoreDrift`, `check_bodies`, `describe_store`, `declared_tables`, `immutability_triggers`, `workspace_tables`, `workspace_guards`, `ensure_immutability`, `refused_as_not_open`, `write_locked`, `note_store_error`, `store_fault(s)`, `SUPERSEDED_INDEXES` | routers (`get_session`), `main.py`, application modules, scripts (`init_db`, `SessionLocal`). `session_scope` has no caller in `app/` or `backend/scripts/` (grep) |
| `backend/app/api/__init__.py` | Empty package marker | none | |
| `backend/app/api/access.py` | The gate, tokens, sessions, visits, workspaces of a request, every sliding window and switch | `require_access`, `current_workspace`, `current_session`, `workspace_for`, `mint`, `verify`, `check_configuration`, `client_network`, `SlidingWindow`, `prune_windows`, `limit_run_starts`, `limit_public_writes`, `limit_pack_downloads`, `limit_document_reads`, `admit_upload`, `refuse_upload_on_headers`, `owner_only`, `paused`, `refuse_if_paused`, `refuse_if_disk_low`, `packs_building`, `trust_reads_building`, routes `access`, `enter`, `visit` | `main.py`, every router, `body_limit.py`, `in_flight.py`, `health.py`; `backend/scripts/access.py` (mint, verify) |
| `backend/app/api/batches.py` | Batch reports and the values CSV | `router`, `batches`, `batch`, `batch_values_csv`, `spreadsheet_cell`, `CsvResponse` | `main.py` |
| `backend/app/api/body_limit.py` | ASGI middleware bounding every body, and uploads at the door | `BodyLimitMiddleware`, `body_limit`, `BodyRefused`, `BodyTooLarge`, `BodyStalled`, `SpoolFull`, `UPLOAD_REQUEST_LIMIT`, `JSON_REQUEST_LIMIT`, `UPLOADS_PER_NETWORK`, `SPOOL_BUDGET`, `BODY_IDLE_SECONDS`, `BODY_GRACE_SECONDS`, `BODY_MIN_RATE` | `main.py` |
| `backend/app/api/contract.py` | Builds each route's declared responses from the error classes | `error_responses`, `merged`, `GATED`, `WRITES`, `INVALID`, `FOUND`, `CONFLICT`, `held_or_created`, `media`, `Responses` | every router |
| `backend/app/api/deps.py` | The provider dependency | `get_provider` | `runs.py` |
| `backend/app/api/documents.py` | Upload, list and read documents; the reading turn | `router`, `upload_document`, `list_documents`, `get_document`, `to_document_out`, `reading_turn`, `READING_WAIT_SECONDS`, `readings`, `reading_threads`, `STALLED` | `main.py` |
| `backend/app/api/engineering.py` | Research records: experiments, contract state (open), citations, families, goldens | `router`, `public_router`, `load_experiments`, `load_contract_state`, `results_path`, `contract_state_path`, `CONTRACT_STATE_SCHEMA`, `DEFAULT_RESULTS`, `DEFAULT_CONTRACT_STATE` | `main.py` |
| `backend/app/api/findings.py` | Review a finding; list findings across runs | `router`, `review`, `list_findings` | `main.py` |
| `backend/app/api/guidance.py` | Save and read guidance | `router`, `create_guidance`, `get_guidance` | `main.py` |
| `backend/app/api/health.py` | Health, store problems, the cached model probe, where the model runs | `router`, `health`, `storage_problem`, `probe_model`, `model_location`, `MIN_FREE_BYTES`, `HEALTH_PROBE_TTL_S`, `LOOPBACK` | `main.py` (also `health.MIN_FREE_BYTES` for the log floor) |
| `backend/app/api/in_flight.py` | ASGI middleware: requests in flight per network and open streams (public store) | `InFlightMiddleware`, `in_flight`, `streams_open`, `IN_FLIGHT_WAIT_S`, `NETWORK_BUSY`, `STREAMS_BUSY` | `main.py`; `tests/test_liveness.py` |
| `backend/app/api/memos.py` | Create memos; serve HTML and DOCX | `router`, `create_memo`, `memo_as_html`, `memo_as_docx`, `MEMO_POLICY`, `DOCX` | `main.py` |
| `backend/app/api/model.py` | Wake the model ahead of a question | `router`, `wake`, `address_wakes`, `WAKES_PER_NETWORK` | `main.py` |
| `backend/app/api/runs.py` | Start, list and read runs; explanation, evidence pack, event stream; the run worker | `router`, `create_run`, `list_runs`, `get_run`, `get_run_detail`, `get_run_explanation`, `evidence_pack`, `run_events`, `run_out`, `run_detail`, `run_summary`, `finding_out`, `relation_out`, `runs_ahead`, `provider_for`, `RUN_EXECUTOR`, `HEARTBEAT_SECONDS` | `main.py`; `finding_out`/`run_out` also by tests and scripts (not traced) |
| `backend/app/api/trust.py` | Trust manifest, revision diff, version statements and lineage | `router`, `run_trust`, `run_trust_diff`, `record_supersedes`, `document_versions`, `manifest_out`, `diff_out`, `version_out`, `_trust_read`, `TRUST_READ` | `main.py` |
| `backend/app/application/workspace.py` | Who may read what; the loaders that refuse like a miss | `PUBLIC_PREFIX`, `is_public`, `document_is_curated`, `can_read_document`, `can_read_run`, `can_read_guidance`, `grant_document`, `require_document`, `require_run`, `require_guidance`, `require_finding`, `require_memo`, `require_own_run`, `visible_runs`, `visible_documents` | routers, `quotas.py`, `ingest_document`, `recover_runs`, `citation_record`, `access.py` |
| `backend/app/application/quotas.py` | Store-counted quotas and the one admission primitive | `Quota`, `daily`, `day_start`, `seconds_to_tomorrow`, `workspace_open`, `document_quotas`, `run_quotas`, `refuse_if_spent`, `admit`, `VISIT_ENDED` | `ingest_document`, `start_run`, `save_guidance`, `versions`, `api/access.admit_upload`, `api/model.wake`, `main.store_refused` |
| `backend/app/application/retention.py` | Deleting ended visitor workspaces; the orphan sweep; process forgetting | `purge_expired_workspaces`, `PurgeReport`, `sweep_orphaned_files`, `forget_process_state`, `_purge_workspace`, `_reanchor`, `_checkpoint`, `_locked`, `SWEEP_GRACE`, `WALL_STEP_TOLERANCE`, `PURGE_GAP_S`, `PURGE_GAP_MAX_S` | `main._retain_hourly`; tests |
| `openapi.json` | The generated API contract (OpenAPI 3.1, title Verity, version 0.1.0, 34 operations) | | `npm run api:types` → `src/lib/api.schema.ts`; `tests/test_api_contract.py`; `tests/test_api_fuzz.py` reads the app's own `/openapi.json` |
| `backend/.importlinter` | The three import contracts (7.6) | | `lint-imports`; `tests/test_import_contracts.py`; `scripts/release-gate.sh` |
| `backend/pyproject.toml` | Check settings: ruff (line length 160, target py313, rule sets E W F I UP B BLE ANN SIM PIE RET C4 RUF PT T20; ignores PT018, RUF001-003; `fastapi.Depends` immutable), mypy strict on `app`, `scripts`, `tests` (Python 3.13), pytest `testpaths = ["tests"]` | | developers, the release gate |
| `backend/requirements.lock` | Exact runtime and test pins (34 lines), among them fastapi 0.141.1, starlette 1.7.0, SQLAlchemy 2.1.1, pydantic 2.13.5, uvicorn 0.54.0, anyio 4.15.1, pypdf 6.21.2, python-docx 1.2.0, lxml 6.1.3, rank-bm25 0.2.2, python-multipart 0.0.32, httpx 0.28.1, pytest 9.1.1 | | the release gate builds the backend from it |
| `backend/requirements-dev.txt` | Check-only tools: ruff 0.16.9, mypy 2.3.1, lxml-stubs 0.5.1, hypothesis 6.168.3, import-linter 2.15, schemathesis 4.28.0 | | `pip install -r requirements.lock -r requirements-dev.txt` |

`backend/requirements.txt` (unpinned names) sits beside these and is not in this chapter's slice. Python 3.13 is
assumed throughout (`admit[T]` uses the PEP 695 generic syntax).

**Matched by this chapter's enumeration glob but documented elsewhere.** `git ls-files backend/app/*.py` matches across
folders. These files belong to chapters 4 to 6: `document_names.py`, `hashing.py`, `unseen.py`; `analysis/`
(`__init__.py`, `schema.py`, `service.py`); `application/` (`__init__.py`, `citation_record.py`,
`clause_location.py`, `create_memo.py`, `evidence_pack.py`, `explain_run.py`, `ingest_document.py`,
`reconstruct_input.py`, `recover_runs.py`, `reverify_run.py`, `review_finding.py`, `save_guidance.py`, `start_run.py`,
`trust_run.py`, `versions.py`, `visible_input.py`, `wake_model.py`); `batch/` (`__init__.py`, `cuad_match.py`,
`service.py`); `families/` (`__init__.py`, `fingerprint.py`, `service.py`); `goldens/` (`__init__.py`, `replay.py`,
`service.py`); `ingest/` (`__init__.py`, `bounded.py`, `coverage.py`, `invisible.py`, `pdf_layout.py`, `readers.py`,
`sections.py`, `terms.py`, `word_display.py`); `memo/` (`__init__.py`, `service.py`, `visible.py`); `policy/`
(`__init__.py`, `durations.py`, `proof.py`); `providers/` (`__init__.py`, `admission.py`, `base.py`, `ollama.py`,
`replay.py`); `retrieval/` (`__init__.py`, `aliases.py`, `hybrid.py`, `lexical.py`); `routing/` (`__init__.py`,
`router.py`); `runs/` (`__init__.py`, `account.py`, `events.py`, `links.py`, `owner.py`, `prose.py`, `relations.py`,
`service.py`, `status.py`, `transitions.py`, `values.py`, `versions.py`); `trust/` (`__init__.py`, `compile.py`,
`diff.py`, `facts.py`, `model.py`); `verify/` (`__init__.py`, `spans.py`, `tokens.py`).

### 7.8 Changing this part safely

Run the checks of section 9 before calling any change done (`ruff`, `mypy`, `lint-imports`, `pytest`). The tests named
here live in `backend/tests/`.

#### Add a route

1. Put it on an existing router in `backend/app/api/`, or a new router module. A new router must be mounted in
   `main.create_app` with the right guard (`gate`, `writes`, `owner_only`, or `limit_run_starts`). Only health, the
   access routes and `/api/engineering/contract-state` are open; an open route must be added to `OPEN` in
   `tests/test_access.py`, deliberately.
2. Take the workspace from `Depends(current_workspace)` and load records only through the `require_*` loaders or the
   `visible_*` filters (`application/workspace.py`). A write to a run or what hangs from it needs `require_own_run`.
3. Keep business rules in an `application/` module; the route maps input to a call and the result to a schema in
   `schemas.py`. Raise `errors.py` classes; never build a status code by hand.
4. Declare responses with `api/contract.py` (`GATED` is on the router; add `WRITES`, `INVALID`, `FOUND`, `CONFLICT`,
   `held_or_created`, `media` as the route can send them).
5. A body larger than 1 MiB needs a change to `body_limit.body_limit`. A heavy read in the public store needs a window
   or a semaphore (see `limit_document_reads`, `packs_building`). A route that must answer while the thread pool is
   full must be `async` and do no blocking work (only health is).
6. Regenerate the contract: `cd backend && python scripts/export_openapi.py`, then `npm run api:types`. Commit both
   `openapi.json` and `src/lib/api.schema.ts`.

Tests that cover a new route without being edited: `tests/test_access.py::test_every_route_but_health_and_the_gate_refuses_a_request_with_no_session`,
`tests/test_api_contract.py` (committed contract equals the code; every answer of a seeded store matches its
declaration; every raised error class is declared), `tests/test_api_fuzz.py` (Schemathesis over every operation but the
event stream), `tests/test_body_limit.py` (every route refuses an oversize body before its gate),
`tests/test_liveness.py::test_every_route_but_health_and_streams_is_counted`, `tests/test_cache_headers.py`. Add your
own isolation cases to `tests/test_workspaces.py` (invite gate) and `tests/test_anonymous.py` (public store), and a
query-count case to `tests/test_read_cost.py` for a list.

#### Add a setting

1. Add a field to `Settings` in `config.py` with `os.environ.get("WORKBENCH_<NAME>", <default>)` and a comment saying
   what it bounds and why that default. The default must be safe on a laptop and in tests.
2. Read it as `settings.<name>` at call time, not into a module constant, unless it must be fixed for the process
   (as `access.RUN_LIMIT` is). A module constant ignores test patches of `settings`.
3. If the deployment needs a non-default value, set it in `deploy/supervise.ps1` (chapter 9) and record the decision in
   `DECISIONS.md`.
4. Tests patch `config.settings` attributes with `monkeypatch`; to prove the environment is read, start a fresh
   interpreter as `tests/test_access.py:251` does. Validation rules go in a `model_validator` and are tested by building
   `config.Settings(...)` directly (`tests/test_health_model.py`). Update the table in 7.4.

#### Add a table or a column

1. Declare it in `models.py`. A new column on an existing table must be nullable (`Mapped[X | None]`,
   `nullable=True`): `ensure_columns` adds it with its type only, and NULL must mean "recorded before this field".
   `tests/test_store_schema.py::test_an_old_store_opens_described_as_a_fresh_store_is` fails if an upgraded store and a
   fresh one differ.
2. New indexes are created on existing stores by `ensure_columns`. To replace an index, add the old name to
   `db.SUPERSEDED_INDEXES`.
3. A new or changed CHECK makes `ensure_checks` rebuild the table at the next start. Widening a vocabulary is safe;
   narrowing it stops the start with `StoreDrift` if any stored row breaks it. Put a vocabulary in `models.py` as a
   `Literal` and derive the CHECK from it, as `RUN_STAGES` does (`tests/test_db_columns.py::test_api_schemas_carry_the_shared_vocabularies`).
4. Do not remove a model column: the column stays in old stores, and a later rebuild of that table refuses to drop it.
5. Rows of a finished run cannot be updated or deleted. New facts about a finished run are new rows (as reviews and
   memos are). A new table hanging from a run that must be immutable needs its own entry in
   `db.immutability_triggers`.
6. A table with a `workspace_id` column gets a workspace guard trigger automatically
   (`tests/test_workspace_rows.py::test_every_table_keyed_by_a_workspace_is_guarded`) and is scanned for unregistered
   workspaces by retention. Its rows are not deleted automatically: add the delete to `retention._purge_workspace`
   (and to `refuse_a_store_with_owner_records` if it can hold owner rows), and write rows through `quotas.admit` with
   `workspace_open(workspace)`. Extend `ROWS` in `tests/test_workspace_rows.py`, which asserts it covers every
   workspace table, and `tests/test_retention.py`.
7. Tests: `tests/test_db_columns.py`, `tests/test_store_schema.py`, `tests/test_uniqueness.py`,
   `tests/test_backup_restore.py`, `tests/test_retention.py`, `tests/test_workspace_rows.py`.

#### Add a quota or a limit

- **Counted in the store** (it must hold across processes and restarts, or decide whether a row is written): add a
  `Quota` (limit from a setting, a `count(session)`, a `refusal()` returning a `TooManyRequests` with `retry_after`, or
  `Busy`) to `document_quotas`, `run_quotas` or a new tuple in `application/quotas.py`. Use `daily(...)` for a per-day
  bound and pass the row's own instant (`at=`). Enforce it only through `admit(session, quotas, create, find)`; an
  early `refuse_if_spent` in the api layer may spare work but decides nothing. Tests: `tests/test_quota_admission.py`
  (concurrent requests stop exactly at the cap, each with a one-at-a-time control), `tests/test_write_lock.py`,
  `tests/test_quota_instant.py`, `tests/test_day_rollover.py`, `tests/test_daily_budget.py`,
  `tests/test_anonymous.py`.
- **A rate in process memory** (per network or per workspace, forgiven on restart): create an
  `access.SlidingWindow(limit, window_s)` at module level, key it by `client_network(request)` (never the raw
  address) or the workspace, and refuse through `access._take` so the answer is a 429 with Retry-After.
  `prune_windows` covers it automatically. Add its `reset()` to the `public` fixture in `tests/conftest.py`, or tests
  leak counts into one another. Tests: `tests/test_network_windows.py`, `tests/test_process_state.py`.
- **Concurrency at the door** (requests or bytes held at once): extend `api/in_flight.py` or `api/body_limit.py`; both
  count on the event loop only, so no lock is needed there. Tests: `tests/test_liveness.py`, `tests/test_body_limit.py`.
- Every refusal must say which bound refused and when it lifts. Update the limit tables in 7.3 and `docs/STATUS.md`.

## 8. The interface

**Frontend supplement, 2026-11-01:** [FRONTEND-POLISH.md](FRONTEND-POLISH.md) records the owner-requested refinement,
its responsibilities, observed issues, and browser validation. The historical release counts above remain unchanged.

**Desktop session supplement:** [SESSION-STATES.md](SESSION-STATES.md) inventories empty, populated, failed and
interrupted states. `RunsView` guards the latest record selection and restores list scroll/focus; `FindingsView` keeps
decision errors beside their row; `AssistantPanel` offers explicit recovery without showing stale progress as live.

The interface is a Next.js 16.4.1 App Router application in `src/`, written in TypeScript with React 19.2.8 and
framer-motion for motion. It renders what the API recorded and decides nothing: no evidence check, no status, no
review rule lives here. This chapter covers every tracked file under `src/` and `e2e/`, and the frontend configuration
files at the repository root. It was checked against commit `865356b` by reading files only; nothing was built, run
or served. Where a fact could only be confirmed by running the app, it says "not verified".

The rule under the whole chapter, enforced by lint (`eslint.config.mjs`) and stated in `AGENTS.md`:

| Next.js and React own | FastAPI and the application layer own |
|---|---|
| presentation, interaction, URL state, following a run's events, rendering the document, motion, the command palette | run creation, retrieval, model calls, quote verification, finding status, reviews, idempotency, memos, persistence |

Components reach the API only through `src/lib/api.ts`, and its types only through `src/lib/types.ts`. A raw `fetch`,
a raw `EventSource` or an import of `api.schema` in `src/components/**` or `src/app/**` is a lint error. The two
exceptions are written in place with a disable comment: fetching a bundled sample file (`Workbench.tsx` `loadSample`,
`RevisionCheck.tsx` `readPrepared`), which are static files of the page's own origin, not API calls.

### 8.1 Pages, URL state and history

#### Routes

| Route | File | Kind | What renders |
|---|---|---|---|
| `/` | `src/app/page.tsx` | client page | `Workbench` (the access gate, then the landing, then the workspace). In the static export (`NEXT_PUBLIC_EXPORT=state`) it renders `StateStory` instead. |
| `/break` | `src/app/break/page.tsx` | server page | `BreakStory`, fed `forPage(break-record.json)` on the server so the browser receives only what the page shows. Returns 404 in the static export unless `NEXT_PUBLIC_WORKBENCH_URL` is set. |
| `/state` | `src/app/state/page.tsx` | server page | `StateStory`, which fetches the contract-state record in the browser. |
| `/icon.svg` | `src/app/icon.svg` | file convention | The favicon. |
| anything else | none | Next default | Next's built-in 404 page (no custom `not-found.tsx` exists). |

There are no route handlers, server actions or API routes in `src/app`. `/api/*` on the live site is the FastAPI
process behind the same origin (chapter 7). `src/app/layout.tsx` wraps every page: it loads the three fonts, sets the
metadata (title and description differ for the static export), adds a "Skip to content" link to `#main`, and calls
`await connection()` so every page renders per request (needed for the script nonce, section 8.3).

#### `/`: what a visitor sees

1. **The door** (`access/AccessGate.tsx`). Before anything else mounts, the gate asks `GET /api/access`. Its states:
   `checking` ("Opening the workbench"), `open` (children render), `closed` (asks for an invite link in one field),
   `unavailable` (a public demo visit was refused; "Try again"), `ended` (a demo workspace expired while the page was
   open; "Start a new workspace"), `switch` (an invite for another reader arrived while this browser is inside; the
   person chooses). In a public demo (`anonymous: true`) a browser with no session is given one at once with
   `POST /api/access/visit`, serialised across tabs with the Web Locks API. An invite in the address fragment
   (`#invite=<token>`) is exchanged for a session cookie and removed from the address bar. Any 401 from any request
   fires `verity:access-required` on `window`, and the gate closes. The gate provides three React contexts
   (`access/PublicDemo.tsx`): `PublicDemo` (retention days, or null), `AccessModeKnown` (false when `/api/access`
   failed, so nothing claims "public" or "private"), and `Reader` (the invited reader's name).
2. **The landing** (`landing/Landing.tsx`, shown while `view === "assistant"` and `stage !== "workspace"`). Top bar:
   the mark (goes home), a mode label ("Public demo", "Open preview", "Private preview" or "Preview"), "Inside as <name>" for an
   invited reader, and `TopLinks` ("Break it" `/break`, "Research" `/state`, "Source" GitHub). Then a kicker, the title "Ask
   about a contract. See who decided each answer.", one lead paragraph, the primary button "Try the amendment
   challenge" (loads the synthetic amended sample), a link to `/break`, the drop box (a question textarea plus "Drop a
   contract here" and "Add a contract"), "try a sample agreement" (the real Common Paper agreement), the public-demo
   retention note, health notices (API unreachable, store fault, model offline), and "Recent contracts" (the first
   three documents `GET /api/documents` lists). Beside it, a receipt for one finished run ("A finished review" for the configured proof run,
   else "Your latest run") with "Open the review", and a four-step list "How each status is set". Below the fold,
   `LandingStory.tsx` renders `RecordPipeline` (the store's own counts), `OneRun` (only for the configured proof run)
   and `Refusals` (what Verity will not do). The footer says where the model runs and carries the independence
   sentence (`src/lib/independence.ts`).
3. **Upload in progress.** While a file is read the drop box shows its name and "Reading document", then "Ready" for
   450 ms, then the workspace opens. A question typed on the landing is asked once the contract opens.
4. **The workspace.** A left rail and one of four views, chosen by the rail: Review (`assistant`), Documents,
   Findings and Runs. Section 8.2 covers each.

#### `/break`

A long single-column page (`break/BreakStory.tsx`) that tells one recorded failure: a real question about a real SEC
exhibit, an answer whose quote was found word for word and passed every check, and that gave a right to the wrong
party. Sections, each an anchor in the top nav: `#failure`, `#investigate` (tabs Input, Retrieved, Output, What code
checked, Adjudication, with a session switch), `#fix` (the rejected deterministic fix and its scores on seen and
unseen cases), `#counterexample` (one rule, one catch, one false alarm), `#your-turn`, and sources. The page reads
only `break-record.json`; it calls no API and runs no model (the browser flow asserts no `/api/` request).

#### `/state`

`story/StateStory.tsx` tells the frozen contract-state experiment in moments: a hero funnel, `#certificate`,
`#arrival` (one recorded arrival, chosen with an arrival picker), `#comparison` (the predecessor engine),
`#audit` (the gate that did not pass), `#authorization` (scopes) and `#engineering`. It fetches the record with
`getContractState()`: `GET /api/engineering/contract-state` on the live site, or the file `/contract-state.json`
beside the page in the static export. If the record fails to load it says so with a retry; if the API says the record
is not connected it says that. It never invents numbers.

#### URL parameters

| Where | Parameter | Written when | Read on load and on Back/Forward |
|---|---|---|---|
| `/` | `document=<id>` | a contract is open in the workspace | opens that document (`openDocument`) |
| `/` | `run=<id>` | a run is on screen beside its document | opens the run, its document and its guidance (`openRun`); a `document` beside it is ignored, since the run names its document |
| `/` | `finding=<id>` | the evidence drawer is open, on the Review view | opens the run and then that finding's drawer (memo citations link here) |
| `/` | `view=documents\|findings\|runs` | a non-Review view is shown (Review writes no `view`) | shows that view; with `run` or `document`, those load in the background |
| `/` | `#invite=<token>` | never (arrives in an invite link) | exchanged for a session, then removed with `replaceState` |
| `/state` | `?arrival=<n>` (1-based) | the reader picks an arrival (`replaceState`, no history entry) | the arrival shown; invalid values fall back to the record's featured arrival |
| `/state`, `/break` | `#<section>` | in-page nav links | `/state` scrolls to it once the record has rendered; a damaged fragment scrolls nowhere (`lib/address.ts safeDecode`) |

Every id read from the address goes through `lib/api.ts` `route` and `recordId`: a value that is not
`[A-Za-z0-9_-]{1,32}` raises `RecordIdError` before any request, and the workbench says "This link does not name a
run: it is damaged, or it was not made by Verity." A 404 says the record "cannot be opened in this workspace".

#### Back and Forward (`hooks/useUrlState.ts`)

- On mount the hook applies the address once (`apply`, line 38). On every `popstate` it applies it again.
- After every state change it writes the address. A move is a `pushState`; moves within 600 ms of the last push
  (`COALESCE_MS`) are one move and use `replaceState`, so one click that passes through several states leaves one
  history entry.
- While a restore is on its way (the run or document is still loading), the hook leaves the address alone, for up to
  5 s (`RESTORE_PATIENCE_MS`). When the state arrives, an address that named it differently (parameters in another
  order, a stale `document` beside a `run`) is corrected in place with `replaceState`; Back still leaves the page.
- An address with no parameters sends the workbench home (the landing).
- A run in flight is written to the address as soon as it exists, so a reload mid-run reattaches to it.

### 8.2 The workbench

#### Layout

```
+------+-------------------------------------+--+------------------------------------+
| Rail | DocumentPane (the contract, paper)  |  | AssistantPanel                     |
|  mark| EvidenceSpine: a mark per quote     |  | "Questions"            [Ctrl K]    |
|  Srch| "Contract" / name / meta            |D | Scope: [doc chip] [+ Add guidance] |
|  Docs| coverage note, structure notice     |i | --------------------------------   |
|  Revw| 1  Heading                          |v | suggestions  OR  the thread:       |
|  Find|    body text ... <mark>quote</mark> |i |   question, StageList | cards      |
|  Runs| 2  Heading ...                      |d |   withheld list, relations, memo   |
|      | sample attribution (if a sample)    |e |   run meta, RevisionCheck          |
|      |                                     |r | composer note, textarea, Send      |
|      |                                     |  | [EvidenceDrawer slides over panel] |
+------+-------------------------------------+--+------------------------------------+
```

The split is a CSS grid, `${docWidth}% 8px minmax(0, 1fr)` (`Workbench.tsx:715`). The document width defaults to
62%, stays within 45 to 75%, and persists for the tab in `sessionStorage` key `workbench.docWidth`
(`hooks/useDocWidth.ts`). The divider (`workspace/Divider.tsx`) drags with the pointer, moves 2% per Left/Right
arrow, moves to its bounds on Home/End, and resets on double-click. Resize keys do not scroll the page. At 640 px wide or less (`NARROW_QUERY`, `shell/constants.ts`, kept in
step with `@media (max-width: 640px)` in `Workbench.module.css`) one pane shows at a time, chosen by an "Answer /
Contract" toggle; the drawer becomes a sheet over the answer, and controls that would mark a passage in the hidden
contract show the passage in the sheet instead.

#### Shell state (`Workbench.tsx`)

- `stage`: `"empty" | "dragging" | "processing" | "workspace"` (`shell/constants.ts`). The landing shows while the
  view is Review and the stage is not `workspace`.
- `view`: `"assistant" | "documents" | "findings" | "runs"`. Only Review needs a document.
- `doc`, `sample` (which bundled sample is open), `notice` (the latest refusal or failure, shown on whichever view
  the reader is on), `evidence` (the finding whose drawer is open), `highlight` and `lit` (the marked passage and
  the section glow, 1.6 s), `paletteOpen`, `composerText`, `narrowPane`.
- The run is not shell state: it is the run follower's (section 8.3), read through `beside(follower, doc.id)` so a
  run is only ever shown beside its own contract.
- **The newest intent owns the screen.** Every open, upload, question and return home calls `beginAction()`, which
  takes a claim token from the follower; after each `await` the code checks the claim and puts nothing on screen if
  a newer intent came since (`Workbench.tsx:130`, used in `loadFile`, `loadSample`, `openDocument`, `openRun`).
- **One run at a time.** `ask` returns early while `runs.live` is true (`Workbench.tsx:312`); the composer's Enter,
  the Send button and the palette all respect it.
- The tab title is `"<screen> · Verity"`: the view name, or the open contract's name without extension.
- A visually hidden `aria-live="polite"` region announces stage changes and "N findings ready".

#### Features and where they live

| Feature | What the visitor does and sees | Implemented in |
|---|---|---|
| Upload by drop | Drag a file anywhere over the landing; "Release to add the contract"; drop | `hooks/useDropZone.ts` (window listeners while no contract is open in the workspace, no upload is running and the API is reachable), `Workbench.tsx loadFile` |
| Upload by picker | "Add a contract" (landing), "Add" (Documents) | hidden `<input type=file accept=".pdf,.docx,.txt">` in `Workbench.tsx`, `loadFile` |
| Sample agreement | "try a sample agreement": Common Paper Cloud Service Agreement, CC BY 4.0, unmodified | `samples.ts` (`SAMPLES.standard`, `/samples/cloud-service-agreement.docx`), `Workbench.tsx loadSample` |
| Amendment challenge | "Try the amendment challenge": a synthetic agreement whose amendment replaces a clause; three ready questions (as amended, as originally signed, at a date) | `samples.ts` (`SAMPLES.amended`, `/samples/linen-services-agreement-amended.pdf`, `questions`), `suggestionsFor` |
| Refused upload | "<name> was not added: <API reason>", on the view the file was added from | `Landing.tsx refusal`, `Workbench.tsx` `notice` |
| Ask a question | Type in the composer (max 2,000 characters, `MAX_QUESTION_CHARS`), Enter or Send; or click a numbered suggestion | `assistant/AssistantPanel.tsx`, `Workbench.tsx ask`, `hooks/useRunFollower.ts ask` |
| Run progress | Stages "Reading contract", "Finding relevant language", "Checking" (or "Checking against guidance"), "Verifying citations", each with the API's detail and a seconds clock; a note on queue position or a sleeping hosted model | `assistant/StageList.tsx`, `lib/types.ts STAGE_LABELS` |
| Reconnect | After a dropped stream: the error, "If the server is still running, so is the question", and "Reconnect" | `AssistantPanel.tsx`, `useRunFollower.resume` |
| Add guidance | "+ Add guidance" chip opens a popover with a default draft; "Use" saves it (`POST /api/guidance`); the chip shows its first 44 characters; x removes it; Escape closes and keeps the draft | `assistant/GuidanceScope.tsx`, `hooks/useGuidance.ts` (`DEFAULT_GUIDANCE`) |
| Review against instructions | The first general suggestion is the literal question "Review against instructions", asked with whatever guidance is attached | `AssistantPanel.tsx ASSISTANT_SUGGESTIONS` |
| Answer cards | Topic, status chip, conclusion, a collapsed "The model also wrote a sentence · withheld" when present, one evidence row per located passage (label and a 150-code-point excerpt), code's value and unseen-section notes, relation notes, a "What was checked" ledger (rows tagged code / model / person / -), and "View in document", "Inspect evidence", "Ask another question" | `assistant/FindingCard.tsx`, `lib/checks.ts checkLedger valueNotes unseenNote` |
| Status chip | The status in words that say who decided: "Model's answer", "Within guidance (model's view)", "Within guidance (confirmed by code)" (records made under policy-v2 only), "Needs review", "Not found in the sections read (model's view)", "Unresolved" | `shell/primitives.tsx StatusChip`, `lib/types.ts statusLabel` |
| Unresolved or failed run | A title from the recorded reason, the API's sentence, the withheld proposals struck through, "Try again" for a failed run | `assistant/RunOutcome.tsx`, `lib/types.ts REASON_TITLES` |
| Withheld proposals | "What the model proposed · withheld by the verifier": each quote and "not found verbatim in ..." | `RunOutcome.tsx WithheldList` |
| Contract's own statements | Replacement and precedence statements code located in the sections read, with both ends opening the document; ones no answer accounts for listed under the answers | `assistant/RelationNotes.tsx` (`RelationNotes`, `UnclaimedRelations`), `lib/diff.ts` |
| Highlight in document | Clicking a citation row, "View in document", a spine mark or a drawer passage scrolls the paper to the exact quote and marks it | `Workbench.tsx jumpTo`, `hooks/useHighlightScroll.ts`, `workspace/DocumentPane.tsx SectionBlock`, `workspace/EvidenceSpine.tsx` |
| Evidence drawer | "Inspect evidence" opens a panel over the questions; layers described below | `assistant/EvidenceDrawer.tsx` |
| Confirm or dismiss | In the drawer's Person layer, or inline on Findings; a name is asked once and remembered in `localStorage` key `workbench.reviewer`; "Clear decision" undoes; a stale decision (409) is refused and the current state shown | `EvidenceDrawer.tsx HumanLayer`, `views/FindingsView.tsx`, `lib/reviewer.ts`, `lib/api.ts reviewFinding isConflict` |
| Memo | "Generate review memo" under a complete run with findings; then "Review memo ready", "Open" (HTML, new tab) and "Download .docx"; if a review happened since, "Review memo predates a later review" and "Generate a new memo" | `hooks/useMemoAction.ts`, `AssistantPanel.tsx` memo row |
| Evidence pack | "Download evidence pack" in the drawer's "Prove it" section and on a run's record in Runs; saved under the API's file name; refusal shown in place | `shell/PackLink.tsx`, `lib/api.ts attachment` |
| Revision check | Under a complete run: "Check a revised version" (or "Use a prepared revision" on the standard sample), a confirm step ("Record as the next version", cannot be undone), then each finding as Stale, Established again or Not reached, and "Ask the same question of the revision" (a new run, both answers side by side, a link to open it) | `assistant/RevisionCheck.tsx` (`SAMPLE_REVISION`, `AskAgain`) |
| Command palette | Ctrl K (Cmd K on Apple) or the "Ctrl K" button: a combobox over Ask, Guidance, Evidence ("Inspect evidence: ..."), "Generate review memo", Go to (Documents, Findings, Runs, "Review another contract") and Jump to (every numbered section). Questions are disabled with "after this answer arrives" while a run is live | `CommandPalette.tsx`, `Workbench.tsx buildCommands` and the keydown handler |
| Search | The rail's "Search (Ctrl K)": opens the palette when a contract is open, otherwise goes to the landing | `shell/Rail.tsx`, `Workbench.tsx openSearch` |
| Why this answer | In the drawer behind "Prove it", and on a run's record in Runs: What was read, What retrieval chose, What the model saw, What the model proposed, What code established (per finding, SourceMatch and the recorded policy evaluation), Reproduce this run (hashes, input hash match) | `assistant/WhyThisAnswer.tsx`, `hooks/useRunExplanation.ts` |
| Coverage notice | Under the contract title: "Not read by this reading: <parts (counts)>. Citations come only from what was read.", plus "(Described from the stored file ...)" for a reconstructed coverage record; and "Little structure was found ..." when fewer than three sections are numbered | `workspace/DocumentPane.tsx` (`notRead`, `data-testid="coverage-note"`) |
| Day comparison picture | When code compared a period with the guidance, an axis with the bound and the contract's figure | `assistant/DayGauge.tsx` (`readComparison` parses code's own sentence exactly, or draws nothing) |
| Model wake | A hosted model that sleeps is woken when a contract is added or a question is started, at most once in 4 minutes | `hooks/useModelWake.ts`, `lib/api.ts wakeModel` |
| Documents view | Count, figures (contracts, sections read, findings, reviewed), one row per document (type, pages, sections, upload time, findings and how many a person reviewed, or "Not analysed"), "Add", and on an empty store the amended sample | `views/DocumentsView.tsx` |
| Findings view | Every finding across runs grouped by document, ordered for attention (undecided needs review first), filter figures, flagged concerns, inline review, curated rows read-only; a row click opens its run with the drawer | `views/FindingsView.tsx` (`forAttention`) |
| Runs view | Citation figures and a quote-method bar, the build commit, the run list ("On screen", "curated"), then a run's record (stages, timing, sections handed to the model, findings incl. unverified, raw output, Why this answer, "Open in workspace", pack); below: Golden set, Batch extraction, Document families (not in a public demo), One contract changes, Before this product | `views/RunsView.tsx`, `views/ContractState.tsx`, `views/Figures.tsx` |

#### The evidence drawer, layer by layer (`assistant/EvidenceDrawer.tsx`)

The drawer reads the run on screen and the run's explanation (`GET /api/runs/{id}/explanation`, read once per open by
`useRunExplanation`). It is keyed by finding id, so a half-made decision never carries to the next finding. While it
is open the rest of the questions panel is `inert`.

| Order | Block | `data-testid` | What it shows |
|---|---|---|---|
| 1 | Decision strip | none (`aria-label="The finding's trail"`) | Four cells, left to right: Model (its proposed status, struck through when code changed it), Source ("N of M found", never in the pass colour), Code ("did not decide" or the status code set, marked decisive), Person (confirmed, dismissed or not yet) |
| 2 | Model proposed | `layer-model` | Its hint (a status chip), "In its words" (observed against required), "It cited N passages", "Its sentence" (the withheld conclusion), "It pointed at", "It suggested". Tagged "Status set here" when the status source is `model_hint` |
| 3 | Source | `layer-source` | Each quoted span: a button to jump to it (a static label on a phone), the quote, "Found word for word in the document text · exact" or the method, or "Not found verbatim ... · withheld"; whether it was found where the model cited it, how many times it occurs, whether it lies outside the model's visible text; a "Text around this quote" disclosure (at every width since 2026-11-01); then the limit sentence and a link to `/break` |
| 4 | The contract on these clauses | `layer-relations` | Relation statements in full, when the finding has any |
| 5 | Code | `layer-code` | Heading from `codeRole`: "Code found a conflict", "Code passed it on the day counts", "Code lowered it", "Code confirmed", "Code withheld" or "Code did not decide"; the guidance text; the day gauge; the reason code recorded; "Not shown to the model" when the quote points at a section the model never saw; the resulting status chip |
| 6 | Person | `layer-human` | The recorded review, or "No one has decided on this finding yet"; Confirm / Dismiss, or Clear decision; the name form. A curated (`run.shared`) record shows the review and no controls |
| 7 | Prove it | none | A toggle revealing model, prompt version and hash, sources, latency, run id, the evidence pack link, and `WhyThisAnswer` for this finding |

#### Keyboard

| Key | Effect |
|---|---|
| Ctrl K / Cmd K | On Review with a contract: toggle the palette. On another view with a contract open: go to Review and open it. With no contract: the browser's own shortcut is left alone |
| Escape | Closes, in order: the palette, the guidance popover, the evidence drawer (focus returns to the control that opened it) |
| Enter / Shift+Enter | In the composer: ask / new line. On the landing's question box, Enter opens the file picker |
| Arrow keys, Enter, Escape, Tab | Inside the palette (listbox navigation; while filtering, disabled commands sort after runnable ones) |
| Left, Right, Home | On the focused divider: resize, reset |

### 8.3 Data flow

#### The API client (`src/lib/api.ts`)

`API_URL = apiBase(NEXT_PUBLIC_API_URL, NODE_ENV === "production")`: a production build uses relative URLs (the same
origin, behind the proxy that sends `/api` to FastAPI) unless the build names an API; a development build uses
`http://127.0.0.1:8000`. Every request goes through `request<T>()` (line 126), which sends cookies
(`credentials: "include"`), turns a network failure into a sentence (`unreachable`), fires `verity:access-required`
on a 401, throws `ApiError(status, detail)` for any non-2xx (the API's `detail` string, or validation messages
joined), and refuses a non-JSON answer (an HTML sign-in page is reported as a possibly expired sign-in).

| Function | Request | Used by |
|---|---|---|
| `health()` | `GET /api/health` | `Workbench`, `AccessGate` |
| `getAccess()` | `GET /api/access` | `AccessGate` |
| `visit()` | `POST /api/access/visit` | `AccessGate` (under a Web Lock) |
| `enterWithInvite(invite, {replace})` | `POST /api/access/session[?replace=true]` | `AccessGate` |
| `wakeModel()` | `POST /api/model/wake` | `useModelWake` |
| `uploadDocument(file)` | `POST /api/documents` (multipart field `file`) | `Workbench.loadFile`, `RevisionCheck` |
| `listDocuments()` | `GET /api/documents` | `Workbench` (recent), `Landing`, `DocumentsView` |
| `getDocument(id)` | `GET /api/documents/{id}` | `Workbench.openDocument`, `openRun` |
| `recordSupersedes(id, previousId)` | `POST /api/documents/{id}/supersedes` | `RevisionCheck` |
| `createGuidance(text)` / `getGuidance(id)` | `POST /api/guidance` / `GET /api/guidance/{id}` | `useGuidance`, `RevisionCheck.AskAgain` / `Workbench.openRun` |
| `createRun({documentId, guidanceId, question})` | `POST /api/runs` | `useRunFollower.ask`, `RevisionCheck.AskAgain` |
| `getRun(id)` | `GET /api/runs/{id}` | `Workbench`, `Landing`, `followRun` (the final record) |
| `listRuns()` | `GET /api/runs` | `chooseProof`, `RunsView` |
| `getRunDetail(id)` | `GET /api/runs/{id}/detail` | `Workbench.openRun`, `chooseProof`, `followRun` (polling), `RunsView` |
| `getRunExplanation(id)` | `GET /api/runs/{id}/explanation` | `useRunExplanation` |
| `getRunTrustDiff(runId, documentId)` | `GET /api/runs/{id}/trust/diff?documentId=` | `RevisionCheck` |
| `listFindings(documentId?)` | `GET /api/findings[?documentId=]` | `FindingsView` |
| `reviewFinding(id, {verdict, reviewer, note, basedOn})` | `POST /api/findings/{id}/review` | `EvidenceDrawer.HumanLayer`, `FindingsView` |
| `createMemo(runId)` | `POST /api/memos` | `useMemoAction` |
| `attachment(path, fallbackName)` | `GET <path>` as a blob, name from `Content-Disposition` | `PackLink` (`/api/runs/{id}/evidence-pack`) |
| `getCitations()` | `GET /api/engineering/citations` | `Landing`, `RunsView` |
| `getExperiments()`, `getGoldens()`, `getFamilies()` | `GET /api/engineering/experiments`, `/goldens`, `/families` | `RunsView` (goldens and families skipped in a public demo) |
| `listBatches()`, `getBatch(id)` | `GET /api/batches`, `/api/batches/{id}` | `RunsView` (skipped in a public demo) |
| `getContractState()` | `GET /api/engineering/contract-state`, or `/contract-state.json` in the static export | `RunsView`, `StateStory` |
| `followRun(...)` | `GET /api/runs/{id}/events` (SSE), polling `/detail` | `useRunFollower`, `RevisionCheck.AskAgain` |
| `absolute(url)` | none: prefixes `API_URL` to an API-relative URL | memo links, pack link |

Paths with ids are built with the `route` template tag (line 111), which validates each id with `recordId` and
encodes it. Use it for every new path. One existing exception: `shell/PackLink.tsx` builds
`/api/runs/${runId}/evidence-pack` with a plain template string from a run id the API issued (not from the address).

#### Types from the OpenAPI document

The backend schema is the source of truth. `npm run api:types` runs `openapi-typescript openapi.json -o
src/lib/api.schema.ts` (generated, 5,081 lines, 32 paths at this commit; do not edit, prettier ignores it). The
backend side is `python backend/scripts/export_openapi.py`, which writes `openapi.json`; commit both files together
(`AGENTS.md`). `src/lib/types.ts` aliases the schemas the interface renders (`FindingView = Schemas["FindingOut"]`,
`RunView = Schemas["RunOut"]`, and 33 more) and holds the wording tables and narrowing helpers: `statusLabel`,
`STATUS_SOURCE_LABELS`, `codeAccount`/`codeRole`/`decidedByCode`, `REASON_TITLES`, `STAGE_ORDER`/`STAGE_LABELS`,
`retrievalNote`, `sectionsReadNote`, `readingParts`, `citationLabel`, `passageLabel`, `isLocated`, `evidenceJump`,
`passageSpan`. Field names in the schema are camelCase.

#### How a run is followed

`followRun(id, onStage, onDone, onError, onAhead)` (`api.ts:341`) opens an `EventSource` on
`/api/runs/{id}/events` with credentials. Events: `stage` (`{stage, detail, final}`; `final` triggers the end),
`queue` (`{ahead}`: how many questions are ahead on the model), and the server's own `error` event (a JSON `detail`,
for an unknown run). A transport error closes the stream and switches to polling `GET /api/runs/{id}/detail`: every
3 s while something changes, doubling to at most 12 s while nothing does, paused while the tab is hidden, giving up
after 5 consecutive failures. On a terminal stage (`complete`, `unresolved`, `failed`) it reads `GET /api/runs/{id}`
once and hands that record to `onDone`. The returned function cancels everything; no callback fires after it.

`hooks/useRunFollower.ts` wraps that in a reducer with exactly these phases (`FollowerState`, line 16):

| Phase | Meaning |
|---|---|
| `idle` | nothing on screen |
| `starting` | the question was sent; `POST /api/runs` not yet answered |
| `not_started` | the API refused the question; the words go back into the composer |
| `following` | the run is in flight; stages come from events and only move forward |
| `loading_record` | a terminal event arrived; the record with findings is being read (the terminal stage is never applied from an event) |
| `finished` | the record is on screen |
| `disconnected` | the stream and polling failed; "Reconnect" calls `resume` |

The hook also exposes `live` (starting, following, loading_record or disconnected: no second question may start),
`claim()` (the intent token the shell uses), `show(run, documentId)` (put a recorded run on screen, following it if
in flight), `refresh(run)` (a newer copy of the finished run on screen, ignored for any other run) and `stop()`.
`beside(runs, documentId)` (line 250) returns an idle view of the follower unless the run belongs to the contract on
screen. Every surface reads the run through it.

#### State and caching

There is no client data cache, no global store and no data-fetching library. State is React state in `Workbench.tsx`
and the hooks; each view fetches its list when it mounts and offers "Try again" when a read fails (`views/Skeleton.tsx
ReadFailed`). What is kept, and where:

| What | Where | Lifetime |
|---|---|---|
| divider position | `sessionStorage["workbench.docWidth"]` | the tab |
| reviewer's name | `localStorage["workbench.reviewer"]` | the browser |
| memos | `useMemoAction`, by run id; cleared when a question is asked or another document or run is opened | the page |
| a run's explanation | `useRunExplanation`, by run id | while the drawer or record is open |
| the session | a cookie the API sets; the interface never reads it | set by the API |

When the Review view is shown again after a review was made on Findings, the workbench re-reads the finished run
(`Workbench.tsx:432`) so the drawer and the memo's review head match the record.

#### The one display primitive for model- or file-written text

`src/lib/text.ts revealInvisible(text, start?, end?)` (line 91) splits text into ordinary pieces and invisible
characters (Unicode Cf format characters, and joiners or selectors between two ASCII letters or digits), naming each
invisible one by its code point. It never changes the record; it only stops such a character from acting on the
page (for example a right-to-left override turning "15" into "51"). Two renderings:

- `shell/primitives.tsx Visible` renders the pieces as React, each invisible character as a marked span showing
  `U+202E` with a title. Every topic, conclusion, quote, file name, heading, guidance and model phrase on screen goes
  through it.
- `shownText(text)` returns one string with `[U+202E]` markers, for attributes, labels and palette entries.

Rule: any new place that shows a string the model or an uploaded file wrote uses `<Visible text=.../>` or
`shownText`. `displaySafe.test.tsx` checks the answer surfaces with the `HOSTILE` character set.

#### Code-point offsets

The API's span offsets count Unicode code points (Python). JavaScript strings count UTF-16 units, so a naive
`slice` shifts by one for every astral character before the span. All slicing of located text is by code points:

| Helper (`src/lib/text.ts`) | Used for |
|---|---|
| `revealInvisible(text, start, end)` via `<Visible start end>` | the highlighted passage in `DocumentPane.SectionBlock` (before, inside the `<mark>`, after; each piece read in the context of the whole section) and the drawer's phone context |
| `splitByCodePoints(text, start, end)` | `/break` (`BreakStory.tsx`) |
| `aroundCodePoints(text, start, end, radius)` | the drawer's "Text around this quote" (280 code points each side, cut between words) |
| `clipCodePoints(text, max, keep)` | 150-code-point quote excerpts, guidance chip, relation excerpts |
| `codePointLength`, `fitsCodePoints` | bounds checks; `EvidenceSpine` positions |

There is no function named `locatedPieces` at this commit; the job that name suggests is done by `revealInvisible`
with `start`/`end` as above.

#### The script nonce (CSP)

- `src/proxy.ts` is Next 16's request interceptor. Next 16 renamed the `middleware` file convention to `proxy`
  (installed docs, `node_modules/next/dist/docs/01-app/01-getting-started/16-proxy.md`); there is no
  `middleware.ts`. For every page request it builds a policy with a fresh nonce (`lib/csp.ts newNonce`: 128 random
  bits, base64) and sets it on the request (Next reads it while rendering and puts the nonce on its own scripts) and on
  the response (the browser enforces it).
- The policy (`contentSecurityPolicy`): `script-src 'self' 'nonce-…' 'strict-dynamic'` (plus `'unsafe-eval'` only
  under `next dev`), `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`. Never `'unsafe-inline'`.
  Styles, images and connections are not governed (framer-motion writes style attributes; the API may be another
  origin).
- The matcher skips `/api`, `/_next/static`, `/_next/image`, `favicon.ico`, `icon.svg`, `samples/`,
  `contract-state.json`, and prefetch requests.
- Because a nonce needs a request, `layout.tsx` calls `await connection()`, so no page is prerendered. Making a page
  static (for example with `export const dynamic = "force-static"` or `generateStaticParams`) would ship it without a
  nonce and its scripts would be refused. The static export skips this, has no proxy, and relies on its host's headers.
- `next.config.ts SECURITY_HEADERS` (HSTS one year, `nosniff`, `strict-origin-when-cross-origin`,
  `frame-ancestors 'none'`) go on every path of the server build; on pages the proxy's CSP takes the place of the
  config's CSP. `poweredByHeader: false`. `e2e/security.spec.ts` proves an injected inline script does not run.

#### Build-time settings

`NEXT_PUBLIC_*` values are inlined when the interface is built; changing one needs a rebuild.

| Variable | Effect |
|---|---|
| `NEXT_PUBLIC_API_URL` | API origin. Unset in production means the same origin; the flows set `http://127.0.0.1:8001` |
| `NEXT_PUBLIC_PROOF_RUN` | the run id the landing offers as "A finished review", with the `OneRun` story (`landing/proofRun.ts chooseProof`: that run or nothing) |
| `NEXT_PUBLIC_BUILD_SHA` | the commit the interface was built from; Runs shows "Interface built from commit <12 chars>" (`data-testid="build-identity"`). Set by `deploy/install-supervision.ps1` to `git rev-parse HEAD`; absent in dev builds |
| `NEXT_PUBLIC_EXPORT=state` | the static artifact: `output: "export"` into `out-state`, `/` renders `StateStory`, no headers, no `connection()`, the record read from `/contract-state.json` (built by `backend/scripts/export_state.py`) |
| `NEXT_PUBLIC_WORKBENCH_URL` | in the static export, the live workbench address that `/break` links to; without it `/break` is a 404 there |
| `NEXT_PUBLIC_HOSTING=cloud` | `/break` says the workbench runs in the cloud images rather than on one laptop |
| `NEXT_DIST_DIR` | build output directory (`.next` by default; the flows use `.next-e2e`) |

### 8.4 File by file

Test files are listed in section 8.6. Paths below are relative to `src/` unless they start with a root name.

#### Root configuration

| File | Job | Notes |
|---|---|---|
| `package.json` | Scripts and pinned dependencies | `dev`, `build`, `start`, `lint` (`eslint --max-warnings=0`), `typecheck` (`tsc --noEmit`), `format:check` (prettier over `src/**/*.{ts,tsx,css}` only), `test` (`vitest run`), `e2e` (`playwright test`), `api:types`. Runtime deps: next 16.4.1, react and react-dom 19.2.8, framer-motion. |
| `next.config.ts` | Next settings | `SECURITY_HEADERS` (exported, tested by `lib/nextConfig.test.ts`), `devIndicators: false`, `poweredByHeader: false`, `distDir` from `NEXT_DIST_DIR`, the static-export switch. |
| `tsconfig.json` | TypeScript | strict, `moduleResolution: bundler`, path alias `@/*` to `src/*`, includes `.next-e2e` types. Next may rewrite it on build; the gate restores it. |
| `eslint.config.mjs` | Lint | `eslint-config-next` core-web-vitals and typescript; ignores build dirs and `backend/**`; bans `fetch`, `EventSource` and `api.schema` imports in components and app (section 8 intro). |
| `vitest.config.ts` | Unit tests | jsdom, `@` alias, includes `src/**/*.test.{ts,tsx}`. |
| `playwright.config.ts` | Browser flows | Starts the API (port 8001, data dir `backend/data/e2e` or `e2e-record`, `WORKBENCH_PROVIDER` from `E2E_PROVIDER`, default `replay`) and a production build of the interface (port 3901, `.next-e2e`); one Chromium project at 1280x800; one worker; traces kept on failure. |
| `playwright.sessions.config.ts` | Desktop state audit | Fresh temporary API store, explicitly selected replay provider, production build, Chromium/Firefox/WebKit; `npm run test:sessions`. Run sequentially with the normal browser suite. |
| `e2e/sessions.audit.ts` | Review-session regressions | Empty and failed ledgers, failed reviews, repeated record navigation, late responses, interrupted connections and question-request recovery; captures and accessibility checks. |
| `.prettierrc` | Formatting | `printWidth: 160`. |
| `.prettierignore` | Formatting | Skips `src/lib/api.schema.ts` (generated) and `src/components/break/break-record.json` (exporter's bytes, re-checked by `backend/tests/test_break_record.py`). |

#### `src/app` and `src/proxy.ts`

| File | Job | Key exports | Used by |
|---|---|---|---|
| `app/layout.tsx` | Root layout: fonts (Inter, Source Serif 4, JetBrains Mono as CSS variables), metadata, skip link, `await connection()` | `metadata`, `RootLayout` | Next |
| `app/page.tsx` | `/`: the workbench, or `StateStory` in the static export (`StateStory` is loaded with `next/dynamic`, so workbench visitors do not download the experiment's 39 KB) | `Page` | Next |
| `app/break/page.tsx` | `/break`: trims the record server-side and renders `BreakStory` | `metadata`, `BreakPage` | Next |
| `app/state/page.tsx` | `/state` | `metadata`, `StatePage` | Next |
| `app/globals.css` | The frozen visual system (section 8.5) | tokens on `:root` | `layout.tsx` |
| `app/icon.svg` | Favicon: a dark tile, a paper page, one brass line | none | Next file convention |
| `proxy.ts` | Per-request CSP with nonce | `proxy`, `config` | Next |

#### `src/lib`

| File | Job | Key exports | Used by |
|---|---|---|---|
| `lib/api.ts` | The only API client; run following | see the table in 8.3; `ApiError`, `RecordIdError`, `route`, `recordId`, `errorMessage`, `isConflict`, `unreachable`, `apiBase`, `API_URL`, `ACCESS_REQUIRED_EVENT`, `POLL_MS`, `POLL_MAX_MS`, `STATE_RECORD_FILE` | every view and hook |
| `lib/api.schema.ts` | Generated OpenAPI types | `paths`, `components` | `types.ts` only |
| `lib/types.ts` | Type aliases and the wording of statuses, sources, reasons, stages | see 8.3 | nearly every component |
| `lib/checks.ts` | The "What was checked" ledger and outcome sentences, read from recorded fields | `checkLedger`, `CheckRow`, `CheckBy`, `locatedNote`, `runOutcome`, `unseenNote`, `valueNotes` | `FindingCard`, `AssistantPanel`, `EvidenceDrawer`, `Landing`, `RunsView` |
| `lib/text.ts` | Code-point slicing and the invisible-character display primitive | `revealInvisible`, `shownText`, `VisiblePiece`, `splitByCodePoints`, `aroundCodePoints`, `clipCodePoints`, `codePointLength`, `fitsCodePoints` | `primitives.tsx`, cards, drawer, document pane, `/break` |
| `lib/diff.ts` | Longest-common-subsequence diffs for presentation | `commonItems`, `joinPieces`, `wordContrast`, `aroundChanges`, `DiffPiece` | `RelationNotes.tsx`, `break/record.ts` |
| `lib/format.ts` | Locale-free formatting (server and client agree) | `formatWhen`, `formatClock`, `formatDelta`, `formatLatency`, `shortHash`, `plural`, `nameWithoutType` | views, drawer, stories |
| `lib/csp.ts` | Nonce and policy | `newNonce`, `contentSecurityPolicy` | `proxy.ts` |
| `lib/address.ts` | Decoding address parts without throwing | `safeDecode` | `AccessGate`, `StateStory` |
| `lib/modelPlace.ts` | Where the model runs, only as `/api/health` says | `modelPlace` | `Workbench`, `Landing`, `AccessGate` |
| `lib/reviewer.ts` | Remembered reviewer name | `REVIEWER_KEY`, `rememberedReviewer`, `rememberReviewer` | `EvidenceDrawer`, `FindingsView` |
| `lib/independence.ts` | The independence sentence, pinned to the README by `backend/tests/test_docs_claims.py` | `INDEPENDENCE` | `Landing`, `BreakStory`, `StateStory` |

#### `src/components/workbench` (shell, hooks, shell parts)

| File | Job | Key exports | Used by |
|---|---|---|---|
| `Workbench.tsx` | Coordinates shell state, opening, uploading, asking, highlighting, keyboard and palette commands; renders landing or workspace | `Workbench` | `app/page.tsx` |
| `Workbench.module.css` | Styles for the rail, paper, questions panel, cards, drawer, palette button; the 640 px layout | CSS module | most workbench components |
| `CommandPalette.tsx` | Modal combobox over supplied commands; at most 40 shown; focus returns to its opener | `CommandPalette`, `Command` | `Workbench` |
| `CommandPalette.module.css` | Palette styles | CSS module | `CommandPalette` |
| `icons.tsx` | Inline SVG icons and the Verity mark | `IconSearch`, `IconDocuments`, `IconAssistant`, `IconFindings`, `IconRuns`, `IconPlus`, `IconArrowUp`, `IconClose`, `IconFile`, `IconCommand`, `IconCheck`, `IconArrowRight`, `VerityMark` | rail, panels, landing |
| `samples.ts` | The two bundled samples and their questions | `SAMPLES`, `SampleKind`, `Sample`, `suggestionsFor` | `Workbench`, `AssistantPanel`, `DocumentPane`; read by `backend/tests/test_amended_sample.py` |
| `shell/constants.ts` | Stage and View types, the motion curve and presets, `NARROW_QUERY` | `Stage`, `View`, `VIEWS`, `TERMINAL`, `EASE`, `transitions`, `NARROW_QUERY` | shell, hooks, panels |
| `shell/QuestionInput.tsx` | Shared question field that grows, shrinks and reflows up to its CSS height cap | `QuestionInput` | landing and assistant |
| `shell/primitives.tsx` | Status chip, progress shimmer, brand, the `Visible` text primitive | `StatusChip`, `Shimmer`, `Brand`, `Visible` | almost every surface |
| `shell/Rail.tsx` | The left rail: mark (home), Search, Documents, Review, Findings, Runs | `Rail` | `Workbench` |
| `shell/PackLink.tsx` | Evidence pack link with wait and refusal states | `PackLink` | `EvidenceDrawer`, `RunsView` |
| `access/AccessGate.tsx` | The door: invite exchange, public-demo visit, session-ended handling | `AccessGate` | `Workbench` |
| `access/PublicDemo.tsx` | Contexts for demo mode, door known, reader name | `PublicDemo`, `AccessModeKnown`, `Reader` | `AccessGate`, `Landing`, `RunsView` |
| `hooks/useRunFollower.ts` | The run state machine and intent tokens | `useRunFollower`, `FollowerState`, `RunController`, `beside` | `Workbench`, `AssistantPanel` (type) |
| `hooks/useUrlState.ts` | Address and history sync | `useUrlState` | `Workbench` |
| `hooks/useGuidance.ts` | Guidance record, popover, draft, save error | `useGuidance`, `GuidanceController`, `DEFAULT_GUIDANCE`, `GuidanceState` | `Workbench`, `GuidanceScope` |
| `hooks/useMemoAction.ts` | Memo requests held per run | `useMemoAction`, `MemoController` | `Workbench`, `AssistantPanel` |
| `hooks/useModelWake.ts` | Wake a sleeping hosted model on intent | `useModelWake`, `WAKE_EVERY_MS` | `Workbench` |
| `hooks/useDocWidth.ts` | Split width with drag and session persistence | `useDocWidth`, `DEFAULT_DOC_WIDTH`, `MIN_DOC_WIDTH`, `MAX_DOC_WIDTH` | `Workbench`, `Divider` |
| `hooks/useDropZone.ts` | Window drag-and-drop while the landing shows | `useDropZone` | `Workbench` |
| `hooks/useHighlightScroll.ts` | Scroll the paper to the `<mark>` in the same commit, 72 px lead | `useHighlightScroll` | `Workbench` |
| `hooks/useNarrow.ts` | Whether the window matches `NARROW_QUERY` | `useNarrow` | `EvidenceDrawer` |
| `hooks/useRunExplanation.ts` | Read a run's explanation once, keyed by run id | `useRunExplanation`, `ExplanationRead` | `EvidenceDrawer`, `WhyThisAnswer` |

#### `src/components/workbench` (panels, landing, views, workspace)

| File | Job | Key exports | Used by |
|---|---|---|---|
| `assistant/AssistantPanel.tsx` | The questions panel: scope, suggestions, thread, stages, cards, memo, run meta, revision check, composer, drawer | `AssistantPanel`, `ASSISTANT_SUGGESTIONS`, `MAX_QUESTION_CHARS` | `Workbench` |
| `assistant/FindingCard.tsx` | One finding as a card | `FindingCard` | `AssistantPanel` |
| `assistant/EvidenceDrawer.tsx` | The drawer and its layers, review controls, "Prove it" | `EvidenceDrawer` | `AssistantPanel` |
| `assistant/WhyThisAnswer.tsx` | The run explained from its record | `WhyThisAnswer` | `EvidenceDrawer`, `RunsView` |
| `assistant/StageList.tsx` | Run progress and the wait note | `StageList` | `AssistantPanel` |
| `assistant/RunOutcome.tsx` | Unresolved or failed run body; withheld proposals | `RunOutcome`, `WithheldList`, `outcomeTitle` | `AssistantPanel`, `Workbench` |
| `assistant/GuidanceScope.tsx` | Scope line and guidance popover | `GuidanceScope` | `AssistantPanel` |
| `assistant/RelationNotes.tsx` | Replacement and precedence statements, their ends and word diffs | `RelationNotes`, `UnclaimedRelations`, `relationEnds`, `statementLine`, `relationSummary`, `relationKey` | `FindingCard`, `AssistantPanel`, `EvidenceDrawer`, `RevisionCheck` |
| `assistant/DayGauge.tsx` | Parse code's comparison sentence; draw it | `DayGauge`, `readComparison`, `DayComparison` | `EvidenceDrawer` |
| `assistant/RevisionCheck.tsx` | Revised-version check and ask-again | `RevisionCheck`, `SAMPLE_REVISION`, `PreparedRevision` | `AssistantPanel` |
| `assistant/RevisionCheck.module.css` | Its styles | CSS module | `RevisionCheck` |
| `assistant/__fixtures__/explanation-e5a20e2283e8416e.ts` | A recorded explanation of the Phase 1 run (read 2026-09-30) | `EXPLANATION_E5A20E22` | `WhyThisAnswer.test`, `EvidenceDrawer.test` |
| `assistant/__fixtures__/hostile.ts` | Invisible characters a model can write | `HOSTILE`, `hostile(text)`, `expectShownByName` | `displaySafe.test`, `FindingsView.test` |
| `landing/Landing.tsx` | The first screen | `Landing`, `refusal` | `Workbench` |
| `landing/LandingStory.tsx` | Below the fold: record pipeline, the proof run told in four steps, refusals. Its sentences about what reaches the model are pinned by `test_docs_claims.py` | `RecordPipeline`, `OneRun`, `Refusals` | `Landing` |
| `landing/Landing.module.css` | Landing and door styles | CSS module | `Landing`, `LandingStory`, `AccessGate`, `TopLinks` |
| `landing/TopLinks.tsx` | Links to `/break`, `/state`, source | `TopLinks`, `SOURCE` | `Landing`, `AccessGate` |
| `landing/proofRun.ts` | Choose the landing's finished review | `chooseProof` | `Workbench` |
| `views/DocumentsView.tsx` | Documents list | `DocumentsView` | `Workbench` |
| `views/FindingsView.tsx` | Findings across runs with inline review | `FindingsView`, `forAttention` | `Workbench` |
| `views/RunsView.tsx` | The engineering record: runs, a run's record, golden set, batches, families, contract state, experiments | `RunsView` | `Workbench` |
| `views/ContractState.tsx` | Contract-state experiment inside Runs, with a link to `/state` | `ContractState` | `RunsView` |
| `views/ContractState.module.css` | Its styles | CSS module | `ContractState` |
| `views/Figures.tsx` | Numerals row (optionally clickable filters) and the quote-method bar | `Figures`, `Figure`, `MethodBar` | Documents, Findings, Runs, `ContractState` |
| `views/Skeleton.tsx` | Still placeholder rows; "could not be read" with retry | `ListSkeleton`, `ReadFailed` | Documents, Findings, Runs |
| `views/Views.module.css` | Shared styles for the three list views | CSS module | views |
| `workspace/DocumentPane.tsx` | The contract on paper, highlight, coverage and structure notices; memoised section blocks | `DocumentPane`, `Highlight` | `Workbench`, `useHighlightScroll` |
| `workspace/EvidenceSpine.tsx` | A mark down the paper's edge for each verified quote | `EvidenceSpine` | `DocumentPane` |
| `workspace/Divider.tsx` | Resizable split, keyboard operable | `Divider` | `Workbench` |

#### `src/components/break` and `src/components/story`

| File | Job | Key exports | Used by |
|---|---|---|---|
| `break/BreakStory.tsx` | The `/break` page; reads the record through a context | `BreakStory`, `unseenSummary` | `app/break/page.tsx` |
| `break/BreakStory.module.css` | Its styles | CSS module | `BreakStory` |
| `break/record.ts` | Record types, `forPage` trimming, and presentation helpers (shared word runs, character diffs, fix scores, party phrases, miss reasons) | `BreakRecord`, `PageRecord`, `CaseRecord`, `SessionRecord`, `SpanRecord`, `VerdictRow`, `forPage`, `sharedRun`, `charDiff`, `fixScore`, `definedParties`, `firstOccurrences`, `whyMissed`, `wordsOf`, `listed` | `BreakStory`, `app/break/page.tsx` |
| `break/break-record.json` | The recorded failure, written by `backend/scripts/export_break_record.py`; do not edit by hand | data | `app/break/page.tsx`, `e2e/break.spec.ts` |
| `story/StateStory.tsx` | The `/state` page | `StateStory` | `app/state/page.tsx`, `app/page.tsx` (export) |
| `story/StateStory.module.css` | Its styles | CSS module | `StateStory` |
| `story/__fixtures__/contract-state.json` | Three arrivals of the contract-state record | data | `StateStory.test`, `ContractState.test`, `e2e/state.spec.ts` |

#### `e2e/`

| File | Job |
|---|---|
| `e2e/*.spec.ts` (9 files) | The browser flows; section 8.6 |
| `e2e/replay.json` | The model's recorded answers, six entries keyed by request hash; section 8.6 |

### 8.5 Styling

`src/app/globals.css` is the visual system. `AGENTS.md` lists it among the fixed decisions: "The visual system is
frozen. No theme switching, no extra pages, no dashboard cards, no marketing content, no agent diagrams, no
onboarding tours." It was chosen on 2026-09-28 from three coded shells ("C frozen; A and B discarded",
`DECISIONS.md`).

What it defines:

- **One dark theme** (`color-scheme: dark`). There is no light theme and no `prefers-color-scheme` switch; do not add one.
- **Ground**: three warm ink steps (`--bg #13110e`, `--bg-raised`, `--bg-sunken`), surfaces as translucent warm
  white, hairline borders.
- **Text**: `--text`, `--text-2`, `--text-3` (the quietest colour words may use; 6.3:1 on `--bg`), `--text-4` (marks
  without words).
- **One accent, brass**: `--accent #d8b46a` and its soft, tint and line variants, for focus, the marked passage,
  the layer where a status was set, and primary actions. `--accent-1`, `--accent-2` and `--spectral` are older
  aliases of it.
- **The paper**: `--doc-bg #f6f2e9`, `--doc-text`, `--doc-mark` (the highlight), `--doc-lit` (the section glow),
  `--doc-link` (a link on paper, 5.7:1).
- **Four status tones**, each a fill, a word colour and a border, always with a word: review (amber), pass (green),
  muted, bad (red).
- **Radii** 6/10/14 px, **durations** 140/220/320 ms, one easing curve. `shell/constants.ts EASE` is the same
  idea for framer-motion; `transitions(reduceMotion)` returns zero durations under reduced motion, and
  `globals.css` zeroes CSS animations and transitions for `prefers-reduced-motion: reduce`.
- **Fonts**: Inter (interface), Source Serif 4 (the contract and headings about it), JetBrains Mono (ids, hashes,
  offsets, counts), loaded by `next/font/google` in `layout.tsx` as `--font-inter`, `--font-source-serif`,
  `--font-jetbrains` and composed into `--font-sans`, `--font-serif`, `--font-mono`.
- **Base rules**: `overflow-wrap: anywhere` on `html, body` (a long unbroken file name wraps instead of widening its
  box), a brass `:focus-visible` outline, `.visually-hidden`, `.skip-link`.

Every component styles itself with a CSS module (`*.module.css`) that reads these tokens. A handful of literal colours
exist at this commit: `#fff` on two hover states in `Workbench.module.css` (lines 658, 1318), a few in
`Landing.module.css`, and the quote-method colours in `views/Figures.tsx`. Treat them as part of the frozen system,
not as precedent.

What "frozen" means for a change:

- New UI reuses existing tokens and existing module classes. Do not add tokens, themes, fonts, radii or durations.
- Do not add pages, dashboards, card grids, tours or decorative animation. A new surface is a view inside the shell
  (section 8.7), not a new route, unless the owner decides otherwise.
- Keep the layout rules `clipping.test.ts` checks over every stylesheet: a grid that clips (`overflow: hidden`) must
  declare its columns with a definite minimum (`minmax(0, 1fr)`, not `auto` or `1fr`), and the root keeps
  `overflow-wrap: anywhere`.
- Keep `NARROW_QUERY` and the 640 px media query in step.
- Status colour always travels with a status word; the pass colour is kept for a pass code stood behind
  (`StatusChip`).

### 8.6 Tests

#### Unit tests (Vitest, jsdom)

`npm test` runs every `src/**/*.test.{ts,tsx}`: 44 files. A static count finds 389 `it(`/`test(` calls; some sit
inside loops (seeded random walks, per-phase and per-link cases), so the run-time total is higher. The run-time
count was not verified here (tests were not run). Tests use the real `api.ts` and components with `fetch` and
`EventSource` stubbed; none calls a network.

| File | Cases | What it covers |
|---|---|---|
| `lib/api.test.ts` | 20 | HTML-instead-of-data answers, unreachable wording, `apiBase`, a stopped follower calls nothing, polling backoff and hidden-tab waits, `route` refuses non-ids, non-JSON answers |
| `lib/types.test.ts` | 28 | `statusLabel`, `codeAccount`, retrieval notes, `passageLabel`, `partOf`, `readingParts`, `evidenceJump`, `stageAnnouncement` |
| `lib/checks.test.ts` | 18 | `checkLedger` rows and who each is by, pre-policy-v2 records, `valueNotes` |
| `lib/text.test.ts` | 14 | code-point slicing, `revealInvisible` (incl. over a stretch), `shownText`, `aroundCodePoints`, `clipCodePoints`, every surface reading offsets in code points |
| `lib/diff.test.ts` | 4 | `wordContrast` |
| `lib/format.test.ts` | 2 | `nameWithoutType` |
| `lib/csp.test.ts` | 6 | policy content, dev-only eval, fresh nonce, proxy sets request and response, matcher scope |
| `lib/nextConfig.test.ts` | 2 | security headers on every path; the static export asks for none |
| `lib/proofPage.test.ts` | 3 | reads `proof/index.html` (outside this slice): its CUAD-30 and BM25 figures match the recorded measurements, each with a date |
| `components/workbench/Workbench.screen.test.tsx` | 17+ | the whole workbench in jsdom: the answer on screen belongs to the contract on screen, newest intent wins, a seeded walk over random interleavings, the palette never starts a second run, crafted links ask the API nothing |
| `components/workbench/hooks/useRunFollower.test.tsx` | 28 | phases, late records after the reader moved on, runs created after moving on, screen ownership, `beside` |
| `components/workbench/hooks/useUrlState.test.tsx` | 10 | restore once, background restore with a view, history entries and coalescing, Back restores, patience while restoring, in-place correction |
| `components/workbench/hooks/useHighlightScroll.test.tsx` | 6 | scrolls to the mark in the same commit |
| `components/workbench/hooks/useMemoAction.test.ts` | 5 | a memo stays with its run; late answers do not replace newer ones |
| `components/workbench/hooks/useModelWake.test.ts` | 7 | wakes only on intent, at most every 4 minutes, never for a server-side model |
| `components/workbench/access/AccessGate.test.tsx` | 24 | door states, invite fragment, public demo, two tabs at once, an invite for another reader |
| `components/workbench/assistant/EvidenceDrawer.test.tsx` | 19 | layers, strip tones, review flow and conflicts, coverage findings, phone sheet, quote context at every width |
| `components/workbench/assistant/FindingCard.test.tsx` | 4 | a finding reported as not found: wording, collapsed model sentence |
| `components/workbench/assistant/GuidanceScope.test.tsx` | 2 | a refused guidance says why in the popover |
| `components/workbench/assistant/RelationNotes.test.tsx` | 12 | relation ends, summaries by effect, word diffs |
| `components/workbench/assistant/RevisionCheck.test.tsx` | 5 | upload, confirm, record, diff; same-file refusal; nothing recorded on cancel; the file input is not a Tab stop |
| `components/workbench/assistant/RevisionAgain.test.tsx` | 4 | prepared revision; asking again; side-by-side with who decided |
| `components/workbench/assistant/StageList.test.tsx` | 5 | the wait note: queue position, sleeping model |
| `components/workbench/assistant/WhyThisAnswer.test.tsx` | 4 | renders the Phase 1 explanation fixture without deciding anything |
| `components/workbench/assistant/DayGauge.test.tsx` | 4 | `readComparison` parses exactly or returns null |
| `components/workbench/landing/Landing.test.tsx` | 27 | door wording, model place, finished review, located note, research link, public demo, refused file, samples, unreachable API, retention |
| `components/workbench/landing/LandingStory.test.tsx` | 4 | counts are shown before any animation |
| `components/workbench/landing/OneRun.test.tsx` | 4 | the proof story says only what the run's record says |
| `components/workbench/landing/proofRun.test.ts` | 4 | `chooseProof` |
| `components/workbench/views/FindingsView.test.tsx` | 13 | ordering for attention, filters and the way back from an empty one, inline review, a failed decision kept beside its row, conflicts, hostile text |
| `components/workbench/views/RunsView.test.tsx` | 8 | public demo hides owner tools; batch read failure said; outcomes; golden-set notes; record hash; a late earlier record read does not replace the latest selection |
| `components/workbench/views/ContractState.test.tsx` | 2 | an arrival from the record; not-connected and edited-file states |
| `components/workbench/workspace/Divider.test.tsx` | 1 | resize keys do not scroll the page; Home and End go to the bounds; double-click resets |
| `components/workbench/workspace/DocumentPane.test.tsx` | 6 | memoised blocks, exact highlight offsets, invisible characters in names and headings, reader parts |
| `components/workbench/workspace/EvidenceSpine.test.tsx` | 1 | marks for verified quotes; read-not-relied marks |
| `components/workbench/shell/PackLink.test.tsx` | 3 | real address, wait, refusal in place |
| `components/workbench/shell/primitives.test.tsx` | 2 | `StatusChip` labels and tones |
| `components/workbench/CommandPalette.test.tsx` | 2 | focus returns to the opener unless a command moved it |
| `components/workbench/samples.test.ts` | 2 | sample files exist in `public/`; suggestions per sample |
| `components/workbench/clipping.test.ts` | 3 | the CSS layout rules over every stylesheet (section 8.5) |
| `components/workbench/displaySafe.test.tsx` | 4 | `HOSTILE` characters are named, never acting, on every answer surface |
| `components/break/BreakStory.test.tsx` | 26 | each `/break` section from the record |
| `components/break/BreakHosting.test.tsx` | 3 | host wording and workbench links follow the build variables |
| `components/break/record.test.ts` | 15 | `sharedRun`, diffs, fix scores, party phrases |
| `components/story/StateStory.test.tsx` | 10 | each moment from the fixture, arrival in the URL, section landing, damaged fragment, not-connected |

#### Browser flows (Playwright)

`npm run e2e` runs 49 flows in 10 specs (`backend/tests/test_docs_claims.py` counts `test(` calls and holds the README
to that number). Each runs against a production build of the interface and the real FastAPI app, with the model's
answers replayed. `workbench.spec.ts` fails a flow on any console error or page error.

| Spec | Flows | What they hold |
|---|---|---|
| `workbench.spec.ts` | 9 | landing offers the sample and a finished review; sample opens as numbered sections with `document=` in the URL; a question ends in a finding whose citation highlights the document's own text; the landing's review opens as the run it names; the most-favoured-nation question is not answered with an invented clause; reload restores the run; a question right after a review keeps its own answer; Findings and Runs show the record and the pack downloads; the memo is written with no second model call |
| `reliability.spec.ts` | 12 | failure states (provider outage, non-schema output, dropped stream finishing by polling); promises on the wire (same question returns the same run, document travels compressed, memo names its run); state that survives (confirmed after reload, out-of-date tab refused then corrected, URL alone restores cold); interaction and accessibility (Escape closes the drawer, phone reopens on the answer, narrow window shows one pane, axe finds no serious or critical violation on landing, workspace and drawer) |
| `defects.spec.ts` | 10 | a decision on Findings shows in the drawer; a late memo is not shown under an earlier answer; a late run stays with its contract; one failed health check does not hide the model's place; refused files on Documents and Findings at desktop and phone keep the reader there; a newer failure replaces a refusal and vice versa; a slow earlier failure does not replace a newer refusal |
| `critical.spec.ts` | 4 | review against guidance ends in a finding with the guidance in the drawer; a malformed upload is refused and nothing opens; a file whose bytes contradict its name is refused, then opens under its own name; a refresh mid-run reattaches |
| `layout.spec.ts` | 4 | answer, record and drawer stay in their boxes from 768 px; views stay in their panes; every Tab stop is visible and moves nothing at 1440 and 375 px; a long unbroken file name keeps the questions pane on screen at 375, 768 and 1280 px |
| `state.spec.ts` | 4 | `/state` on desktop and phone from the fixture (served by `page.route`), no overflow, no console errors, axe clean; keyboard nav and arrival picker in the URL; an unavailable record is said with a retry |
| `break.spec.ts` | 1 | `/break` at 1280 and 375 px: the failure reads, the investigation controls work, no `/api/` request, no serious axe violation |
| `revision.spec.ts` | 1 | the prepared revision is recorded, the same question asked of it, and the two answers set side by side with who decided |
| `polish.spec.ts` | 3 | a delayed contracts read announces loading, then shows the real records; question fields grow, shrink and reflow with Send on screen; quote context keeps the sheet header reachable and Escape returns focus |
| `security.spec.ts` | 1 | the CSP carries a nonce and no `unsafe-inline`; injected markup and an injected inline script do not run; the nonce changes per response |

#### The replay provider and `e2e/replay.json`

- `playwright.config.ts` starts the API with `WORKBENCH_PROVIDER=replay` (or `record`), its own data directory
  (`backend/data/e2e`, or `backend/data/e2e-record` when recording, so every question reaches the model), and
  `WORKBENCH_RUN_START_LIMIT=1000`. The replay file defaults to `e2e/replay.json`
  (`backend/app/config.py`, `WORKBENCH_REPLAY_FILE`).
- The provider (`backend/app/providers/replay.py`) keys each answer by `sha256(system + "\n␞\n" + user)`: the exact
  system prompt and user message, nothing else. A request with no recorded answer fails with "no recorded answer for
  this request (key …)", never a made-up answer. So any change to the prompt, the retrieval, the section window or
  the contract text sent invalidates keys.
- Each entry holds `model`, `text` (the raw JSON the model returned), token counts, `latency_ms`, `recorded_at` and
  `user_head` (the user message's first line, for humans; not used to match). At this commit there are six entries,
  all `qwen3:8b`, recorded 2026-10-30: the MFN question, the liability question (plain and with a delay marker),
  two cure-period questions (the revision flow), and "Review against instructions".
- Markers in a question, honoured by the replay provider only: `[[fault:provider]]` (simulated outage),
  `[[fault:garbage]]` (non-JSON output), `[[zzdelay]]` or `[[zzdelay:<letters>]]` (hold the answer 8 s so a flow can
  reload mid-run; stripped before the key is computed, so it is served by the plain question's entry). Nonces in flow
  questions are letters only, because the question is also the retrieval query and a digit could match a section.
- Re-recording: with Ollama running the recorded model, in PowerShell `$env:E2E_PROVIDER = "record"; npm run e2e`,
  then commit `e2e/replay.json`. Timeouts rise to 600 s; fault flows are skipped while recording. The recorder adds
  or replaces keys and never removes them. Because it hashes the delayed question with its marker, the delay entry
  appears unused in replay (inference from the code, not verified by running).

#### Ports

| Port | What | Set in |
|---|---|---|
| 8001 | API for the flows (`http://127.0.0.1:8001`, health at `/api/health`) | `playwright.config.ts`; `reliability.spec.ts` names it as `API` |
| 3901 | Interface for the flows (`http://localhost:3901`) | `playwright.config.ts` |
| 8011 / 3911 | The same, inside the release gate, which rewrites a copy of the config and the specs and never reuses a running server | `scripts/release-gate.sh` |
| 8000 / 3900 | The development API default and the live interface (not used by the flows) | `lib/api.ts apiBase`; deploy |

Outside CI, Playwright reuses a server already listening on 8001 or 3901 (`reuseExistingServer: !process.env.CI`).
A stale server there means the flows test that server, not your tree.

### 8.7 Changing the interface safely

Before any change: the interface renders and asks; it never decides. If a change needs a new judgement (is this
quote good enough, should this status be lower), it belongs in the API (chapters 5 to 7), and the interface shows
the API's new field.

#### Add a view

1. Add the id to `View` and `VIEWS` in `shell/constants.ts`. `useUrlState` accepts any id in `VIEWS` from `?view=`.
2. Add a rail button in `shell/Rail.tsx` (label, icon from `icons.tsx`, `aria-current` follows `active`).
3. Render it in `Workbench.tsx` beside `DocumentsView`/`FindingsView`/`RunsView` (inside the non-assistant branch),
   pass `notice={noticeText(notice)}`, and add its name to the tab-title effect and a "Go to" palette command.
4. Build it from `views/Views.module.css` classes, `Figures`, `ListSkeleton` and `ReadFailed`; fetch on mount with a
   `cancelled` guard as the other views do.
5. Tests: a view test beside it; a `useUrlState` case if it carries state in the address; a flow in
   `e2e/layout.spec.ts` (the pane-overflow control) if it has new layout. Remember the frozen-system limits (8.5).

#### Show a new field from the API

1. Change `backend/app/schemas.py`, then `python backend/scripts/export_openapi.py` and `npm run api:types`. Commit
   `openapi.json` and `src/lib/api.schema.ts` together. Never edit `api.schema.ts` by hand.
2. If a component needs a new schema, alias it in `src/lib/types.ts` (components may not import the schema).
3. Render model- or file-written strings with `<Visible>` or `shownText`; slice located text by code points
   (`lib/text.ts`); never `String.prototype.slice` on API offsets.
4. If the field changes what a status means or who decided it, its words go in `lib/types.ts` or `lib/checks.ts`,
   the shared tables every surface reads; do not word it locally in one component.
5. A record made before the field existed carries `null`: say nothing for it rather than guess (the pattern used by
   `retrievalNote`, `sectionsReadNote`, `readingParts`).
6. A new endpoint is a function in `lib/api.ts`, using `request` and the `route` tag for ids.

#### Change copy

- Words that state who decided (status labels, code accounts, check rows) live in `lib/types.ts` and `lib/checks.ts`
  and have unit tests that pin them; change the table, not the component, and update those tests deliberately.
- `backend/tests/test_docs_claims.py` reads interface files:
  - `src/lib/independence.ts`: `INDEPENDENCE` must appear verbatim in the README.
  - `landing/LandingStory.tsx`: its sentences on what the model is shown and sent must match the backend's config
    (retrieval k and section window written as words, "the question, any guidance, the contract's file name and the
    sections retrieval ranked"), and its sentence "lowers some passes whose quote leaves out" must name only words the
    condition check reads.
  - every non-test `src/**/*.tsx`: a line mentioning what is "sent" or "handed to the model" with "question" and
    "guidance" must also name the file "name".
  - every non-test `src/**/*.ts*`: no sentence may deny a check code now performs (the `DENIAL` patterns in
    `backend/tests/test_docs_claims.py`, which match a denial of the left-out-condition and one-value-for-every-party
    checks).
- `backend/tests/test_amended_sample.py` reads `samples.ts`; `backend/tests/test_break_record.py` re-checks
  `break-record.json`. Regenerate that file with `backend/scripts/export_break_record.py`, never by hand.
- The flows match visible text and accessible names ("try a sample agreement", "Ask a question about this contract",
  "Inspect evidence", `data-testid`s such as `layer-code`, `coverage-note`, `revision-check`, `build-identity`).
  Search `e2e/` and `src/**/*.test.tsx` for a string before you change it.
- No sentence may claim more of code than the record says (a pass is "the model's view" unless its source says
  otherwise), or claim where the model runs before `/api/health` says (`lib/modelPlace.ts`).

#### Add an API call or a stream

Put it in `lib/api.ts`. Components may not call `fetch` or `EventSource` (lint). If a component must fetch a static
file of this origin, write the disable comment with its reason, as `loadSample` does.

#### Change prompts, retrieval or anything sent to the model

The replay keys change. Re-record `e2e/replay.json` (8.6) against the same model, check the flows pass, and commit
the file. The replay provider refuses unknown requests; a flow failing with "no recorded answer" means this.

#### Change the page shell or a Next primitive

Read the installed Next docs first (`node_modules/next/dist/docs/`; `AGENTS.md` says they outrank memory). Keep
`await connection()` in `layout.tsx` and the `proxy.ts` matcher unless the CSP is redesigned; `e2e/security.spec.ts`
and `lib/csp.test.ts` catch a regression.

#### Checks before saying done

```
npm run typecheck        # tsc --noEmit
npm run lint             # eslint, zero warnings allowed
npm run format:check     # prettier, src/ only, 160 columns
npm test                 # vitest
npm run e2e              # playwright: builds into .next-e2e, starts API :8001 and web :3901, replays the model
```

The release gate (`scripts/release-gate.sh`) runs `npm ci`, vitest, lint, tsc, `npm run build` and the flows on a
fresh clone (on 8011/3911). It does not run `format:check` (verified by reading the script's frontend steps; the
gate's other steps are chapter 9's). The flows need the backend's virtualenv (`backend/.venv`) or a `python` on the
path with the backend's requirements.

#### Common mistakes

| Mistake | Why it breaks | Instead |
|---|---|---|
| `text.slice(span.start, span.end)` | API offsets are code points | `splitByCodePoints` or `<Visible start end>` |
| `{finding.topic}` in JSX | invisible characters act on the page | `<Visible text={finding.topic} />` |
| `` `/api/runs/${id}` `` | an id from the address could choose a route | `` route`/api/runs/${id}` `` |
| showing `follower.run` directly | it may belong to another contract | read `beside(follower, doc.id)` |
| setting screen state after an `await` without a claim | a slower, older action lands over a newer one | `const latest = beginAction(); …; if (!latest()) return;` |
| a second question while one is live | abandons the run on screen | check `runs.live` |
| labelling a pass "Within guidance" | overstates code's role | `statusLabel(status, hasGuidance, source)` |
| a new colour, font or theme | the visual system is frozen | existing tokens and module classes |
| a statically rendered page | no nonce, scripts refused by the CSP | keep pages per-request |
| editing `api.schema.ts` or `break-record.json` | generated; overwritten and re-checked | regenerate from the backend |

## 9. Running, testing and shipping

This chapter covers how Verity is started, checked, released and operated, and what every file outside `backend/app/`
and `src/` that serves those jobs does. It was written from the repository at commit `865356b` (the live site's
commit) by reading files only: no command below was run for this chapter. Where a fact could not be read from a file,
the text says "not verified".

Paths are repository-relative. Ports used throughout:

| Port | What listens | Who uses it |
|---|---|---|
| 8000 | the API (uvicorn) | local development and the live laptop deployment |
| 3900 | the interface (`next dev` or `next start`) | local development and the live laptop deployment |
| 8001 / 3901 | API / interface for the browser flows | `playwright.config.ts` (`npm run e2e`) |
| 8011 / 3911 | API / interface for the browser flows inside the release gate | `scripts/release-gate.sh` (rewritten copy of the config) |
| 11434 | Ollama | the model (`WORKBENCH_OLLAMA_URL`, default `http://127.0.0.1:11434`) |
| 20241 | cloudflared metrics | `backend/scripts/status.py` `tunnel` line |

---

### 9.1 Run it locally from zero

#### 9.1.1 Prerequisites

| Need | Version | Where the version comes from |
|---|---|---|
| Python | 3.13 | `README.md` ("Python 3.13"); `backend/pyproject.toml` (`python_version = "3.13"` for mypy); `deploy/cloud/Dockerfile.api` (`python:3.13-slim`, pinned by digest); `backend/app/serving.py` copies CPython 3.13's Windows proactor internals (`asyncio.proactor_events`), so a different minor version may not match it on Windows |
| Node.js | 22 | `README.md` ("Node 22"); `deploy/cloud/Dockerfile.web` (`node:22-slim`). `package.json` declares no `engines` field and there is no `.nvmrc` |
| Ollama | not pinned for the laptop | the cloud kit names Ollama 0.40.4 (`deploy/cloud/README.md`); `docs/CASEBOOK.md` case 6 measured 0.40.6 and 0.40.7 on the serving machine. `status.py` prints the running server version |
| Model | `qwen3:8b` | default of `WORKBENCH_MODEL` in `backend/app/config.py`; the cloud kit pins digest `500a1f067a9f` (Q4_K_M). `WORKBENCH_MODEL_DIGEST` makes the API refuse a different build |
| Playwright browser | Chromium | `npx playwright install chromium`, once per machine (`docs/STATUS.md`, Checks) |
| Git Bash (Windows) | any | `scripts/release-gate.sh` is a bash script ("Git Bash on Windows", `docs/STATUS.md`) |

Pull the model once:

```bash
ollama pull qwen3:8b
```

**Ollama's host-RAM prompt cache must be off** wherever answers are meant to be reproducible (the live site, golden
recordings, the release gate's exporter step). `deploy/README.md`: set the user environment variable
`LLAMA_ARG_CACHE_RAM=0`, then quit Ollama and start it again; leave `OLLAMA_NUM_PARALLEL` unset or 1. Why
(`docs/CASEBOOK.md` case 6, `DECISIONS.md` 2026-10-21): llama-server starts a prompt from the longest prefix it already
holds, in its slot or in an 8 GiB host-RAM cache, so one recorded input at temperature 0 gave two different answers
depending on what was asked before it. The fix needs both the setting and the API's one-token raw prompt sent before
every answer (`OllamaProvider._start_clean`, held by `backend/tests/test_model_from_token_zero.py`). Nothing in the API
checks the setting; `backend/scripts/status.py` reports it on its `cache` line.

The repository does not give the exact command for setting the variable. One way, not taken from the repository:

```powershell
[Environment]::SetEnvironmentVariable("LLAMA_ARG_CACHE_RAM", "0", "User")   # Windows; then quit Ollama and start it again
# Unix (not verified): LLAMA_ARG_CACHE_RAM=0 in the environment of the process that runs `ollama serve`
```

#### 9.1.2 The API

From `README.md` ("Run it"):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate                         # Windows PowerShell: .venv\Scripts\activate
pip install -r requirements.lock -r requirements-dev.txt
uvicorn app.main:app --port 8000
```

- Install from `requirements.lock` (every version pinned). `backend/requirements.txt` is an unpinned list that
  nothing installs; Dependabot watches it (`docs/STATUS.md`, Dependencies).
- On Windows, a venv under a path with a short-name component (`NAME~1`) fails at `ensurepip`; this is why the release
  gate clones beside the repository and not into a temp folder (`scripts/release-gate.sh` comment).
- Data directory: `WORKBENCH_DATA_DIR`, default `backend/data` (`backend/app/config.py`). It holds `workbench.db`
  (SQLite, WAL), `documents/` (original uploads), `memos/`, `logs/`, and on the deployment `access.secret` and
  `access.revoked`. It is gitignored. `WORKBENCH_DATABASE_URL` overrides the database URL alone.
- The deployment starts the API with more flags (`deploy/supervise.ps1`, `deploy/up.ps1`):

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --loop app.serving:ResilientProactorEventLoop --no-access-log
```

  `--loop app.serving:ResilientProactorEventLoop` exists only on Windows (`serving.py` defines it under
  `sys.platform == "win32"`). It is the proactor loop with one change: an accept that failed because the client reset
  the connection (WinError 64) is retried instead of closing the listening socket, which once left the live API up and
  answering no one (`docs/CASEBOOK.md` case 1). On Unix use the default loop; the cloud image runs
  `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --loop asyncio --no-server-header`. Always one worker:
  SQLite, the in-process run executor, the event bus and the limiters assume one process.

Check it: `GET http://127.0.0.1:8000/api/health` answers 200 with whether the model is reachable and the gate state
(`access`: `off`, `required` or `entered`).

#### 9.1.3 The interface

From the repository root, in a second shell (`README.md`):

```bash
npm ci
npm run dev -- -p 3900                            # http://localhost:3900
```

`package.json` scripts: `dev` (`next dev`), `build` (`next build`), `start` (`next start`), `lint`
(`eslint --max-warnings=0`), `typecheck` (`tsc --noEmit`), `format:check` (prettier over `src/**/*.{ts,tsx,css}`),
`test` (`vitest run`), `e2e` (`playwright test`), `api:types` (`openapi-typescript openapi.json -o src/lib/api.schema.ts`).

Where the interface finds the API (`src/lib/api.ts`, `apiBase`): `NEXT_PUBLIC_API_URL` if set at build time;
otherwise a development build uses `http://127.0.0.1:8000` and a production build uses its own origin (relative URLs,
for a proxy that sends `/api` to the API). So a local production build needs the variable at build time. This is what
`deploy/up.ps1 -Local` does:

```powershell
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"; npm run build; npm run start -- -p 3900
# Unix: NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run build && npm run start -- -p 3900
```

The API's CORS default already allows `http://localhost:3900` and `http://127.0.0.1:3900`
(`WORKBENCH_CORS_ORIGINS`). Other build-time variables: `NEXT_PUBLIC_PROOF_RUN` (the finished run the first screen
offers), `NEXT_PUBLIC_BUILD_SHA` (shown on Runs as "Interface built from commit"), `NEXT_PUBLIC_HOSTING=cloud`
(cloud images), `NEXT_PUBLIC_EXPORT=state` with `NEXT_PUBLIC_WORKBENCH_URL` (the static `/state` mirror), and
`NEXT_DIST_DIR` (build directory; `.next` by default, `.next-e2e` for the flows, `.next-staging` for a deploy build).

The `AGENTS.md` block written by `next dev` says the installed Next.js docs under `node_modules/next/dist/docs/` are
authoritative and that `next dev` re-adds that block; committing it keeps the tree clean.

#### 9.1.4 Environment settings

All read in `backend/app/config.py` at import time. Defaults "work on a laptop with Ollama running".

| Variable | Default | Notes |
|---|---|---|
| `WORKBENCH_PROVIDER` | `ollama` | `record` or `replay` for the browser flows (below); nothing else in `app/` answers for the model |
| `WORKBENCH_MODEL` | `qwen3:8b` | part of a run's identity |
| `WORKBENCH_OLLAMA_URL` | `http://127.0.0.1:11434` | an address, not `localhost` (IPv6 first cost 2 s per call on Windows) |
| `WORKBENCH_MODEL_DIGEST` | empty | pin the model build; a different build is refused |
| `WORKBENCH_OLLAMA_HEADERS` | empty | JSON object of headers for a model behind an authenticating proxy; anything else stops the start |
| `WORKBENCH_MODEL_HOST`, `WORKBENCH_MODEL_ON_SERVER` | empty | where health says the model runs; setting both is an error |
| `WORKBENCH_MODEL_CONCURRENCY` | 1 | model calls in flight per process |
| `WORKBENCH_MODEL_WAKEUP`, `_WAKEUPS_PER_DAY`, `_AWAKE_S` | off, 10, 240 | waking a hosted model that sleeps (cloud plans) |
| `WORKBENCH_HEALTH_PROBES_MODEL` | 1 | whether `/api/health` asks the model server |
| `WORKBENCH_PROMPT_VERSION` | `answer-v2` | prompt files under `backend/app/analysis/prompts/`, frozen by manifest |
| `WORKBENCH_RETRIEVAL` | `bm25` | `hybrid` needs an embedding model (`WORKBENCH_EMBED_MODEL`, default `nomic-embed-text`) |
| `WORKBENCH_RETRIEVAL_K` | 6 | part of a run's identity |
| `WORKBENCH_RETRIEVAL_ALIASES` | 1 | the alias table, on since its measurement |
| `WORKBENCH_SECTION_WINDOW` | 6000 | characters of each section the model is shown |
| `WORKBENCH_ROUTING_POLICY` | `{}` | task to model overrides; empty by rule (`docs/ROUTING.md`) |
| `WORKBENCH_DATA_DIR` | `backend/data` | the store; the public demo uses its own directory |
| `WORKBENCH_DATABASE_URL` | empty | overrides the SQLite URL |
| `WORKBENCH_REPLAY_FILE` | `e2e/replay.json` | the replay provider's recordings |
| `WORKBENCH_CORS_ORIGINS` | `http://localhost:3900,http://127.0.0.1:3900` | comma-separated |
| `WORKBENCH_APP_URL` | `http://localhost:3900` | links from memos and packs back to the workbench |
| `WORKBENCH_ACCESS_SECRET` | empty | the gate is on when set; the deployment reads it from `backend/data/access.secret` |
| `WORKBENCH_ACCESS_REQUIRED` | off | with it, a missing or short (<32 chars) secret stops the API from starting |
| `WORKBENCH_ACCESS_REVOKED`, `WORKBENCH_ACCESS_SESSION_DAYS` | empty, 7 | revoked invite subjects; session length |
| `WORKBENCH_ANONYMOUS_SESSIONS` | off | the public demo: each browser gets its own workspace |
| `WORKBENCH_ANONYMOUS_RETENTION_DAYS` | 7 | a visitor workspace's life |
| `WORKBENCH_ANONYMOUS_MAX_DOCUMENTS`, `_MAX_RUNS_PER_DAY`, `_MAX_RUNS_IN_FLIGHT` | 10, 30, 2 | per visitor workspace |
| `WORKBENCH_ANONYMOUS_MAX_UPLOADS_PER_DAY`, `_MAX_UPLOAD_BYTES_PER_DAY` | 300, 1 GiB | all visitors together |
| `WORKBENCH_PUBLIC_MAX_RUNS_IN_FLIGHT` | 8 | the public model queue; past it a question is refused at once |
| `WORKBENCH_PUBLIC_REQUESTS_PER_NETWORK`, `_STREAMS_PER_WORKSPACE`, `_STREAMS_PER_NETWORK` | 8, 4, 16 | requests and event streams at the door |
| `WORKBENCH_PUBLIC_MIN_FREE_BYTES` | 2 GiB | uploads and writes pause below it |
| `WORKBENCH_MAX_RUNS_PER_DAY` | 0 (no ceiling) | the supervisor sets 200 for the public store |
| `WORKBENCH_RUN_START_LIMIT` | 20 | run starts per reader in ten minutes; the flows set 1000 |
| `WORKBENCH_LOG_DIR`, `WORKBENCH_LOG_SEGMENT_BYTES`, `WORKBENCH_LOG_KEEP_BYTES` | unset, 10 MiB, 200 MiB | the API's own bounded log (`backend/app/log_sink.py`) |
| `WORKBENCH_EXPERIMENTS_RESULTS`, `WORKBENCH_EXPERIMENTS_URL` | a sibling `ivo-experiments/docs/results.json` | the killed experiments on Runs; absent means "not connected" |
| `WORKBENCH_CONTRACT_STATE` | a sibling `ivo-experiments/.../contract-state.json` | the `/state` record |
| `WORKBENCH_FUZZ_SCALE` | 1 | tests only: multiplies Hypothesis and Schemathesis budgets; 20 is the deep pass |
| `WORKBENCH_CORPUS_SOURCES` | a sibling `ivo-experiments` CSV | `data_audit.py` only |

#### 9.1.5 Running without a GPU: the replay provider

`backend/app/providers/replay.py`, chosen only by `WORKBENCH_PROVIDER=record|replay`:

- `record` wraps Ollama and writes every answer to the replay file.
- `replay` serves only what was recorded (key: a hash of system and user message), byte for byte, and fails loudly
  for anything else. A changed prompt or a change in the retrieved sections shows as a missing key, never as a
  different answer. The run built from a replayed answer is verified, decided and stored like a live one.
- Markers in a question, honoured by the replay provider: `[[fault:provider]]` (provider down), `[[fault:garbage]]`
  (non-schema output), `[[zzdelay]]` or `[[zzdelay:<letters>]]` (hold the answer 8 s so a flow can refresh mid-run).

The committed recordings in `e2e/replay.json` cover the questions the browser flows ask about the bundled sample, so
a replay API answers those and fails every other question. To run the API this way, give it a separate store:

```powershell
$env:WORKBENCH_PROVIDER = "replay"; $env:WORKBENCH_DATA_DIR = "data\replay"; .venv\Scripts\python -m uvicorn app.main:app --port 8000
# Unix: WORKBENCH_PROVIDER=replay WORKBENCH_DATA_DIR=data/replay uvicorn app.main:app --port 8000
```

(The separate data directory is advice from `playwright.config.ts`'s practice, not a documented command.) Re-recording
the flows' answers needs Ollama: `$env:E2E_PROVIDER = "record"; npm run e2e`, then commit `e2e/replay.json`
(`playwright.config.ts` header). A recording gets its own store (`backend/data/e2e-record`) so every question reaches
the model.

---

### 9.2 Checks

#### 9.2.1 What an agent runs before saying a change is done

From `AGENTS.md`, in this order:

```bash
cd backend && python -m ruff format --check . && python -m ruff check . && python -m mypy && python -m pytest -q
npm run typecheck && npm run lint && npm run format:check && npm test
npm run e2e   # browser flows: builds the interface, replays the model's recorded answers; about three minutes
```

`docs/STATUS.md` (Checks) adds `lint-imports` (the three import contracts in `backend/.importlinter`: verifier pure,
providers blind, layers downward) and notes:

- `python -m mypy` reads its scope from `pyproject.toml` (strict, app + scripts + tests). On 2026-10-13 that wider run
  reported errors in test files; the gate runs mypy on `app` and the exporter only.
- `pytest -q` needs no model: the `client` fixture uses `FakeProvider`. One Schemathesis fuzz of every route runs at
  default scale; `WORKBENCH_FUZZ_SCALE=20` is the deep pass.
- Two backend tests run only on Windows: `test_supervisor_records.py` (needs PowerShell) and `test_accept_resets.py`
  (the proactor accept failure).
- `npx playwright install chromium` is needed once per machine before `npm run e2e`.
- After changing `backend/app/schemas.py`: `python backend/scripts/export_openapi.py` then `npm run api:types`, and
  commit both `openapi.json` and `src/lib/api.schema.ts` (nothing automated checks they match).
- After changing what a document claims, run `backend/tests/test_docs_claims.py`; it holds `README.md` and
  `docs/STATUS.md` counts and versions to the code.

No CI runs any of this. A workflow exists only on a local branch named `ci`; it was never pushed (the token lacks the
`workflow` scope). The GitHub Actions tab shows only Dependabot's own jobs (`docs/STATUS.md`).

#### 9.2.2 The release gate, `scripts/release-gate.sh`

```bash
bash scripts/release-gate.sh <commit>                         # clones into ../verity-gate/clone
GATE_DIR=/some/scratch bash scripts/release-gate.sh <commit>
```

Every step records its own exit status; a line of output is never taken as the verdict. Any failed step ends the run
with `GATE FAILED: <sha> (n step(s))`, the failed step names, and exit 1. All passing prints `GATE PASSED: <sha>`.

| # | Step name (as printed) | What runs | Passes when |
|---|---|---|---|
| 0 | (abort, not a step) | removes `$GATE_DIR/clone` and `$GATE_DIR/verity-export`; `git clone` of the source repo; `git checkout <sha>`; prints porcelain count and files changed by the last commit | aborts at once if the clone dir cannot be removed or the commit cannot be checked out |
| 1 | backend environment | `python -m venv .venv`; `pip install -q -r requirements.lock -r requirements-dev.txt` | pip exit 0 |
| 2 | backend full suite | `pytest -q -p no:cacheprovider -rf` | exit 0 |
| 3 | backend named suites | `pytest` on `test_workspaces.py test_trust.py test_run_identity.py test_run_invariants_stateful.py test_review_evidence_export.py` | exit 0 |
| 4 | ruff check | `ruff check .` | exit 0 |
| 5 | ruff format | `ruff format --check .` | exit 0 |
| 6 | mypy | `mypy app scripts/export_review_evidence.py tests/test_review_evidence_export.py` | exit 0 |
| 7 | import contracts | `lint-imports` from the venv | exit 0 |
| 8 | trust fault matrix | `scripts/trust_faults.py` | every fault caught, every file restored |
| 9 | fault run left the tree clean | `git status --porcelain` count | 0 lines |
| 10 | npm ci | `npm ci --no-audit --no-fund` (log `npm-ci.log`) | exit 0 |
| 11 | frontend unit tests | `npx vitest run` (log `vitest.log`) | exit 0 |
| 12 | eslint | `npm run lint` (log `lint.log`) | exit 0 |
| 13 | tsc | `npm run typecheck` (log `tsc.log`) | exit 0 |
| 14 | production build | `npm run build` (log `build.log`) | exit 0 |
| 15 | browser flows start their own servers | writes `pw-gate.config.ts` from `playwright.config.ts` with ports 8011/3911, `NEXT_DIST_DIR=.next-e2e-gate`, `reuseExistingServer: false`; rewrites the port in `e2e/*.spec.ts` | the copy has `reuseExistingServer: false` and no `reuseExistingServer: !` |
| 16 | browser flows | `npx playwright test -c pw-gate.config.ts` (log `playwright.log`); then removes the copy and its build and restores `tsconfig.json` and `e2e/` | exit 0 |
| 17 | evidence exporter | `scripts/export_review_evidence.py --out $GATE_DIR/verity-export` | exit 0 |
| 18 | exported run record unchanged by the diff, no model call after the revision | inline Python reads `bundle.json` and `records/review-snapshot.json` | run record hash equal before and after the diff and 0 model calls after the revision |
| 19 | exporter names its commit | compares `source_commit` in `bundle.json` with the last commit that touched the exporter or `scripts/revision_evidence/` | equal |
| 20 | clean tree at the end | `git status --porcelain` | 0 lines |

Notes that change how a gate run is read:

- Step 17 records a real review with **the configured model** (Ollama `qwen3:8b` unless the shell sets another
  provider), so Ollama must be up with the model pulled. Whether the gate can pass with `WORKBENCH_PROVIDER=replay`:
  not verified (the replay file is not known to hold the exporter's fixture questions).
- The flows run on 8011/3911 and never reuse a server, because on 2026-10-13 a stale replay stack on those ports
  answered every gate's flows for hours. A taken port now fails the step.
- The gate does **not** run: the hand mutants (`backend/scripts/mutate_by_hand.py`), prettier (`npm run format:check`),
  the deep fuzz pass, mypy over all of `scripts` and `tests`, or a check that `src/lib/api.schema.ts` matches
  `openapi.json` (the full suite does check that `openapi.json` equals the API, in `tests/test_api_contract.py`). `backend/tests/test_docs_claims.py` holds `docs/STATUS.md`'s list of what the gate does not run to the script.
- The gate does not install Playwright's browser; it must already be on the machine (not verified otherwise).
- Each gate run's counts are only in its own log under `$GATE_DIR`.

#### 9.2.3 The trust fault matrix, `backend/scripts/trust_faults.py`

Seventeen planted faults in `backend/app/trust/` (`diff.py`, `compile.py`, `model.py`) and two application modules it
leans on (`application/trust_run.py`, `application/versions.py`). For each: replace one exact line, run
`pytest tests/test_trust.py -q -x`, restore the bytes, compare them. Output lines `CAUGHT` or `MISSED`, then
`n of 17 faults caught`. Exit 0 only when all 17 are caught and every file is restored byte for byte; exit 2 (`STALE`)
when a fault's line is no longer in its file exactly once, which means the fault list must be updated with the code.
Run: `cd backend && .venv/Scripts/python scripts/trust_faults.py`.

#### 9.2.4 Hand mutants, `backend/scripts/mutate_by_hand.py`

Twenty-four mutants of the evidence boundary (`M1` "mismatch counts as verified" through `M24`), each changing one
decision line in the run service, the verifier, the database triggers, the evidence pack's `verify_template.txt` and
similar. For each: apply, run the suite, restore from memory in a `finally`, compare bytes; it refuses to report
success if anything differs. Every mutant must be killed. Run by hand, not by the gate:

```bash
cd backend && .venv/Scripts/python scripts/mutate_by_hand.py          # all
cd backend && .venv/Scripts/python scripts/mutate_by_hand.py M3 M7    # by name prefix
```

It writes to tracked files under `backend/app/` while it runs. Do not run it beside a live server reading the same
checkout, and do not interrupt it (not verified what an interrupted run leaves; the restore is in `finally`).
`test_docs_claims.py` holds the README's counts of mutants (24) and faults (17) to these scripts.

#### 9.2.5 Browser flows, `npm run e2e`

`playwright.config.ts`: Chromium at 1280x800, one worker, not parallel, retries only under `CI`. It starts two servers:

- the API: `<venv python> -m uvicorn app.main:app --host 127.0.0.1 --port 8001` from `backend/`, with
  `WORKBENCH_PROVIDER` = `E2E_PROVIDER` or `replay`, data dir `backend/data/e2e` (or `e2e-record`), CORS for 3901 and
  `WORKBENCH_RUN_START_LIMIT=1000`;
- the interface: `npm run build && npm run start -- -p 3901` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001` and
  `NEXT_DIST_DIR=.next-e2e`, so `.next` (the live build on the serving machine) is untouched.

Outside `CI`, `reuseExistingServer` is true: a server already on 8001 or 3901 is reused. On the serving laptop a Docker
stack once held 8001. If results look wrong, check those ports first. 49 flows in `e2e/*.spec.ts` (`docs/STATUS.md`;
counted by `test_docs_claims.py`). Traces and screenshots are kept on failure only.

---

### 9.3 Tests map (`backend/tests/`, 195 files)

#### 9.3.1 How the test client and FakeProvider work

- `conftest.py`
  - `read_in_this_process` (autouse): sets `ingest.bounded.READ_IN_CHILD = False`, so files are parsed in the test
    process; `test_reading_cost.py` tests the child.
  - `client`: a fresh SQLite file at `tmp_path/test.db` bound into `app.db` (engine and `SessionLocal`),
    `settings.data_dir = tmp_path`, the gate off (`access_secret = ""`, `access_required = False`) whatever the
    machine's environment holds, rate limiters reset, a `FakeProvider`, `create_app(provider=provider)`, wrapped in
    FastAPI's `TestClient`. The fake is reachable as `client.provider`, so a test flips its knobs.
  - `public`: on top of `client`, the deployment's settings: secret set, gate required, anonymous sessions on, the
    test origin as `app_url`, every per-address and per-workspace limiter reset, `client.base_url` set to that origin.
- `support.py`
  - `CONTRACT`: a three-clause services agreement (term, termination for convenience at 15 days, governing law).
    `GUIDANCE`: 30 days or more.
  - `FakeProvider`: answers like a well-behaved model. It finds the `[sec_N] 2 Termination for Convenience` section in
    the user message (asserting it was handed) and quotes it verbatim with a `pass` hint. Knobs: constructor
    `paraphrase=True` (a quote not in the text); attributes `fail_always` (provider down), `fail_once` (one transient
    failure, retried), `garbage` (not JSON), `no_evidence`, `invented_reference` (a real quote under a section the
    document lacks), `cite_wrong_section`. Every call's user message is appended to `calls`.
  - `through_get_and_post`: lets a test that fakes `httpx.get`/`httpx.post` also answer `httpx.stream`, which the
    Ollama provider uses.
  - `FUZZ_SCALE` from `WORKBENCH_FUZZ_SCALE`.
  - `upload_and_ask(client, question, with_guidance=True)`: uploads `CONTRACT`, saves `GUIDANCE`, starts a run
    (expects 202) and returns the document, the run and its id.
- `code_closure.py`: finds the code a semantic version names by following its entry points through the app's AST
  (docstrings removed), for `test_semantic_versions.py`. Tests only.
- `dying_child.py`: reading children that die before answering, importable by name in a child process
  (`test_reading_cost.py`).
- `__init__.py`: empty package marker, so tests import `tests.support`.

#### 9.3.2 Fixtures (`backend/tests/fixtures/`)

| File | What it is |
|---|---|
| `fixtures/reader/content-controls.docx` | a block-level content control around a heading and a clause (reader sweep, `test_reader_sweep.py`) |
| `fixtures/reader/degenerate-tables.docx` | an empty table, a row without cells, a table inside a content control |
| `fixtures/reader/image-only-middle-page.pdf` | three pages, the middle one an image |
| `fixtures/reader/merged-cells.docx` | horizontal and vertical merges |
| `fixtures/reader/nested-tables.docx` | a table inside a cell |
| `fixtures/reader/utf16.txt` | UTF-16 LE with a byte-order mark |
| `fixtures/reader/windows-1252.txt` | "€1,500" and accented names in Windows-1252 |
| `fixtures/relations_oracle.json` | 34 agreements and 82 decisions written before the code by an independent author (`test_relations_oracle.py`) |
| `fixtures/services-agreement.pdf` | a PDF services agreement for PDF reading tests |
| `fixtures/store-release-2026-10-02.sql` | a `.dump` of a store made by release-2026-10-02 and upgraded since, without a later CHECK constraint (`test_store_schema.py`) |

The seven reader fixtures were generated by `research/depth_pass/gen_adversarial.py` and copied under plainer names;
regenerated files differ in bytes (python-docx stamps a time) but not in text.

#### 9.3.3 Reader and ingestion

| File | What it holds |
|---|---|
| `test_ingest.py` | DOCX read as the accepted view; same bytes parse the same; custom heading styles; numbered sections and tables in order; TXT headings; unsupported extension refused |
| `test_sections.py` | heading splitting, lead-ins, computed vs explicit numbering, oversized sections split at paragraphs |
| `test_pdf_ingest.py` | PDFs read as text; headings from numbering or capitals; flat files said so; quotes still verify |
| `test_coverage.py` | what the reader does not read (headers, footers, footnotes, comments) is counted and declared omitted |
| `test_hidden_styles.py` | text Word hides through a style never reaches the model (reader v6) |
| `test_hostile_packages.py` | entity bomb, deep nesting, 20,000 members, external relationships: refused or bounded, never a crash or network call |
| `test_reading_cost.py` | a reading past 768 MB or 30 s is ended in its child process (`ingest/bounded.py`) |
| `test_reader_boundary.py` | any parser failure on damaged bytes is a refusal with a reason, never a 500 |
| `test_reader_logs.py` | nothing of a file being read reaches a log line or the API's output |
| `test_reader_names.py` | file names of invisible characters, and where text a reader does not see is taken from |
| `test_reader_references.py` | a line opening with a reference to a clause does not open that clause |
| `test_reader_study_fixes.py` | fixes from the retrieval study: DOCX with no heading styles and other reading defects |
| `test_reader_sweep.py` | defects from the 2026-10-01 document sweep, each on the fixture file that exposed it |
| `test_reader_typed_headings.py` | a typed clause heading is a heading in a document that styles its others (reader v14) |
| `test_reader_v15.py` | schedule headings in every format; PDF running headers and footers left out and counted |
| `test_reader_v16_bounds.py` | bounded sections; long paragraphs cut only where a passage ends; invisible marks cannot part a number |
| `test_reader_v16_docx.py` | DOCX read as Word displays it, cell columns kept, unread parts counted (Word 16 as oracle) |
| `test_reader_v16_headings.py` | a capitals line is a heading only when it stands alone |
| `test_reader_v16_pdf.py` | PDF read in layout order (columns, tables); invisible text not read |
| `test_reader_v17_parts.py` | a section split for size says so as data, not in its heading |
| `test_docx_numbering.py` | reader v13/v14: a DOCX heading carries a number only when Word shows one |
| `test_running_lines.py` | a page's running header or footer is never a heading |
| `test_section_numbers.py` | a section number for a TXT or PDF reading is one the text states at the heading |
| `test_file_types.py` | a file is read as the type its bytes are; the name only claims it |
| `test_long_names.py` | a document's type is its checked media type; a long name is cut without breaking it |
| `test_invisible_characters.py` | Unicode format characters removed wherever text enters, and counted |

#### 9.3.4 Verifier (quote location)

| File | What it holds |
|---|---|
| `test_spans.py` | the ladder: exact offsets, normalised quotes and whitespace, casefold, paraphrase refused, label stripping, no match inside a longer number or word |
| `test_spans_properties.py` | Hypothesis: a located span never highlights text whose letters and digits differ from the quote |
| `test_tokens.py` | typed tokens keep number meaning while forgiving punctuation; matches are whole tokens |
| `test_verify_evidence.py` | a quote is found in its cited section, relocated from a wrong one, or not found; nothing past the model's window counts |
| `test_locate_prefilter.py` | prefilters only skip work; they never reject what the full ladder accepts |
| `test_verifier_v7.py` | a changed number is never found (tokens do not end inside a letter-digit run) |
| `test_verifier_v8.py` | no span begins or ends inside a number; signs kept |
| `test_verifier_v9.py` | a sign-inverted amount is never verified, in any currency or magnitude notation |
| `test_verifier_v11.py` | four ways v10 found a quote the text does not say, each reproduced and closed |
| `test_verifier_v12.py` | an invisible character inside a word no longer parts it at the typed tier, in the workbench and the pack; a property that invisible characters change nothing the typed tier decides |
| `test_verifier_v13.py` | a word read whole through a combining mark drops no part of the token it reaches, in the workbench and the pack; properties that reading words whole drops no character, that a changed digit and a clause letter of another case are never found, and that the pack compares as the workbench does under v13 |
| `test_replay_window.py` | `reverify` searches the window each run was verified over |

#### 9.3.5 Status policy and the finding account

| File | What it holds |
|---|---|
| `test_retrieval_and_status.py` | BM25 basics, RRF fusion, run identity carries the retriever, status computed from quote and guidance, reference check |
| `test_pass_gate.py` | a pass is the model's; code reads the source for reasons against it (`policy.proof`) |
| `test_pass_blockers_named.py` | "code found the day counts consistent" appears exactly when no reason against the pass holds |
| `test_policy_rules.py` | fixes from the 2026-10-01 hostile review: which duration, which comparison word, floor and ceiling |
| `test_policy_v10_calendar.py` | non-converting units on the calendar; Business Days from the contract's own definition |
| `test_durations.py` | durations parsed by code: units, doubts, words vs digits, business vs calendar days, months |
| `test_periods_as_written.py` | policy-v17: ranges, lists and number words read as written |
| `test_guidance_polarity.py` | a guidance bound read as written ("must not exceed" is a ceiling) or not read |
| `test_condition_words.py` | every way a contract opens a condition is read as one |
| `test_left_out_conditions.py` | a quote that drops its sentence's condition does not support a pass that drops it too (policy-v14) |
| `test_part_edges.py` | a sentence cut across two parts of a clause is read whole |
| `test_scoped_day_convention.py` | a "days" convention limited to one clause is not applied everywhere |
| `test_defined_terms.py` | one reader of where a contract defines a term |
| `test_located_text.py` | after verification, code reads the contract's text, never the model's spelling |
| `test_withheld_stays_withheld.py` | a finding with an unverified quote stays withheld whatever later checks say |
| `test_value_support.py` | a pass must not state a value its evidence does not show (policy-v6) |
| `test_values_from_the_guidance.py` | a value only the guidance states supports a comparison, never a statement about the contract |
| `test_value_choices.py` | when cited passages state several candidate values, code says so |
| `test_unquoted_values.py` | a number the answer states that no quote states is noted by code |
| `test_identifier_values.py` | an instrument's marked number is not a value the answer states (policy-v15) |
| `test_uniform_party_values.py` | one value given to every party when evidence gives it to some is not a pass (policy-v14) |
| `test_reference_check.py` | a reference is unknown only when the document has no such clause |
| `test_source_handles.py` | a section handle the model was not given is shown as such and lowers a pass |
| `test_unseen_disclosure.py` | a status says whether code compared a period and what the model never saw |
| `test_unhanded_amendment.py` | a pass resting on text an unhanded amendment changes is not established |
| `test_absence_wording.py` | "not found" means "not found in the sections read", and when retrieval ranked nothing |
| `test_clause_location.py` | a verified passage is placed by the clause its own text names |
| `test_finding_account.py` | one account of each finding (who set its status, what code raised), read alike by every surface |
| `test_prose.py` | the model's section handles become labels or a visible mark, never dropped |
| `test_post_pilot_repair.py` | five post-pilot repairs (verifier v10, reader v14, policy-v9, memo) with controls and properties |

#### 9.3.6 Contract relations and document versions

| File | What it holds |
|---|---|
| `test_relations_oracle.py` | replacement and precedence statements held to `fixtures/relations_oracle.json` |
| `test_relations.py` | relations beyond the oracle: what the stored corpus taught, plus properties |
| `test_relations_cost.py` | locating relations costs a bounded amount per statement |
| `test_relations_definitions.py` | a definition an amendment replaces is the replaced text |
| `test_relations_stance.py` | an answer's conclusion and stated value are each read for the replaced wording's values |
| `test_relations_surfaces.py` | one recorded account of relations, read alike by API, memo, list and pack |
| `test_policy_v16.py` | quoting the replacement is not following it |
| `test_amended_sample.py` | the synthetic amended sample offered on the first screen shows what it is offered for |
| `test_run_dates.py` | a run is reused only while the same amendment starts are reached |
| `test_version_statements.py` | concurrent version statements end as if made one after the other |

#### 9.3.7 Retrieval

| File | What it holds |
|---|---|
| `test_aliases.py` | the alias table: deterministic, versioned by hash, recorded on a run only when on |
| `test_lexical.py` | retrieval-v3: the tokenizer agrees with the verifier on what is one text; the cut |
| `test_retrieval_links.py` | retrieval-v2: sections the top-ranked ones depend on (definitions, amendments) |
| `test_retrieval_record.py` | the run records amendments left out for room and alias groups that widened the query |
| `test_section_window.py` | the section window is a run option recorded only when not the default |

#### 9.3.8 Model provider, admission and the queue

| File | What it holds |
|---|---|
| `test_admission.py` | bounded calls in flight; a person served four to one over a corpus job; waits recorded |
| `test_model_queue.py` | the public queue is bounded and visible |
| `test_model_transport.py` | one deadline per call, fields not words, a clean start, answers kept only from the build asked |
| `test_model_from_token_zero.py` | the one-token raw prompt before every answer, with the answer's load settings |
| `test_model_saw.py` | a prompt over the context window is refused, not cut; the answer says how many sections it had |
| `test_model_endpoint.py` | a remote model is the one named, with its credentials, never substituted |
| `test_model_wake.py` | waking a hosted model is bounded |
| `test_health_model.py` | health says where the model runs and never wakes a billed model |
| `test_replay_provider.py` | record and replay byte for byte; anything else fails; default provider untouched |
| `test_daily_budget.py` | past `WORKBENCH_MAX_RUNS_PER_DAY` a new question is refused with a sentence |

#### 9.3.9 Runs: lifecycle, identity, recovery and record

| File | What it holds |
|---|---|
| `test_api_flow.py` | the full path to a verified finding and a memo; paraphrase unresolved; garbage failed; SSE replay; reuse and retry; restart recovery |
| `test_failure_matrix.py` | one test per failure row: provider down and retry, 413/422 cases, triggers, prompt change, reader version, encrypted PDF, gzip |
| `test_transitions.py` | the run lifecycle is a table; nothing else can happen |
| `test_uniqueness.py` | one row per (bytes, reader), one memo per run, under concurrent first requests |
| `test_run_identity.py` | identity carries the rules; a run executes from what it recorded |
| `test_semantic_versions.py` | fingerprints of the code behind each version; fails until a version is bumped or re-recorded |
| `test_version_order.py` | a record made under newer rules is never called "earlier" nor re-checked as old |
| `test_run_invariants_stateful.py` | Hypothesis state machine of uploads, questions, reviews, undos, memos; invariants after each step |
| `test_run_endings.py` | how a run ends when something other than its worker ends it |
| `test_run_liveness.py` | a run is live while a worker answers it, not while its process exists |
| `test_run_ceiling.py` | no run stays open forever |
| `test_owner.py` | a stage row's owner is a process; only a provably dead owner's run is recovered at once |
| `test_run_outcomes.py` | a runs list says what each run concluded |
| `test_stream_resume.py` | a reconnecting stream gets only the events after `Last-Event-ID` |
| `test_reconstruct_input.py` | the exact model input is rebuilt from the record and hashes to the recorded value |
| `test_retry_provenance.py` | every kept output is stored with, or reconstructable to, its exact input; a retry's input is not claimed |
| `test_explanation.py` | "why this answer" is a projection of the record and nothing else |
| `test_prompts_frozen.py` | a used prompt file is frozen by `prompts/manifest.json` |
| `test_question_input.py` | a question is what is left after invisible characters are removed |
| `test_visible_input.py` | names, questions and guidance are stored only when something is visible |
| `test_failure_words.py` | a visitor reads plain words; server detail goes to the log |
| `test_visitor_wording.py` | counts agree with their nouns; two visitor sentences said right |

#### 9.3.10 Trust layer, evidence pack, memo, exports

| File | What it holds |
|---|---|
| `test_trust.py` | version-aware trust: supported findings, what a revision does to them (the fault matrix's target) |
| `test_trust_align_bounds.py` | a revision check compares a bounded number of section pairs |
| `test_evidence_pack.py` | the pack's `verify.py` re-hashes and re-locates with plain Python; tampering fails |
| `test_pack_binding.py` | every field the pack shows is checked or printed UNCHECKED |
| `test_pack_parity.py` | the pack's checker and the workbench agree on what each verifier version verified |
| `test_memo_atomicity.py` | a memo row never points at a missing file |
| `test_memo_display.py` | memo and pack text is the checked text (hostile model output) |
| `test_memo_docx.py` | the Word memo carries the run in properties, bookmarks and links |
| `test_memo_identity.py` | a memo handed back says what a memo written now would say |
| `test_memo_restraint.py` | a memo suggests a change only where review is needed |
| `test_memo_revisions.py` | a later review earns a new memo; the earlier stays |
| `test_acceptance_memo_withheld.py` | a memo accounts for every proposal, withheld ones included |
| `test_review_concurrency.py` | a review states the state it decided against; a stale decision is refused |
| `test_review_evidence_export.py` | `export_review_evidence.py`: the record and the bundle it writes |
| `test_break_record.py` | `/break`'s record re-checked by the product's own code |
| `test_export_state.py` | the static `/state` export writes exactly the frozen record |
| `test_contract_state_record.py` | the API reads the contract-state record, checks its hash, shows it as is |

#### 9.3.11 Access, workspaces, quotas and request bounds

| File | What it holds |
|---|---|
| `test_access.py` | with a secret, nothing but health and the gate answers without a session (walks every route) |
| `test_anonymous.py` | each public visitor gets a session and workspace of their own |
| `test_workspaces.py` | two reviewers, two workspaces: A's work is A's; curated records readable by all, changeable by none |
| `test_document_names.py` | a workspace sees the name it gave a file, never another workspace's |
| `test_name_leaks.py` | no workspace, nor the model, sees another workspace's name for the same bytes |
| `test_workspace_rows.py` | an ended public workspace adds no row by any path |
| `test_quota_admission.py` | a quota is counted and its row written in one transaction |
| `test_write_lock.py` | the primitive under every quota (`quotas.admit` over `db.write_locked`) |
| `test_quota_instant.py` | a daily quota counts a row on its own instant |
| `test_day_rollover.py` | daily quotas reopen at the next UTC day, not before |
| `test_network_windows.py` | hourly per-network bounds hold for IPv6 (/64) |
| `test_clock_steps.py` | a visit's life does not depend on the clock stepping |
| `test_body_limit.py` | no request body is read past its route's need |
| `test_cache_headers.py` | every API response is `no-store` unless it sets its own policy |
| `test_liveness.py` | health does not queue behind request threads; no network holds them |
| `test_upload_race.py` | a new document and its uploader's grant are one transaction |
| `test_mission_security.py` | two security-review defects (one visitor holding the queue, and a second) with controls |
| `test_hardening.py` | defects from the 2026-10-01 hostile review: names, control characters, overflow, absolute paths |

#### 9.3.12 Store, schema, files and retention

| File | What it holds |
|---|---|
| `test_hashing.py` | identity in one place; fails if any other app module imports `hashlib` |
| `test_db_columns.py` | an existing SQLite file gains new columns without losing rows |
| `test_db_concurrency.py` | no wait on a connection pool; a writer waits out another's write |
| `test_store_schema.py` | a store from any earlier build opens with today's constraints |
| `test_store_files.py` | files beside SQLite hold their rows' bytes across crash, purge and race |
| `test_store_faults.py` | health and `status.py` see a damaged store |
| `test_health_storage.py` | health reports a store that cannot take a write |
| `test_upload_atomicity.py` | a document row never exists without its bytes |
| `test_retention.py` | the public store deletes ended visitor workspaces and nothing else |
| `test_retention_files.py` | one undeletable file never stops a pass; in-use judged without the wall clock |
| `test_purge_bounds.py` | a retention pass holds the write lock for a bounded time |
| `test_process_state.py` | after retention the process keeps nothing of an ended visitor |
| `test_text_retention.py` | no contract text kept in memory past its work |
| `test_backup_restore.py` | `backup.py`: consistent under writes; restore checks every hash; history stays immutable |

#### 9.3.13 API contract, fuzz and import boundaries

| File | What it holds |
|---|---|
| `test_api_contract.py` | `openapi.json` describes what the API sends, error statuses included |
| `test_api_fuzz.py` | Schemathesis over the OpenAPI document with the fake provider: no 5xx |
| `test_import_contracts.py` | the verifier's purity and the `.importlinter` contracts checked whole |

#### 9.3.14 Performance and cost

| File | What it holds |
|---|---|
| `test_read_cost.py` | a list read costs a fixed number of queries whatever the rows (other cost bounds sit with their area) |

#### 9.3.15 Operations and deployment scripts

| File | What it holds |
|---|---|
| `test_accept_resets.py` | Windows only: the API keeps accepting after clients reset (`app/serving.py`) |
| `test_supervisor_records.py` | Windows only: `supervise.ps1` survives a log held open by a reader (`CreateFileW` share flags) |
| `test_status_script.py` | `status.py` reads the store read-only and each log once |
| `test_log_bounds.py` | the API's log is bounded per line, per flood and in total |
| `test_operability.py` | the log says why a run ended, why a request was refused, model vs queue time, which build answered |
| `test_compose_release.py` | the cloud stack runs exactly the release its `.env` names |
| `test_lockfile.py` | `package-lock.json` installs on Windows and Linux |

#### 9.3.16 Published figures and measurement records

| File | What it holds |
|---|---|
| `test_docs_claims.py` | README and STATUS versions, part, flow, mutant and fault counts, golden, CUAD and retrieval figures, and the "gate does not run" list, held to the code |
| `test_goldens.py` | the golden judge; Recording 6c replayed through the code in force |
| `test_cuad_score.py` | the CUAD scorer judges the reported answer over the whole pre-registered population |
| `test_data_audit.py` | the data audit keeps each set's denominator; deterministic |
| `test_batch.py` | a batch is the same run over a corpus; report from the records |
| `test_batch_csv.py` | `values.csv` opens in a spreadsheet as text (no formula injection) |
| `test_families.py` | families from structure, judged pairwise against labels |

---

### 9.4 Scripts (`backend/scripts/`)

All are run from `backend/` with the venv's Python (`.venv/Scripts/python` on Windows, `.venv/bin/python` on Unix).
"Store" means the data directory `WORKBENCH_DATA_DIR` (default `backend/data`). "Model" means the configured
provider is called.

| Script | What it does | Run | Writes? Model? |
|---|---|---|---|
| `status.py` | the operator's one look: lines `api`, `model`, `cache`, `disk`, `store`, `runs`, `rules`, `tunnel`, `api sup`, `web sup`, each `ok` or `PROBLEM`; exit 1 on any problem | `scripts/status.py` (owner store) or `scripts/status.py --data-dir <public store> --public` | read-only (SQLite `mode=ro`, each log read once); no model call (it asks Ollama for version and model list) |
| `backup.py` | consistent backup (SQLite online backup, `documents/`, `memos/`, manifest of sha256) and verified restore into an empty directory; secrets not copied | `create --data-dir <dir> --out <dir>`; `verify <dir>`; `restore <dir> --to <new dir>` | writes only the backup or restore target |
| `access.py` | the gate's secret and invite links | `secret [--replace]`; `invite <subject> [--days N] [--path "/?…"]`; `check "<link>"` | writes `backend/data/access.secret` (never printed); prints invites |
| `data_audit.py` | every agreement touched, by sha256: source, licence, role, measurements, denominators | `scripts/data_audit.py` or `--write` | read-only; `--write` replaces the marked block in `docs/DATA-EVIDENCE.md` |
| `export_openapi.py` | writes `openapi.json` at the repository root from `create_app().openapi()` | `scripts/export_openapi.py`, then `npm run api:types` | writes a tracked file |
| `export_review_evidence.py` | records one real review of `revision_evidence/agreement-v1.txt`, then v2 as its revision, in a scratch store, and writes an Evidence Bundle v1 (`bundle.json`, `records/`, `sources/`) | `--out <folder>` (refuses uncommitted inputs unless `--review-build`) | writes the out folder; **calls the model** |
| `export_state.py` | builds the static `/state` site (`NEXT_PUBLIC_EXPORT=state`) into `out-state/` with the frozen record, refusing any other bytes | `--build [--workbench-url <url> --hosting workstation\|cloud]` or `--out <dir>` | writes `out-state/`; no model |
| `export_break_record.py` | builds `/break`'s record from copied stores and evaluation files | many required flags (see its docstring); `--out` defaults to `src/components/break/break-record.json` | writes a tracked file; stores copied, never opened for write; replay provider |
| `run_goldens.py` | records the 44 goldens through `start_run`; reports and replays recordings | no args; `--prompt`, `--model`, `--only gNN`, `--report`, `--compare-models a b`, `--record <file>`, `--replay <file> [--write]` | writes runs to the store; **calls the model** except `--report` and `--replay` |
| `reverify.py` | replays the current verifier over recorded runs and reports what would change | `<run_id> …`, `--withheld`, `--all` | read-only; no model |
| `reconstruct_inputs.py` | rebuilds each recorded model input and compares with the recorded hash | `--all` or `<run_id> [--show]` | read-only; no model |
| `eval_retrieval.py` | BM25 (or dense/hybrid) Recall@k against CUAD-30, the SkillOpt split and the goldens | no args; `--mode`, `--k`, `--ranks`, `--data`, `--results scripts/results/eval_retrieval-bm25.json` | read-only; `--results` writes a tracked file; dense and hybrid need the embedding model |
| `run_batch.py` | a field task over a corpus as ordinary runs | `--corpus <dir> --task core-fields [--concurrency N] [--label L]`; `--report <batch_id>` | writes runs; **calls the model** |
| `score_cuad.py` | scores a CUAD-30 batch against experts' spans, by the rule in `docs/CUAD.md` | `<batch_id> [--json F] [--record F]` or `--recording F` | read-only except the files named |
| `cuad_corpus.py` | selects CUAD-30 from `data/cuad/data.zip` by a fixed rule | no args | writes `data/cuad/corpus-30/` and the tracked manifests `app/batch/corpora/cuad-30.json`, `cuad-30-labels.json` |
| `cluster_corpus.py` | ingests a corpus (no model), fingerprints, clusters into families, scores against labels | `--corpus <dir> …`, `--threshold T` | writes documents to the store |
| `domain_review_pack.py` | builds the ten-finding domain review pack from the record | `scripts/domain_review_pack.py > ../docs/archive/DOMAIN-REVIEW.md` | read-only; stdout |
| `load_envelope.py` | 1, 5, 10, 20 concurrent golden questions against a running API; wall, queue, model, verification times, peak memory | `--api http://127.0.0.1:8002 --document <file>` | writes runs to the API it targets; **calls the model** |
| `measure_admission.py` | batch against interactive latency, FIFO vs weighted admission | `--corpus data/cuad/corpus-30 --documents 3 --questions 4` | writes runs and `data/logs/admission-<stamp>.json`; **calls the model** |
| `mutate_by_hand.py` | 24 hand mutants (§9.2.4) | all, or name prefixes | edits tracked files temporarily, restores them |
| `trust_faults.py` | 17 planted trust faults (§9.2.3) | no args | edits tracked files temporarily, restores them |
| `results/eval_retrieval-bm25.json` | the committed retrieval measurement with its fingerprint (versions, alias table, k, label and data hashes); `docs/STATUS.md`'s Recall figure is held to it | data | |
| `revision_evidence/agreement-v1.txt`, `revision_evidence/agreement-v2.txt` | the two fixture versions of one agreement for the exporter; they differ in one phrase | data | |

---

### 9.5 Deploy and operations on the laptop

#### 9.5.1 Shape

The live site is one Windows laptop: the API (127.0.0.1:8000), the Next production server (127.0.0.1:3900), Ollama
with `qwen3:8b` (127.0.0.1:11434) and one SQLite store, published through a named Cloudflare Tunnel. Both servers
listen on loopback only. `deploy/cloudflared.yml` routes one hostname by path: `^/api(/.*)?$` to 8000, everything else
to 3900, anything else 404. One hostname, so API calls and the event stream are same-origin. The connector runs as a
Windows service started by the system and is not managed by these scripts.

#### 9.5.2 The public store

Since 2026-10-09 the site opens to anyone. The API runs with `WORKBENCH_ACCESS_REQUIRED=1`,
`WORKBENCH_ANONYMOUS_SESSIONS=1`, `WORKBENCH_MAX_RUNS_PER_DAY=200` and `WORKBENCH_DATA_DIR` set to a **public data
directory** outside the checkout, never the owner's store (`backend/data`, every historical run). The API refuses to
start with anonymous sessions on if its store holds any owner or curated record, so a misplaced data directory cannot
put the owner's records in front of the public. Each browser gets a signed `__Host-` cookie and a workspace no other
browser can read, deleted with everything in it seven days after the first visit (`application/retention.py`, hourly
and at start).

Bounds (`deploy/README.md`): 10 contracts held and 30 questions a UTC day per workspace; 20 new sessions, 30 uploads, 30
questions an hour per network address (`Cf-Connecting-Ip`); 300 uploads and 1 GiB a day for everyone; 8 requests in
flight per network; 200 questions a day for everyone; 25 MB uploads of PDF, DOCX or TXT; model timeout 600 s; writes
pause under 2 GiB free.

**Owner's pause switch:** create an empty file `public.paused` in the public data directory. New uploads and questions
get a 503 with a plain sentence; reading stays up. Delete it to resume; no restart.

A backup of the public store holds visitors' contracts and must be deleted within seven days. No backup of it is
scheduled.

#### 9.5.3 The scripts in `deploy/`

| File | What it does |
|---|---|
| `deploy/README.md` | the runbook: public demo, rollback across releases, the old invite-gate period (kept for the record), tunnel setup, supervision, what protects the site, logs, copying the store |
| `deploy/cloudflared.yml` | tunnel ingress (above); credentials live under the user's `.cloudflared`, not here |
| `deploy/up.ps1` | unsupervised start: refuses if 8000 or 3900 is taken; sets the API environment (ollama, qwen3:8b, bm25, k 6, answer-v2, CORS, app URL, secret from `backend/data/access.secret`); starts uvicorn with the resilient loop; `npm run build` with `NEXT_PUBLIC_API_URL`; `npm run start -- -p 3900`; waits up to 90 s for both; starts the tunnel unless `-Local`; writes `pids.json` (pid and start time) under `backend/data/logs/deploy/`. `-Local` uses localhost origins and no tunnel |
| `deploy/down.ps1` | writes `api.stop` and `web.stop` (supervisors exit instead of restarting); stops each recorded server only when both its pid **and** its start time match (Windows reuses pids; a pid-only stop once killed an unrelated process tree); also honours `up.ps1`'s `pids.json`; removes the records |
| `deploy/supervise.ps1` | one supervisor per server (`-Name api` or `web`, optional `-Origin`, `-Port`, `-PublicDataDir`, `-Tag`): starts it, writes stamped `*.out.log`/`*.err.log`, probes health every 30 s after a 60 s grace and kills it after 3 misses, restarts with a backoff doubling 5 s to 60 s while it dies within a minute, logs every start/exit/restart to `<tag>.supervisor.log`, prunes its outputs past 14 days or 200 MB. API mode sets the production environment and `WORKBENCH_ACCESS_REQUIRED=1` (no secret, no start); with `-PublicDataDir` also the public store, anonymous sessions and the 200/day ceiling. Web mode runs `swap-build.ps1 -Recover` first, then `node next start -H 127.0.0.1 -p 3900`. Every log write goes through `Write-Record` (retry, then give up and count), so a held log cannot end it. Only a stop file ends its loop |
| `deploy/install-supervision.ps1` | registers Scheduled Tasks "Verity API" and "Verity Web" (at logon, current user, no time limit, battery allowed, `IgnoreNew`) and starts them. `-Build` builds into `.next-staging` with `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_PROOF_RUN`, `NEXT_PUBLIC_BUILD_SHA` (HEAD), restores `tsconfig.json`, marks the build `VERITY_COMPLETE`; then stops running tasks (`down.ps1`), waits up to 60 s, swaps the build, starts the tasks, waits 90 s for health. `-PublicDataDir` implies `-ProofRun ""`. `-Uninstall` stops and removes the tasks |
| `deploy/swap-build.ps1` | `-Swap`: only a staged build carrying `VERITY_COMPLETE` becomes `.next`; the replaced one becomes `.next-previous`; a failed rename puts the old build back. `-Recover`: only when `.next` is missing, takes a whole `.next-staging`, else `.next-previous` |

#### 9.5.4 Releasing to the laptop

The command (`deploy/README.md`, public demo):

```powershell
powershell -ExecutionPolicy Bypass -File deploy\install-supervision.ps1 -Build -Origin https://ivo.pavankg.dev -PublicDataDir "<public data dir>"
```

When `package-lock.json` changed since the serving release: run `deploy\down.ps1`, wait until both scheduled tasks are
no longer Running, run `npm ci` in the checkout, then the command above. `npm ci` under a running `next start` deletes
files the server may still load. The site is down from the stop to the restart.

`install-supervision.ps1` without `-Build` restarts the servers (removes the stop files) on the build in `.next`.

#### 9.5.5 Rollback

- **Code:** the same steps at the previous commit (with `npm ci` if the lock differs). `.next-previous` holds the last
  build but no script swaps it back on demand; `swap-build.ps1 -Recover` uses it only when `.next` is missing.
- **Store:** a code rollback leaves the store as it is. Builds from 2026-10-30 on name records made under rules they do
  not know ("recorded under rules this build does not know"), judge none of their evidence, and a pack's `verify.py`
  prints NOT CHECKED and exits 2 for a newer verifier. `status.py`'s `rules` line counts such runs and documents.
  Builds before that (named in `deploy/README.md`: `a844ebf`, `2e8fe68`) cannot, and their packs of v11 runs can
  falsely FAIL: after rolling back to one of them, export no pack of a v11 run.
- **Data:** `backend/scripts/backup.py` is the data rollback ("a code rollback cannot undo what a newer reader
  wrote"). A plain copy of `workbench.db` misses the WAL; use SQLite's online backup.
- Outside the repository, the owner's release notes name `a844ebf` as the rollback target for `865356b` (with
  `npm ci`, the backend `pip install` and the installer); `a844ebf` is one of the builds warned about above.

#### 9.5.6 Never hold a live log open

On 2026-10-11 an operator's `tail -F` on `api.supervisor.log` held the file without write sharing; the supervisor's
next write failed, the supervisor exited under `$ErrorActionPreference = "Stop"`, and the API stayed down 17 minutes
(`docs/CASEBOOK.md` case 2). `supervise.ps1` now survives that (`Write-Record`), but the rule stands
(`docs/TROUBLESHOOTING.md`): read a log once (`Get-Content <file> -Tail 50`) and read it again to see more. Never
`tail -f`, `Get-Content -Wait` or an editor that locks the file.

#### 9.5.7 Logs and the first look

All under `backend/data/logs/deploy/` on the serving machine (`docs/TROUBLESHOOTING.md`):

| File | Written by |
|---|---|
| `api.supervisor.log`, `web.supervisor.log` | `supervise.ps1`: starts, exits with code, run time and last error line, missed probes, unrecorded ends (shutdown, sign-out) |
| `api/api.<stamp>.<pid>.<n>.log` | the API (`app/log_sink.py`): 10 MiB segments, 200 MiB total, 2,000-char lines, 60 a minute per kind; request lines, `refused … kind=…`, run stages, `model_ms`/`queue_ms`, `model_build` |
| `api.<stamp>.err.log` | Python outside logging: a fatal traceback |
| `api.<stamp>.out.log` | uvicorn (access log off) |
| `web.<stamp>.*.log` | `next start` |
| `<tag>.pid`, `<tag>.stop`, `pids.json` | pid and start time; stop files; `up.ps1`'s record |

First look on the live machine:

```powershell
cd backend
.venv\Scripts\python scripts\status.py --data-dir "<public data dir>" --public
```

| Line | `ok` means | `PROBLEM` says |
|---|---|---|
| `api` | `/api/health` answered and reports ok | not answering (supervisor?), or health's fault |
| `model` | Ollama answers, the model is pulled, matches `WORKBENCH_MODEL_DIGEST` if set | start Ollama, pull the model, or a different build |
| `cache` | host-RAM prompt cache off at the last model load (or not checkable) | cache on: set `LLAMA_ARG_CACHE_RAM=0` and restart Ollama |
| `disk` | free space above the floor (2 GiB public) | writes will pause |
| `store` | SQLite `quick_check` ok | problems found; back up and restore the last good backup |
| `runs` | day's budget and open runs; none stuck over 15 min | budget spent or a run without progress |
| `rules` | every run and document recorded under rules this build knows | counts of records from newer rules |
| `tunnel` | cloudflared metrics on 20241 answer, with edge connections | connector stopped |
| `api sup`, `web sup` | last supervisor line is not an exit | supervisor exited or not installed |

`docs/TROUBLESHOOTING.md` has the table of symptoms (502, missed probes, store faults, full disk, 503 "busy", 429s,
a run stuck at Checking, answers changing without a code change).

#### 9.5.8 What this is not

A laptop that restarts a dead server while its owner is signed in. Not high availability: a logoff ends both tasks;
after a reboot nothing runs until sign-in (the connector then answers 502); if a supervisor is killed, its server keeps
running and nothing restarts it when it dies. The machine must stay awake. No security headers were sent when first
measured (2026-10-02); `next.config.ts` and the API now send a set (HSTS, nosniff, referrer policy, frame-ancestors).

#### 9.5.9 The cloud kit, `deploy/cloud/` (not used live)

A laptop-independent layout of the same public demo on one Hetzner server: interface, API, SQLite store and Ollama
with the pinned Qwen3 8B in one Docker Compose stack, Cloudflare Tunnel (or Caddy) in front. **Not deployed for
production.** A staging host of 2026-10-13 ran the interface, API and store with the model elsewhere; a local Docker
rehearsal passed on 2026-10-12. The public name still reaches the laptop. Every step that creates a resource, spends
money, changes DNS or access is the owner's. Its quotas follow the laptop's: 200 questions a day for everyone and 30 per workspace (`deploy/cloud/env.example`).

| File | What it holds |
|---|---|
| `deploy/cloud/README.md` | the layout, building and gating images (`docker build -f deploy/cloud/Dockerfile.api --target test .` runs the backend suite in the image), the Caddy edge, DNS/TLS, environment, disk retention, recovery, rollback by `VERITY_TAG`, limits, the rehearsal record |
| `deploy/cloud/HETZNER.md` | the host runbook: server choice (AX42 CPU, GEX45 GPU fallback; neither measured), the model, the tunnel, releases on the server, stores, rollback and moving the public name, what only the server can show, cost |
| `deploy/cloud/compose.yml` | services `api`, `ollama`, `web`, and profile-gated `caddy` and `tunnel`; images tagged by `VERITY_TAG` with no default |
| `deploy/cloud/compose.gpu.yml` | overlay reserving NVIDIA GPUs for `ollama` |
| `deploy/cloud/Dockerfile.api` | Python 3.13-slim by digest, installs `requirements.lock`, a `test` stage, one uvicorn worker, health check via `liveness.py` |
| `deploy/cloud/Dockerfile.web` | Node 22-slim by digest, `npm ci`, `next build` with no `NEXT_PUBLIC_API_URL` (same origin), `next start` |
| `deploy/cloud/Caddyfile` | TLS from Let's Encrypt (staging first), h1/h2, `/api` to the API, overwrites `Cf-Connecting-Ip` |
| `deploy/cloud/cloudflared.yml` | the tunnel ingress with container addresses; credentials file `tunnel.json` is never committed |
| `deploy/cloud/env.example` | template for `.env` (mode 600): access, `VERITY_TAG`, `VERITY_STORE`, `VERITY_SHARED`, `COMPOSE_PROFILES`, `VERITY_TUNNEL_ID`, site, model and retrieval settings, digest |
| `deploy/cloud/liveness.py` | the container health check; kills a server that ran past a minute and fails three probes, so `restart: unless-stopped` replaces it |
| `deploy/cloud/acceptance.mjs` | acceptance check against a running site (`BASE=… SHA=… node deploy/cloud/acceptance.mjs`): asks the live model two or three questions and checks evidence, `/break`'s record and isolation |

`.gitignore` and `.dockerignore` keep `deploy/cloud/.env` and `deploy/cloud/tunnel.json` out of git and out of images.

---

### 9.6 Docs map

#### 9.6.1 `docs/`

| File | What it holds | Read it when |
|---|---|---|
| `docs/STATUS.md` | the "what works" record: measured claims with their measurement, what exists, every check command, release checklist table (one row per path: upload, verifier, pack, access, retrieval, flows, gate…), what is deliberately not built. Counts and versions held to the code by `test_docs_claims.py` | first, for what is true today and the versions in force (policy-v17, verifier v13, retrieval-v3, input-v1, reader v17) |
| `docs/SYSTEM_MAP.md` | which files own each subsystem, front and back, plus tests and scripts. Not held by a test; read the owning file before relying on a row | locating code |
| `docs/TROUBLESHOOTING.md` | the operator's first look, log files, symptom table | the live site misbehaves |
| `docs/CASEBOOK.md` | six traced failures: silent API (WinError 64), log reader killed the supervisor, prompt cut silently, pool drained, queries growing per row, temperature 0 with two answers | before touching serving, supervision, the model call or reads |
| `docs/FAILURE-ENVELOPE.md` | one table of failure cases: expected, observed, the test that holds it | adding or changing an error path |
| `docs/GOLDENS.md` | the 44-question golden set, the keep/kill rule for prompt and retrieval changes, categories, how to run, recordings and results | any prompt, retrieval, reader, verifier or model change |
| `docs/RETRIEVAL.md` | BM25 measured against labels; hybrid built not default; k, window, aliases, retrieval-v2 and v3 | changing retrieval |
| `docs/CUAD.md` | CUAD-30 pre-registered scoring and results, with corrections of 2026-10-30 | reading or re-scoring CUAD numbers |
| `docs/BATCH.md` | batch extraction over 20 licensed contracts: method, concurrency, results | batch work |
| `docs/FAMILIES.md` | document families by structure, labels, results | families work |
| `docs/ROUTING.md` | model routing rule (empty policy until a smaller model passes the goldens) | considering a second model |
| `docs/SCALE.md` | what was measured (batch, concurrency envelope, admission) and what each next step must earn | before any scaling claim or change |
| `docs/PERFORMANCE.md` | interface rendering of 2,001 sections, Lighthouse, why no virtualisation | front-end performance |
| `docs/DATA-EVIDENCE.md` | every agreement touched, by sha256, with denominators; its block is written by `data_audit.py --write` | before quoting any number |
| `docs/DEMO.md` | the 90-second walkthrough script | recording a demo |
| `docs/DEMO-PROOF.md` | a stranger's document end to end (the Phase 1 run, the hero run) | understanding the proof run |
| `docs/img/evidence-drawer.png` | the README's screenshot of the evidence drawer (1440x900) | |
| `docs/adr/0001-local-model-behind-a-provider.md` | the default model runs locally behind a provider interface ($0 budget, confidentiality) | provider work |
| `docs/adr/0002-citations-are-verified-by-code.md` | citations verified by deterministic code before anything is shown | verifier work |
| `docs/adr/0003-langgraph-only-for-stateful-flow.md` | LangGraph for the flow: **not adopted** (status 2026-10-19) | someone proposes orchestration |
| `docs/adr/0004-hybrid-retrieval.md` | lexical first, vectors fused: **partly adopted** (BM25 live, hybrid behind a setting, no pgvector) | retrieval work |
| `docs/archive/README.md` | the archive is dated notes, not the current account; nothing here is held to the code | |
| `docs/archive/DESIGN.md` | the 2026-09-28 design draft: problem contract, domain model, invariants, first slice | history of intent |
| `docs/archive/SYSTEM_TRUTH.md` | comprehension pass at `43a67f3` (2026-09-29), with defects found | history |
| `docs/archive/VALIDATION.md` | validation phase 2026-09-29: proven, partial, missing | history; deep fuzz scale |
| `docs/archive/REVIEW-INDEPENDENT.md` | a read-only reviewer's seven findings, as delivered | history |
| `docs/archive/PARSER-COMPARISON.md` | parser tournament: Docling did not earn its place | proposing a new reader |
| `docs/archive/SKILLOPT.md` | SkillOpt run over the answer prompt: zero edits proposed | prompt optimisation ideas |
| `docs/archive/DOMAIN-REVIEW.md` | ten findings packed for a lawyer (generated); not yet reviewed | |
| `docs/archive/CONTRACT-STATE-RELEASE.md` | release notes of the `/state` page | `/state` |

#### 9.6.2 `DECISIONS.md`

1,914 lines. Structure: a title, "Each decision as it was taken, newest last", an index of 29 links, then one
`## YYYY-MM-DD: title` section per entry. From 2026-09-28 to 2026-10-14 most work was recorded as bold-led paragraphs
(`**Title (date).**`) inside the long "2026-09-28: the role-specific audit, P0 and P1" section; from 2026-10-14 each
decision has its own `##` heading. Entries state what was found, what was measured, what was decided, and what was
rejected and why. The latest entry is "2026-10-30: a stress test by 125 agents".

To add one: append a `## YYYY-MM-DD: <short title>` section at the end, and add a matching link line at the end of the
index (`- [YYYY-MM-DD: title](#slug)`, GitHub's heading slug). Write what was measured and what was rejected. Do not
edit earlier entries; correct them with a dated note or a later entry (the house practice throughout the file).

#### 9.6.3 Root and config files

| File | What it holds |
|---|---|
| `README.md` | what Verity is, how an answer is made, run and check commands, ten-minute reading list, layout, how it was built, sample licence |
| `AGENTS.md` | the binding rules for agents (§9.7) and the Next.js installed-docs rule |
| `CLAUDE.md` | one line: `@AGENTS.md` |
| `ENGINEERING_CONSTITUTION.md` | ownership map, 17 rules, five questions, the audits it was adopted with, what is deliberately not done |
| `DECISIONS.md` | above |
| `.gitattributes` | `* text=auto eol=lf`; `.docx .pdf .ico .png .woff2` binary |
| `.gitignore` | `node_modules`, `.next*` build dirs, `out/`, `out-state/`, `.env*`, Playwright output, `/.claude/`, `deploy/cloud/.env`, `deploy/cloud/tunnel.json` |
| `.dockerignore` | the image context holds code only: no `.git`, stores, venvs, caches, builds, secrets, `.env*`, `tunnel.json` |
| `.github/dependabot.yml` | weekly grouped minor/patch PRs for npm (`/`), pip (`/backend`) and GitHub Actions; no workflow runs checks |
| `backend/.gitignore` | `.venv/`, `data/`, `__pycache__/`, tool caches |
| `backend/requirements.txt` | an unpinned dependency list; nothing installs it (use `requirements.lock`); Dependabot reads it |

#### 9.6.4 `research/`

`research/README.md`: experiments run against the product, kept as they were run. Not part of the product, not
linted, not run by the gate. They were run from `backend/experiments/`, and scripts that locate the backend by their
own path expect that place, so such a script has to be copied back there to run (inferred; not verified). Treat the
folder as a frozen record.

| Path | What it is |
|---|---|
| `research/demo_proof/make_fixture.py` | builds the DOCX behind `docs/DEMO-PROOF.md` from one CUAD contract outside every measured set |
| `research/depth_pass/README.md` | the 2026-10-01 depth pass: two defaults (window 6,000, aliases on) and reader v5, with its scripts and results |
| `research/depth_pass/gen_adversarial.py` | generates 70 adversarial reader files; seven became `backend/tests/fixtures/reader/` |
| `research/depth_pass/tail_measure.py` | census of expert spans beyond the 5,000-char window; no model |
| `research/depth_pass/tail_cases.py` | the six tail cases re-run under 6,000 (model, first time) |
| `research/depth_pass/judge_options.py` | goldens under a run option judged against the baseline; no model |
| `research/depth_pass/isolate_g30.py` | which setting moves golden g30 (model, first time) |
| `research/depth_pass/results/window-census.json` | output of `tail_measure.py` |
| `research/depth_pass/results/tail-cases-6000.json` | output of `tail_cases.py` |
| `research/depth_pass/results/goldens-section-window.json` | goldens at window 6,000 |
| `research/depth_pass/results/goldens-retrieval-aliases.json` | goldens with the alias table |
| `research/depth_pass/results/goldens-v5.json` | Recording 6c, reader v5 |
| `research/depth_pass/results/g30-isolation.json` | output of `isolate_g30.py` |
| `research/final_audit/README.md` | the 2026-10-02 zero-assumption audit: each probe, how to run it, what it printed |
| `research/final_audit/harness.py` | isolated store, app, scriptable provider and recorder shared by the probes |
| `research/final_audit/chaos_app.py` | the app the chaos journey starts as a process |
| `research/final_audit/chaos_journey.py` | one journey over real HTTP, server killed twice |
| `research/final_audit/probe_memo_review.py` | memo atomicity, review identity and concurrency |
| `research/final_audit/probe_concurrency.py` | SQLite under many writers; executor; list query scale |
| `research/final_audit/probe_verifier_policy.py` | hostile quotes and clauses |
| `research/final_audit/probe_content_pack.py` | markup and Unicode end to end; pack tampering; failing writes |
| `research/final_audit/probe_context_overflow.py` | what Ollama does with an over-window prompt (calls the model) |
| `research/final_audit/census_store.py` | the store on a snapshot: bytes, hashes, spans, memos; restore |
| `research/final_audit/census_projections.py` | run view, explanation and findings record agree for every complete run |
| `research/final_audit/replay_verifier.py` | every verified span re-located by the verifier of the day |
| `research/final_audit/supervisor_longtail.ps1` | the supervisor on a second instance (port 8020): port taken, kill, supervisor killed, stop file |
| `research/parser_tournament/run.py` | parser tournament harness (current reader vs Docling) |
| `research/skillopt/build_data.py` | SkillOpt data from CUAD, disjoint from CUAD-30 |
| `research/skillopt/config.yaml` | SkillOpt configuration (machine paths filled in by `run.py`) |
| `research/skillopt/run.py` | runs SkillOpt over the answer prompt on local Ollama |
| `research/skillopt/workbench_env/__init__.py` | package marker for the SkillOpt environment |
| `research/skillopt/workbench_env/adapter.py` | SkillOpt's view of the workbench |
| `research/skillopt/workbench_env/dataloader.py` | items per contract and question, experts' spans as labels |
| `research/skillopt/workbench_env/rollout.py` | the rollout: the production answer path scored by the CUAD rule |
| `research/skillopt/workbench_env/prompts/analyst_error.md` | analyst prompt for failures |
| `research/skillopt/workbench_env/prompts/analyst_success.md` | analyst prompt for successes |

The contract-state experiment behind `/state` is frozen (README: "a frozen research experiment"); its code is in the
separate, non-public `ivo-experiments` repository, and Verity only reads its exported record.

#### 9.6.5 `proof/`

| File | What it is |
|---|---|
| `proof/README.md` | the static fallback page: what it is, publishing to Cloudflare Pages (owner's account), refreshing screenshots |
| `proof/index.html` | plain HTML, no scripts or external requests: one real run walked from status to model input, measurements with denominators. Edited by hand when a recording changes. It names reader v15 while the code is at v17; whether its other figures are current is not verified |
| `proof/shots.mjs` | Playwright screenshots of the production build on 3900 (`node proof/shots.mjs proof/img`) |
| `proof/img/finding.png`, `proof/img/highlight.png`, `proof/img/runs.png`, `proof/img/why-drawer.png` | the page's screenshots |

---

### 9.7 House rules for agents

From `AGENTS.md`, `CLAUDE.md` (which only includes `AGENTS.md`) and `ENGINEERING_CONSTITUTION.md`. These are binding.

#### 9.7.1 The rule under everything

- A finding may come from the model; a claim that its evidence is verified may only come from deterministic code.
- Every sophisticated component earns its existence with a measured failure it fixes or an explicit product
  requirement. A component that cannot point at either is removed.
- Answer the five questions before every meaningful change: which layer owns this; what invariant it enforces; what
  happens when it fails; can it be tested without the interface, model or database; is the abstraction required or
  only sophisticated-looking. If the last, do not add it.

#### 9.7.2 Fixed decisions (not re-litigated in a session)

| Rule | What it means in practice |
|---|---|
| The visual system is frozen | `src/app/globals.css` stays. No theme switching, extra pages, dashboard cards, marketing content, agent diagrams or onboarding tours |
| Dependencies are earned | no Postgres, pgvector, LangGraph, queues, caches, agents or observability stacks without a measurement showing the current choice failing, recorded in `DECISIONS.md` |
| The primary path is never mocked | fakes live in `backend/tests`. Sole exception: `app/providers/replay.py`, chosen only by `WORKBENCH_PROVIDER=record\|replay`, never by default |
| Schema-first types | `backend/app/schemas.py` is the source of truth; after changing it run `export_openapi.py` then `npm run api:types`, commit both generated files; never retype frontend types |
| Identity through `backend/app/hashing.py` | no other app module may import `hashlib` (`test_hashing.py` fails otherwise) |
| Versions change only by hand | changing code behind the policy, verifier, retrieval, input or reader version fails `test_semantic_versions.py` until you either bump the version (rule changed; add a new fingerprint, never replace an old one) or re-record the current fingerprint (no rule change), with a reason |
| The golden set judges | a prompt or retrieval change is kept only if the golden set moves in its favour and no passing golden fails (`docs/GOLDENS.md`); goldens are never edited to make a change pass |
| Git is the owner's | agents do not commit or push unless asked. The constitution: nothing is committed by the assistant; commit hashes are recorded by whoever commits |
| Keep records true | record decisions in `DECISIONS.md` as taken; keep `docs/STATUS.md` true (`test_docs_claims.py` holds it) |

#### 9.7.3 Constitution rules (summary of all 17)

1. Name the owning layer before adding code; if two could own it, pick the one testable alone.
2. The frontend renders truth, never decides it (verified flags, offsets, statuses, reasons come from the API).
3. Routes stay thin: validate, call one application service, map the result.
4. Models propose; deterministic code owns identity, verification, hashes, permissions, transitions, persistence and
   reproducibility.
5. Model output is untrusted until validated and verified; an unlocatable quote is never shown and the finding is
   withheld.
6. Never encode an invariant only in a prompt when code can enforce it.
7. One canonical implementation each for hashing, normalisation, citation location, status decisions. No `utils`,
   `helpers` or `misc` modules.
8. The primary runtime path never falls back to mock data (replay is the one exception, above).
9. Failures are typed by owner, each with one response shape and one wording.
10. Every run persists what reproducing it needs (hashes, provider, model, options, prompt version and hash, sections
    handed, raw output, quote locations, stage times, outcome and reason).
11. Completed runs are immutable; a changed prompt, model or document is a new run. One exception: the public store's
    retention deletes ended visitor workspaces.
12. Repeating a request never repeats a model call (unique index over non-failed runs; failed runs retryable).
13. The database holds what invariants it can (foreign keys, CHECK constraints, fingerprint index).
14. Runtime validation and typed contracts at every API boundary; backend schema is the source of truth.
15. Dependencies earned by demonstrated requirement.
16. Tests target boundaries (verifier refusal, route contract, full path with a fake provider, idempotency, recovery).
17. Visual sophistication never justifies coupling; the visual system is frozen.

#### 9.7.4 Framework documentation order

1. Next.js: the installed docs in `node_modules/next/dist/docs/` (the pinned 16.4.1) win over the web and memory.
   Reading them never moves domain truth, verification, persistence or model behaviour into a React component,
   Server Component, Route Handler, Server Action or middleware. Before adding a Next.js primitive: read its installed
   docs, name the responsibility, confirm FastAPI or the application layer does not own it, use the smallest
   mechanism.
2. Other libraries (Playwright, FastAPI, SQLAlchemy, pydantic): the docs of the pinned version.

#### 9.7.5 Commit style

Stated by the owner, not written in the repository's files: one-line subjects of 72 characters or fewer, no
`Co-Authored-By` trailer. The last 40 commits at `865356b` follow it (none over 72 characters, none with a trailer);
older history has longer subjects. `DECISIONS.md` (2026-10-01) records that machine identifiers (home-directory paths,
short-name paths, a hostname) were scrubbed from unpushed history: keep machine paths out of commits and documents.
Line endings: `.gitattributes` stores text as LF.

#### 9.7.6 Operating rules that bit before

- Never hold a live log open (§9.5.6).
- Keep `LLAMA_ARG_CACHE_RAM=0` on the serving machine and one Ollama slot (§9.1.1).
- Never point `WORKBENCH_DATA_DIR` for the public API at the owner's store; the API refuses, but do not test it live.
- `npm run e2e` on the serving machine reuses servers on 8001/3901 if any are up; the live build in `.next` is safe
  because the flows build into `.next-e2e`.
- Build the interface for the public site only through `install-supervision.ps1 -Build`, which stages and swaps; a
  build straight into `.next` under a running `next start` once served a half-written bundle.
- A `next build` rewrites `tsconfig.json`'s type paths; the installer and the gate put it back.

## 10. Changing Verity safely: a recipe index

Find the task, read the named section, change the named files, run the named checks. Every recipe ends with the checks
in §9.2.

### 10.1 Before any change

1. Read `AGENTS.md` (the house rules, summarised in §9.7).
2. Find the code with this book, then read only those files.
3. Decide whether the change touches code that decides an outcome. If it does, it moves a version's fingerprint
   (`backend/tests/test_semantic_versions.py` fails and says which). Then:
   - the version is **not yet released** (not on `main` at a deployed commit): replace its fingerprint in `RECORDED`;
   - the version **is released**: bump it where it is declared and add the new version with its fingerprint;
   - the change **does not change what is decided** (a rename, a reworded reason): replace the fingerprint and say why
     in the commit.
4. Write the test first and watch it fail (`invariant-first`: name the invariant, cover the failure class, fix the
   shared primitive, add a property test and a control).

### 10.2 Recipes

| I want to … | Read | Touch | Version | Tests to extend |
|---|---|---|---|---|
| support a new file type | §4.7 | `ingest/readers.py` and a reader module, `ingest/bounded.py`, upload type checks | reader (`PARSER_VERSION`) | reader tests listed in §4.7 |
| change how sections are split or headed | §4.7 | `ingest/sections.py` | reader | §4.7 |
| treat more characters as invisible | §4.7 | `unseen.py` (one definition) or `ingest/invisible.py`; the verifier's own `IGNORABLE_RANGES` stays a superset (a test holds it) | reader, maybe verifier | `test_import_contracts.py` and §4.7 |
| add a policy check (lower a pass for a new reason) | §5.6 "Recipe: add a policy check" | `runs/status.py` (+ `policy/`), its call in `runs/service.py`, `runs/account.py` for the wording code shows | policy | §5.6; replay over recorded passes before release (§9) |
| change retrieval | §5.6 "Recipe: change retrieval" | `retrieval/lexical.py`, `retrieval/aliases.py`, `runs/links.py`, `runs/service.py:_retrieve` | retrieval | golden set and `eval_retrieval.py` (§9) |
| change the prompt | §5.6 "Recipe: change the prompt" | a new file in `analysis/prompts/` and its manifest | the prompt's hash is its identity | golden set (`docs/GOLDENS.md`); re-record `e2e/replay.json` |
| change what the model is sent or how its answer is read | §5.6 | `analysis/service.py`, `analysis/schema.py`, `providers/ollama.py` (`chat_request`, `generate_json`) | input (`input-v1`) | re-record `e2e/replay.json` (§8.6) |
| change the verifier | §5.3, §5.6 | `verify/spans.py`, `verify/tokens.py`, and the pack's mirror `application/verify_template.txt` + `evidence_pack.py` injections | verifier (keep older versions side by side) | verifier properties and pack parity tests (§5.6, §6.5) |
| change the model provider or the queue | §5.6 | `providers/` | input, if the request or reply reading changes | provider and queue tests (§5.6) |
| add a field to the evidence pack | §6.5 | `application/evidence_pack.py`, `verify_template.txt` | — | pack binding tests (§6.5); a field is bound to a recorded hash or printed UNCHECKED |
| change memo wording | §6.5 | `memo/` | — (a memo's identity is its content) | memo tests (§6.5) |
| change trust rules | §6.5 | `app/trust`, `application/trust_run.py` | `TRUST_VERSION` | `test_trust.py`, the trust fault matrix (§9.2) |
| add an API route | §7.8 | `api/<router>.py`, `schemas.py`, then `python backend/scripts/export_openapi.py` and `npm run api:types` | — | route tests and the Schemathesis fuzz (§7.8) |
| add a setting | §7.8 | `config.py`; `deploy/supervise.ps1` if the deployment sets it | — | §7.8 |
| add a table or a column | §7.8 | `models.py`; `db.py` only for constraints the models cannot carry | — | `test_store_schema.py` (an old store must open with the models' schema) |
| add a quota or a limit | §7.8 | `application/quotas.py`, `api/access.py`, `api/in_flight.py` | — | §7.8 |
| add a view to the interface | §8.7 | `src/components/workbench/views/`, the view switch, URL state | — | vitest beside the component, a browser flow in `e2e/` |
| show a new API field | §8.7 | `schemas.py` → `openapi.json` → `src/lib/api.schema.ts` (generated) → the component | — | §8.7 |
| change copy that states what code checks | §8.7 | the component and `README.md` | — | `backend/tests/test_docs_claims.py` pins those claims |
| ship a change | §9.2, §9.5 | — | — | the release gate on the exact commit, then the deploy steps |

### 10.3 Things that look safe and are not

- **Editing a function "only for clarity" inside a version's closure.** It moves the fingerprint; decide the version.
- **Giving `build_user_message` or `context_slice` a default window.** The window is a run's own option; a default
  once let an old run be rebuilt with a window it never had.
- **Reading a setting during a run that the run's options do not record.** The run must execute from its own record
  (`FrozenOptions`); a new setting a run uses belongs in its options and its identity.
- **Adding a CHECK or a vocabulary value in `models.py` without a store test.** `db.ensure_checks` rebuilds a table
  whose CHECKs drift, and refuses to open a store with rows the new rule refuses, naming them. Test against
  `backend/tests/fixtures/store-release-2026-10-02.sql`.
- **Changing the interface to decide something.** The API decides; the page renders. A status, a label of who decided,
  or a limit computed in `src/` will disagree with the record, the memo and the pack.
- **Holding a live log file open** (`tail -f`, `Get-Content -Wait`). It once stopped the live supervisor. Read logs
  once and close them (§9.5).
- **Recording browser-flow answers without the local model.** `E2E_PROVIDER=record` needs Ollama; replay fails loudly
  for any request it has not seen.

## 11. Keeping this book true

This book is a map, not the territory. It was checked against commit `865356b`. To keep it useful:

- **When you add, move or delete a file**, update its row in the chapter that owns its directory (chapters 4 to 9 each
  list every file of their slice). A file missing from this book is a file the next agent will not find.
- **When you change a version** (policy, verifier, retrieval, input, reader), update section 5's version table and the
  "Versions" notes in chapters 4 and 5.
- **When you change a number this book quotes** (limits, quotas, test counts, ports), update it here and in
  `docs/STATUS.md`, which is the authority for "what works today".
- **When you take a decision**, record it in `DECISIONS.md` (dated, with what was rejected), not here. This book says
  what is; `DECISIONS.md` says why it became so.
- A quick check that every tracked file is still named here:

```bash
git ls-files | grep -v -e "^research/" -e "^docs/archive/" -e "^proof/img/" | while read -r f; do
  grep -qF "$(basename "$f")" docs/BOOK.md || echo "not in the book: $f"
done
```

## 12. Glossary

| Term | Meaning in Verity |
|---|---|
| **Account (of a finding)** | Code's statement of what it checked for a finding and what it did not (`runs/account.py`): which quotes it found, what it compared, what stays the model's view. Shown in the drawer and the pack |
| **Admission** | The single gate in front of the model (`providers/admission.py`): one model call at a time; waiters queue, interactive questions ahead of batch work four to one. It never refuses; the public quota refuses a question past 8 open ones (503, `application/quotas.py`) |
| **Amendment challenge** | A sample (an agreement plus an amendment that replaces a clause) the landing offers, to show how replacement wording is located |
| **Casebook** | `docs/CASEBOOK.md`: failures traced to their mechanism, each with its fix and test |
| **Closure (of a version)** | The set of code a version names, found by following its entry points through the code (`backend/tests/code_closure.py`). A change inside it moves the version's fingerprint |
| **Condition (left out)** | An "unless / except / subject to …" in a quote's own sentence but outside the quoted words. Since policy-v17 it lowers a pass unless another verified quote of the finding covers it |
| **Coverage** | What a reading of a file read and what it left out (headers, footers, hidden text), shown as "Not read by this reading" and never cited |
| **CUAD** | The Contract Understanding Atticus Dataset; Verity scores itself on a subset (`docs/CUAD.md`) |
| **Evidence pack** | A zip a reader downloads for a run: the run, its findings, sections, model output, relations and a plain-Python `verify.py` that re-checks every span |
| **Evidence span** | One quote of a finding, with where code found it (section, start, end, method) or that it did not |
| **Failure envelope** | `docs/FAILURE-ENVELOPE.md`: what Verity is known to get wrong, case by case, with the status it gives |
| **Finding** | One answer to a question: topic, conclusion, status, status source, reason, and its evidence spans |
| **Fingerprint** | A hash of the syntax tree of the code behind a version, recorded in `backend/tests/test_semantic_versions.py` |
| **Gate (release gate)** | `scripts/release-gate.sh <commit>`: a fresh clone and every check; its log must end `GATE PASSED: <sha>` |
| **Golden set** | A fixed set of questions with expected answers used to judge prompt and retrieval changes (`docs/GOLDENS.md`) |
| **Guidance** | A playbook rule or instruction the visitor adds ("we accept 30 days' notice or more"); code compares a finding against it where it can |
| **Input version** | `input-v1`: what the model is handed of the sections and how its answer is read |
| **Memo** | The review memo (HTML and DOCX) written from a run's stored findings and reviews, without another model call |
| **Model hint** | The status the model proposed (`status_hint`); a status with source `model_hint` is the model's view, not code's |
| **NON_DECIDING** | The named list of code a run reaches that records or reports rather than decides; every version's closure stops there (`backend/tests/test_semantic_versions.py`) |
| **Obligation / standing** | In the trust layer: one thing a finding needs to hold (a quote exists, is unique, the reader and rules are compatible) and whether it is established |
| **Part** | A piece of a long clause the reader split for size, recorded as data (`sections.part`) so the interface rejoins only what the reader split |
| **Policy version** | `policy-v17`: how a status is decided (`runs/status.py` and what it reaches) |
| **Reader / reading** | The module that reads a file into sections (`app/ingest`), and one stored result of it; documents are identified by their bytes' SHA-256 and the reader version |
| **Reader version** | `PARSER_VERSION` in `app/ingest/__init__.py`, currently `v17` |
| **Replay provider** | A provider that serves recorded model answers from `e2e/replay.json`, keyed by the hash of the system prompt and user message, so the browser flows run without a GPU |
| **Retrieval version** | `retrieval-v3`: which sections are handed to the model |
| **Review / review head** | A person's verdict on a finding (confirmed, dismissed, cleared) under a name; the review head identifies the latest reviews a memo was written from |
| **Run** | One question asked of one document (with optional guidance), executed in stages and immutable once finished |
| **Run identity / reuse** | A run is identified by its inputs and the versions of the rules; the same request under the same rules returns the existing run (`reused: true`) |
| **Section** | One numbered or headed piece of a contract as read, with its text; quotes are found in sections |
| **Stage** | One step of a run: reading, finding_evidence, checking, verifying, then complete, unresolved or failed; each recorded with input and output hashes |
| **Status** | `pass`, `needs_review`, `missing` or `unresolved`, with a **status source** saying who set it (`model_hint`, `computed_days`, `confirmed_days`, `no_evidence`, `reference_check`, `position_check`, `ambiguous_fact`) |
| **Trust layer** | `app/trust`: per finding, which obligations hold today, and what a later version of the document does to it (the revision diff) |
| **Typed tier** | The verifier's last tier: compare a quote and the text token by token as typed values (numbers with signs, words, sentence ends) |
| **Verifier version** | `v11`: when a quote counts as found (`app/verify`) |
| **Withheld** | A finding whose quotes code could not all find; it is shown struck through, never as an answer, and its status is `unresolved` |
| **Workspace** | A visitor's private space (`pw-…`), created by their first visit, holding their documents, runs and reviews, deleted seven days later |
