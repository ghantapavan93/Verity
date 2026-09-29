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

## At ten times the load

The first bottleneck is model inference: one GPU serves one generation at a time, about 73 s per
value at the batch rate. A thousand contracts and three fields is about two and a half days here.
Nothing else in the pipeline is within an order of magnitude of that.

## What each next step would have to earn

| Step | Earned by |
|---|---|
| A worker queue | concurrent workload with restart durability across more than one process; today one process, staleness recovery, idempotent runs |
| Object storage for documents | more than one worker needing the same bytes; today one data directory, content-addressed |
| PostgreSQL | more than one writer, or more than one tenant; today WAL SQLite, one writer, measured at concurrency 1 |
| A persistent embedding index | retrieval across documents (repository search), not within one; today every retrieval is within one document, so corpus size does not touch it |
| A second GPU or a faster model | throughput; the only measured bottleneck |
| Virtualised document view | more than about 5,000 sections on screen; measured not needed at 2,001 |

Each of these is a measurement to make, not a box to tick.
