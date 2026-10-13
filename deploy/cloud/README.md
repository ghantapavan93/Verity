# Verity in the cloud: one VM, a serverless GPU, a static evidence page

This replaces nothing in `deploy/` (the workstation and tunnel setup); it is the laptop-independent layout of the same
public demo `deploy/README.md` describes: anyone may enter, each browser in a workspace of its own, deleted with
everything in it seven days after the first visit. Deployed so far: staging only, on a Hetzner VM behind a tunnel
(`ORACLE.md`, which also holds the cutover); the public name still reaches the workstation. Every step that creates a resource,
spends money, changes DNS or changes who can enter is the owner's to take. What is ready, what was rehearsed and what
still needs a paid test: `CLOUD-READINESS.md`.

## Layout

| Piece | Where | Why this and not more |
|---|---|---|
| Live workbench, /break, /state | One Linux VM (DigitalOcean Basic, 4 GB, 2 vCPU, $24/month) running `compose.yml`: Caddy, the interface, the API | SQLite needs a local disk and one process; one VM is the simplest thing that gives both, with no cold start for the pages and documented SSE behaviour |
| Model | Ollama 0.40.3 on a Modal L4, scale to zero (`modal_ollama.py`) | The only way found to serve the exact reference build (qwen3:8b, Ollama digest 500a1f067a9f, Q4_K_M); no managed provider serves those weights |
| Storage | SQLite (WAL) and the original uploads on the VM's disk, in the `verity-data` volume; no backups (below) | Measured traffic is a demo; the store holds nothing older than seven days by design |
| Optional mirror of /state and /break | Static files on Cloudflare Pages (`backend/scripts/export_state.py --build --workbench-url <live workbench> --hosting cloud`) | No server, store or model; survives the VM being down |

The engineering boundaries do not move: the same images run the same code as the workstation's public API, with the
same settings (`env.example` names each one); one uvicorn worker; the model proposes, deterministic code verifies every
quote, and every answer is preceded by a check that the endpoint serves the pinned build.

Rejected: Kubernetes, Postgres, Redis, queues; Vercel in front (a 300 s function limit breaks a streamed run); Railway
(5-minute idle, 15-minute cap); a CPU-only model (650–1,000 s a run, over the 600 s timeout); renting an always-on GPU
($117–$580/month for a few runs a day); Cloudflare's proxy in front of the VM (below).

A host with no public address to serve from (Oracle Always Free, an ARM VM) runs the same stack with a Cloudflare Tunnel
as its edge in place of Caddy, as the workstation does: `ORACLE.md`.

## Build, and gate the image

Build on a machine with room for `next build` (it can run a small VM out of memory) and carry the images over; nothing
goes to a public registry. From the repository root, at the commit to deploy:

```bash
docker build -f deploy/cloud/Dockerfile.api --target test .       # the backend suite inside the API image: must pass
cd deploy/cloud
BUILDX_NO_DEFAULT_ATTESTATIONS=1 VERITY_SITE=x VERITY_BUILD_SHA=$(git rev-parse HEAD) docker compose build
docker save verity-api:local verity-web:local | gzip > verity-images-$(git rev-parse --short HEAD).tar.gz
```

The API image installs `backend/requirements.lock`, the versions the workstation runs and the release gate tests, and
the `test` stage runs the whole backend suite on that image's own Python and packages (Linux). The web build refuses a
bundle that names a loopback API. Without attestations the archive holds only the images, which `docker load` takes as
they are.

The record /state shows is the lab's frozen file (`experiments/contract-lineage/results/contract-state.json` in
ivo-experiments, sha256 `cff26179f199d6d58768df968fbf4af5fda3e446e6fbe04844bf73c057290f1d`); it is copied beside
`compose.yml` and mounted read-only. Check the hash before copying it: the API's loader refuses any other file.

## The droplet

Ubuntu 24.04 LTS, SSH keys only, **backups off**, an IPv4 address only (no AAAA record: behind Docker's port proxy every
IPv6 visitor would share one per-address limit). As root, once:

```bash
apt-get update && apt-get -y install docker.io docker-compose-v2 unattended-upgrades
ufw default deny incoming && ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
# Docker publishes ports around ufw: never add a `ports:` entry to any service but Caddy.
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config && systemctl reload ssh
sshd -T | grep -i '^passwordauthentication'               # must say "no"; a cloud-init drop-in can override the sed
swapon --show                                             # must print nothing (below)
mkdir -p /opt/verity && chmod 700 /opt/verity
```

Ubuntu's own `docker.io` and `docker-compose-v2`, not Docker's repository: one source, updated by unattended-upgrades.
No swap: an upload or a SQLite temporary file held in memory could be paged out to a disk no retention pass reaches.
That is why the VM has 4 GB: the stress case rehearsed (four 25 MB uploads at once) took the containers to 1.29 GiB
(below), which with Ubuntu and Docker would leave a 2 GB machine no margin; each further large upload at the same
moment adds about 260 MiB.

Then, from the build machine:

```bash
scp verity-images-<sha>.tar.gz compose.yml Caddyfile env.example contract-state.json root@<droplet>:/opt/verity/
```

and on the droplet:

```bash
cd /opt/verity && sha256sum contract-state.json          # cff26179f199…; anything else: stop
gunzip -c verity-images-<sha>.tar.gz | docker load
cp env.example .env && chmod 600 .env                     # fill in, VERITY_SITE included; make the secret with the line in env.example
# First boot: Let's Encrypt staging until the name resolves and 80/443 answer, then production.
VERITY_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory docker compose up -d
docker compose up -d --force-recreate caddy
```

`VERITY_SITE` in `.env` is the hostname alone (`verity-staging.example.com`); `WORKBENCH_APP_URL` and
`WORKBENCH_CORS_ORIGINS` hold `https://` and the same name: sessions and every write are refused from any other origin.
After each release, keep the previous release's images for rollback and remove older ones (`docker image prune`).

## DNS, TLS and sessions

An A record for the hostname to the droplet, **DNS only** (grey cloud). Caddy obtains and renews the certificate and
serves HTTP/1.1 and HTTP/2 only (the firewall opens no UDP for HTTP/3). Not Cloudflare's proxy: the API's per-address
limits read `Cf-Connecting-Ip`, which Caddy sets from the address it saw; behind the proxy that is Cloudflare's edge, and
every visitor would share one bucket. The proxy also cuts an origin response at 125 s, and a streamed run can be longer.

A browser that arrives without a session is given one (`POST /api/access/visit`): a `__Host-` cookie, Secure, HttpOnly,
SameSite=Strict, signed with `WORKBENCH_ACCESS_SECRET`, naming a workspace no other browser can read. The VM's store
starts empty: nothing is migrated from the workstation, whose visitors start again here, and whose own store keeps
nothing past its seven days.

## Environment

`env.example` is the schema: the workstation's public settings (anonymous sessions on, the gate required, BM25 with
six sections, answer-v2) with the cloud's own question bounds (15 a day for everyone, 5 per workspace), plus what the
cloud adds: the site name, the model URL, its proxy
token as `WORKBENCH_OLLAMA_HEADERS`, the pinned digest, the host label, and health that never wakes the GPU.

The owner's switch: `docker compose exec api touch /data/public.paused` refuses new uploads and questions at once with a
plain sentence; `rm` it to resume. No restart.

## What the disk keeps, and for how long

The first screen promises that what a visitor adds is deleted seven days after the first visit. Every place a
contract's words can reach is covered:

| Where | What happens | How it is known |
|---|---|---|
| `workbench.db` rows | Deleted by the hourly retention pass once the workspace ends; `secure_delete` overwrites their pages | `tests/test_retention.py`; rehearsed (below) |
| `workbench.db-wal` | Checkpointed and truncated by every pass | same |
| SQLite's temporary files | Written under `TMPDIR=/tmp`, in memory; without it SQLite uses `/var/tmp`, on disk | a spilled sort in the image opened `/tmp/etilqs_…`; without the setting, `/var/tmp/etilqs_…` |
| Uploaded originals, memos | Unlinked after the commit (their blocks stay on the disk until overwritten or trimmed); an hourly sweep removes any file no row names, abandoned memo drafts included | same, and `test_the_sweep_removes_a_memo_draft_a_killed_process_left` |
| Upload spools | `/tmp` is in memory (`tmpfs`), never on disk; there is no swap to page it out to | `compose.yml`; `swapon --show` |
| Core dumps | Off for the API (`ulimits: core: 0`) | `compose.yml` |
| Logs | Ids, stages and durations, never a contract's words; SQL errors without their values; rotated at 3 × 10 MB | `test_ordinary_logs_carry_ids…`, `test_an_error_the_store_raises…`; no marker in any log after the rehearsal |
| Backups, snapshots, archives | **None.** No backup volume, no cron, DigitalOcean backups off, no snapshot of the volume | this file |
| The model host (Modal) | Each question's sections, the question and any guidance are sent to the Modal endpoint. Ollama does not log request bodies. A call still running at 150 s is answered by a 303 and its result held by Modal for a later fetch, for a time Modal does not document; Modal's own retention is under its terms | this file; `WORKBENCH_MODEL_HOST` tells the reader where the text goes |

A backup of the public store would hold visitors' contracts past the promise unless it were deleted before the
earliest workspace it holds ends, which can be minutes after it is taken. The store holds nothing older than seven days
by design, so it is not backed up: what must survive the VM is the deployment, and that is rebuilt (below). Losing the
VM loses at most seven days of visitors' workspaces, which their first screen already says will go.

## Recovery

| Failure | What brings it back | Rehearsed |
|---|---|---|
| A container exits | `restart: unless-stopped` | yes |
| The API runs but stops answering | `liveness.py`: after its first minute, three failed probes in a row (about ninety seconds) kill the server, and the container restarts | yes: frozen, back in 145 s, by the restart policy |
| The API restarts mid-run | The run left in flight is failed at start, never left running (`hostname: verity-api` keeps the owner's name stable) | yes |
| The VM reboots | Docker starts the stack (`restart: unless-stopped`); the store is on the volume | partly: every container stopped and started, the store intact; a Docker daemon restart was not rehearsed |
| The model endpoint is down or serves another build | The question fails with a sentence; health stays up; nothing is answered by another build | yes |
| The VM is lost | Rebuild: a new droplet as above, the images from the build machine, `.env` from where the owner keeps it (the secret), the record from ivo-experiments; the store starts empty | partly: on the same machine with the images loaded, every volume removed, healthy again in 10 s and `acceptance.mjs` 82 of 82 (`rebuild-final.txt`); a new droplet was not |

Keep the last two image archives on the build machine. `.env` is the only thing that cannot be rebuilt from the
repository; a new secret ends every session, and the workspaces they held are deleted when their seven days end.

## Rollback

On a host that builds its own images (ORACLE.md) every build is tagged with its commit (`VERITY_TAG`), and the previous
release's images are kept: set `VERITY_TAG=<previous>` in `.env` and run `docker compose up -d`, in seconds (ORACLE.md,
Rollback). A tag given only on the command line lasts for that command: the next bare `up -d` returns to the one in
`.env`. On a host that loads archives:

1. `docker compose down` (the volume stays).
2. `docker load` the previous release's images and `docker compose up -d`.
3. When the release being undone changed the schema (the delivery preflight's "schema owners changed"), the older build
   may not read the store: start it on an empty one (`docker volume rm verity_verity-data` first), which ends every
   visitor's workspace at once, or fix forward. Additive changes (`ensure_columns`) read the same store both ways.

## Spend boundaries

- GPU: one L4 container at most, released 300 s after the last request, under the Modal workspace budget (a hard cap).
  Adding a contract or starting a question wakes it (WORKBENCH_MODEL_WAKEUP), at most WORKBENCH_MODEL_WAKEUPS_PER_DAY times a UTC day.
  About $0.96 an hour while up (GPU, two cores, 8 GiB); a question costs $0.02–0.07 depending on whether the GPU is
  already warm. Estimates, not measurements: the first paid test measures them (`CLOUD-READINESS.md`).
- Questions: 15 a day for everyone together and 5 per workspace (env.example; the workstation allows 200 and 30), 30 an
  hour per network address; one model call at a time; 600 s per model call, which Modal's per-request timeout also
  enforces once it redirects a long call. Uploads: 25 MB each (an upload declaring more is refused by the API before its
  body is read, behind Caddy or a tunnel), 10 per workspace, 300 a day for everyone.
- Health never wakes the GPU (`WORKBENCH_HEALTH_PROBES_MODEL=0`); every answer still checks the pinned build first.
- VM: $24/month. Pages: free. DNS: the existing Cloudflare zone.

## Rehearsed (local Docker, 2026-10-12)

The final run used the images of `fe030a8` and this kit (the load and failure runs with the in-memory `/tmp` at its earlier 256 MiB bound; the rebuild and its acceptance on the committed kit), under Docker Desktop with Caddy's internal CA at
`https://localhost:28443` (an isolated Compose project, volume and ports; the API and interface publish no ports), the
API calling the workstation's Ollama over HTTP, the same build the cloud serves. Scripts and every output are in the
`cloud/rehearsal2` folder on the workstation, not in the repository.

Passed: `acceptance.mjs` 82 of 82 (two questions on the real model), three times, once after every volume was removed;
two unrelated visitors isolated by list, by id, by run, by event stream and by memo, with uploads, a review, HTML and
.docx memos, events streamed through Caddy as the run proceeded, a refresh mid-run reattached to the same run, a forged
`Cf-Connecting-Ip` held to the per-address limit, a 28 MB body refused with 413 before the API, a file whose bytes are
not its type and a write from another origin refused (19 of 19); the failure rows of the recovery table and the owner's
pause switch (7 of 7, and the frozen API back in 145 s); the retention pass: after a visitor's workspace ended, the
marker word in their contract was in no file under `/data` or `/tmp`, nor in any container's log; response headers with
HSTS, `nosniff` and `frame-ancestors 'none'`, and no `Server`, `X-Powered-By` or HTTP/3 advertisement.

Memory: nine visitors at once (contracts of 1.9–25 MB, three questions queued on the model, twenty extra event streams)
peaked at 731 MiB for the three containers; four 25 MB uploads at once, the stress case, at 1.29 GiB (the API
1.20 GiB, about 260 MiB for each large upload in progress), with 121 MiB of `/tmp` in use. No 500, no lock or pool error, no out-of-memory kill, in either.
Upload times under load varied three- to twelvefold between runs on the shared workstation (the 25 MB file took 3.9 s
in one, 46 s in another), so they are indicative; staging measures them on the droplet.

Found by the rehearsal and its review, and fixed, each with a test or a probe: the kit ran invite-only (it now runs the
public demo's settings); the image installed versions no gate had tested; a hung API would have stayed hung, and the
first version of the fix chose a process it could not end; the first question after the GPU scaled to zero would have
failed its 5 s build check, and an answer past Modal's 150 s request limit would have failed on the redirect; the lock
file had again lost two packages a Linux install needs; questions asked together exhausted the database connection pool
and every other request waited 30 s; a memo draft could outlive a killed process; a SQL error could carry a contract's
words into the log; SQLite's temporary files and a swap file could each have put a contract's words on the disk.

Not rehearsed: the Modal endpoint itself, public DNS and Let's Encrypt, a phone on the real hostname, a new droplet.
`CLOUD-READINESS.md` names the paid acceptance test for each.
