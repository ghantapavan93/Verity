# Scale, as measured

Nothing here says millions. These are the numbers this machine produced, and what each next step
would have to earn.

## Measured

| What | Number | Where |
|---|---|---|
| Batch, 20 contracts × 3 fields, Qwen3 8B, one laptop GPU | 57 min, 0.82 values/min, 0 failures, model p50 44 s, p95 135 s | `docs/BATCH.md` |
| Pipeline overhead per value (read, retrieve, verify, persist) | under 1 s | `docs/BATCH.md` |
| Document of 2,001 sections on screen, production build | 1.6 s to paper, 35 ms per citation jump, 8,094 nodes | `docs/PERFORMANCE.md` |
| Lighthouse, production build | landing 100/100/100/100, workspace 99/100/100/100 | `docs/PERFORMANCE.md` |
| Document JSON on the wire | 55,971 bytes raw, 16,393 gzipped | `docs/PERFORMANCE.md` |
| Retrieval, per document | BM25 over a document's sections, in memory, milliseconds; hybrid adds one embedding call per section | `docs/RETRIEVAL.md` |
| Golden set, 44 questions | about 35 min per prompt version on this GPU | `docs/GOLDENS.md` |
| Record | 300 or so runs in SQLite (WAL), every read under 100 ms except the full run list at 1.4 s | API logs |

## Concurrency envelope, one process, one GPU (2026-09-29)

`backend/scripts/load_envelope.py` against a running API with the live model, each level on
distinct golden questions so no run is reused, the API on its own data directory. Queue is the
time from a run's creation to its checking stage, that is until the model was asked; model is
the provider's latency, which includes Ollama's own queue; verify is the verifying stage; memory
is the API process's peak working set.

| concurrent | level wall s | run wall s p50 / p95 | queue s p50 / p95 | model s p50 / p95 | verify ms p50 / p95 | failed | API peak MB |
|---|---|---|---|---|---|---|---|
| 1 | 20 | 20.3 / 20.3 | 0.0 / 0.0 | 19.9 / 19.9 | 13 / 13 | 0 | 110.3 |
| 5 | 202 | 104.6 / 201.9 | 0.1 / 0.2 | 104.4 / 200.8 | 10 / 13 | 0 | 118.4 |
| 10 | 377 | 172.2 / 377.2 | 0.2 / 0.4 | 171.6 / 376.5 | 13 / 35 | 0 | 128.3 |
| 20, first attempt | crashed: `QueuePool limit of size 5 overflow 10 reached` on twenty-four reads, 500s to the client | | | | | 20 | |
| 20, after the pool fix | 662 | 438.2 / 662.1 | 0.6 / 1.1 | 235.5 / 510.7 | 14 / 23 | 6 | 143.4 |
| 20, after the staleness fix | 830 | 455.4 / 807.0 | 0.6 / 0.9 | 232.1 / 527.0 | 17 / 41 | 0 | 144.9 |

What the two failures were, neither of them throughput. First, the request's session stayed open
until the background task ended, and a read after the commit had started a new transaction, so
every start pinned a pool connection for the length of its run; at twenty the pool of fifteen ran
dry. `create_run` now commits before it returns, and the twenty starts all went through. Second,
the six failures on the next attempt were live runs: at 660 s, the model timeout plus a minute,
staleness recovery declared them dead while they were still waiting in Ollama's queue, freed their
fingerprints, and their workers then hit the immutability trigger when the answer arrived. The
window is now four model timeouts plus a minute, the longest legitimate run (two validation rounds,
each with one transport retry). Both were found by the envelope, not by a report, and both have a
test.

What the table says about capacity: the API's own queue is under two seconds at twenty; every
second above that is the model, which serves one generation at a time, so the median question at
twenty waits seven to eight minutes and the slowest over thirteen, longer than the old staleness
window, which is why that window had to move. Verification and persistence stay in the tens of
milliseconds and memory grows by under 2 MB per concurrent run. Nothing here earns a
worker queue or a second process. The only lever is the model: a second GPU, or a smaller model,
and the smaller model measured worse on the golden set (`docs/ROUTING.md`).

## At ten times the load

The first bottleneck is model inference: one GPU serves one generation at a time, about 73 s per
value at the batch rate. A thousand contracts and three fields is about two and a half days here.
Nothing else in the pipeline is within an order of magnitude of that.

## What each next step would have to earn

| Step | Earned by |
|---|---|
| A worker queue | concurrent workload with restart durability across more than one process; today one process, staleness recovery, idempotent runs |
| Object storage for documents | more than one worker needing the same bytes; today one data directory, content-addressed |
| PostgreSQL | more than one writer, or more than one tenant; today WAL SQLite, one writer, measured to twenty concurrent runs in one process (above) |
| A persistent embedding index | retrieval across documents (repository search), not within one; today every retrieval is within one document, so corpus size does not touch it |
| A second GPU or a faster model | throughput; the only measured bottleneck |
| Virtualised document view | more than about 5,000 sections on screen; measured not needed at 2,001 |

Each of these is a measurement to make, not a box to tick.

## Admission to the model, measured (2026-09-29, 22:00 local)

`scripts/measure_admission.py --corpus data/cuad/corpus-30 --documents 3 --questions 4 --concurrency 2`: a batch runner
asking three fields over three CUAD contracts with two workers while a person asks four questions one after another,
all in one process through one admission controller with one call in flight, against the live Qwen3 8B; the same work
twice, once served first come first served and once as shipped (four interactive admissions per batch admission).
Record `data/logs/admission-20260929-221804.json`.

| Policy | Person's queue waits (s) | Person finished | Everything finished | Batch queue waits, max (s) |
|---|---|---|---|---|
| first come, first served | 95, 111, 120, 58 | 705 s | 735 s | 248 |
| four interactive per batch | 34, 32, 70, 59 | 534 s | 778 s | 324 |

The weighting halves what a person waits (median 103 s to 46 s, finished 24% sooner) and costs the batch six percent
on its total, with no call starved: the worst batch wait grew from 248 to 324 s and every call finished. That is the
measurement that earns the two queues; the first-come policy stays in the code for the next measurement and nothing
else. Every call's wait is on its checking stage ("model answered in 58 s · queued 111 s behind 2"), so the queue is
visible in the record, not inferred. What this does not do: cross processes. The API and a batch runner started as a
separate process each have their own controller and meet only at the model, which serialises them without a record;
a shared queue is earned by a requirement for that, not by this.
