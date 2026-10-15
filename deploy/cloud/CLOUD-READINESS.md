# Cloud readiness: Verity on one DigitalOcean VM and a Modal GPU

Prepared 2026-10-12 on branch `cloud-2`, from the production release `001b6a0`. Code candidate `fe030a8` (release gate
passed); the deployment kit and this report were corrected after the independent review, without code changes. Nothing
is deployed, no paid resource exists, production is unchanged. The runbook is `README.md` in this folder; this report is
what the owner needs before paying.

## 1. The deployment, and what does not change

```
visitor ── https ──> Caddy (TLS, Let's Encrypt) ──/api──> API: FastAPI, one uvicorn worker, SQLite (WAL) on the VM's disk
                         │                                  │  every answer: check the pinned build, then ask
                         └── everything else ──> interface: Next.js (next start)        ▼
                                                                Modal: Ollama 0.40.3, qwen3:8b 500a1f067a9f, one L4,
                     one DigitalOcean VM, Docker Compose            scale to zero, proxy-token auth
```

Unchanged from the workstation's public demo (`deploy/README.md`): the same code; anonymous sessions, each a `__Host-`
cookie signed with the gate's secret, the gate required; one workspace per browser, isolated by every route; the same
bounds (10 contracts and 30 questions per workspace, 200 questions a day for everyone, per-address limits, 25 MB per
upload, one model call at a time, 600 s per call); deletion of a workspace with everything in it seven days after the
first visit; the public store never the owner's (the API refuses to start on a store with owner records); BM25 with six
sections, answer-v2, temperature 0, seed 42, a 16,384-token window. The model proposes; deterministic code locates every
quote; nothing is answered by a build other than the pinned one. One VM, one process, SQLite: no new service, queue or
database.

What the cloud adds, and only this: Caddy for TLS; a liveness rule for the API container (the workstation supervisor's
three-probe rule); the model behind Modal's proxy token; no backups (section 8).

## 2. Implemented, tested, and still to test with money

| | State | Evidence |
|---|---|---|
| Compose stack (Caddy, interface, API) for the public demo | implemented, rehearsed | local Docker, isolated project, images of `fe030a8` |
| API image on the workstation's locked versions, with the backend suite inside it | passed | Linux, `fe030a8`: 1,274 passed, 22 skipped (Windows-only) |
| Release gate (fresh clone: backend, faults, interface, browser flows, exporter) | **passed** | `fe030a8`: 1,295 + 1 skipped, 514 named, 17/17 faults, 209 unit, 31 flows |
| `acceptance.mjs` (evidence and behaviour, two real questions) | passed | 82 of 82 each time, including after every volume was removed on the committed kit |
| Two visitors isolated; uploads, review, memos, SSE through Caddy, refresh mid-run, forged address, oversized and false uploads, cross-origin write | passed | 19 of 19 |
| Failures: restart mid-run, model down, wrong build, frozen API, stop and start, pause switch | passed | 7 of 7; frozen API back in 145 s |
| Retention on the VM: database, WAL, SQLite temporary files, originals, memos, `/tmp`, logs | passed | marker gone from every file and log after the purge; SQLite temporaries shown in `/tmp` |
| Memory: nine visitors at once / four 25 MB uploads at once | passed | 731 MiB / 1.29 GiB, no error |
| Modal app | checked against Modal's docs and SDK 1.6.1, imports cleanly; **not deployed** | needs the owner's approval to spend |
| Cold start, the 150 s redirect, latency on an L4 | tested against a local emulation only | **paid test S0** |
| The cloud model answering like the workstation's | **not tested** | **paid test S0**; no claim before it |
| Public DNS, Let's Encrypt, a phone on the real hostname, a new droplet, a Docker daemon restart | not tested | **staging S1** |

Fixed while preparing this, each with a test that failed before the fix, or a probe: the kit ran invite-only; the
image's versions had drifted from every tested environment, and the gate itself tested newer ones than the workstation
runs; a hung API would have stayed hung; the first question after the GPU slept would have failed its 5 s build check;
an answer past Modal's 150 s limit would have failed on the redirect; the lock file had again lost two packages a Linux
build needs; questions asked together exhausted the database pool (every other request waited 30 s, a run failed); a
long ingest made uploads beside it fail on the lock; a memo draft could outlive a killed process; a SQL error could
carry a contract's words into the log; SQLite's temporary files would have been written to the container's disk; a swap
file would have let an upload reach the disk.

## 3. The VM

**DigitalOcean Basic droplet, Regular, 4 GB RAM / 2 vCPU / 80 GB SSD / 4 TB transfer: $24.00 a month.** Ubuntu 24.04
LTS x64, IPv4 only. Region **SFO3** if most visitors are on the US west coast, **NYC3** otherwise (the model's latency
dominates either way). Storage: the droplet's own disk; no Block Storage volume. **Backups off, no snapshots, no swap**
(section 8). Monitoring on (free; system metrics only).

Why 4 GB and not 2: the privacy design rules out swap, so memory is the hard limit. Measured on the final images: idle,
the three containers use 145 MiB; nine visitors at once (contracts of 1.9–25 MB, three questions queued, twenty extra
event streams) peaked at 731 MiB; four 25 MB uploads at once peaked at 1.29 GiB, the API at 1.20 GiB (about 260 MiB for
each large upload in progress, SQLite's temporary files now in memory among it). With Ubuntu and Docker (roughly 0.4 GB),
that stress case would leave a 2 GB machine (1.9 GiB usable) almost nothing, and one more large upload would end in the
kernel killing the API. 4 GB holds the stress case with about 2 GB to spare, and the second vCPU keeps pages and
event streams responsive while uploads are read. Upload times under load varied three- to twelvefold between runs on the
shared workstation (the 25 MB file from 3.9 s to 46 s), so they are indicative and S1 measures them on the droplet. The $12
plan (2 GB / 1 vCPU) runs ordinary use, and would restart the API under a burst of large uploads; it is not recommended.
Disk: images 1.8 GB (keep two releases: 3.6 GB), logs at most 90 MB, the store about 2.3 times the text visitors upload,
all of it deleted after seven days; uploads stop on their own below 2 GiB free.

## 4. The model

**Modal, one NVIDIA L4 (24 GB), Ollama 0.40.3 (the workstation's version; Ollama's own image, pinned by digest
`sha256:adca95a1…`), qwen3:8b at Ollama digest `500a1f067a9f` (Q4_K_M), baked into the image; checked by the API before
every answer.** Limits in `modal_ollama.py`: at most one container; scaled to zero 60 s after the last request; 2 cores and
8 GiB; 600 s per request (the API's own limit per model call, which once Modal redirects a long call only this bound
enforces); one generation at a time (`OLLAMA_NUM_PARALLEL=1`); proxy-token authentication.

Cost (Modal's price list, 2026-10-12): L4 $0.000222/s, plus $0.0000131/s per core and $0.00000222/s per GiB, about
**$0.96 an hour while a container is up**, billed by the second including start-up and the 60 s idle tail. A question is
up to four model calls; on the workstation one took 17–75 s of model time. Estimate: about $0.02 a question when the GPU
is already warm, $0.04–0.07 when it starts cold. A month at 10 questions a day: about $6–21; at 50: $30–105. The 200-a-day
ceiling would allow $190–420, so the **Modal workspace budget is the bound: set $50 a month** (Modal stops new work at
the limit). The Starter plan's $30 monthly credit covers light use. These are estimates; S0 measures them.

## 5. Secrets and credentials (the owner keeps each one)

| Secret | Where it lives | Made by |
|---|---|---|
| `WORKBENCH_ACCESS_SECRET` (48 random bytes) | `/opt/verity/.env` (chmod 600) and the owner's password manager | the line in `env.example`, on the VM |
| Modal proxy token (`Modal-Key`, `Modal-Secret`) | `.env` as `WORKBENCH_OLLAMA_HEADERS`, and the password manager | Modal dashboard or `modal workspace proxy-tokens create` |
| Modal CLI token | the owner's machine only (already made: the workstation's CLI is authenticated) | `modal setup` |
| DigitalOcean login (with 2FA) and the SSH private key | the owner's machine and password manager | DigitalOcean; `ssh-keygen` |
| Cloudflare login | as today | — |

Nothing else: no database password, no API key, no third-party service. The secret never enters an image, the
repository or a log. A leaked proxy token lets anyone spend the GPU up to the budget, and reach Ollama's own management
calls (the pinned digest still decides which build answers): revoke it in Modal, make a new one, put it in `.env`,
`docker compose up -d api`. A leaked access secret lets anyone mint sessions: replace it the same way (every visitor gets
a new session).

## 6. What only the owner can do (or approve, step by step)

1. Modal (the account exists, the CLI is authenticated): approve a **workspace budget of $50/month**; approve creating
   the proxy token (its secret goes straight into a local file, never into chat); approve `modal deploy
   deploy/cloud/modal_ollama.py` (creates the paid resource; the image build itself runs on Modal's builders); approve S0's
   GPU time (estimated under $10).
2. DigitalOcean: create the account with 2FA; add a payment method; set a **billing alert at $30**; upload the SSH public
   key; create the droplet exactly as section 3 says, **backups unticked**; note its IPv4.
3. Cloudflare: add the staging A record (section 7). Later, the production switch (section 10).
4. Decide the wording of `WORKBENCH_MODEL_HOST` (shown wherever the interface says where a contract's text goes; suggested:
   "Modal"; modal_ollama.py pins no GPU region, so name none) and whether to keep 200 questions a day.
5. Approve, in turn: S0 (model only), the staging deployment S1, the production switch S2, and later retiring the
   workstation's tunnel.

## 7. DNS, TLS and sessions

Staging: `verity-staging.<your domain>` A record to the droplet's IPv4, **DNS only (grey cloud)**, no AAAA. Caddy
obtains the certificate (first against Let's Encrypt's staging CA, then production, as the runbook says) and serves
HTTP/1.1 and HTTP/2. Not Cloudflare's proxy: the API's per-address limits would all see Cloudflare's edge, and the proxy
cuts a response at 125 s. `.env` names the hostname in `VERITY_SITE` and the same `https://` origin in
`WORKBENCH_APP_URL` and `WORKBENCH_CORS_ORIGINS`; sessions and writes from any other origin are refused. Sessions: a
browser without one is given one on arrival (`POST /api/access/visit`), a `__Host-` cookie, Secure, HttpOnly,
SameSite=Strict, signed with the secret, seven days. The VM's store starts empty; nothing is migrated.

## 8. Backups, retention and recovery

**No backups and no snapshots of the store.** A copy of the public store holds visitors' contracts; to keep the promise
on the first screen it would have to be deleted before the earliest workspace in it ends, which can be minutes after it
is taken. The store holds nothing older than seven days by design, so what must survive is the deployment, not the data:
images (rebuilt from the commit; keep the last two archives), `compose.yml`, `Caddyfile`, the frozen /state record
(from ivo-experiments, sha256 `cff26179…`), and `.env` (the password manager). Losing the VM loses at most seven days of
visitors' workspaces, which their first screen already says will go. Where every copy of a contract's words can be, on
the VM and at the model host, and what removes it, is the table in README ("What the disk keeps"); the rehearsal checked
each place on the VM. On Modal: the question, any guidance, the contract's file name and the question's sections are sent
with each call; Ollama
does not log request bodies; a call still running at 150 s has its result held by Modal for a later fetch, for a time
Modal does not document.

Recovery, rehearsed: a container that exits restarts; an API that stops answering is killed after three failed probes
and restarted by its policy (frozen in the rehearsal: back in 145 s); a run cut by a restart ends failed (one created in
the instant before the restart, before its first stage row, names no process: it stays `reading` until staleness fails
it on a read 41 minutes later; war room F-25, not rehearsed);
stopping and starting every container keeps the store; losing the VM is a rebuild from the runbook (rehearsed on the
same machine with the images loaded, on the committed kit: every volume removed, healthy again in 10 s, the store empty,
`acceptance.mjs` 82 of 82). Not rehearsed: a Docker daemon restart and a new droplet; on a new droplet add provisioning and copying, about
30 minutes by hand.

## 9. Acceptance gates and stop conditions

**S0, the model alone (after `modal deploy`, before any VM), run from the workstation against the Modal URL**, with a
sandbox API in its own data directory and `WORKBENCH_OLLAMA_URL`, `WORKBENCH_OLLAMA_HEADERS`, `WORKBENCH_MODEL_DIGEST`
set:

1. Provenance: `/api/tags` names qwen3:8b with a digest starting `500a1f067a9f`; `/api/version` says 0.40.3; each run
   records answer-v2, its prompt hash, temperature 0, seed 42, window 16,384.
2. Cold start: after 5 minutes idle, time the first build check and the first answer; then three answers warm.
3. The 44 goldens (`backend/scripts/run_goldens.py --prompt answer-v2`): the workstation's answer-v2 passed 37 of 44 in
   two recordings with the same seven failures (g08, g11, g12, g26, g30, g35, g42; docs/GOLDENS.md). The judge checks
   each run's stage, statuses and cited sections, not the answer's words (docs/GOLDENS.md, rule 4).
4. The 15 frozen false-premise controls (the CUAD pair and six held-out texts, frozen by hash; the workstation's
   answer-v2: 3 of 7 negatives, 6 of 8 positives), scored by the same code.
5. The wrong-party record: the /break headline question and the nine wrong-party questions of the rejected fix, twice
   each; reported answer by answer against the recorded sessions, not scored.
6. Citations: the share of quotes located, by method, against the workstation's rate on the same runs.
7. Latency p50/p95 per model call, any call past 150 s (the redirect path), no call reaching 600 s.

Stop if: the digest or version differs; any 401/403/5xx from the endpoint; a golden that passes on the workstation fails
(a "flip"; two workstation recordings showed none), or the goldens pass fewer than 37; a control result differs from the
workstation's; any run fails on a timeout or the redirect; the cold start exceeds 180 s; S0's own cost exceeds $10.
"The cloud answers like the workstation" is said only with zero flips; otherwise every flip is reported, run by run.

**S1, staging (the VM, the staging hostname, the Modal endpoint).** The image's `test` stage and the release gate pass
on the commit being deployed; then on the staging origin: `acceptance.mjs` with `SHA` set (all checks OK, exit 0);
`curl -sI` shows HSTS and `frame-ancestors`, and no `Server` or `X-Powered-By`; two browsers isolated (each sees only its
own documents; a run id from one is 404 in the other); a 28 MB upload refused with 413;
`docker compose exec api touch /data/public.paused` refuses an upload with 503, removing it restores; the retention probe
(a marker contract, its workspace ended, the purge, the marker in no file or log); a phone on the real hostname;
`swapon --show` empty and `sshd -T` showing no password login; a reboot of the droplet with the stack back on its own;
24–72 hours of monitoring with no container restart that is not explained. Stop on any failed check, any 5xx in the
logs, memory above 75% or a restart loop.

**S2, production.** S1 passed; the switch in section 10; `acceptance.mjs` against the production origin; the workstation's
stack left running for 72 hours as the way back.

## 10. Migration and rollback

1. S0: with the owner's approvals, the Modal app is deployed and the model acceptance runs from the workstation.
   Production is untouched.
2. The owner creates the droplet; it is hardened by the runbook; images, `compose.yml`, `Caddyfile`, the record and `.env`
   (staging origin) go to `/opt/verity`; Let's Encrypt staging first, then production; the staging A record.
3. S1 on staging, then a soak of one to three days while the workstation keeps serving `ivo.pavankg.dev`.
4. Production switch, in a quiet hour: set `.env` to `https://ivo.pavankg.dev` (`VERITY_SITE`, `WORKBENCH_APP_URL`,
   `WORKBENCH_CORS_ORIGINS`); in Cloudflare, replace the hostname's tunnel record with an A record to the droplet, DNS
   only; `docker compose up -d` (Caddy obtains the certificate within a minute of the name resolving). Visitors arrive at
   an empty store with new sessions; nothing is copied from the workstation.
5. Rollback: put the tunnel record back in Cloudflare. The workstation's stack has kept running, so the site is back as
   soon as DNS answers (minutes). A bad release on the VM: the previous images (README, rollback).
6. After the soak: retiring the tunnel and the workstation's public stack is a separate decision. Its store keeps
   nothing past seven days; the four backup copies identified on 2026-10-12 remain the owner's to delete as already
   planned.

## 11. Blockers, risks, and the independent review

**Release gate:** passed on `fe030a8` (fresh clone; the backend environment from `requirements.lock` for the first time):
1,295 passed, 1 skipped; named suites 514; ruff, mypy, import contracts; 17 of 17 planted trust faults caught; 209
interface unit tests; production build; 31 browser flows; the evidence exporter unchanged.

**Independent review (infrastructure, security, reliability; a fresh agent that could reject): APPROVE WITH FIXES on
the first pass, APPROVE on `e1cf0ef` after the fixes** (its last three points, wording about a timing, the kit a run
used and how far upload times are indicative, are corrected here). No
security hole found: signed sessions, origin checks, per-address limits behind Caddy, non-root containers, secrets kept
out of images and logs, and the no-backup design were each verified. Its blocker (this report was not committed) and its
fixes are done: SQLite's temporary files moved to memory (`TMPDIR=/tmp`, shown by a probe); the README's claims narrowed
to what the evidence shows and every rehearsal step re-run on the final images with its output kept; what Modal keeps
stated; `VERITY_SITE` in `.env`; Modal's request timeout set to the API's 600 s; core dumps off, capabilities dropped,
`no-new-privileges`; HTTP/3 not advertised; `X-Powered-By` removed; `frame-ancestors 'none'`; Ollama installed from its
own image pinned by digest instead of a script; `.env*` kept out of the build context; four 25 MB uploads at once
measured (which moved the recommendation from 2 GB to 4 GB).

**No blocker remains for the owner's step 1 (S0).** Risks that remain by design or until a paid test:

- The cloud model's answers are unmeasured: same weights, another GPU; llama.cpp does not promise identical logits
  across hardware. S0 decides; until then the workstation remains the reference.
- The Modal image change (Ollama's own image instead of the install script) and the 150 s redirect are first exercised
  by `modal deploy` and S0.
- The first question after the GPU sleeps waits for a container (estimated one to two minutes); the interface shows the
  run in progress meanwhile.
- One VM is one point of failure, and its store is not backed up: a lost VM is a rebuild and an empty store.
- Cost is bounded by the Modal budget, not by the daily ceiling alone.
- A misconfiguration that would weaken the design: Cloudflare's proxy turned on, an AAAA record, a swap file,
  DigitalOcean backups ticked, or a second API process. Each is named in the runbook.
