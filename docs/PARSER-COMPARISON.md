# Parser tournament

The reader (`backend/app/ingest/readers.py`, version v4) reads a DOCX as its accepted view and, as
`docs/SYSTEM_TRUTH.md` and the coverage census record, leaves headers, footers, footnotes, endnotes,
comments, block-level content controls, embedded objects and imported chunks unread, keeps only the
cached result of fields, and does not render automatic numbering. Two open-source readers claim more:
Docling (MIT, IBM; a typed document model with body, furniture, hierarchy and provenance) and Docxodus
(MIT; DOCX extraction with character offsets, headers, footers, footnotes, endnotes and nested tables,
used by OpenContracts for its DOCX pipeline). Neither replaces the reader because it is popular. A
reader is adopted only if it beats the current one on criteria written here before any of it ran.

## Rule, fixed before the run

A challenger is measured on the same documents through one adapter contract (a list of blocks with
kind, level and text, plus a coverage statement) and wins only if, on the licensed corpus and the
adversarial fixtures:

1. **Accepted-view correctness is not worse.** On the redline fixtures (tracked insertions kept,
   deletions and moved-away text dropped, hidden runs dropped, deleted rows skipped, a deleted
   paragraph mark joining its paragraphs) every current assertion in `tests/test_ingest.py` holds for
   the challenger's text. One failure ends the tournament for that challenger; our accepted-view
   semantics are legal-domain-specific and are not traded for more parts.
2. **Exact quote retention is not worse.** Every verified span in the record whose quote is exact
   under reader v4 is exact under the challenger's text of the same document (replayed with the
   verifier over the challenger's sections). A lost exact quote is a regression, counted per document.
3. **Coverage is better.** The challenger reads at least one of the parts v4 omits (headers, footers,
   footnotes, endnotes, comments, block-level content controls) with the text where it belongs and
   labelled as what it is, on the documents that have it (32 footers, 12 headers, 2 footnotes in the
   census).
4. **Reading order and structure are not worse.** Headings, numbering and body order on the sample
   agreement and five corpus contracts, checked by eye against Word, with every difference written
   down.
5. **Cost is bounded.** Parse wall time no more than three times v4's on the 20-document corpus, peak
   memory under 1 GB, and the adversarial fixtures (`tests/test_hostile_packages.py`, the failure
   envelope) refused or read within the same bounds, never a crash and never a network call.

Two of the five failing ends the tournament for the challenger; a challenger that wins is adopted
behind a new reader version (v5), with v4 readings kept as they are and re-read only when a run asks.
The harness is `backend/experiments/parser_tournament/run.py`; its own venv is
`backend/data/tournament/venv` (ignored), so nothing enters the application's dependencies before the
result. Offset stability between backend and interface (the reason OpenContracts pins Docxodus's WASM
build to its server build) is not a criterion here: the workbench highlights from stored section text
and offsets it computed itself.

## Result

**Docling, 2026-09-29 (22:20 to 22:38 local, the machine otherwise idle; docling 2.x in `backend/data/tournament/venv`,
`experiments/parser_tournament/run.py`, record `backend/data/tournament/docling.json`).** Twenty DOCX documents: the
nineteen licensed contracts of the first corpus and the sample agreement.

| Reader | Documents read | Exact quotes of the record retained | Total wall time | Peak memory, worst document |
|---|---|---|---|---|
| reader v4 (current) | 20 of 20 | 292 of 292 | 25.7 s | 30 MB |
| Docling | 19 of 20 (one "Pipeline SimplePipeline failed") | 256 of 292 | 1,026 s | 161 MB |

Criterion 2, exact-quote retention, is lost on ten documents (the sample and CP01 keep 95 of 104, CP04 keeps 1 of
6, CP05 1 of 3, UK08 none of 4 because it failed to read); criterion 5, cost, is lost on every document, Docling
taking 30 to 60 times the reader's wall time on most, 78 and 419 times on the two largest, and five times the
memory. Two of five lost ends the tournament under the rule; criteria 1, 3 and 4 were not scored for it. Docling
emits finer blocks (375 against 123 on the sample) and about the same characters, which says it reads no more of the
contract than the reader does on these files; what it would have added on headers and footers was not measured
because the rule had already ended it. Docxodus was not entered: no adapter exists yet, and its runtime is not
Python. Reader v4 stays. Coverage (what a reading did not read) remains the honest answer for now, and a challenger
that reads furniture is entered against the same criteria when one is adapted.

**Reader v5 against the same criterion (2026-10-01).** The reader changed for measured reasons (block-level content
controls and nested tables read, text files decoded, a wall of text split and named by its first words, a textless
PDF page counted; `DECISIONS.md`), so it was run through the harness as a challenger to itself: 35 documents (the
twenty licensed contracts, the corpus twins and the sample), every one read, 377 of 377 exact quotes in the record
retained, the largest contract in 20.2 s and 30.3 MB (`data/tournament/v5.json`). Nothing the record had quoted is lost
by reading more.
