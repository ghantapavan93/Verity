# The depth pass of 2026-10-01: the measurements behind two defaults and one reader version

Everything here reads the ordinary store (`backend/data/workbench.db`) and writes a compact JSON result into
`results/`; nothing is copied by hand. Run each from `backend` with the project's interpreter. The verdicts these
results carry are written in `docs/RETRIEVAL.md`, `docs/GOLDENS.md` (Recording 6) and `DECISIONS.md`.

| Script | What it measures | Model calls | Result |
|---|---|---|---|
| `tail_measure.py --window 5000` | the census: of the 111 expert spans of CUAD-30, how many sit in a section longer than the window, start beyond it or are cut by it | none | `results/window-census.json` |
| `tail_cases.py --window 6000` | the six census cases re-run under a 6,000 window through the ordinary run path and scored by the CUAD rule; `--existing` re-reads the recorded runs without an upload or a model call | six, the first time | `results/tail-cases-6000.json` |
| `judge_options.py section_window` | the 44 goldens recorded with `section_window=6000` judged against the baseline (answer-v2, k = 6, reader v4) | none | `results/goldens-section-window.json` |
| `judge_options.py retrieval_aliases` | the same for the alias table | none | `results/goldens-retrieval-aliases.json` |
| `judge_options.py v5` | Recording 6c: the reader-v5 golden document with both defaults on | none | `results/goldens-v5.json` |
| `isolate_g30.py` | g30 on the v5 document under each of the other three settings; the runs are reused by fingerprint | three, the first time | `results/g30-isolation.json` |
| `gen_adversarial.py [dir]` | the 70 adversarial and unusual files of the reader sweep (DOCX structure, tracked changes, scripts, sizes, PDFs, text encodings) | none | files in `dir` (default `./gen`, ignored) |

## The reader fixtures

Seven of the generated files are the fixtures of `backend/tests/test_reader_sweep.py`, copied under plainer names.
python-docx stamps a creation time into each package, so a regenerated file is not byte-identical to the fixture;
its text is.

| Fixture | Generated as | Holds |
|---|---|---|
| `nested-tables.docx` | `c2_nested_tables.docx` | a table inside a cell ("Inner 2: termination fee 5,000 EUR") |
| `content-controls.docx` | `d3_content_controls.docx` | a block-level `w:sdt` around a heading and a clause ("liability is capped at 100,000 USD") |
| `degenerate-tables.docx` | `g14_degenerate_tables.docx` | an empty table, a row without cells, a table inside a content control ("fee 9,999 USD") |
| `merged-cells.docx` | `c3_merged_cells.docx` | a horizontal and a vertical merge |
| `image-only-middle-page.pdf` | `h3_image_only_page.pdf` | three pages, the middle one an image |
| `utf16.txt` | `i2_utf16.txt` | UTF-16 LE with its byte-order mark |
| `windows-1252.txt` | `i4_latin1.txt` | "€1,500" and "Société Générale" in Windows-1252 |

## What the record said

- Census at 5,000: 111 labelled spans, 45 carried by a section longer than the window, 4 starting beyond it, 2 cut.
- Tail cases at 6,000: 4 of 6 correct (the recorded batch at 5,000 answered 2 of the 6).
- Goldens at 6,000: 37 of 44, no gain, no regression. Alias table on: 37 of 44, no gain, no regression.
- Recording 6c (reader v5, both defaults): 37 of 44, gain g44, regression g30; the two model inputs for g30 differ in
  one line, the contract's filename, and g30 withholds on the v5 document under every setting.

## The three reports

`reports/` holds the three agents' reports as they were written on 2026-10-01: `reader-sweep.md` (115 uploads of
the generated files, three tables and the ranked defects), `ui-sweep.md` (the product driven through Playwright on an
isolated stack, ten area tables and 23 ranked defects) and `code-review.md` (the hostile read of the code, 26 findings).
The reports name the files by their generated names (`gen\...`); the 115 screenshots the interface sweep took were not
kept. Which findings became changes, and which were left with a reason, is in `DECISIONS.md`.
