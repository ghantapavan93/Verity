# Verity in the cloud: one VM, a serverless GPU, a static evidence page

This replaces nothing in `deploy/` (the workstation and tunnel setup); it is the laptop-independent layout of the same
public demo `deploy/README.md` describes: anyone may enter, each browser in a workspace of its own, deleted with
everything in it seven days after the first visit. Nothing here has been deployed. Every step that creates a resource,
spends money, changes DNS or changes who can enter is the owner's to take. What is ready, what was rehearsed and what
still needs a paid test: `CLOUD-READINESS.md`.

## Layout

| Piece | Where | Why this and not more |
|---|---|---|
| Live workbench, /break, /state | One Linux VM (DigitalOcean Basic, 2 GB, 1 vCPU, $12/month) running `compose.yml`: Caddy, the interface, the API | SQLite needs a local disk and one process; one VM is the simplest thing that gives both, with no cold start for the pages and documented SSE behaviour |
| Model | Ollama 0.40.3 on a Modal L4, scale to zero (`modal_ollama.py`) | The only way found to serve the exact reference build (qwen3:8b, Ollama digest 500a1f067a9f, Q4_K_M); no managed provider serves those weights |
| Storage | SQLite (WAL) and the original uploads on the VM's disk, in the `verity-data` volume; no backups (below) | Measured traffic is a demo; the store holds nothing older than seven days by design |
| Optional mirror of /state | Static files on Cloudflare Pages (`backend/scripts/export_state.py --build`) | No server, store or model; survives the VM being down |

The engineering boundaries do not move: the same images run the same code as the workstation's public API, with the
same settings (`env.example` names each one); one uvicorn worker; the model proposes, deterministic code verifies every
quote, and every answer is preceded by a check that the endpoint serves the pinned build.

Rejected: Kubernetes, Postgres, Redis, queues; Vercel in front (a 300 s function limit breaks a streamed run); Railway
(5-minute idle, 15-minute cap); a CPU-only model (650–1,000 s a run, over the 600 s timeout); renting an always-on GPU
($117–$580/month for a few runs a day); Cloudflare's proxy in front of the VM (below).

## Build, and gate the image

Build on a machine with room for `next build` (it can run a 2 GB VM out of memory) and carry the images over; nothing
goes to a public registry. From the repository root, at the commit to deploy:

```bash
docker build -f deploy/cloud/Dockerfile.api --target test .       # the backend suite inside the API image: must pass
cd deploy/cloud
VERITY_SITE=x VERITY_BUILD_SHA=$(git rev-parse HEAD) docker compose build
docker save verity-api:local verity-web:local | gzip > verity-images-$(git rev-parse --short HEAD).tar.gz
```

The API image installs `backend/requirements.lock`, the versions the workstation runs and the release gate tests, and
the `test` stage runs the whole backend suite on that image's own Python and packages (Linux). The web build refuses a
bundle that names a loopback API.

The record /state shows is the lab's frozen file (`experiments/contract-lineage/results/contract-state.json` in
ivo-experiments, sha256 `cff26179f199d6d58768df968fbf4af5fda3e446e6fbe04844bf73c057290f1d`); it is copied beside
`compose.yml` and mounted read-only. Check the hash before copying it: the API's loader refuses any other file.

## The droplet

Ubuntu 24.04 LTS, SSH keys only, **backups off**. As root, once:

```bash
apt-get update && apt-get -y install docker.io docker-compose-v2 unattended-upgrades
ufw default deny incoming && ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
# Docker publishes ports around ufw: never add a `ports:` entry to any service but Caddy.
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config && systemctl reload ssh
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
mkdir -p /opt/verity && chmod 700 /opt/verity
```

Ubuntu's own `docker.io` and `docker-compose-v2`, not Docker's repository: one source, updated by unattended-upgrades.
The swap file is a margin for `docker load` and spikes, not working memory (measured peak below).

Then, from the build machine:

```bash
scp verity-images-<sha>.tar.gz compose.yml Caddyfile env.example contract-state.json root@<droplet>:/opt/verity/
```

and on the droplet:

```bash
cd /opt/verity && sha256sum contract-state.json          # cff26179f199…; anything else: stop
gunzip -c verity-images-<sha>.tar.gz | docker load
cp env.example .env && chmod 600 .env                     # fill in; make the secret with the line in env.example
# First boot: Let's Encrypt staging until the name resolves and 80/443 answer, then production.
VERITY_SITE=<host> VERITY_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory docker compose up -d
VERITY_SITE=<host> docker compose up -d --force-recreate caddy
```

`VERITY_SITE` is the hostname alone (`verity-staging.example.com`); `.env` holds `https://` and the same name in
`WORKBENCH_APP_URL` and `WORKBENCH_CORS_ORIGINS`: sessions and every write are refused from any other origin.

## DNS, TLS and sessions

An A record for the hostname to the droplet, **DNS only** (grey cloud). Caddy obtains and renews the certificate. Not
Cloudflare's proxy: the API's per-address limits read `Cf-Connecting-Ip`, which Caddy sets from the address it saw; behind
the proxy that is Cloudflare's edge, and every visitor would share one bucket. The proxy also cuts an origin response at
125 s, and a streamed run can be longer.

A browser that arrives without a session is given one (`POST /api/access/visit`): a `__Host-` cookie, Secure, HttpOnly,
SameSite=Strict, signed with `WORKBENCH_ACCESS_SECRET`, naming a workspace no other browser can read. The VM's store
starts empty: nothing is migrated from the workstation, whose visitors start again here, and whose own store keeps
nothing past its seven days.

## Environment

`env.example` is the schema: the workstation's public settings (anonymous sessions on, the gate required, 200 questions
a day for everyone, BM25 with six sections, answer-v2), plus what the cloud adds: the model URL, its proxy token as
`WORKBENCH_OLLAMA_HEADERS`, the pinned digest, the host label, and health that never wakes the GPU.

The owner's switch: `docker compose exec api touch /data/public.paused` refuses new uploads and questions at once with a
plain sentence; `rm` it to resume. No restart.

## What the disk keeps, and for how long

The first screen promises that what a visitor adds is deleted seven days after the first visit. Every place a
contract's words can reach on this VM is covered:

| Where | What happens | How it is known |
|---|---|---|
| `workbench.db` rows | Deleted by the hourly retention pass once the workspace ends; `secure_delete` overwrites their pages | `tests/test_retention.py`; rehearsed (below) |
| `workbench.db-wal` | Checkpointed and truncated by every pass | same |
| Uploaded originals, memos | Unlinked after the commit; an hourly sweep removes any file no row names, abandoned memo drafts included | same, and `test_the_sweep_removes_a_memo_draft_a_killed_process_left` |
| Upload spools | `/tmp` is in memory (`tmpfs`), never on disk | `compose.yml` |
| Logs | Ids, stages and durations, never a contract's words; SQL errors without their values; rotated at 3 × 10 MB | `test_ordinary_logs_carry_ids…`, `test_an_error_the_store_raises…` |
| Backups, snapshots, archives | **None.** No backup volume, no cron, DigitalOcean backups off, no snapshot of the volume | this file |

A backup of the public store would hold visitors' contracts past the promise unless it were deleted before the
earliest workspace it holds ends, which can be minutes after it is taken. The store holds nothing older than seven days
by design, so it is not backed up: what must survive the VM is the deployment, and that is rebuilt (below). Losing the
VM loses at most seven days of visitors' workspaces, which their first screen already says will go.

## Recovery

| Failure | What brings it back | Rehearsed |
|---|---|---|
| A container exits | `restart: unless-stopped` | yes |
| The API runs but stops answering | `liveness.py`: after its first minute, three failed probes in a row (about ninety seconds) kill the server, and the container restarts | yes: frozen, back in 144 s |
| The API restarts mid-run | The run left in flight is failed at start, never left running (`hostname: verity-api` keeps the owner's name stable) | yes |
| The VM reboots | Docker starts the stack; the store is on the volume | yes (stop and start of every container) |
| The model endpoint is down or serves another build | The question fails with a sentence; health stays up; nothing is answered by another build | yes |
| The VM is lost | Rebuild: a new droplet as above, the images from the build machine, `.env` from where the owner keeps it (the secret), the record from ivo-experiments; the store starts empty | yes (volumes removed, rebuilt, acceptance run) |

Keep the last two image archives on the build machine. `.env` is the only thing that cannot be rebuilt from the
repository; a new secret ends every session, and the workspaces they held are deleted when their seven days end.

## Rollback

1. `docker compose down` (the volume stays).
2. `docker load` the previous release's images and `docker compose up -d`.
3. When the release being undone changed the schema (the delivery preflight's "schema owners changed"), the older build
   may not read the store: start it on an empty one (`docker volume rm verity_verity-data` first), which ends every
   visitor's workspace at once, or fix forward. Additive changes (`ensure_columns`) read the same store both ways.

## Spend boundaries

- GPU: one L4 container at most, released 60 s after the last request, under the Modal workspace budget (a hard cap).
  About $0.96 an hour while up (GPU, two cores, 8 GiB); a question costs $0.02–0.07 depending on whether the GPU is
  already warm. Estimates, not measurements: the first paid test measures them (`CLOUD-READINESS.md`).
- Questions: 200 a day for everyone together, 30 per workspace a day, 30 an hour per network address; one model call at
  a time; 600 s per model call. Uploads: 25 MB each (Caddy refuses a larger body before the API reads it), 10 per
  workspace, 300 a day for everyone.
- Health never wakes the GPU (`WORKBENCH_HEALTH_PROBES_MODEL=0`); every answer still checks the pinned build first.
- VM: $12/month. Pages: free. DNS: the existing Cloudflare zone.

## Rehearsed (local Docker, 2026-10-12)

The stack ran under Docker Desktop with Caddy's internal CA at `https://localhost:18443` (an isolated Compose project,
volume and ports; the API and interface publish no ports), the API calling the workstation's Ollama over HTTP, the same
build the cloud serves. Scripts and results are in a rehearsal folder on the workstation, not in the repository.

Passed: `acceptance.mjs`, 81 of 81 (two questions on the real model); two unrelated visitors isolated by list, by id, by
run, by event stream and by memo; uploads, a review, HTML and .docx memos; events streamed through Caddy as the run
proceeded; a refresh mid-run reattached to the same run; a forged `Cf-Connecting-Ip` did not escape the per-address
limit; a 28 MB body refused with 413 before the API; a file whose bytes are not its type refused; a write from another
origin refused; every failure in the recovery table above; the owner's pause switch; and the retention pass: after a
visitor's workspace ended, the marker word in their contract was in no file under `/data` or `/tmp` and in no
container's log. Under load (nine visitors at once, contracts of 1.9–25 MB, three questions queued on the model, twenty
extra event streams): every upload and question completed, no 500, peak memory 457 MiB for the three containers; with
the three held to one vCPU and 1.8 GB between them, 573 MiB, still no error.

Found by the rehearsal and fixed, each with a test: the kit ran invite-only (it now runs the public demo's settings);
the image installed versions no gate had tested; a hung API would have stayed hung; the first question after the GPU
scaled to zero would have failed its 5 s build check, and an answer past Modal's 150 s request limit would have failed
on the redirect; the lock file had again lost two packages a Linux install needs; questions asked together exhausted
the database connection pool and every other request waited 30 s; a memo draft could outlive a killed process; a SQL
error could carry a contract's words into the log.

Not rehearsed: the Modal endpoint itself, public DNS and Let's Encrypt, a phone on the real hostname. `CLOUD-READINESS.md`
names the paid acceptance test for each.
