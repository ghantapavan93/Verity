# Verity (Contract Workbench) UI sweep

Isolated instance: web `http://localhost:3910` (Next dev) → API `http://127.0.0.1:8010` (store `backend/data/explore`).
Playwright 1.63 headless Chromium, 1280×800 unless stated. Scripts `s1`–`s7*.mjs` and `lib.mjs` in this folder; every
observation is also in `results.jsonl`; screenshots in `shots/`. Model runs used: **7 of 8** (R1–R7 below), all on the
bundled sample (stored in this store as `CP01.docx`, id `ef1837cdca124da5`).

Caveats about the environment, since they shaped some timings:

- The "empty" store was not empty: 47 documents (CUAD batch texts, CP/UK corpus, fixtures from other sessions) and, during
  the sweep, other sessions' runs queued on the same GPU (`admission limit 1, 1 waiting`). My runs therefore took 104–466 s
  wall-clock for 71–183 s of model latency.
- The API on 8010 exited (code −1, no traceback) at 02:37 local while the guidance sweep ran; nothing in its log points to a
  request. I restarted it with the `api-explore` launch config and re-ran that script. The live API on 8000 was also absent at
  that moment; I did not touch it.

## 1. Landing, upload, Documents

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| Open `/` | Title "Contract Workbench"; H1 "What are you reviewing?"; composer; "Add contract"; three chips; "PDF, DOCX or TXT. Or try a sample agreement."; Recent (3) + All documents; "PG Pavan G." chip top-right | ok | 01-landing.png |
| Which API the build calls | Only `http://127.0.0.1:8010` | ok | — |
| Click each chip ("Review a contract", "Compare against guidance", "Ask about a clause") | All three just open the OS file picker; nothing distinguishes them (no preset question, no guidance popover) | medium | — |
| Type a question in the landing composer, press Enter | Opens the file picker; the typed text is kept and reappears in the Assistant composer after upload | note | 01b-landing-typed-enter.png, 02-upload-200char-name.png |
| Upload .txt with a 204-char name | Parsed, 6 sections. Title not truncated: overflows the document header and the Scope chip; the ⌘K hint is pushed off-screen | low | 02-upload-200char-name.png |
| Unicode name `Vertrag – Überprüfung 契約書 ☕.txt` | Shown verbatim everywhere | ok | 03-upload-unicode-name.png |
| `<b>x</b><img src=x onerror=alert(1)>.docx` with text bytes | 422 "the file is not a readable .docx package"; no HTML injected; no page error | ok | 04-upload-html-name-badbytes.png |
| `<b>x</b>.txt` | Literal name shown; no `<b>` rendered | ok | 04b-upload-html-name-txt.png |
| Two different files both named `duplicate.txt` | Two documents, two ids; Recent list shows "duplicate.txt duplicate.txt" with nothing to tell them apart | low | 05-…png, 07-landing-recent.png |
| Same bytes uploaded as `first-name.txt`, then as `second-name.txt` | POST 200 (reused). Workspace opens **`first-name.txt`** with "already in the workbench, opened as stored"; the name the user just chose is gone | medium | 06-same-bytes-second-name.png |
| `evil.exe` via the hidden input | 422 "unsupported file type .exe; upload .docx, .pdf or .txt" | ok | 09-upload-exe.png |
| 0-byte `empty.txt` | 422; message shown as alert | ok | 10-upload-empty.png |
| 26 MB `.txt` | 413 "file larger than 25 MB"; stays on landing | ok | 11-upload-26mb.png |
| "try a sample agreement" | Opens `CP01.docx` (not "Cloud Service Agreement (Common Paper).docx"): 11 pages, 123 sections, "2 parts not read", attribution line under the paper | note | 12-sample-open.png |
| Reload the sample | Attribution line gone (not in the record) | low | 12b-sample-reload.png |
| Documents view | 47 rows, name / pages / sections / uploaded / findings; no search, sort or filter; "Open now" marks the current one | note | 08-documents-view.png |
| Console during the sweep | Only the 4xx "Failed to load resource" lines from the rejected uploads; no page errors | ok | — |

## 2. Command palette

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| Ctrl+K on the landing / on Documents, Findings, Runs | Nothing opens (only works in the workspace with the Assistant shown) | note | — |
| Ctrl+K in the workspace; rail Search button; ⌘K chip in the Assistant | Dialog "Commands", input focused, placeholder "Type a command or a clause…". Unfiltered list is **capped at 40 rows**: 4 Ask, 1 Guidance, 4 Go to, 31 Jump to — 89 of the 120 numbered sections only appear by typing | note | 20-palette-open.png |
| Rail Search on the Documents view | Switches to the Assistant and opens the palette | ok | 26-… |
| `12.6` | 1 match: Jump to §12.6 · Assignment; Enter scrolls and lights the section | ok | 21-…, 25-… |
| `12` | 19 matches (every 12.x and 13.21 etc.) | ok | — |
| `liability`, `LIABILITY`, `   liability   ` | 5 matches (1 Ask + 4 headings); case- and whitespace-insensitive | ok | — |
| `limitation of liability` | 2 matches; all terms must appear in group+label+hint | ok | — |
| `Customer will pay` (body text), `indemnif` (prefix) | Body text: "Nothing matches". Prefix matches headings only (§9 Indemnification, §13.21) | see below | 22-palette-filter-bodytext.png |
| `Überprüfung`, `é`, `(`, `[`, `\`, `.*`, 500×`x` | "Nothing matches"; no crash (substring match, not regex) | ok | 23-palette-500chars.png |
| `go to`, `findings`, `inspect` (no run) | Group names match; with no run there are no "Inspect evidence" entries at all | note | — |
| Arrow keys | Move the active row (aria-activedescendant); clamp at both ends; End/Home do nothing | ok | — |
| Tab | Focus leaves the input to the `ul[role=listbox]`, dialog stays open — focus is not trapped | low | 24-palette-after-tab.png |
| Escape / click scrim / Ctrl+K again | Closes; focus lands on `body`, not back on the trigger | low | — |
| Enter on "Go to Findings" | Navigates (`?view=findings&document=…`) | ok | — |
| Ask group | Enter on any of the 4 suggestions **starts a model run immediately**, no confirmation | note | — |

What it is: a filter over commands, the four canned questions, and the numbered section headings ("Jump to"). What it is not:
a search over the contract text, over findings/evidence of past runs, or over documents. Typing a clause phrase that is not a
heading gives "Nothing matches". A first-time user who reads "Type a command or a clause…" will expect clause text search
and will be disappointed on the second try.

## 3. Guidance popover

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| Open "Add guidance" | Popover pre-filled with the demo rule (30 days' notice); textarea focused; popover background is translucent so the idle prompt bleeds through | low | 30-guidance-popover-default.png |
| Apply empty / whitespace | No request; popover closes; no chip | ok | 31-guidance-empty.png |
| Exactly 20,000 chars | POST 201; chip "Legal instructions" | ok | 32-guidance-20000.png |
| 20,001 chars | 422; raw pydantic text "String should have at most 20000 characters" appears under the suggestion list; popover stays open with the draft | medium | 34-guidance-20001.png |
| After the 422, apply valid unicode text | POST 201 and chip appears, **but the old 422 message stays on screen** (runError never cleared on success) | medium | 35-guidance-unicode.png |
| "Ignore previous instructions…" | Stored and used like any text (201); nothing in the UI distinguishes it | note | 36-guidance-injection.png |
| Remove (×), re-add the same text | Second POST is 200 (reused record) — same id, invisible to the user | ok | 37-guidance-readd.png |
| Switch document via Documents view | Chip "Legal instructions" **stays** on the new document; the hint said "Applies to every question in this scope" while the scope chip changed | medium | 38-guidance-other-document.png |
| Reload | Guidance gone (not in URL or storage) | note | 39-guidance-after-reload.png |
| Escape / Cancel | Closes; unapplied draft kept until reload | ok | — |

## 4. Asking (model runs R1–R7)

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| Empty / whitespace + Enter | Nothing sent; whitespace stays in the composer | ok | — |
| 5,000-char question | Sent; thread shows the 5,000-char bubble, composer cleared, 422 "String should have at most 2000 characters" rendered **below the fold** of the bubble; the text is lost (no restore to the composer) | medium | 42-question-5000chars.png |
| R1 "What is the limitation of liability?" (Enter) | 202; stages Reading (11 pages · 123 sections) → Finding (6 candidate sections) → Checking the contract; 104 s; 1 card "Answered", 3 verified passages; footer "qwen3:8b · prompt answer-v2 · 71 s" | ok | 40-R1-inflight-1.png, 41-R1-result.png |
| Same question via the Send button | POST 200 `reused: true`, same run id, footer prefixed "answered earlier for this exact question"; no model call. (Code: question is `strip()`ped but not case-folded, so a lower-case variant would be a new run.) | ok | 41-R1-again-result.png |
| R2 "Quote the exact wording of the limitation of liability clause in full" | Answered with 2 verified passages — **not withheld**. The conclusion itself says "The full clause is: 'Except as provided…General Cap Amount.'" — a one-sentence excerpt presented as the full clause, in prose the verifier does not check | high (see D2) | 41-R2-result.png |
| R3 "Is there a most favoured nation clause?" | Complete, 1 card "Not found", "Closest provisions read · 3 · none states the point" (§13.19 GDPR, §13.1, §12.11); no withheld proposal this time | ok | 41-R3-result.png |
| R4 "What is the cap on liability? [[fault:provider]]" | Plain text under the real provider: question shown verbatim, 2 verified passages, no failure | ok | 41-R4-result.png |
| R5 in flight: Send button | Disabled while a stage is live | ok | 43-R5-inflight.png |
| R5 in flight: **Enter** with another question | Not guarded: POST fires, the view switches to the other (reused) run, URL `run=` changes, R5 keeps running on the server with nothing on screen saying so | high (D1) | 44-R5-enter-while-inflight.png |
| Reload mid-run (`?run=R5`) | Reattaches: stage list resumes at "Checking the contract" with the question | ok | 45-R5-reload-midrun.png |
| Switch document mid-run | Follower stops (2 event streams aborted), idle prompt on the other document; no "a run is still in progress" notice anywhere | medium | 46-R5-switched-document.png |
| Return to `?run=R5` later | Followed to the end: "Not found", 3 closest provisions | ok | 47-R5-result.png |
| R6 guidance + "Review against instructions" | 466 s wall (183 s model) behind another session's run; the stage list showed "Checking against guidance" the whole time with no queue/ETA hint and no cancel; ended complete with 2 "Within guidance" findings | medium | 41-R6-result.png |
| R7 unicode question "Quelle est la limitation de responsabilité ? — 責任制限はありますか？ ☕" (guidance chip still attached from R6) | Question shown verbatim; "Checking against guidance" for >10 min, queued behind another session's run on a 100k-paragraph document (health: "1 waiting"), no queue hint, no cancel. Finished later: 1 finding "Limitation de responsabilité", 3 verified passages, chip **"Within guidance"** — for a liability question judged against a 30-day-notice rule (D3 again), model latency 84 s | medium (D5), high (D3) | 41-R7-result.png |
| Console/page errors | none | ok | — |

## 5. Results and evidence drawer

All on R1 (`64ad2bbcb92e44b8`, 1 finding, 3 verified spans), R2 and R3, restored through `?run=`.

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| Finding cards for R1 | 1 card = 1 API finding: topic, "Answered" chip, conclusion, "Evidence · 3 verified passages", three citation rows, View in document / Inspect evidence / Ask follow-up, "Generate review memo", footer line | ok | 50-R1-cards.png |
| Click each of the 3 citation rows | Each sets a `<mark>` whose text equals the stored quote (193 / 188 / 75 chars) and lights the section. On the first click the smooth scroll was still mid-way after 0.7 s (the paper is ~15 screens long), so the mark was not yet in view; rows 2 and 3 were in view. Not a defect, but long jumps take >1 s with no cue | note | 51-R1-citation-0.png, 51-R1-citation-1.png |
| "View in document" on every card (R1, R2, R3) | Jumps to the first located span; enabled whenever a span is located (also for R3's "searched" provisions) | ok | 52-R1-view-in-document-card2.png |
| Open the drawer | `aside[aria-label=Evidence]`, 360 px, focus moves to the Close button; sections Contract (3 quotes, each "Verified verbatim in the document text · exact"), Result (Observed, Result chip), Run (model, prompt hash, sources, latency, run id) | ok | 53-drawer-open.png |
| Section link inside the drawer | Jumps and highlights; drawer stays open | ok | — |
| "Why this answer?" | Loads `/explanation`: What was read / What retrieval chose (rank table) / What the model saw / What the model proposed / What code established (SourceMatch + PolicyEvaluation) / Reproduce this run; 2,055 px tall inside the 360 px drawer; "rebuilt input matches" | ok | 54-drawer-why.png |
| Hide toggle | Collapses; label returns to "Why this answer?" | ok | — |
| Escape | Closes; focus returns to the "Inspect evidence" button that opened it | ok | 55-drawer-closed-focus.png |
| Open from the palette, close with the X | Focus falls to `body` (no trigger to return to) | low | — |
| "Ask follow-up" | Focuses the composer; nothing is pre-filled, no thread context | note | — |
| R2 "Quote the exact wording … in full" | Not withheld: "Answered", 2 verified passages; the **conclusion** embeds a one-sentence quote and calls it "The full clause" | high (D2) | 56-R2-withheld.png |
| Withheld findings display | No run in this sweep produced a withheld proposal (R3 and R5 came back "Not found" with "Closest provisions read"), so `WithheldList` (struck-through quotes, "not found verbatim in …") was not exercised live; it is covered by `e2e/workbench.spec.ts` under replay | — | — |
| "No supporting passage found" | Not produced either: the API returned complete runs with a "Not found" finding and coverage citations; the `RunOutcome` unresolved body never appeared | note | 58-R3-unresolved.png |
| Retry ("Try again") | Only on failed runs; none failed under the real provider | — | — |

## 6. Findings view

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| Open `?view=findings` | "Findings with verified evidence · 17", lede with "17 findings awaiting review · 0 reviewed"; column heads Topic / Finding / Evidence / Status; grouped by document (CP01.docx, CUAD text, f9_2500_sections.docx, f1_hindi.docx, …). **No filter, sort or search**; the only input on the page is the reviewer-name field | note | 60-findings-view.png |
| Status chips | "Within guidance" on R6's two findings whose conclusions say the contract *does not provide* termination for convenience / a notice period; the record says "Status taken from the model's hint; no comparable day counts" | high (D3) | 60-findings-view.png, 73-run-record-top.png |
| Conclusion text | R4's finding reads "This is found in §49 and §50" — the model's internal labels `sec_49`/`sec_50` leaked as section numbers; the UI prints prose as-is | high (D4) | 60-findings-view.png |
| Confirm with no remembered reviewer | Inline form "Your name, asked once" (maxLength 80, required, focused) with Confirm / Cancel | ok | 61-findings-name-prompt.png |
| Empty name | Browser validation "Please fill out this field." | ok | — |
| Whitespace-only name | Trimmed to empty → submit silently does nothing; form stays, no message | low | 62-findings-whitespace-name.png |
| 200-char name | Silently cut at 80 by `maxLength`; stored and displayed as 80 N's, breaking the row | low | 63-findings-200char-name.png |
| `<script>alert(1)</script><b>bold</b>` | Stored verbatim by the API; rendered as text (React escaping); no page error | ok | 64-findings-script-name.png |
| Notes | No note field in the UI; the API accepts a 2,000-char note | note | — |
| Reload | Dismissal persists ("Dismissed by … · time · Undo") | ok | — |
| Open the dismissed finding (row click) | `openRun` → workspace, drawer open, mark highlighted, Result section shows "Reviewed · Dismissed by <name> · time" | ok | 65-findings-open-drawer.png |
| Undo | Returns to Review · Confirm · Dismiss (a `cleared` review is appended) | ok | — |

## 7. Runs view

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| `?view=runs` | "Every model run, as recorded · 13", citation record line ("30 of 30 quoted passages verified (24 exact, 4 normalized, 1 relocated:exact, 1 typed) · 0 of 17 findings withheld"), one row per run: question, document, model, prompt, latency, findings, "with guidance", time, outcome chip, id | ok | 70-runs-list.png |
| Two runs "Checking · in progress" | R7 (mine) and another session's run on `f8_100k_paragraph.docx`; R7 had been "checking" for 10+ minutes behind it (health: "admission limit 1, 1 waiting") — nothing on the list or in the workspace says *queued* | medium (D5) | 70-runs-list.png, 41-R7-result.png |
| Open R1's record | Facts (document sha, guidance none, model via ollama + routing reason, prompt hash, options, tokens 1077/319, citations 3 of 3, latency 71 s, started/finished), "Open in workspace", "Download evidence pack" | ok | 73-run-record-top.png |
| Stages timeline | Reading 02:41:51.653 → Finding +22 ms (6 candidates) → Checking +141 ms ("model answered in 71 s") → Verifying +70.9 s (3 of 3) → Complete | ok | — |
| Timing table | Parse at upload 73 ms, Load sections 22 ms, Retrieve 119 ms, Model call 71 s, Verify 20 ms | ok | — |
| Candidates table | 6 rows `sec_47 … sec_53` with §label · heading, rank order | ok | — |
| Findings on the record | Finding with chip, conclusion, status-source sentence, each span with "cited sec_49 · located exact · offsets 0–193" and the quote | ok | — |
| Raw model output | 1,369 chars of valid JSON in a `<pre>` | ok | 74-run-record-raw.png |
| "Why this answer?" section | Same explanation as the drawer, inline and un-collapsed | ok | 75-run-record-why.png |
| Evidence pack link (fetched with the page's `fetch`) | 200, `application/zip`, 155,550 bytes | ok | — |
| "Open in workspace" | Workspace with the card | ok | 76-open-in-workspace.png |
| Golden set on this store | Not empty: "answer-v2: 2 of 2 pass, mean model latency 112 s · by category: absence 2/2" (another session ran `run_goldens.py` here); set hash and sample hash shown | note | 71-runs-goldens.png |
| Batch extraction | "No batch recorded yet." | ok | — |
| Document families | Table: threshold 0.15, weights, closest pairs (CP01/CP08 0.66 …), label-set evaluation | ok | — |
| Before this product (experiments) | "Three ideas I tried to kill", B1 etc. with Expected / Kill rule / Observed, source commit 6ad9bd6 | ok | 72-runs-experiments.png |
| Run whose document is not in the store | Not reproducible: the API has no delete | — | — |

## 8. URL state

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| `?document=doesnotexist` | Landing with alert "document not found"; URL rewritten to `/` | ok | 80-url-bad-document.png |
| `?run=doesnotexist` | Landing with "run not found" | ok | 81-url-bad-run.png |
| `?run=R1` alone | Document and run restored, `document=` added | ok | — |
| `?run=` for the unresolved/not-found run (R3) | Restores the "Not found" card | ok | 82-url-unresolved-run.png |
| `?run=` for a failed run | No run failed under the real provider in this sweep (R4's fault marker is plain text); not exercised | — | — |
| `?view=findings` cold | Findings view; rail Assistant labelled "Assistant · add a contract"; clicking it goes to the landing and drops `view` | ok | 83-, 84-… |
| `?view=bogus&document=…` | Ignored, workspace opens | ok | — |
| `?run=R1&finding=<id>` | Drawer opens, passage highlighted and scrolled into view; `finding` is dropped from the URL immediately (link is one-shot) | note | 85-url-finding-deeplink.png |
| `?finding=nope` | Silently ignored | note | — |
| Back/Forward | All navigation uses `replaceState`; after landing → sample → Findings → Runs, Back leaves… nowhere useful: the URL changes to the previous session entry and the view does not change (`history.length` 10 from earlier navigations) | medium | 86-url-back.png |
| Two tabs on R1 | Review in tab 1; tab 2's open drawer is stale until it visits Findings and returns (by design). My automated check targeted the wrong row (see s7), so the re-read path is covered by the Findings→open-drawer test in §6 instead | note | 87-two-tabs-drawer.png |

## 9. Layout, themes, motion, focus, axe

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| 1280×800, 1024×700 | Split 62/38; no horizontal overflow | ok | 90-workspace-1280x800.png, 90-workspace-1024x700.png |
| 768×1024 | Still the split: 165-px composer, card text wraps every 3–4 words; works but cramped | low | 90-workspace-768x1024.png |
| 375×812 | "The document workspace needs a wider window. Documents, Findings and Runs still work at this size." (breakpoint 640); the lists work; no overflow | ok | 90-workspace-375x812.png, 91-runs-375x812.png |
| prefers-color-scheme light vs dark | Identical: dark only (`color-scheme: dark` in globals.css). No light theme | note | 93-scheme-light.png |
| prefers-reduced-motion | Palette and drawer appear at opacity 1 / no transform immediately; 0 elements animating | ok | 94-reduced-motion.png |
| 200 % zoom (640×400 CSS px, DPR 2) | Workspace hidden behind the "wider window" note; Findings view fine | note | 95-, 96-… |
| Console / page / network errors on landing, workspace, documents, findings, runs | None | ok | — |
| Tab order, landing | textarea → "Add contract" → arrow button (aria-label "Add a contract", a duplicate) → chips → sample → recent → All documents → body. The "Pavan G." chip is static | note | — |
| Tab order, workspace | rail (5) → document pane (tabIndex 0) → divider → ⌘K → Add guidance → 3 citation rows → View/Inspect/Ask → memo → composer; no skip link | note | 97-focus-workspace.png |
| Landmarks | 1 `nav`; **no `main`**, no `h1` on the workspace (only on the landing), content not in regions | low | — |
| axe wcag2a/aa/best-practice on landing, workspace, drawer, palette, findings, runs, documents | No serious/critical. Moderate only: `landmark-one-main`, `region`, `page-has-heading-one` (workspace, drawer) | note | axe.json |

## 10. Error states

| Tried | What happened | Verdict | Shot |
|---|---|---|---|
| GET /api/documents delayed 10 s on the landing | Landing renders without "Recent"; no indicator; list pops in later | low | 100-slow-documents-landing.png |
| …on the Documents view | Heading + lede and nothing else for 10 s: no spinner, no "loading", indistinguishable from an empty store | medium | 101-slow-documents-view.png |
| `?run=R1` with /detail delayed 10 s | The **landing** is shown (composer, chips, sample link) for 10 s, then it jumps to the workspace; a user could start a second upload meanwhile | medium | 102-slow-run-restore.png |
| POST /api/runs delayed 8 s | Previous answer disappears at once; "Reading contract" shimmer for 8 s; Send disabled | ok | 103-slow-post-run.png |
| GET /api/findings → 500 `{detail}` | Notice "database is locked" (the API's text); no empty state, no retry | ok | 104-findings-500.png |
| GET /api/runs refused | "The workbench API at http://127.0.0.1:8010 is not reachable." under the citation line; the other sections render normally | ok | 105-runs-unreachable.png |
| /api/health refused or `ok:false` | Landing: "Model offline: …" status line; sample link still offered; in the workspace nothing at all says the model is offline — the user finds out after sending a question | medium | 106-, 107-, 108-… |
| Upload while POST /api/documents refused | Alert "The workbench API at … is not reachable."; stays on landing | ok | 109-upload-api-down.png |
| Evidence pack for an unknown run | 404 | ok | — |
| 404 for run/document in the URL | see §8 | ok | — |

## Defects

Ranked. Repro steps are against the sample (`try a sample agreement`) unless stated. Screenshot names are in `shots/`.

**High — wrong information shown / broken flow**

- **D1 (high, broken flow)** Enter in the composer while a run is in flight starts/loads another run and silently abandons the one on screen. Repro: ask "What notice is needed to terminate for convenience?"; while "Checking the contract" is live, type "What is the limitation of liability?" and press Enter (the Send button is disabled, the textarea is not). The thread flips to the other answer, `?run=` changes, and the first run keeps running on the server with nothing on screen saying so (it reappears only under Runs). `AssistantPanel.tsx` guards `disabled={!!stageLabel}` on the button only; `onKeyDown` calls `onAsk` unguarded. Shots 43-R5-inflight.png → 44-R5-enter-while-inflight.png.
- **D2 (high)** A conclusion that quotes the contract is shown with the same weight as verified evidence. Repro: ask "Quote the exact wording of the limitation of liability clause in full". Result: "Answered", 2 verified passages, and the conclusion text "The full clause is: 'Except as provided in Section 8.4 … General Cap Amount.'" — one sentence of §8.1.1 presented as the full clause. The verifier checks `spans`, not prose, and the card does not distinguish the two. Shot 56-R2-withheld.png.
- **D3 (high)** "Within guidance" is asserted where code did not decide it. Repro: Add guidance (default 30-day rule) → "Review against instructions". Both findings ("The contract does not provide for termination for convenience", "does not specify a notice period") carry the chip "Within guidance"; the record says "Status taken from the model's hint; no comparable day counts". A reviewer reads a green compliance verdict for a point the policy could not evaluate. Shots 60-findings-view.png, 73-run-record-top.png (status-source line).
- **D4 (high)** Internal section labels leak into conclusions as section numbers. Repro: ask "What is the cap on liability? [[fault:provider]]" (or any cap question): conclusion ends "This is found in §49 and §50" — those are `sec_49`/`sec_50`; the contract has §8.1.1/§8.1.2. Shown verbatim in the card, the Findings table and the memo. Shot 60-findings-view.png (row "Liability Cap").

**Medium — confusing / unexpected**

- **D5** No queue, ETA or cancel while a run waits for the shared model. R6 showed "Checking against guidance" for 466 s (183 s of it model time); R7 sat in "checking" for >10 min behind another document while `/api/health` reported "1 waiting". The Runs list shows "Checking · in progress" with no start-relative time. Shots 41-R6-result.png, 41-R7-result.png, 70-runs-list.png.
- **D6** A rejected question is lost. Repro: paste a 2,001+ char question, Enter. The composer is cleared, the bubble is rendered in full, and the 422 text "String should have at most 2000 characters" appears below it (off-screen for a long bubble). No client-side limit or counter. Shot 42-question-5000chars.png.
- **D7** Stale error line. Repro: Add guidance → paste 20,001 chars → Use (422 shown under the suggestions) → Cancel → add valid guidance → Use. The chip appears but "String should have at most 20000 characters" stays until the document changes. `useGuidance.apply` calls `onError` on failure and never clears it. Shots 34-guidance-20001.png, 35-guidance-unicode.png, 36-guidance-injection.png.
- **D8** Guidance follows the user across documents. Repro: add guidance on the sample → Documents → open another contract. "Legal instructions" is still attached to the new scope; the popover hint says "Applies to every question in this scope". A reload drops it. Shots 38-guidance-other-document.png, 39-guidance-after-reload.png.
- **D9** Switching document mid-run silently drops the follower; nothing says a run is still in progress. Repro: ask, then Documents → open another; the Assistant is idle; the run finishes unseen. Shot 46-R5-switched-document.png.
- **D10** Re-upload of known bytes shows the old name. Repro: upload `first-name.txt`, then the same bytes as `second-name.txt`: workspace titled `first-name.txt` with "already in the workbench, opened as stored". Shot 06-same-bytes-second-name.png.
- **D11** Loading states are blank. Documents view with a slow list shows only the heading (looks empty); `?run=` with a slow `/detail` shows the full landing (composer, chips) for the duration, then jumps. Shots 101-slow-documents-view.png, 102-slow-run-restore.png.
- **D12** Browser Back does not undo in-app navigation (all `replaceState`); after landing → sample → Findings → Runs, Back changes the URL to the previous entry while the view stays. Shot 86-url-back.png.
- **D13** The three landing chips ("Review a contract", "Compare against guidance", "Ask about a clause") all do the same thing: open the file picker. Shot 01-landing.png.
- **D14** Palette placeholder "Type a command or a clause…" but body text never matches; the unfiltered list is capped at 40 so 89 of 120 sections are invisible until typed. Shots 20-palette-open.png, 22-palette-filter-bodytext.png.
- **D15** Model offline is announced only on the landing; in the workspace nothing changes and the user learns at send time. Shot 108-workspace-model-offline.png.

**Low — cosmetic**

- **D16** 200-char file name overflows the document header and the Scope chip and pushes the ⌘K hint off-screen. Shot 02-upload-200char-name.png.
- **D17** "⌘ K" glyph on Windows (rail tooltip says "Ctrl K"). Shot 06-same-bytes-second-name.png (top right).
- **D18** Guidance popover is translucent; the idle prompt bleeds through. Shot 30-guidance-popover-default.png.
- **D19** Tab inside the palette moves focus to the listbox and out of the dialog; Escape returns focus to `body`. Shot 24-palette-after-tab.png.
- **D20** Reviewer name: 200 chars silently cut at 80; whitespace-only submit does nothing. Shots 63-findings-200char-name.png, 62-findings-whitespace-name.png.
- **D21** No `main` landmark, no `h1` on the workspace, no skip link (axe moderate: landmark-one-main, region, page-has-heading-one); arrow send button labelled "Add a contract" beside "Add contract". axe.json.
- **D22** The sample opens as `CP01.docx` and its attribution line disappears on reload; Recent shows two identical "duplicate.txt" entries. Shots 12b-sample-reload.png, 07-landing-recent.png.
- **D23** 768-px tablet keeps the split: 165-px composer, 3-word lines. Shot 90-workspace-768x1024.png.

## What a first-time Ivo engineer would notice

1. Every "Answered" card looks the same whether the model's prose is backed by the quoted passages or not: only the citation rows are verified, and D2/D4 show the prose can be wrong (a partial quote called "the full clause", "§49 and §50"). The verifier's guarantee is narrower than the card implies.
2. "Within guidance" is a policy verdict, and the first guidance run shows it on two findings the policy could not evaluate (status taken from the model's hint). The one chip that matters most to a lawyer is the least trustworthy one.
3. Nothing withheld, nothing unresolved, nothing failed in seven real runs. The failure-state UI (struck-through withheld quotes, "No supporting passage found", "Try again") exists only in the replay e2e; the happy path is what a visitor sees.
4. A run is one question, one document, no thread: "Ask follow-up" just focuses the empty composer, and asking anything replaces the previous answer. Reviewers will expect at least the question history of the document.
5. Waiting is silent. A 2–8 minute "Checking the contract" with no queue position, no elapsed time, no cancel, on a single-admission GPU shared with batch scripts; and Enter during that wait quietly abandons the run (D1).
6. The palette is navigation, not search. It cannot find text in the contract, findings or documents; the placeholder promises clauses, and the Ask entries start model runs with no confirmation.
7. Guidance is a per-session chip, not a document setting: it persists across documents in the same session, vanishes on reload, is pre-filled with a demo rule, and surfaces raw pydantic errors.
8. The Findings table has no filters, no search, no notes, and the reviewer identity is a free-text name in localStorage (80 chars, anything goes) — fine for a demo, not for an audit trail; the avatar "PG Pavan G." is hard-coded.
9. The Runs page is the strongest surface: timeline, candidates, raw JSON, "Why this answer?", a 150 KB evidence pack that verifies offline. But it also exposes `sec_47` labels, sha256s and prompt hashes to the same user who sees the lawyer-facing card — two audiences on one rail.
10. Dark-only, 640-px cutoff ("needs a wider window"), no `main`/`h1`, `replaceState`-only URLs, and the sample opening as `CP01.docx`: the product is a well-instrumented engineering bench wearing a chat-app landing page.
