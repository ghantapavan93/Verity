# Batch extraction

One document through the workbench is a demonstration. A batch is the same pipeline over a
corpus: a field task (three questions a repository review asks of every contract) run against
every document, through the same `start_run` and `execute_run` the interface uses, with a bound
on how many runs are in flight, and a report computed from the run records. Nothing about how a
value is decided changes: a value is the first finding whose quoted passage code found in the
document, with its status and citation; a document the model could not answer from, or answered
with a quote that was not there, is recorded as not found or withheld, not filled in.

The task is `backend/app/batch/tasks/core-fields.json` (governing law and forum, termination,
liability cap). The runner is `backend/scripts/run_batch.py`. The record is `Batch` and
`BatchItem` in `backend/app/models.py`; the report is computed by `backend/app/batch/service.py`
and served by `GET /api/batches/{id}` (with `values.csv`). The Runs surface shows every batch,
its numbers and every value with its citation.

```bash
cd backend
.venv/Scripts/python scripts/run_batch.py --corpus ../../ivo-experiments/experiments/b1-word-structure/corpus --task core-fields --label b1-corpus
.venv/Scripts/python scripts/run_batch.py --corpus <dir> --task core-fields --concurrency 2
.venv/Scripts/python scripts/run_batch.py --report <batch_id>
```

## What is measured

| Number | How it is computed |
|---|---|
| documents/min, values/min | documents in the batch, and values answered with a verified citation, over the batch's wall time |
| model latency p50, p95, mean | over the runs the batch created (reused runs made no model call) |
| invalid output, provider errors | failed runs by reason |
| verified citation rate | verified spans over spans proposed, across the batch's runs |
| withheld rate | findings whose quotes did not verify, over findings |
| reuse | runs that began before the batch did (same document bytes, question, prompt, model and options); a corpus that lists the same bytes twice counts one document and one pair |
| retries | model calls that took a second attempt after a transport failure |

## The corpus

Twenty public contracts with licences that allow this use, the same corpus the killed B1
experiment was built on: eight Common Paper standard agreements (CC BY 4.0), eight UK
government templates from the Cabinet Office, the NHS special terms, the Lambert toolkit and the
Department for Education (Open Government Licence v3.0), the ICO's two international transfer
instruments and two Scottish Government model contracts (OGL v3.0). Twenty is what is licensed
and on disk; it is stated as twenty, not as a repository. A larger public corpus (SEC exhibits
as text) is the next step if the numbers on twenty justify it.

## Concurrency

Ollama serves one generation at a time by default, so concurrency above one pipelines only the
stages around the model call (read, retrieve, verify, persist) and queues the model calls.
The bound is a semaphore-sized thread pool in the runner; each worker has its own database
session; SQLite in WAL mode carries the concurrent writes. The report records the concurrency
used, so two batches of the same task can be compared.

## Results

**Recording 1, 2026-09-28: `core-fields` over the twenty public contracts, Qwen3 8B, prompt
answer-v2, concurrency 1, reader v4 (batch `ff81b6b33a804475`).**

| Number | Value |
|---|---|
| documents · values requested | 20 · 60 |
| runs created · reused | 60 · 0 |
| wall time | 57.1 min |
| documents/min · values/min | 0.35 · 0.82 |
| answered with a verified citation | 47 of 60 |
| not found (the model said the contract does not address it) | 9 |
| withheld (the quote was not in the document) | 4 |
| failed runs (invalid output, provider error, other) | 0 · 0 · 0 |
| retries of the model call | 0 |
| model latency p50 · p95 · mean | 44.3 s · 134.7 s · 57.0 s |
| findings · withheld findings | 128 · 11 |
| quoted spans · verified | 146 · 135 (92%) |

Reading the values table (`GET /api/batches/ff81b6b33a804475/values.csv`): every contract
returned a governing-law and a termination value except two (the Pilot Agreement and the
Mid-Tier charges schedule said "not found" for governing law; the NHS special terms had their
governing-law quote withheld), and the liability cap was "not found" on seven documents, most
of them plausibly right (the mutual NDA, the DPA addendum, the consolidated schedules, the ICO
addendum carry no cap of their own) and withheld on two. Three citations point at a schedule's
or cover page's text rather than a numbered clause, and the Model Services Contract's clause
numbers come out as `0.15.11`-style labels because its outline levels start below the visible
numbering; both are things a person sees in the citation and can judge, which is what the
citation is for.

What the number says about scale: one laptop GPU serving one 8B model answers a repository
question at about one value every 73 seconds, so a thousand contracts and three fields would
take about two and a half days on this machine; the pipeline's own overhead (parse, retrieve,
verify, persist) is under a second of that per value. Throughput is a model-serving question,
not a workbench question, and the numbers to compare against are recorded here so that a
faster model or a second GPU can be measured rather than assumed.
