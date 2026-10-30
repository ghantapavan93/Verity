# The audit of 2026-10-02: the probes, as they were run

`DECISIONS.md` ("The zero-assumption audit of the published candidate") says what was found and what was changed.
These are the scripts behind its numbers. Each builds its own store in a temporary directory, or reads a snapshot
of the store made with SQLite's online backup; none writes to `backend/data`, and only `probe_context_overflow.py` calls the model (the others
that need one script it). They are probes, not tests: they print PASS, FAIL and INFO lines and are kept as they
were run. What they found that needed fixing is held by ordinary tests under `backend/tests/`.

Run from `backend/`:

```bash
.venv/Scripts/python experiments/final_audit/probe_memo_review.py       # memo crash-atomicity, review identity and concurrency, time and ordering
.venv/Scripts/python experiments/final_audit/probe_concurrency.py 7 11  # SQLite under 5 and 20 writers, a held write lock; the executor at 5, 20, 64, 80 runs; retries
.venv/Scripts/python experiments/final_audit/probe_concurrency.py 16    # list endpoints at 200, 500, 1,000 and 5,000 runs, with the SQL statements counted (ten minutes)
.venv/Scripts/python experiments/final_audit/probe_verifier_policy.py   # hostile quotes for the verifier, hostile clauses for the policy
.venv/Scripts/python experiments/final_audit/probe_content_pack.py      # markup and Unicode end to end, the evidence pack tampered, writes that fail
.venv/Scripts/python experiments/final_audit/chaos_journey.py           # one journey over real HTTP against a real server process, killed twice
.venv/Scripts/python experiments/final_audit/census_store.py            # the store on a snapshot: bytes, hashes, spans, memos; then the snapshot restored and used
.venv/Scripts/python experiments/final_audit/census_projections.py      # every complete run: run view, explanation and findings record compared
.venv/Scripts/python experiments/final_audit/replay_verifier.py         # every verified span looked for again by the verifier as it is now
.venv/Scripts/python scripts/reconstruct_inputs.py --all                # every recorded model input rebuilt and compared with its recorded hash
.venv/Scripts/python experiments/final_audit/probe_context_overflow.py  # what the model server does with a prompt larger than its window (one GPU call each way)
powershell -ExecutionPolicy Bypass -File experiments\final_audit\supervisor_longtail.ps1   # the supervisor on a second instance: port taken, kill, supervisor killed, stop file
```

`harness.py` is the isolated store and the scripted model the probes share; `chaos_app.py` is the application the
journey starts as a process. The hero case is the scripted model's default: it proposes "pass", cites the wrong
section and quotes the right words.

## What they printed on 2026-10-02

| Probe | Result |
|---|---|
| Memo atomicity (before the fix) | the move failed after the commit: 1 memo row with no file, retry 200, download 500 |
| Memo atomicity (after) | no row without its file; retry 201; recorded hash equals the bytes; 12 concurrent first requests, one memo |
| Review concurrency | A confirms and B dismisses at once: both rows kept, the higher id is the state; 8 identical decisions at once: 1 row |
| Time and ordering | latest by row id, not timestamp; an evening review was dated the next day in the memo (fixed) |
| SQLite, 5 and 20 writers | guidance, run starts, reviews, memos: none refused, none lost; a lock held 2 s: writers wait and succeed; held 8 s: 500 after 5 s, nothing written; reads never blocked |
| Executor and queue | 5, 20, 64, 80 distinct runs at admission limit 1: all complete, one model call each; 12 identical asks: 1 run, 1 call; an outage: 2 calls and a failed run |
| Query scale | Runs list 200 rows / 203 statements / 0.15 s at 5,000 runs; findings record 500 rows / 1,502 statements / 0.7 s; the document filter applies before the cap |
| Verifier, hostile | before: "the rapist" verified against "therapist", "un able" against "unable"; after (v6): 25 of 25 hostile cases refused or reported |
| Policy, hostile | before: "90 days unless … 10 days" and "120 days except … 5 days" were computed passes; after: needs review, ambiguous fact; 26 of 26 |
| Content | script, img, entities, RTL override, zero-width, emoji, astral and combining characters, a 5,000-letter word: offsets exact, memo HTML escaped, DOCX opens |
| Evidence pack | 3 MB document: 0.07 MB pack in 0.13 s; six kinds of edit rejected; an edited status or question is not detected (the pack is not signed) |
| Writes that fail | before: an upload whose bytes failed to write left a row with no file, and the retry reused it; after: no row, retry whole |
| Chaos journey | 25 of 25 steps ended in an honest state |
| Store census | 850 runs; integrity and foreign keys clean; 1,479 of 1,479 verified spans recover their quote at their offsets; 4 of 4 memos; 4 of 92 documents have no original bytes (historical) |
| Restore | the snapshot opened under the application in another directory: the proof run, its explanation, its rebuilt input, all memos; 31 packs from old and new runs verified |
| Cross-projection | 776 of 776 complete runs, 1,083 findings, no disagreement |
| Verifier replay | 7 of 1,479 verified spans (5 runs, none a golden) are not located by v6: the price of the rule |
| Reconstruction | 792 runs recorded an input hash and 792 rebuild to it; 58 recorded none (all before 2026-09-28 08:05 UTC) |
| Context window (`probe_context_overflow.py`, calls the model) | a prompt of 20,695 tokens with the answer at its start: by default the server evaluated 8,194 tokens and the model answered "30 days" where the text said 47; asked not to truncate, the server refused in 2 s with the exact counts |
| Supervisor | port taken: retried at 5, 10, 20, 40 s and up by itself when freed; killed server restarted; supervisor killed: its server keeps answering and is not restarted when it dies |

The deep links, the expired-session wording and the public headers were checked against the deployed build and the
public origin; those scripts name that deployment and are not kept here. `deploy/README.md` has what they found.
