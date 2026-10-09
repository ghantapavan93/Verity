# Verity in the cloud: one VM, a serverless GPU, a static evidence page

This replaces nothing in `deploy/` (the workstation and tunnel setup); it is the laptop-independent layout. Nothing here
has been deployed. Every step that creates a resource, spends money, changes DNS or changes who can enter is the owner's
to take.

## Layout

| Piece | Where | Why this and not more |
|---|---|---|
| Public evidence (`/state`) | Static files on Cloudflare Pages (`backend/scripts/export_state.py --build`) | No server, store or model; open to anyone; survives every outage below |
| Live workbench | One Linux VM (DigitalOcean Basic 2 GB, $12/month) running `compose.yml`: Caddy, the interface, the API | SQLite needs a local disk and one process; one VM is the simplest thing that gives both, with no cold start and documented SSE behaviour |
| Model | Ollama on a Modal L4, scale to zero (`modal_ollama.py`) | The only way found to serve the exact reference build (qwen3:8b, Ollama digest 500a1f067a9f, Q4_K_M); no managed provider serves those weights |
| Storage | SQLite (WAL) and the original uploads on the VM's disk, in the `verity-data` volume | Measured traffic is an invited demo; nothing here needs a database server |

Rejected: Kubernetes, Postgres, Redis, queues; Vercel in front (a 300 s function limit breaks a streamed run); Railway
(5-minute idle, 15-minute cap); a CPU-only model (650–1,000 s a run, over the 600 s timeout); renting an always-on GPU
($117–$580/month for a few runs a day).

## Owner approvals, in order

1. A Modal account, a workspace budget (hard cap, suggested $50/month) and `modal deploy deploy/cloud/modal_ollama.py`.
   Then the equivalence check below, before anyone is told the cloud answers like the workstation.
2. A DigitalOcean droplet (Ubuntu LTS, 2 GB), weekly backups on (+20%), SSH keys only.
3. DNS: an A record for the workbench (e.g. `verity.pavankg.dev`) to the droplet, grey cloud (DNS only: Caddy does TLS,
   and Cloudflare's proxy cuts an origin response at 125 s); a Pages custom domain for the evidence page.
4. Who may enter: `WORKBENCH_ACCESS_REQUIRED=1` (in `env.example`; it refuses to start open) and the invites you send.
5. The proof run the first screen shows: record one on this deployment, or restore the curated store (a production data
   migration). Until one exists, build with `VERITY_PROOF_RUN` unset: the first screen then shows the reader's own latest
   run, without the proof run's story.
6. The words for `WORKBENCH_MODEL_HOST` (shown wherever the interface says where a contract's text goes), the daily
   ceiling `WORKBENCH_MAX_RUNS_PER_DAY`, budget alerts in Modal, and a weekly copy of `/backups` off the machine.

## The droplet

```bash
# as root, once
apt-get update && apt-get -y install docker.io docker-compose-v2 unattended-upgrades
ufw default deny incoming && ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
# Docker publishes ports around ufw: never add a `ports:` entry to any service but Caddy.
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config && systemctl reload ssh
```

Build the images on a machine with room for `next build` (it can run a 2 GB droplet out of memory) and carry them over;
nothing goes to a public registry:

```bash
cd deploy/cloud
VERITY_SITE=verity.pavankg.dev VERITY_BUILD_SHA=$(git rev-parse HEAD) VERITY_PROOF_RUN=<id or empty> docker compose build
docker save verity-api:local verity-web:local | gzip > verity-images.tar.gz
scp verity-images.tar.gz compose.yml Caddyfile env.example root@<droplet>:/opt/verity/
# on the droplet
cd /opt/verity && gunzip -c verity-images.tar.gz | docker load
cp env.example .env && chmod 600 .env    # fill in; make the secret with the line in env.example
# first boot: Let's Encrypt staging until the name resolves and 80/443 answer, then production
VERITY_SITE=verity.pavankg.dev VERITY_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory docker compose up -d
VERITY_SITE=verity.pavankg.dev docker compose up -d --force-recreate caddy
```

## Environment

`env.example` is the schema. The essentials: `WORKBENCH_ACCESS_REQUIRED=1` with a secret of 32+ characters;
`WORKBENCH_APP_URL` and `WORKBENCH_CORS_ORIGINS` set to the one https origin; `WORKBENCH_OLLAMA_URL`,
`WORKBENCH_OLLAMA_HEADERS` (the Modal proxy token, as JSON) and `WORKBENCH_MODEL_DIGEST=500a1f067a9f`. The interface is
built with no API address: it calls its own origin, and Caddy sends `/api` to the API.

## Spend boundaries

- GPU: one container at most, released 60 s after the last request, under the Modal workspace budget (a hard cap).
  Estimated $25–50/month at 50 runs a day; less at demo traffic.
- Runs: invite-only; 20 run starts per 10 minutes per reader; `WORKBENCH_MAX_RUNS_PER_DAY` new questions a day for
  everyone together (the owner's number); one model call at a time per API; 25 MB per upload; 600 s per model call.
- Health never wakes the GPU: a visitor who has not entered never makes it ask the model, and with
  `WORKBENCH_HEALTH_PROBES_MODEL=0` no one does; every answer still checks the pinned build first.
- VM: $12/month plus $2.40 backups. Pages: free. Total at demo traffic: about $15–65/month, bounded by the GPU budget.

## Backups and restore

The backup is the rollback: a code rollback cannot undo what a newer reader wrote.

```bash
# nightly, on the droplet (crontab -e)
15 3 * * * cd /opt/verity && docker compose exec -T api python scripts/backup.py create --data-dir /data --out /backups/$(date +\%Y\%m\%d) >> /var/log/verity-backup.log 2>&1
# restore into a fresh volume, then point the API at it
docker run --rm -v verity_verity-backups:/backups -v verity_restored:/restore -u root verity-api:local \
  python scripts/backup.py restore /backups/<date> --to /restore/data
```

Rehearse a restore once a month: restore the latest backup into a fresh volume (above) and compare its runs with the
live store's. Nightly backups sit on the droplet's own disk; the droplet's weekly backup is what survives losing the droplet, so the
gap is up to a week. Copying `/backups` off the machine (R2 or B2, about free at this size) closes it and needs an account.

## Rollback

1. `docker compose down` (the volumes stay).
2. Restore the last backup taken before the change (above) if the change wrote anything an older build cannot read.
3. `docker load` the previous images (keep the last `verity-images.tar.gz`) and `docker compose up -d`.
The evidence page rolls back by redeploying the previous `out-state/` from Pages' history.

## Rehearsed (local Docker, 2026-10-09)

The stack ran under Docker Desktop with Caddy's internal CA at `https://localhost:8443` (the API and interface publish
no ports) and the API calling the workstation's Ollama over HTTP, the same build the cloud would serve. Results are in
a rehearsal folder on the workstation, not in the repository. Passed: the gate and the first-party session cookie; upload and a
real streamed run (66 s, cited passages verified); every request to the page's own origin; two readers isolated by list
and by id; two readers at once; a forged `Cf-Connecting-Ip` ignored; unknown ids; a stale session; the API restarting
mid-run (the run ends failed, never complete); history surviving restarts; the interface restarting; the model endpoint
down; another model build behind the tag (refused before any answer); a read-only store (health false, upload refused);
a backup taken in the deployment restored into a fresh volume with the same runs and findings; a refresh mid-run
reattaching to the same run, with one result on screen; health never asking an unreachable model for a visitor who has
not entered (0.00 s) or with probes off, and asking it (5 s, false) when on; the interface naming the hosted model and
what is sent to it. Found by the rehearsal and fixed: interrupted runs of a restarted container stayed in progress
forever (pid 1 under one hostname), and the lock file could not be installed on Linux.

Not rehearsed: the Modal endpoint itself, public DNS and Let's Encrypt, a remote phone on the real hostname.

## Before calling the cloud model equivalent

Pre-registered, before the first GPU run: the 44 goldens (the workstation's answer-v2 baseline is 37/44, 0 flips across
two recordings), the 15 false-premise controls (v2: 3/7 negatives, 6/8 positives), exact-source proof on the CUAD pair,
and wall-clock latency. "Identical" only with 0 golden flips; otherwise the flips are reported, run by run. The same
weights on an L4 can still decode differently from the workstation's GPU.
