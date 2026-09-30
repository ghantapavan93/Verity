# A stranger's document, end to end

The walkthrough in `docs/DEMO.md` uses the bundled sample, which is also the golden document. This
record answers a different question: does the path a stranger takes work on a file the workbench has
never seen, with nothing scripted? It was made on 2026-09-30 against the running product at commit
`192519d` (API on 8000, the interface's dev build on 3900, Ollama with `qwen3:8b`, the default
provider, prompt, reader and retrieval), driven through the browser like a person would, and every
number below was read back from the record afterwards, not from the screen.

`open app → upload a DOCX → see what was and was not read → ask, with guidance → answer → the exact
evidence → why the status → review the finding → refresh mid-run, reopen by URL → memo → evidence pack`

Nothing on the path was reused: the document, the guidance and the run were new rows (201, 201, 202),
the provider was Ollama, not the replay file, and no golden or corpus document was involved.

## The document

| | |
|---|---|
| File | `MTI-Reseller-Agreement.docx`, 47,778 bytes, sha256 `d510d1d71a7b6629636d424c8756dbf24a02808d8b93c97e9f6842bfcb097f5a` |
| Where it comes from | CUAD v1 (The Atticus Project, CC BY 4.0): the reseller agreement between McDATA Corporation and MTI Technology Corporation of 29 September 2004 (an SEC exhibit, 32,744 characters, 158 lines), rendered as one plain paragraph per line by `backend/experiments/demo_proof/make_fixture.py`. No heading styles, headers, footers, fields or tables were added. The script's output has every member byte-identical to the file above (`word/document.xml` sha256 `b63f7e82c92f67bb…`); the package hash differs because python-docx stamps zip members with the clock, which the script now pins, so its output hashes to `8961d52bc9c94838b06f189bcbbbc657b8828cea2c1897e6aade4bf34b4ee33c` on every machine |
| Why this one | not in CUAD-30, not in the SkillOpt set, not the golden document; never read by the workbench before; its notice clause writes the count in words and digits ("sixty (60) days"), which exercises the duration parser's agreement check |
| Why a generated DOCX | no real Word file on this machine was outside the measured sets, and fetching one is a download Pavan makes, not the agent. The text is the real contract; only the container is plain |

## What was recorded

| Step | Recorded |
|---|---|
| Upload | `POST /api/documents` 201, `reused: false`, document `7b8ed34fd627491c`, parse 109.5 ms, 1 page |
| Reader | v4 |
| Parse coverage | `schema_version 1`, `reader_version v4`, `source persisted`; `main_body` read; `style_hidden_text` unknown (the reader does not resolve styles); every other part absent. The paper says nothing was left unread, which is true of this file |
| Sections | 6: five of 5,686 to 5,993 characters and one of 3,329, labelled "EXHIBIT 10.102 (part 1)" to "(part 6)"; the paper says "Little structure was found in this file's text, so sections are approximate" (see observation 1) |
| Guidance | "We require at least 90 days' written notice for termination for convenience. Anything shorter needs review." (107 characters), `POST /api/guidance` 201, id `13e2b070fa084168`, sha256 `33f5a9af540d87e1…` |
| Question | "May either party terminate this agreement for convenience, and on what notice?" |
| Run | `POST /api/runs` 202, run `e5a20e2283e8416e`, fingerprint `f6f70f4429bf5382…`, task `guidance_comparison`, routing "no measured alternative for guidance_comparison; the default model" |
| Model and prompt | `qwen3:8b`, `answer-v2` (sha256 `9dbeb12a871ece17…`), options `{num_ctx 16384, retrieval_k 6, seed 42, temperature 0.0}` |
| Retrieval candidates | all six sections, in BM25 order `sec_0, sec_3, sec_1, sec_4, sec_2, sec_5` (k = 6 and the document has six sections, so retrieval had nothing to leave out; the order is its ranking). Stage `finding_evidence`: input `6c59fa0f89961a4c…`, output `5479c1222f03031f…`, 18.7 ms |
| Context slices | `sec_0` 0–5000 truncated `987ca9a5…`; `sec_3` 0–5000 truncated `adb96c4e…`; `sec_1` 0–5000 truncated `f7fc52f9…`; `sec_4` 0–5000 truncated `d23fd167…`; `sec_2` 0–5000 truncated `2d4c0360…`; `sec_5` 0–3329 whole `c50d3c5a…`. 28,329 of the 32,704 section characters reached the model; 4,375 (13%) did not (observation 2) |
| The exact model input | rebuilt from the record: `scripts/reconstruct_inputs.py e5a20e2283e8416e` → match, `answer-v2` match, 6 slices, 5 truncated; the checking stage's input hash `f5991f5897599598…`; system message 2,731 characters, user message 28,855 |
| Stages | reading 15.8 ms (in `d510d1d7…`, out `eb2a7646…`) → finding_evidence 18.7 ms → checking 68,995 ms ("model answered in 69 s", 6,743 tokens in, 196 out, in `f5991f58…`, out `7d4513de…`) → verifying 23.2 ms ("1 of 1 quote verified", out `a47cd5cc…`) → complete. Every row owned by `LAPTOP-HOST:28144:…`, the API process |
| The model's proposal (raw output) | one finding, topic "Termination for convenience", conclusion "Either party may terminate this agreement for convenience with 60 days' written notice.", `status_hint: "pass"`, evidence `sec_4` with the quote below, `observed` "60 days' written notice", `required` "at least 90 days", `suggested_position` "90 days' written notice" |
| SourceMatch | quote "4.1 TERMINATION WITHOUT CAUSE. Either party may terminate this Agreement without cause upon sixty (60) days prior written notice to the other party." was not in `sec_4` (part 5); found in `sec_0` (part 1) at characters 4136–4284, method `relocated:exact`, `match_count 1`, inside the 5,000-character window the model saw. The highlight in the paper is that text, character for character (read back from the `<mark>` element) |
| ObservedFact | 60 calendar days, parsed from the verified quote; "sixty" and "(60)" agree |
| PolicyEvaluation | rule from the guidance: at least 90 calendar days (a floor); 60 < 90 → `needs_review`, source `computed_days`, reason "the contract provides 60 calendar days; the guidance requires at least 90 calendar days". The model's hint was `pass` and was discarded: the drawer shows "Decided by code" with that sentence |
| Terminal state | `complete`, 1 of 1 span verified, 0 withheld, run wall 69.1 s |
| Refresh mid-run | the page was reloaded at the checking stage with the URL the run had already written (`?document=…&run=…`): it fetched `/detail`, `/runs/{id}`, `/guidance/{id}`, reattached to `/events`, showed "Checking against guidance", and ended with the same run. Reloading after completion, and opening the URL alone, both restore the run |
| Review | Findings → Confirm: `finding_reviews` row, `confirmed` by "Pavan" (the reviewer name this browser had stored) at 22:25:57Z; the run's review head moved from the empty head `e3b0c442…` to `a6dbd8e298d5d3c7…`; the confirmation was still there after a reload and on `GET /api/runs/{id}` |
| Memo | `POST /api/memos` 201, memo `f02e4f64a15e4a3f`, review head `a6dbd8e2…`; the HTML carries "Needs review", "Confirmed by Pavan on 30 September 2026", "relocated:exact · characters 4136–4284", the run id, model and prompt hash; the DOCX (sha256 `b7be01d360bd3745…`) carries `workbench_run_id`, `_run_fingerprint`, `_document_sha256`, `_guidance_sha256`, `_model`, `_prompt_version`, `_prompt_hash`, `_citations_verified "1 of 1"`, `_review_head`, `_link` in its custom properties |
| Evidence pack | `GET /api/runs/e5a20e2283e8416e/evidence-pack`, 74,705 bytes; `verify.py` with nothing but Python: document bytes PASS, canonical sections PASS, sections are what the run read PASS, the one span PASS, model input rebuilt to the recorded hash PASS, prompt hash PASS, six context slices PASS; "1 located span checked, 0 withheld, 0 beyond the model-seen slice, 0 failures". `run.json` names verifier v5 with its 5,000-character window and carries `parse_coverage` (persisted, v4) under `document` |

Nothing above worked because of something particular to the sample: the replay file was not
consulted, the ids are new, and the defaults were not touched.

## What the stranger's document exposed

Recorded before anything is changed; each is a candidate for a measured change, not a fix made here.

1. **Headings in a DOCX are recognised by style only.** A DOCX whose numbering is typed into ordinary
   paragraphs, which is what an SEC exhibit saved as Word looks like, has no heading styles and no outline
   levels, so the reader sees one long body and cuts it into 6,000-character parts. The paper says so
   ("sections are approximate"), the citation still verified, and the finding was right, but retrieval
   had nothing to choose between and the section labels carry no clause number. The same text uploaded
   as `.txt` sections under the line rules into 41 sections (one over 5,000 characters), with a quirk of
   its own: the address lines "380 INTERLOCKEN CRESCENT" and "BROOMFIELD, CO 80021" become sections
   "380" and "381". A DOCX reader that also applies the line rules to unstyled numbered paragraphs is a
   reader change, to be measured against the record like any other (`docs/PARSER-COMPARISON.md`).
2. **The section split is 6,000 characters; the prompt window is 5,000.** Every part between those two
   sizes loses its tail before the model sees it: here 4,375 of 32,704 characters, 13% of the contract,
   in five tails of 686 to 993 characters. The record is honest about it (the slices say `truncated`,
   the pack's `verify.py` would report a quote beyond the window), but the gap is structural: the split
   should not be larger than the window. Aligning the two is a reader or prompt change with a replay
   and a golden run behind it.
3. **The model cited the wrong part.** It attributed the quote to `sec_4` (part 5); the quote lives in
   `sec_0` (part 1). The verifier relocated it and recorded `relocated:exact` and the cited label
   (`citedSectionLabel` on the span), and the drawer shows the method; it does not say which section the
   model had named. Part of the "Why this answer?" mapping.
4. **The memo omits the policy sentence.** It carries observed, required, the status and the review, but
   not "the contract provides 60 calendar days; the guidance requires at least 90 calendar days", which
   is the one line that says why the status is what it is.
5. **A memo has no record endpoint.** `GET /api/memos/{id}` is 404; only `/html` and `/docx` exist. The
   memo's identity (run, review head, hashes) is readable from the DOCX properties and the run's
   `review_head`, not from the API.
6. **The model's hint was wrong and it did not matter.** Sixty days against a ninety-day floor, and the
   model wrote `pass`. The status on screen is `needs_review`, computed from the quote and the guidance,
   with the sentence that says so. This is the sentence a demo should end on.

## Reproducing this record

```bash
cd backend
.venv/Scripts/python experiments/demo_proof/make_fixture.py MTI-Reseller-Agreement.docx   # the same members; package sha256 8961d52b… (the proof's d510d1d7… carries the clock in its zip entries)
.venv/Scripts/python scripts/reconstruct_inputs.py e5a20e2283e8416e                      # the exact model input, against the recorded hash
curl -o pack.zip http://127.0.0.1:8000/api/runs/e5a20e2283e8416e/evidence-pack && python -c "import zipfile; zipfile.ZipFile('pack.zip').extractall('pack')" && python pack/verify.py
```

A second run of the same question with the same guidance on the same bytes returns run
`e5a20e2283e8416e` with `reused: true`; a different guidance or model is a different fingerprint and
a new run, and the record above cannot change: the run is finished and the database refuses updates.
