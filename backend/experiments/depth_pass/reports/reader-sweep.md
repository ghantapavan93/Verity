# Reader sweep: Verity document reader and upload path (isolated API, port 8010)

Date: 2026-10-01. Store: `backend/data/explore` (fresh at start). Reader `v4`, coverage schema 1, prompt `answer-v2`, model `qwen3:8b` (num_ctx 16384, retrieval_k 6, section window 5,000 chars).
Scripts: the generator and the measurement scripts beside this report in the repository; the raw JSON dumps of the sweep were not kept (`part1_real.py`, `gen_adversarial.py`, `part2_adversarial.py`, `part3_runs.py`, `out/*.json`, `out/part2_dump.txt`).
No 500 was returned by any upload or run request in this sweep (115 uploads, 6 runs). The API's stdout is not redirected to `backend/data/explore/logs` (the folder does not exist; the uvicorn process was started without a log file), so the server log could not be checked; the sibling restart of the 8010 process mid-sweep is noted in Part 2.

Column notes: `numbered` = sections whose `number` is non-empty (printed or computed; the API does not distinguish). `over5000` = sections longer than the prompt window (their tail is never shown to the model). `over6000` = sections longer than the split limit (the split is at paragraph boundaries, so one long paragraph is never split). `coverage` lists only parts whose status is not `read`/`absent`. `approximate` = fewer than 3 numbered sections (the UI then says "sections are approximate"). `pages` comes from `docProps/app.xml`, not from a layout.

## Part 1. Real documents (62 uploads; 200 = same bytes already stored)

The 16 pilot-redline-integrity files are byte-identical to the b1 corpus files and came back 200 `reused`; `public/samples/cloud-service-agreement.docx` is the same file as CP01.

| name | status | detail | parseMs | pages | sections | numbered | longest | over5000 | over6000 | coverage | trackedChanges | hiddenRuns | approximate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b1/CP01.docx | 201 |  | 72.8 | 11 | 123 | 120 | 5408 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(5); footers=omitted(3) | 0 | 0 | False |
| b1/CP02.docx | 201 |  | 50.1 | 11 | 105 | 102 | 5265 | 1 | 0 | style_hidden_text=unknown(0); headers=omitted(4); footers=omitted(2) | 0 | 0 | False |
| b1/CP03.docx | 201 |  | 10.7 | 2 | 2 | 0 | 5923 | 1 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(11) | 0 | 0 | True |
| b1/CP04.docx | 201 |  | 47.5 | 9 | 6 | 0 | 5965 | 4 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(72) | 0 | 0 | True |
| b1/CP05.docx | 201 |  | 21.8 | 4 | 3 | 0 | 5984 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(47) | 0 | 0 | True |
| b1/CP06.docx | 201 |  | 42.5 | 7 | 86 | 84 | 5987 | 1 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1) | 0 | 0 | False |
| b1/CP07.docx | 201 |  | 36.1 | 5 | 68 | 67 | 3688 | 0 | 0 | style_hidden_text=unknown(0); headers=omitted(3); footers=omitted(2); automatic_numbering=omitted(67) | 0 | 0 | False |
| b1/CP08.docx | 201 |  | 41.0 | 5 | 113 | 112 | 1549 | 0 | 0 | style_hidden_text=unknown(0); headers=omitted(1); footers=omitted(1) | 0 | 0 | False |
| b1/UK01.docx | 201 |  | 250.9 | 15 | 336 | 334 | 5992 | 3 | 0 | style_hidden_text=unknown(0); headers=omitted(3); footers=omitted(3); endnotes=omitted(1); fields=partial(393); automatic_numbering=omitted(12) | 0 | 0 | False |
| b1/UK02.docx | 201 |  | 7919.3 | 6 | 2659 | 2657 | 5998 | 93 | 0 | style_hidden_text=unknown(0); headers=omitted(40); footers=omitted(58); endnotes=omitted(1); fields=partial(2854); automatic_numbering=omitted(4499) | 0 | 0 | False |
| b1/UK03.docx | 201 |  | 147.8 | 38 | 44 | 43 | 5958 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(4); endnotes=omitted(1); fields=partial(324); automatic_numbering=omitted(8) | 0 | 0 | False |
| b1/UK04.docx | 201 |  | 712.9 | 76 | 939 | 939 | 5997 | 6 | 0 | style_hidden_text=unknown(0); headers=omitted(1); footers=omitted(2); endnotes=omitted(1); fields=partial(782); automatic_numbering=omitted(77) | 0 | 0 | False |
| b1/UK06.docx | 201 |  | 45.6 | 17 | 92 | 91 | 4378 | 0 | 0 | style_hidden_text=unknown(0); headers=omitted(1); footers=omitted(2); fields=partial(40); automatic_numbering=omitted(31) | 0 | 0 | False |
| b1/UK07.docx | 201 |  | 166.3 | 36 | 49 | 46 | 5994 | 10 | 0 | style_hidden_text=unknown(0); footers=omitted(1); automatic_numbering=omitted(275) | 0 | 0 | False |
| b1/UK08.docx | 201 |  | 210.1 | 70 | 48 | 47 | 5985 | 10 | 0 | style_hidden_text=unknown(0); footers=omitted(2); footnotes=omitted(2); fields=partial(1); automatic_numbering=omitted(376) | 0 | 0 | False |
| b1/X01.docx | 201 |  | 98.2 | 36 | 309 | 309 | 5170 | 1 | 0 | style_hidden_text=unknown(0); headers=omitted(1); footers=omitted(2); fields=partial(228); automatic_numbering=omitted(39) | 0 | 0 | False |
| b1/X02.docx | 201 |  | 27.2 | 9 | 14 | 14 | 3891 | 0 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(3); fields=partial(44); automatic_numbering=omitted(24) | 0 | 0 | False |
| b1/X04.docx | 201 |  | 393.6 | 50 | 95 | 94 | 7106 | 9 | 1 | style_hidden_text=unknown(0); headers=omitted(1); footers=omitted(1); fields=partial(169); automatic_numbering=omitted(639) | 0 | 0 | False |
| b1/X05.docx | 201 |  | 2134.2 | 154 | 160 | 159 | 7103 | 39 | 1 | style_hidden_text=unknown(0); headers=omitted(4); fields=partial(603); automatic_numbering=omitted(245) | 0 | 0 | False |
| b1/smoke/UK05.docx | 201 |  | 42.3 | 8 | 3 | 0 | 5979 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(3); fields=partial(28); automatic_numbering=omitted(51) | 0 | 0 | True |
| pilot/CP01.docx | 200 |  | 72.8 | 11 | 123 | 120 | 5408 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(5); footers=omitted(3) | 0 | 0 | False |
| pilot/CP02.docx | 200 |  | 50.1 | 11 | 105 | 102 | 5265 | 1 | 0 | style_hidden_text=unknown(0); headers=omitted(4); footers=omitted(2) | 0 | 0 | False |
| pilot/CP03.docx | 200 |  | 10.7 | 2 | 2 | 0 | 5923 | 1 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(11) | 0 | 0 | True |
| pilot/CP04.docx | 200 |  | 47.5 | 9 | 6 | 0 | 5965 | 4 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(72) | 0 | 0 | True |
| pilot/CP05.docx | 200 |  | 21.8 | 4 | 3 | 0 | 5984 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(47) | 0 | 0 | True |
| pilot/CP06.docx | 200 |  | 42.5 | 7 | 86 | 84 | 5987 | 1 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1) | 0 | 0 | False |
| pilot/CP07.docx | 200 |  | 36.1 | 5 | 68 | 67 | 3688 | 0 | 0 | style_hidden_text=unknown(0); headers=omitted(3); footers=omitted(2); automatic_numbering=omitted(67) | 0 | 0 | False |
| pilot/CP08.docx | 200 |  | 41.0 | 5 | 113 | 112 | 1549 | 0 | 0 | style_hidden_text=unknown(0); headers=omitted(1); footers=omitted(1) | 0 | 0 | False |
| pilot/UK01.docx | 200 |  | 250.9 | 15 | 336 | 334 | 5992 | 3 | 0 | style_hidden_text=unknown(0); headers=omitted(3); footers=omitted(3); endnotes=omitted(1); fields=partial(393); automatic_numbering=omitted(12) | 0 | 0 | False |
| pilot/UK02.docx | 200 |  | 7919.3 | 6 | 2659 | 2657 | 5998 | 93 | 0 | style_hidden_text=unknown(0); headers=omitted(40); footers=omitted(58); endnotes=omitted(1); fields=partial(2854); automatic_numbering=omitted(4499) | 0 | 0 | False |
| pilot/UK03.docx | 200 |  | 147.8 | 38 | 44 | 43 | 5958 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(4); endnotes=omitted(1); fields=partial(324); automatic_numbering=omitted(8) | 0 | 0 | False |
| pilot/UK04.docx | 200 |  | 712.9 | 76 | 939 | 939 | 5997 | 6 | 0 | style_hidden_text=unknown(0); headers=omitted(1); footers=omitted(2); endnotes=omitted(1); fields=partial(782); automatic_numbering=omitted(77) | 0 | 0 | False |
| pilot/UK05.docx | 200 |  | 42.3 | 8 | 3 | 0 | 5979 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(3); fields=partial(28); automatic_numbering=omitted(51) | 0 | 0 | True |
| pilot/UK06.docx | 200 |  | 45.6 | 17 | 92 | 91 | 4378 | 0 | 0 | style_hidden_text=unknown(0); headers=omitted(1); footers=omitted(2); fields=partial(40); automatic_numbering=omitted(31) | 0 | 0 | False |
| pilot/UK07.docx | 200 |  | 166.3 | 36 | 49 | 46 | 5994 | 10 | 0 | style_hidden_text=unknown(0); footers=omitted(1); automatic_numbering=omitted(275) | 0 | 0 | False |
| pilot/UK08.docx | 200 |  | 210.1 | 70 | 48 | 47 | 5985 | 10 | 0 | style_hidden_text=unknown(0); footers=omitted(2); footnotes=omitted(2); fields=partial(1); automatic_numbering=omitted(376) | 0 | 0 | False |
| targets/CP01-M1/A/redline.docx | 201 |  | 67.7 | 11 | 123 | 120 | 5408 | 2 | 0 | tracked_insertions=accepted(1); tracked_deletions=excluded(1); style_hidden_text=unknown(0); headers=omitted(5); footers=omitted(3); tracked_changes_total=accepted(2) | 2 | 0 | False |
| targets/CP01-M1/A/accepted.docx | 201 |  | 60.4 | 3 | 123 | 120 | 5408 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(5); footers=omitted(3) | 0 | 0 | False |
| targets/CP01-M1/A/rejected.docx | 201 |  | 51.8 | 3 | 123 | 120 | 5408 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(5); footers=omitted(3) | 0 | 0 | False |
| targets/CP02-M1/A/redline.docx | 201 |  | 47.0 | 11 | 105 | 102 | 5265 | 1 | 0 | tracked_insertions=accepted(1); tracked_deletions=excluded(1); style_hidden_text=unknown(0); headers=omitted(4); footers=omitted(2); tracked_changes_total=accepted(2) | 2 | 0 | False |
| targets/CP02-M1/A/accepted.docx | 201 |  | 47.9 | 3 | 105 | 102 | 5265 | 1 | 0 | style_hidden_text=unknown(0); headers=omitted(4); footers=omitted(2) | 0 | 0 | False |
| targets/CP02-M1/A/rejected.docx | 201 |  | 47.5 | 3 | 105 | 102 | 5265 | 1 | 0 | style_hidden_text=unknown(0); headers=omitted(4); footers=omitted(2) | 0 | 0 | False |
| targets/CP04-M1/A/redline.docx | 201 |  | 50.4 | 9 | 6 | 0 | 5998 | 4 | 0 | tracked_insertions=accepted(1); tracked_deletions=excluded(1); style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(72); tracked_changes_total=accepted(2) | 2 | 0 | True |
| targets/CP04-M1/A/accepted.docx | 201 |  | 46.1 | 3 | 6 | 0 | 5998 | 4 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(72) | 0 | 0 | True |
| targets/CP04-M1/A/rejected.docx | 201 |  | 47.4 | 3 | 6 | 0 | 5965 | 4 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(72) | 0 | 0 | True |
| targets/CP05-M2/A/redline.docx | 201 |  | 33.0 | 4 | 3 | 0 | 5984 | 2 | 0 | tracked_insertions=accepted(1); tracked_deletions=excluded(1); style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(47); tracked_changes_total=accepted(2) | 2 | 0 | True |
| targets/CP05-M2/A/accepted.docx | 201 |  | 22.4 | 3 | 3 | 0 | 5984 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(47) | 0 | 0 | True |
| targets/CP05-M2/A/rejected.docx | 201 |  | 21.8 | 3 | 3 | 0 | 5984 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(2); footers=omitted(1); automatic_numbering=omitted(47) | 0 | 0 | True |
| fixtures/services-agreement.pdf | 201 |  | 34.3 | 1 | 1 | 0 | 573 | 0 | 0 | tables=partial(0); headers=unknown(0); footers=unknown(0); footnotes=unknown(0); scanned_pages=unknown(0); embedded_objects=omitted(0) | 0 | 0 | True |
| samples/cloud-service-agreement.docx | 200 |  | 72.8 | 11 | 123 | 120 | 5408 | 2 | 0 | style_hidden_text=unknown(0); headers=omitted(5); footers=omitted(3) | 0 | 0 | False |
| cuad/01-2themartcominc-19990826-10-12g-ex-10-10-6700288-ex-10-10-co-.txt | 201 |  | 0.4 |  | 12 | 11 | 5811 | 3 | 0 |  | 0 | 0 | False |
| cuad/02-alamogordofinancialcorp-12-16-1999-ex-1-agency-agreement.txt | 201 |  | 0.8 |  | 28 | 27 | 5977 | 21 | 0 |  | 0 | 0 | False |
| cuad/03-atmosenergycorp-11-22-2002-ex-10-17-transportation-service-a.txt | 201 |  | 0.5 |  | 30 | 29 | 4608 | 0 | 0 |  | 0 | 0 | False |
| cuad/04-audibleinc-20001113-10-q-ex-10-32-2599586-ex-10-32-co-brandi.txt | 201 |  | 1.0 |  | 27 | 26 | 5894 | 7 | 0 |  | 0 | 0 | False |
| cuad/05-blueflyinc-03-27-2002-ex-10-27-e-business-hosting-agreement.txt | 201 |  | 0.7 |  | 51 | 50 | 5152 | 1 | 0 |  | 0 | 0 | False |
| cuad/06-ccaindustriesinc-04-14-2014-ex-10-1-outsourcing-agreement.txt | 201 |  | 0.7 |  | 40 | 39 | 3526 | 0 | 0 |  | 0 | 0 | False |
| cuad/07-ccrealestateincomefundadv-20181205-pos-8c-ex-99-h-3-11447739.txt | 201 |  | 0.2 |  | 6 | 0 | 5828 | 4 | 0 |  | 0 | 0 | True |
| cuad/08-drivendeliveries-inc-05-22-2020-ex-10-4-consulting-agreement.txt | 201 |  | 0.2 |  | 7 | 0 | 6056 | 1 | 1 |  | 0 | 0 | True |

Observations on Part 1:

- Four of the twenty licensed DOCX contracts (CP03, CP04, CP05, UK05) come out as 2–6 unnumbered chunks named "(part n)". They are Common Paper / Crown Commercial templates whose clauses are Normal paragraphs with automatic numbering (`automatic_numbering=omitted(11/72/47/51)`), so the whole contract is one section split at 6,000 characters. Each part over 5,000 characters loses its tail in the prompt: 11–14 % of CP03, CP05 and UK05 is never shown to the model.
- Three sections exceed 6,000 characters although the reader claims to split at 6,000 (X04 §21 7,106; X05 §99 7,103; CUAD 08 6,056): each is a single paragraph, and the split only happens at paragraph boundaries.
- Text beyond the 5,000-character window, per document: UK02 71,451 chars in 93 sections (5.7 %), X05 31,104 (8.2 %), CUAD 02 14,242 (10.2 %), UK05 1,792 (14.1 %). The run explanation reports this honestly (`truncated: true`, `charactersOutsideContext`); the document pane does not.
- CUAD 07 and 08 (TXT) have a first line longer than 90 characters; it becomes the title and the heading of every part, so a 2,733-character "heading" is repeated on 6 sections (CUAD 07) and a 2,316-character one on 7 (CUAD 08). Headings are never truncated in the prompt.
- X04's title is the unfilled template field `«F1: CONTRACT REFERENCE NUMBER (IF ANY)»`.
- Tracked changes: the four redline files read exactly as their accepted.docx twins (text identical) and differ from rejected.docx, with `trackedChanges=2` and `tracked_insertions=accepted(1); tracked_deletions=excluded(1)`. The accepted/rejected twins report `pages=3` while the redline reports 11: `pages` is the generator's stale `docProps/app.xml`, not a count.
- UK01, UK03 and X05 carry 1, 1 and 20 block-level content controls (their tables of contents and X05's schedule cover sheets); the reader drops them and reports `content_controls=read` (see defect 2).
- UK02: 2,659 sections in 7.9 s; UK04: 939 in 0.7 s; the 2,500-section synthetic file: 3.4–4.0 s.

## Part 2. Generated adversarial and unusual files (65 uploads)

Honesty verdict: does the stored coverage / detail say what the reader did not read? The API was restarted by a sibling process part-way through the first pass, so the second pass shows 200 `reused` for files the first pass had already stored; the reader results are identical.

| name | status | detail | sections | numbered | longest | cov | trackedChanges | hiddenRuns | what | honest |
|---|---|---|---|---|---|---|---|---|---|---|
| a1_heading_styles.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | 6 sections, 5 numbered (computed 1-5 from heading levels) | yes |
| a2_typed_numbers_normal.docx | 201 |  | 1 | 0 | 922 | style_hidden_text=unknown(0) | 0 | 0 | ONE section; typed '1. Term' lines in Normal style are not headings in DOCX | no: nothing says the numbering was ignored; UI only says 'approximate' |
| a2b_heading_typed_numbers.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | 6 sections, printed numbers kept | yes |
| a3_numpr_auto_numbering.docx | 201 |  | 1 | 0 | 907 | style_hidden_text=unknown(0); automatic_numbering=omitted(5) | 0 | 0 | ONE section; numPr paragraphs not headings; list numbers absent from text | partly: automatic_numbering=omitted(5) |
| a3b_numpr_on_headings.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0); automatic_numbering=omitted(5) | 0 | 0 | 6 sections; numbers computed 1-5 (match Word here by luck) | partly: computed numbers look printed |
| b1_mixed_formatting.docx | 201 |  | 1 | 0 | 292 | style_hidden_text=unknown(0) | 0 | 0 | ONE section; 14pt bold Normal and ALL-CAPS lines are not headings in DOCX | no |
| c1_tables_only.docx | 201 |  | 1 | 0 | 177 | style_hidden_text=unknown(0) | 0 | 0 | one section, rows joined with ' \| ' | yes (tables=read) |
| c2_nested_tables.docx | 201 |  | 1 | 0 | 50 | style_hidden_text=unknown(0) | 0 | 0 | nested table DROPPED: 'Inner 2: termination fee 5,000 EUR' gone | NO: coverage says tables=read(2) |
| c3_merged_cells.docx | 201 |  | 1 | 0 | 104 | style_hidden_text=unknown(0) | 0 | 0 | horizontal merge de-duplicated; vertical merge text repeated on each row | yes |
| d1_header_footer.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0); headers=omitted(1); footers=omitted(1) | 0 | 0 | header/footer text left out | yes: headers=omitted(1), footers=omitted(1) |
| d2_footnotes_endnotes_comments.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0); footnotes=omitted(1); endnotes=omitted(1); comments=omitted(1) | 0 | 0 | footnote, endnote, comment text left out; reference marks gone | yes: each omitted(1) |
| d3_content_controls.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | BLOCK content control DROPPED (heading 'Liability…' + 'liability is capped at 100,000 USD'); inline kept | NO: content_controls=read(2) 'inline controls read' |
| d4_fields.docx | 201 |  | 6 | 5 | 307 | style_hidden_text=unknown(0); fields=partial(5) | 0 | 0 | cached results kept (PAGE '7', REF '3', stale 'Error! Reference source not found.'); TOC entries become the title block '1 Definitions 2' | partly: fields=partial(5); TOC-as-title unsaid |
| d5_hyperlinks.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | display text kept, targets not fetched | yes |
| e1_hidden_runs_and_styles.docx | 201 |  | 6 | 5 | 280 | hidden_runs=excluded(1); style_hidden_text=unknown(0) | 0 | 1 | direct hidden run left out (hiddenRuns=1); style-hidden paragraph and style-hidden run KEPT ('liability cap is 1 USD', 'jurisdiction is Texas') | partly: style_hidden_text=unknown |
| e2_tracked_changes_raw.docx | 201 |  | 6 | 5 | 548 | tracked_insertions=accepted(2); tracked_deletions=excluded(5); move_revisions=accepted(2); style_hidden_text=unknown(0); tracked_changes_total=accepted(9) | 9 | 0 | accepted view: 'sixty (60) days', moved text once at destination, deleted mark joins 'sentencesecond'; heading with deleted mark loses heading status | yes: 2 ins, 5 del, 2 moves, total 9 |
| f1_hindi.docx | 201 |  | 5 | 4 | 93 | style_hidden_text=unknown(0) | 0 | 0 | 5 sections, 4 numbered; Devanagari intact | yes |
| f2_chinese.docx | 201 |  | 5 | 4 | 26 | style_hidden_text=unknown(0) | 0 | 0 | 5 sections, 4 numbered; CJK intact | yes |
| f4_greek.docx | 201 |  | 5 | 4 | 85 | style_hidden_text=unknown(0) | 0 | 0 | 5 sections, 4 numbered; Greek intact | yes |
| f3_arabic_rtl.docx | 201 |  | 5 | 4 | 73 | style_hidden_text=unknown(0) | 0 | 0 | 5 sections, 4 numbered; Arabic intact (bidi flag dropped, harmless) | yes |
| f5_emoji_astral.docx | 201 |  | 3 | 2 | 101 | style_hidden_text=unknown(0) | 0 | 0 | emoji, flags, ZWJ family, math-bold and Gothic kept verbatim | yes; verifier cannot match math-bold text (locate -> None) |
| f6_zero_width_soft_hyphen.docx | 201 |  | 4 | 3 | 115 | style_hidden_text=unknown(0) | 0 | 0 | soft hyphen, ZWJ, ZWSP, NBSP, LRE/PDF kept verbatim: '3\xad0 days', 'ter\u200dmin\u200date' | verbatim, but verifier: '30 days' vs '3\xad0 days' -> None; ZWJ word -> None |
| f7_typographic.docx | 201 |  | 3 | 2 | 180 | style_hidden_text=unknown(0) | 0 | 0 | curly quotes, en/em dashes, ellipsis, non-breaking hyphen kept | yes; verifier normalizes straight quotes to curly |
| f8_100k_paragraph.docx | 201 |  | 1 | 0 | 100000 | style_hidden_text=unknown(0) | 0 | 0 | ONE section; heading AND text are the full 100,000 chars (title path) | no: heading line is never truncated in the prompt |
| f8b_100k_paragraph_under_heading.docx | 201 |  | 2 | 1 | 100000 | style_hidden_text=unknown(0) | 0 | 0 | 2 sections; the 100,000-char body is NOT split (one paragraph); prompt shows 5,000 + ' […]' | explanation says 'the rest was cut' |
| f9_2500_sections.docx | 201 |  | 2501 | 2500 | 138 | style_hidden_text=unknown(0) | 0 | 0 | 2,501 sections, 2,500 numbered, 3.4 s | yes |
| g1_at_25mb.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0); embedded_objects=omitted(1) | 0 | 0 | exactly 25 MiB accepted; the 25 MB pad is counted as embedded_objects=omitted(1) | yes |
| g1b_under_25mb.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0); embedded_objects=omitted(1) | 0 | 0 | accepted | yes |
| g2_over_25mb.docx | 413 | file larger than 25 MB |  |  |  |  |  |  | 413 'file larger than 25 MB' | yes |
| g3_declares_300mb.docx | 413 | the .docx unpacks to 300 MB; the limit is 256 MB |  |  |  |  |  |  | 413 'unpacks to 300 MB; the limit is 256 MB' | yes |
| g3b_underdeclared_300mb.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0); embedded_objects=omitted(1) | 0 | 0 | accepted: the under-declared 300 MB member is unreferenced so never read | n/a |
| g4_macro.docm | 200 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | 200 REUSED: same bytes as a1 -> the .docm extension check is bypassed | no: a .docm is 'accepted' |
| g4b_docm_as_docx.docx | 422 | the file is not a readable .docx package |  |  |  |  |  |  | 422 'not a readable .docx package' (macroEnabled main part) | generic |
| g5_docx_renamed.pdf | 200 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | 200 REUSED under .pdf name (same bytes) | n/a: reuse by bytes |
| h1_multicolumn.pdf | 201 |  | 3 | 2 | 138 | tables=partial(0); headers=unknown(0); footers=unknown(0); footnotes=unknown(0); scanned_pages=unknown(0); embedded_objects=omitted(0) | 0 | 0 | columns INTERLEAVED line by line: 'The term of this Agreement is This Agreement is governed by' | no: coverage says main_body=read; nothing flags columns |
| h2_running_header_footer.pdf | 201 |  | 6 | 5 | 95 | tables=partial(0); headers=unknown(0); footers=unknown(0); footnotes=unknown(0); scanned_pages=unknown(0); embedded_objects=omitted(0) | 0 | 0 | running header becomes an all-caps heading on every page with COMPUTED numbers 2 and 3 that collide with real clauses 2 and 3; footer 'Page n of 3 Doc ref 380 INTERLOCKEN CRESCENT' inside each clause body | no: headers/footers=unknown |
| h3_image_only_page.pdf | 201 |  | 3 | 2 | 46 | tables=partial(0); headers=unknown(0); footers=unknown(0); footnotes=unknown(0); scanned_pages=unknown(0); embedded_objects=omitted(0) | 0 | 0 | image-only middle page silently contributes nothing; pages=3, main_body=read(3) | no: scanned_pages=unknown(0) though the page count with no text is known |
| h3b_image_only.pdf | 422 | no readable text found in the file |  |  |  |  |  |  | 422 'no readable text found in the file' | yes |
| h4_encrypted.pdf | 422 | the PDF is encrypted; remove the password and upload it again |  |  |  |  |  |  | 422 encrypted | yes |
| h4b_encrypted_empty_user_pw.pdf | 422 | the PDF is encrypted; remove the password and upload it again |  |  |  |  |  |  | 422 encrypted although it opens with an empty password | documented |
| h5_2001_pages.pdf | 413 | the PDF has 2001 pages; the limit is 2000 |  |  |  |  |  |  | 413 '2001 pages; the limit is 2000' | yes |
| h6_blank_pages.pdf | 422 | no readable text found in the file |  |  |  |  |  |  | 422 'no readable text' | yes |
| h6b_empty.pdf | 422 | the file is not a readable PDF |  |  |  |  |  |  | 422 'not a readable PDF' | yes |
| g6_pdf_renamed.docx | 422 | the file is not a readable .docx package |  |  |  |  |  |  | 422 'not a readable .docx package' | yes |
| g7_external_image.docx | 201 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | accepted; the linked image is ignored, not fetched; body text after it kept | embedded_objects=absent (0) although a linked picture exists |
| g8_empty.docx | 422 | the file is not a readable .docx package |  |  |  |  |  |  | 422 'not a readable .docx package' | yes |
| g9_UPPER.DOCX | 200 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | 200 reused (bytes) — extension case would be fine anyway | n/a |
| g10_noext | 200 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | 200 reused: no extension, accepted because the bytes are known | no: 'unsupported file type (none)' never fires for known bytes |
| g11_docx_renamed.txt | 200 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | 200 reused under .txt name | n/a |
| g12_broken_document_xml.docx | 422 | the file is not a readable .docx package |  |  |  |  |  |  | 422 'not a readable .docx package' | yes |
| g13_broken_footnotes.docx | 200 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | accepted; corrupt footnotes.xml never parsed; footnotes=absent | footnotes reported absent, not unreadable |
| g14_degenerate_tables.docx | 200 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | empty table and row-without-cells survive; 'Only cell' kept; sdt-wrapped table ('fee 9,999 USD') DROPPED | NO: tables=read(3), content_controls=read(1) |
| g15_missing_style.docx | 200 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | missing style, outlineLvl 42 and 'x' all treated as body text; no 500 | yes |
| g16_gridspan_overflow.docx | 200 |  | 6 | 5 | 253 | style_hidden_text=unknown(0) | 0 | 0 | gridSpan 5-of-2 survives; vMerge continuation repeats 'A' on the second row | yes |
| g17_deleted_row.docx | 200 |  | 6 | 5 | 253 | tracked_insertions=accepted(1); tracked_deletions=excluded(1); style_hidden_text=unknown(0); tracked_changes_total=accepted(2) | 2 | 0 | deleted row left out, inserted row kept; trackedChanges=2 | yes |
| i1_utf8_bom.txt | 200 |  | 4 | 3 | 45 |  | 0 | 0 | BOM U+FEFF kept at the start of the title | cosmetic |
| i2_utf16.txt | 200 |  | 1 | 0 | 339 |  | 0 | 0 | UTF-16 decoded as UTF-8: '\ufffd\ufffdS\x00E\x00R\x00…' one 339-char section of NUL-interleaved text | NO: 200 with garbage, no warning |
| i3_crlf.txt | 200 |  | 4 | 3 | 45 |  | 0 | 0 | CRLF fine | yes |
| i4_latin1.txt | 200 |  | 3 | 2 | 80 |  | 0 | 0 | cp1252 bytes -> U+FFFD: '€1,500' becomes '\ufffd1,500', 'Société' mangled | no: silent replacement |
| i5_empty.txt | 422 | no readable text found in the file |  |  |  |  |  |  | 422 'no readable text' | yes |
| i6_addresses_dates.txt | 200 |  | 5 | 4 | 149 |  | 0 | 0 | '380 INTERLOCKEN CRESCENT' -> section 380; 'BROOMFIELD, CO 80021' -> computed section 381; '30 June 2026' -> section 30 holding the whole notice body | no: computed 381 looks printed |
| i7_cr_only.txt | 200 |  | 4 | 3 | 45 |  | 0 | 0 | CR-only line endings fine | yes |
| i8_nul_bytes.txt | 200 |  | 2 | 1 | 23 |  | 0 | 0 | NUL bytes kept inside the text and the heading | cosmetic |
| i9_whitespace_only.txt | 422 | no readable text found in the file |  |  |  |  |  |  | 422 'no readable text' | yes |
| g3c_underdeclared_document_xml_40mb.docx | 422 | the file is not a readable .docx package |  |  |  |  |  |  | 422 'not a readable .docx package': zipfile CRC check refuses an under-declared document.xml | generic message, correct outcome |

## Part 3. Model runs (6, serialized on the shared GPU)

| document | question | post | stage | reason | findings | withheld | verified spans | methods | latencyMs | wall_s | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| UK05 (fields, Schedule 3 Charges) | What happens to the Charges when the contract is terminated or expires, and what adjustments apply? | 202 | complete |  | 1 | 0 | 2/2 | exact, normalized | 72584.00479999545 | 75 |  |
| CP01-M1/A redline.docx (tracked changes) | How much notice is required to terminate this agreement for convenience, and who may give it? | 202 | complete |  | 1 | 0 | 1/1 | exact | 71534.33000000223 | 165 |  |
| f1_hindi.docx | Which law governs this agreement and which courts have jurisdiction? | 202 | complete |  | 2 | 0 | 2/2 | exact | 136532.91790000367 | 232 |  |
| f9_2500_sections.docx | Which law governs this agreement? | 202 | complete |  | 1 | 0 | 1/1 | exact | 68790.62130000239 | 160 |  |
| cuad/01 2themart co-branding (txt) | How can this agreement be terminated and what notice is required? | 202 | complete |  | 5 | 0 | 5/5 | exact, normalized, relocated:exact | 285528.5793000003 | 411 |  |
| f8_100k_paragraph.docx (100,000-char first paragraph) | What notice period applies to termination of this agreement? | 202 | failed | provider_error | 0 | 0 | 0/0 |  |  | ~1470 (08:00:42 -> 08:25:13 UTC) | Ollama request failed: timed out |

Per-run notes:

1. **UK05.docx** (fields, 3 unnumbered parts): `complete`, one `missing` finding ("Charges are not explicitly addressed upon termination"), `evidence_kind=coverage`, two verified spans (`normalized`, `exact`). Parts 1 and 2 were truncated at 5,000 of 5,813 / 5,979 chars (`charactersOutsideContext: 1792`); no termination text lies beyond the window, so the answer was not caused by the cut. The explanation lists `notRead: headers (2), footers (3), automatic numbering (51)` but not `fields=partial(28)`.
2. **CP01-M1/A redline.docx**: `complete`, one `missing` finding whose conclusion is wrong: "No notice is required to terminate this agreement for convenience". The only termination section handed over was §5.3 (76 chars: "Either party may terminate … immediately:") because the list items 5.3.1 / 5.3.2 ("following 30 days notice", "upon notice …") are separate sections and were not retrieved. The tracked change (liability cap, §8) was irrelevant to the question and read in its accepted form. Reconstructable, 0 chars outside context.
3. **f1_hindi.docx**: `complete`, two `pass` findings (Indian law; Delhi courts), both spans `exact`, Devanagari quotes verified at 0–93 of §4. Headings "1. परिभाषाएँ" were numbered 1–4 from the typed numbers. Nothing odd.
4. **f9_2500_sections.docx**: `complete`, one `pass` finding; BM25 ranked §1777 second of 2,501; span `exact` at 71–138. Nothing odd.
5. **CUAD 01 (TXT)**: `complete` in 285 s, five `pass` findings (breach, change of control, bankruptcy, force majeure, renewal). One span is `relocated:exact`: the model cited `sec_12`, a label that was not among the six handed over (sec_8, 6, 7, 5, 2, 4); the verifier found the quote in sec_8 (§12 GENERAL PROVISIONS) and the finding is shown as verified with `relocated: true`. Three of the six retrieved sections were truncated (5,709 / 5,811 / 5,811 chars; 2,331 chars outside context). "Renewal of Term" is not an answer to the termination question but is shown as a `pass`.
6. **f8_100k_paragraph.docx** (100,000-char first paragraph = title = heading): the prompt carried the 100,000-char heading line untruncated plus the 5,000-char slice (`charactersOutsideContext: 95000`, `truncated: true`); the explanation shows `proposalsProblem: "Model proposal not reconstructable for this run."` while the run is in flight. The run stayed in `checking` ("against the question") past the 15-minute poll limit; `/api/health` meanwhile reported "0 waiting". Final state: `failed`, `reason: provider_error`, `error: "Ollama request failed: timed out"` at 08:25:13 UTC, 24.5 minutes after start (600 s model timeout, retried once); no findings, no raw output; the explanation still says `reconstructable: true` with `proposalsProblem: "Model proposal not reconstructable for this run."`. The GPU was held for the whole 24 minutes by a prompt of ~105,000 characters sent to a 16,384-token context.

## Defects and edge cases (ranked by severity)

Severity key: critical = crash/500; high = silent data loss or wrong structure that changes what the model sees; medium = misleading UI/text; low = cosmetic. Files are under `gen\`. Upload command for any file: `curl -s -F "file=@<path>" http://127.0.0.1:8010/api/documents`.

### Critical (crash / 500)

None found. 115 uploads and 6 run starts returned 2xx/4xx only; degenerate tables (empty `w:tbl`, row without cells, gridSpan 5 of 2), missing style ids, `outlineLvl` 42 and `x`, a corrupt `footnotes.xml`, an under-declared zip member and a 0-byte DOCX all return 201 or 422. One run (f8) did not reach a terminal stage within 15 minutes (see High 7).

### High (silent data loss / wrong structure the model sees)

1. **Block-level content controls are dropped and reported as "read".** The whole `w:sdt` body child (heading + clause) vanishes from the sections, while coverage says `content_controls=read(N) "inline controls read through their content"`. Cause (`backend/app/ingest/coverage.py`): the block-control regex `<w:body>(?:(?!</w:body>).)*?<w:sdt>` never matches because the serialised body is `<w:body xmlns:w=…>`, so `block_controls` is always 0; the second regex `(?<=</w:p>|<w:body>)\s*<w:sdt>` would raise `re.error: look-behind requires fixed-width pattern` if it ever ran. In the licensed corpus UK01, UK03 and X05 carry 1, 1 and 20 block controls (TOCs and 19 schedule cover sheets) all reported as read.
   Repro: `curl -s -F "file=@gen\d3_content_controls.docx" http://127.0.0.1:8010/api/documents` → 201, 6 sections, no "Liability (inside a block-level content control)" / "capped at 100,000 USD", coverage `content_controls: read, 2`. Also `g14_degenerate_tables.docx`: the table inside an sdt ("fee 9,999 USD") is gone, `tables=read(3)`.
2. **Nested tables are dropped and counted as read.** `c2_nested_tables.docx`: "Inner 2: termination fee 5,000 EUR" is absent; coverage `tables=read(2)` counts the nested table as read. Repro: `curl -s -F "file=@gen\c2_nested_tables.docx" http://127.0.0.1:8010/api/documents` → text is `Schedule of charges / Outer A1 | Outer A2 / Outer B1`.
3. **Contracts whose clauses are Normal paragraphs (typed "1." numbers, `w:numPr`, bold 14pt, ALL CAPS) become one section.** DOCX uses only styles/outline levels for headings; the TXT/PDF line rules are not applied. The model then sees 5,000-char slices of unnamed "(part n)" chunks and cannot cite a clause number. Real cases: CP03 (2 parts), CP04 (6), CP05 (3), UK05 (3) with 0 numbered sections; 6.5–14 % of each is beyond the window. Repro: `curl -s -F "file=@gen\a2_typed_numbers_normal.docx" http://127.0.0.1:8010/api/documents` → 1 section, `numbered 0`; same for `a3_numpr_auto_numbering.docx`, `b1_mixed_formatting.docx`.
4. **A list item styled as a heading is split from its lead-in, and retrieval hands over the lead-in alone.** CP01 §5.3 "Termination" is a 76-char section ending in a colon; its items are §5.3.1/§5.3.2. Run 2b049f6a723745d8 received §5.3 without its items and concluded "No notice is required to terminate for convenience" (status `missing`, span verified `exact`). Repro: `POST /api/runs {"documentId":"<CP01 redline id>","guidanceId":null,"question":"How much notice is required to terminate this agreement for convenience, and who may give it?"}`; see `out/part3_runs.json` entry 2. (Common Paper templates: all CP0x files.)
5. **Style-hidden text is read as if visible.** A paragraph style or character style with `w:vanish` hides text in Word; the reader keeps it ("STYLE-HIDDEN PARAGRAPH: the liability cap is 1 USD.", "jurisdiction is Texas.") and only a direct run `w:vanish` is excluded (`hiddenRuns=1`). Coverage says `style_hidden_text=unknown`, which is honest but the text reaches the model and can be quoted and verified. Repro: `curl -s -F "file=@gen\e1_hidden_runs_and_styles.docx" http://127.0.0.1:8010/api/documents` → §5 text contains both sentences.
6. **UTF-16 and Latin-1/cp1252 text files are accepted as garbage.** `i2_utf16.txt` → 200/201, one 339-char section of `\ufffd\ufffdS\x00E\x00R…` (every other byte NUL); no section is numbered, no warning. `i4_latin1.txt` → "€1,500" becomes "\ufffd1,500", "Société" is mangled. Repro: `curl -s -F "file=@gen\i2_utf16.txt" http://127.0.0.1:8010/api/documents`.
7. **A 100,000-character first paragraph is the heading and reaches the prompt whole, and the run does not end.** `f8_100k_paragraph.docx` → 1 section whose `heading` and `text` are both 100,000 chars; the explanation confirms `charactersOutsideContext: 95000` yet the heading line is sent uncut, so the prompt is ~105,000 chars for a 16,384-token context. Run 6d6fbd7ed8dc4889 sat in `checking` for >16 min (model timeout 600 s, one retry) while `/api/health` said "0 waiting". Final state: `failed`, `reason: provider_error`, `error: "Ollama request failed: timed out"` at 08:25:13 UTC, 24.5 minutes after start (600 s model timeout, retried once); no findings, no raw output; the explanation still says `reconstructable: true` with `proposalsProblem: "Model proposal not reconstructable for this run."`. The GPU was held for the whole 24 minutes by a prompt of ~105,000 characters sent to a 16,384-token context.. Repro: `curl -s -F "file=@gen\f8_100k_paragraph.docx" http://127.0.0.1:8010/api/documents` then POST /api/runs with any question. (Under a heading, `f8b_…`, the paragraph is one 100,000-char section, never split, and the model sees 5 %.)
8. **PDF running headers become numbered headings that collide with real clause numbers; footers land inside clause text.** `h2_running_header_footer.pdf` → sections numbered `''`, `1`, `2` (the header, empty), `2` (TERMINATION), `3` (the header, empty), `3` (GOVERNING LAW); each clause body ends with "Page n of 3 Doc ref 380 INTERLOCKEN CRESCENT". The computed numbers are indistinguishable from printed ones. Repro: `curl -s -F "file=@gen\h2_running_header_footer.pdf" http://127.0.0.1:8010/api/documents`.
9. **Two-column PDF text is interleaved line by line.** `h1_multicolumn.pdf` → "The term of this Agreement is This Agreement is governed by twelve (12) months from the the laws of the State of Effective Date. Delaware." Coverage says `main_body=read`. Repro: `curl -s -F "file=@gen\h1_multicolumn.pdf" http://127.0.0.1:8010/api/documents`.
10. **Sections 5,001–6,000 characters long lose their tail silently in the prompt; one-paragraph sections are never split.** 93 sections of UK02, 39 of X05, 21 of CUAD 02; X04 §21 is 7,106 chars (one paragraph). The explanation marks `truncated: true`; the document pane and the finding card do not. A quote from the cut tail is refused by the verifier (bounded to 5,000), so a correct citation past the window becomes "withheld".
11. **TXT/PDF lines that start with a number become sections with computed numbers.** `i6_addresses_dates.txt` → "380 INTERLOCKEN CRESCENT" is section 380, "BROOMFIELD, CO 80021" is section **381** (computed from 380), "30 June 2026" is section 30 and holds the whole notice body. Repro: `curl -s -F "file=@gen\i6_addresses_dates.txt" http://127.0.0.1:8010/api/documents`.

### Medium (misleading UI / text / policy)

12. **The `.docm` rejection is bypassed by byte reuse.** Bytes already stored under a `.docx` name are returned 200 `reused` for `g4_macro.docm`, `g5_docx_renamed.pdf`, `g10_noext` (no extension) and `g11_docx_renamed.txt`, under the stored name. The extension check runs only after the hash lookup. Repro: upload `a1_heading_styles.docx`, then `curl -s -F "file=@gen\g4_macro.docm" http://127.0.0.1:8010/api/documents` → 200.
13. **Image-only PDF pages are invisible.** `h3_image_only_page.pdf` → `pages=3`, `main_body=read(3)`, `scanned_pages=unknown(0)`; page 2 contributed nothing and the count of text-less pages (known to the reader) is not reported. Repro: `curl -s -F "file=@gen\h3_image_only_page.pdf" http://127.0.0.1:8010/api/documents`.
14. **Soft hyphens and zero-width joiners defeat the verifier.** Text is stored verbatim ("3\u00AD0 days", "ter\u200Dmin\u200Date"); `verify.spans.locate("30 days", "…3\u00AD0 days…")` → `None`, likewise for the ZWJ word and for mathematical-bold letters, so a correct quote is withheld. ZWSP ("1\u200B2 months") and BOM are folded. Repro: upload `f6_zero_width_soft_hyphen.docx`; offline: `cd backend && .venv\Scripts\python -c "from app.verify.spans import locate; print(locate('30 days','3\u00ad0 days'))"`.
15. **TOC field text is read as body and becomes the title.** `d4_fields.docx` → title block "1 Definitions 2 / 3 Termination 4 / SHORT SERVICES AGREEMENT"; the stale field result "Error! Reference source not found." is contract text. `fields=partial(5)` says nothing about TOC entries. Repro: `curl -s -F "file=@gen\d4_fields.docx" http://127.0.0.1:8010/api/documents`.
16. **Document pane shows only `omitted` parts.** `DocumentPane.tsx` filters `status === "omitted" && count > 0`, so `partial` (fields: 28 in UK05, 2,854 in UK02), `unknown` (style-hidden text, scanned pages, PDF headers/footers) and the wrong `read` of defects 1–2 are never shown there; the explanation's `notRead` list has the same filter.
17. **Computed section numbers look printed.** `number_computed` is not persisted (SYSTEM_TRUTH says so); defects 8 and 11 show it producing duplicate and non-existent numbers (`2`, `3`, `381`) that the model cites as clause numbers.
18. **A long first line of a TXT becomes the heading of every part.** CUAD 07: a 2,733-char heading on 6 sections (≈16 k prompt chars of repeated title); CUAD 08: 2,316 chars on 7. Headings are exempt from the 5,000 window and the 110-char heading cap applies only to lead-in splitting.
19. **A model citation to a label that was never handed over is accepted after relocation.** CUAD 01 run 372cc857fcbf411e: `citedLabel: sec_12` (not among the six candidates) was relocated to sec_8 and shown as verified (`relocated:exact`). The finding card shows a verified quote; only the explanation says `relocated: true`.
20. **PDF that opens with an empty user password is refused** (`h4b_encrypted_empty_user_pw.pdf` → 422 "encrypted"); documented, but a common case (owner-password-only PDFs from DMS exports).
21. **A linked (external) image is not counted.** `g7_external_image.docx` → `embedded_objects=absent`; the relationship with `TargetMode="External"` is neither fetched (good) nor reported.
22. **Corrupt `footnotes.xml`** (`g13_broken_footnotes.docx`) → 201 with `footnotes=absent`: the part is never parsed, so a damaged notes part reads as "no footnotes".

### Low (cosmetic)

23. UTF-8 BOM is kept as U+FEFF at the start of the title (`i1_utf8_bom.txt`); NUL bytes are kept inside headings and text (`i8_nul_bytes.txt`, heading `Term\x00`).
24. Vertically merged cells repeat their text on every row they span (`c3_merged_cells.docx`: "Vertical: Fees | R1C1 | R1C2 / Vertical: Fees | R2C1 | R2C2"; `g16`: "A | B / A | C").
25. PDF/TXT whose first line is a numbered heading produce an empty leading section whose heading is that line (`h1`, `h3`, `i8`: `[''] '1. TERM' len=0` followed by `['1'] 'TERM'`).
26. `pages` is the file's `docProps/app.xml` value: the generated accepted/rejected twins report 3 pages for an 11-page contract.
27. A heading paragraph whose mark is a tracked deletion loses its heading status and is glued to the next paragraph without a space ("Deleted-mark headingBody following…"); this matches Word's accepted view, but the glued text is what the model quotes.
28. Under-declared zip members: an unreferenced 300 MB member declared as 1 byte is accepted in 35 ms (never read); an under-declared `document.xml` is refused by zipfile's CRC check with the generic "not a readable .docx package" (`g3c`). The 25 MB limit is inclusive (exactly 25 MiB accepted, +1 byte → 413).

### Claims in SYSTEM_TRUTH C/D now measured

| Claim | Status |
|---|---|
| `.docm` renamed `.docx` → generic 422 (UNPROVEN) | proven (`g4b`): 422 "not a readable .docx package" |
| Body-walk exceptions → 500 (UNPROVEN) | not reproduced: degenerate tables, missing styles, bad outline levels all 2xx |
| Empty DOCX → 422 same string (UNPROVEN) | proven (`g8`) |
| Archives that under-declare sizes (UNPROVEN) | unreferenced member accepted; referenced member refused by CRC (`g3b`, `g3c`) |
| Scanned PDF → 422 "no readable text" (UNPROVEN) | proven for all-image (`h3b`); a scanned page among text pages is silently empty (`h3`) |
| Empty PDF → "not a readable PDF"; blank pages → "no readable text" (UNPROVEN) | proven (`h6b`, `h6`) |
| All-caps footer/header is a heading on every page (UNPROVEN) | proven (`h2`), with colliding computed numbers |
| BOM stays as U+FEFF (UNPROVEN) | proven (`i1`) |
| 100,000-char first paragraph reaches the prompt whole through the heading (UNPROVEN) | proven (`f8`): heading = 100,000 chars; run did not end within 15 min |
| Moves and formatting revisions UNPROVEN / not counted | moves counted (`move_revisions=accepted(2)`) and read once at the destination; `rPrChange` not counted (`e2`) |
| Linked images and OLE UNPROVEN | linked image accepted, not fetched, not counted (`g7`) |
| Sections over 6,000 characters split "(part n)" | only at paragraph boundaries: one paragraph of 7,106 / 100,000 chars stays whole |
| Block-level content controls IGNORED and reported | ignored, but reported as `read` (defect 1) |
| Nested tables dropped | dropped, counted as read (defect 2) |
