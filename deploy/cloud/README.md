# Verity on one Hetzner server: the interface, the API, the store and the model on one host

This replaces nothing in `deploy/` (the workstation and tunnel setup); it is the laptop-independent layout of the same
public demo `deploy/README.md` describes: anyone may enter, each browser in a workspace of its own, deleted with
everything in it seven days after the first visit. Everything runs on one Hetzner server: the interface, the API, the
SQLite store, the uploaded documents and the model (Ollama serving the pinned Qwen3 8B build); Cloudflare carries the
public name and HTTPS through a tunnel. Not deployed yet: the public name still reaches the workstation, and a staging
host of 2026-10-13 ran this stack with the model elsewhere. `HETZNER.md` is the host's runbook, the cutover included.
Every step that creates a resource, spends money, changes DNS or changes who can enter is the owner's to take.

## Layout

| Piece | Where | Why this and not more |
|---|---|---|
| Live workbench, /break, /state | One Hetzner dedicated server running `compose.yml`: the tunnel connector (or Caddy), the interface, the API (HETZNER.md: The server) | SQLite needs a local disk and one process; one host is the simplest thing that gives both, with no cold start for the pages and documented SSE behaviour |
| Model | Ollama 0.40.4 on the same host (service `ollama`), on its CPU, or its GPU with `compose.gpu.yml`; kept loaded | It serves the exact reference build (qwen3:8b, Ollama digest 500a1f067a9f, Q4_K_M) the workstation serves; nothing a visitor adds leaves the host |
| Storage | SQLite (WAL) and the original uploads on the host's disk, in the volume `VERITY_STORE` names; no backups (below) | Measured traffic is a demo; the store holds nothing older than seven days by design |
| Optional mirror of /state and /break | Static files on Cloudflare Pages (`backend/scripts/export_state.py --build --workbench-url <live workbench> --hosting cloud`) | No server, store or model; survives the VM being down |

The engineering boundaries do not move: the same images run the same code as the workstation's public API, with the
same settings (`env.example` names each one); one uvicorn worker; the model proposes, deterministic code verifies every
quote, and every answer is preceded by a check that Ollama serves the pinned build.

Rejected: Kubernetes, Postgres, Redis, queues; Vercel in front (a 300 s function limit breaks a streamed run); Railway
(5-minute idle, 15-minute cap); a model on two shared vCPUs (650–1,000 s a run, over the 600 s timeout, 2026-10-12); a
serverless GPU elsewhere (Modal, staged 2026-10-13: 95–168 s to wake, the text of every question sent to a second
company, and a bill per second; dropped 2026-10-16 for one host); Cloudflare's proxy in front of a Caddy host (below).
A model on eight dedicated cores and a GPU server are both measured in HETZNER.md before either is bought.

The production host has no inbound port for visitors: its edge is a Cloudflare Tunnel connector (the `tunnel` profile), as
on the workstation (`HETZNER.md`). A host with its own public address can use Caddy instead (below).

## Build, and gate the image

Build on a machine with room for `next build` (it can run a small VM out of memory) and carry the images over; nothing
goes to a public registry. From the repository root, at the commit to deploy:

```bash
docker build -f deploy/cloud/Dockerfile.api --target test .       # the backend suite inside the API image: must pass
cd deploy/cloud
export VERITY_TAG=$(git rev-parse --short HEAD)                   # the images are tagged with the commit they hold
BUILDX_NO_DEFAULT_ATTESTATIONS=1 VERITY_SITE=x VERITY_STORE=unused VERITY_BUILD_SHA=$(git rev-parse HEAD) docker compose build   # a build opens no store
docker save verity-api:$VERITY_TAG verity-web:$VERITY_TAG | gzip > verity-images-$VERITY_TAG.tar.gz
unset VERITY_TAG
```

The API image installs `backend/requirements.lock`, the versions the workstation runs and the release gate tests, and
the `test` stage runs the whole backend suite on that image's own Python and packages (Linux). The web build refuses a
bundle that names a loopback API. Without attestations the archive holds only the images, which `docker load` takes as
they are.

The record /state shows is the lab's frozen file (`experiments/contract-lineage/results/contract-state.json` in
ivo-experiments, sha256 `cff26179f199d6d58768df968fbf4af5fda3e446e6fbe04844bf73c057290f1d`); it is copied beside
`compose.yml` and mounted read-only. Check the hash before copying it: the API's loader refuses any other file.

## A host with its own address (the Caddy edge)

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
The memory to plan for: the model holds about 6 GB with its context, and the rest of the stack, under the stress case
rehearsed (four 25 MB uploads at once), took 1.29 GiB (below); each further large upload at the same moment adds
about 260 MiB. An AX42's 64 GB holds all of it with no swap.

Then, from the build machine:

```bash
scp verity-images-<sha>.tar.gz compose.yml Caddyfile env.example contract-state.json root@<host>:/opt/verity/
```

and on the host:

```bash
cd /opt/verity && sha256sum contract-state.json          # cff26179f199…; anything else: stop
gunzip -c verity-images-<sha>.tar.gz | docker load
cp env.example .env && chmod 600 .env                     # fill in, VERITY_SITE and VERITY_STORE included (HETZNER.md, Stores); make the secret with the line in env.example
sed -i '/^VERITY_TAG=/d' .env && echo VERITY_TAG=<sha> >> .env   # the archive's tag; compose refuses to start without it
# First boot: Let's Encrypt staging until the name resolves and 80/443 answer, then production.
VERITY_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory docker compose up -d
docker compose up -d --force-recreate caddy
```

`VERITY_SITE` in `.env` is the hostname alone (`verity-staging.example.com`); `WORKBENCH_APP_URL` and
`WORKBENCH_CORS_ORIGINS` hold `https://` and the same name: sessions and every write are refused from any other origin.
After each release, keep the previous release's images for rollback and remove older ones (`docker image prune`).

## DNS, TLS and sessions

An A record for the hostname to the host, **DNS only** (grey cloud). Caddy obtains and renews the certificate and
serves HTTP/1.1 and HTTP/2 only (the firewall opens no UDP for HTTP/3). Not Cloudflare's proxy: the API's per-address
limits read `Cf-Connecting-Ip`, which Caddy sets from the address it saw; behind the proxy that is Cloudflare's edge, and
every visitor would share one bucket. The proxy also cuts an origin response at 125 s, and a streamed run can be longer.

A browser that arrives without a session is given one (`POST /api/access/visit`): a `__Host-` cookie, Secure, HttpOnly,
SameSite=Strict, signed with `WORKBENCH_ACCESS_SECRET`, naming a workspace no other browser can read. The VM's store
starts empty: nothing is migrated from the workstation, whose visitors start again here, and whose own store keeps
nothing past its seven days.

## Environment

`env.example` is the schema: the workstation's public settings (anonymous sessions on, the gate required, BM25 with
six sections, answer-v2, 200 questions a day for everyone and 30 per workspace), plus what the host adds: the site
name, the store's name, the release tag, the model's address on the compose network and the pinned digest.

The owner's switch: `docker compose exec api touch /data/public.paused` refuses new uploads and questions at once with a
plain sentence; `rm` it to resume. No restart. On a host laid out as HETZNER.md says, this and every other compose
command here runs in `/opt/verity/current/deploy/cloud` with `--env-file /opt/verity/shared/.env`; without it compose
stops at the missing `VERITY_STORE` and `VERITY_TAG` and does nothing.

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
| Backups, snapshots, archives | **None.** No backup volume, no cron, host backups off, no snapshot of the volume | this file |
| The model (`ollama` on this host) | Each question, any guidance, the contract's file name and the sections retrieval chose for the question (the opening ones when it ranks none) go to the Ollama container over the compose network and nowhere else. Ollama keeps no request bodies and logs none; its volume holds only the model's public weights | `compose.yml` (no port published); the first screen says the model runs on the Verity server |

A backup of the public store would hold visitors' contracts past the promise unless it were deleted before the
earliest workspace it holds ends, which can be minutes after it is taken. The store holds nothing older than seven days
by design, so it is not backed up: what must survive the host is the deployment, and that is rebuilt (below). Losing the
host loses at most seven days of visitors' workspaces, which their first screen already says will go. The dedicated
server's two disks are a RAID 1 pair (HETZNER.md), so one failed disk loses nothing.

## Recovery

| Failure | What brings it back | Rehearsed |
|---|---|---|
| A container exits | `restart: unless-stopped` | yes |
| The API runs but stops answering | `liveness.py`: after its first minute, three failed probes in a row (about ninety seconds) kill the server, and the container restarts | yes: frozen, back in 145 s, by the restart policy |
| The API restarts mid-run | A run whose stage row names the stopped process is failed at start (`hostname: verity-api` keeps the owner's name stable). A run created in the instant before the restart, before its first stage row, names no process: it stays `reading`, and the same question is handed that run, until a read after the staleness bound (four 600 s model timeouts plus a minute, 41 minutes) fails it (war room F-25) | yes, for a run with a stage row; the run with none was reproduced by the war room, not rehearsed |
| The host reboots | Docker starts the stack (`restart: unless-stopped`); the store and the model's weights are on their volumes; the first question after a start waits for the model to load | partly: every container stopped and started, the store intact; a Docker daemon restart was not rehearsed |
| Ollama is down, still loading, or serves another build | The question fails with a sentence; health says the model is not reachable; nothing is answered by another build (`WORKBENCH_MODEL_DIGEST`) | yes (2026-10-16: the model container stopped mid-session) |
| The host is lost | Rebuild: a new server as HETZNER.md says, the images built there from the release, the model fetched again and its digest checked, `.env` from where the owner keeps it (the secret), the record from ivo-experiments; the store starts empty | partly: on the same machine with the images loaded, every volume removed, healthy again in 10 s and `acceptance.mjs` 82 of 82 (2026-10-12); a new server was not |

Keep the last two image archives on the build machine. `.env` is the only thing that cannot be rebuilt from the
repository; a new secret ends every session, and the workspaces they held are deleted when their seven days end.

## Rollback

On a host that builds its own images (HETZNER.md) every build is tagged with its commit (`VERITY_TAG`), and the previous
release's images are kept: set `VERITY_TAG=<previous>` in `.env` and run `docker compose up -d`, in seconds (HETZNER.md,
Rollback). A tag given only on the command line lasts for that command: the next bare `up -d` returns to the one in
`.env`. On a host that loads archives:

1. `docker compose down` (the volume stays).
2. `docker load` the previous release's images and `docker compose up -d`.
3. When the release being undone changed the schema (the delivery preflight's "schema owners changed"), the older build
   may not read the store: start it on an empty one (`docker volume rm` the store `VERITY_STORE` names, first), which ends every
   visitor's workspace at once, or fix forward. Additive changes (`ensure_columns`) read the same store both ways.

## Limits and spend

- The host: one monthly price (HETZNER.md, Cost). A question costs time, not money: nothing is billed per call.
- Questions: 200 a day for everyone together and 30 per workspace, as on the workstation (env.example), 30 an hour per
  network address, two in flight per workspace; one model call at a time, the next queued behind it; 600 s per model
  call. Uploads: 25 MB each (an upload declaring more is refused by the API before its body is read, behind Caddy or a
  tunnel), 2,000 pages, 10 per workspace, 300 a day for everyone; a reading runs in its own process with time and
  memory bounds.
- Pages: free. DNS and the tunnel: the existing Cloudflare zone.

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
in one, 46 s in another), so they are indicative; staging measures them on the host.

Found by the rehearsal and its review, and fixed, each with a test or a probe: the kit ran invite-only (it now runs the
public demo's settings); the image installed versions no gate had tested; a hung API would have stayed hung, and the
first version of the fix chose a process it could not end; the first question after the GPU scaled to zero would have
failed its 5 s build check, and an answer past Modal's 150 s request limit would have failed on the redirect; the lock
file had again lost two packages a Linux install needs; questions asked together exhausted the database connection pool
and every other request waited 30 s; a memo draft could outlive a killed process; a SQL error could carry a contract's
words into the log; SQLite's temporary files and a swap file could each have put a contract's words on the disk.

Not rehearsed then: public DNS and Let's Encrypt, a phone on the real hostname, a new host. The model was then planned
on a serverless GPU; the layout above, with the model on the same host, is rehearsed below.
