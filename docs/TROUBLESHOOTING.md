# Troubleshooting

What to look at when the public workbench misbehaves, in the order an operator would look. Every log line named here is
written by code in this repository; each section names where.

## First look

```
cd backend
.venv/Scripts/python scripts/status.py --data-dir <the public store> --public
```

One line each for the API, the model, the disk, the day's runs, the tunnel and the two supervisors, `ok` or `PROBLEM`;
the exit code is 1 when any line is a problem. It changes nothing: the store is opened read-only and each log is read
once from its end.

**Never hold a live log open.** On 2026-10-11 a `tail -F` on `api.supervisor.log` held the file without write sharing,
the supervisor's next line failed, and the API stayed down for 17 minutes. Read a log once
(`Get-Content <file> -Tail 50`), and read it again to see more.

## Where things are written

All under `backend/data/logs/deploy` on the machine that serves the site.

| File | Written by | What its lines say |
|---|---|---|
| `api.supervisor.log`, `web.supervisor.log` | `deploy/supervise.ps1` | each start; each exit with its code and run time, and the last line the server wrote to its error output; missed health probes and `answering again`; a supervisor that ended without a record (Windows shut down or signed out) with the machine's boot time; old output removed |
| `api.<stamp>.err.log` | the API (`app/main.py`, Python logging) | one line per request (`request_id`, `path`, `status`, `duration_ms`; the health probe is left out); `refused path=… status=… kind=… detail=…` for every 429 and 503, the upload door's included (`kind=SpoolFull`, `kind=UploadsPerNetwork`, the quota's class); a `status=500` request line for an unhandled error, its traceback beside it; a run's stages (`run_id=… stage=… reason=…`); the model's time apart from the queue's (`model_ms=… queue_ms=… queue_depth=…`); `model_build server_version=… model=… build=…` at start; `recovered_runs=…` |
| `api.<stamp>.out.log` | uvicorn | nothing in normal running: its access log is off (the request line above replaces it) |
| `web.<stamp>.*.log` | `next start` | the interface server's own output |

A start's two output files are removed after 14 days; the supervisor logs are kept.

## Symptoms

| What is seen | Look at | What it means, and what to do |
|---|---|---|
| The site answers 502, or the page says the API is not reachable | `status.py` `api` and `tunnel`; the last lines of `api.supervisor.log` | `exited api … code … (0x40010004: ended by Windows at shutdown or sign-out)`: the machine went down; supervision restarts at the next sign-in. `the previous supervisor ended without a record`: the same, said on the next start. No line since the machine started: the supervision task did not run (`deploy/install-supervision.ps1`; the machine must be signed in). `tunnel PROBLEM`: the cloudflared service is stopped. |
| `api … did not answer … (n of 3)` in the supervisor log | the time of the line | A health probe waits 10 s; three misses in a row restart the API. One miss while the machine is busy (a test suite or a build on the same machine, 2026-10-19 20:36) is load, not a fault; `answering again` follows. |
| Uploads and questions refused: "The demo's disk is nearly full" | `status.py` `disk` | Free space fell below the public floor (2 GiB, `WORKBENCH_PUBLIC_MIN_FREE_BYTES`). Health reports `fault: store` at the same floor. Free space; reading keeps working meanwhile. |
| Visitors told "8 visitors' questions are being answered, the most this demo queues" (503) | `refused … kind=Busy` lines; `queue_ms` on run lines | The model answers one call at a time; past `WORKBENCH_PUBLIC_MAX_RUNS_IN_FLIGHT` (8) a question is refused at once rather than queued for half an hour. If `model_ms` has grown, the model is slow (another program on the GPU, heat): fix that before raising the bound. |
| "This demo workspace has N questions being answered" (429) | `refused … kind=TooManyRequests` | One visitor's bound (`WORKBENCH_ANONYMOUS_MAX_RUNS_IN_FLIGHT`, 2). Working as intended. |
| "Today's run budget … is spent" (429) | `status.py` `runs` | `WORKBENCH_MAX_RUNS_PER_DAY` (200 on the public site) reached; it resets at midnight UTC. |
| A run sits at "Checking" | `status.py` `runs` and `model` | `without progress for over 15 min`: look for `model call failed` lines and whether Ollama answers. Recovery marks such a run failed (`recovered_as=failed`) once it has made no progress for four model timeouts and a minute, on the next read of runs or the next start. |
| The page says questions asked earlier are still being answered | nothing | The run is waiting for the model; the count falls as answers arrive (`RunOut.ahead`, read at every poll and stream heartbeat). |
| A run ended without an answer | the run's last `stage=` line: `reason=…` | `citations_unverified`: the passages the model cited could not be matched verbatim to the document; `insufficient_evidence`: the model found no passage that answers it in the sections it was given, or answered without quoting one; `invalid_output`: the model's output did not parse after a retry; `provider_error`: the model could not be reached; `internal_error`: the process stopped mid-run. |
| Answers changed and the code did not | the `model_build` line of each start; Ollama's `upgrade.log` and `server.log` in `%LOCALAPPDATA%\Ollama\` | Ollama updates itself, and a pull replaces a tag: a different `server_version` or `build` changes answers. So does the model server's prompt cache, with neither changed: the same input computed from another start point (`cached n_tokens` on its `new prompt` line in Ollama's `server.log`) can answer differently (`docs/CASEBOOK.md`, case 6). Pin the build with `WORKBENCH_MODEL_DIGEST`. The cache path is closed only while Ollama runs with `LLAMA_ARG_CACHE_RAM=0`: `status.py`'s `cache` line says whether its last model load had the cache off. |
| The page polls instead of streaming | nothing | The event stream dropped on its way through the tunnel; the page falls back to polling, every 3 s while the run moves, slowing to 12 s while it does not, and not at all while the tab is hidden. |

## What is deliberately not here

No metrics service, dashboards or log shipping: one machine, one process and one model, and the lines above answer
every question the audit of 2026-10-19 asked. Add one when a question comes up that a line cannot answer.
