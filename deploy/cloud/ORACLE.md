# Verity on one small VM behind a Cloudflare Tunnel (Hetzner CAX11, staging since 2026-10-13)

The same compose stack as README.md, on a host with no inbound port for visitors: the edge is the `tunnel` profile (a
cloudflared connector, as on the workstation) instead of Caddy. The model is the Modal endpoint of README.md
(modal_ollama.py). Everything README.md says about the store, retention, recovery and spend holds here; this file says
only what differs. The file keeps its first name: it was written for Oracle Always Free, which on 2026-10-13 had no A1
capacity in any availability domain for any size (Oracle's Compute Capacity Report API), so the host is a Hetzner VM.

## The VM

- Hetzner Cloud CAX11: Arm64, 2 vCPU, 4 GB, 40 GB, Ubuntu 24.04, about $7 a month with its IPv4 address, billed by the
  hour; the x86 CX23 was unavailable. No backups (a copy of the store holds visitors' contracts past the deletion the
  first screen promises), no volumes, no swap.
- A Hetzner Cloud Firewall on the server: inbound TCP 22 and ICMP only. Nothing serves on 80 or 443: visitors reach the
  stack through the tunnel, which dials out. Outbound open (Cloudflare, Docker Hub, Modal, Ubuntu updates).
- SSH by key only: `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin prohibit-password`
  in `/etc/ssh/sshd_config.d/99-verity.conf`. `unattended-upgrades` on.
- Measured on staging: 520-740 MB in use of 3.8 GB with the stack up; the full API suite (Dockerfile.api `test` stage)
  passes natively on Arm64, the four timing-bound tests included.

## The tunnel

One tunnel per host, never shared: Cloudflare sends each request to the nearest connector of a tunnel, so a second
host's connector would put a second store behind the same name. On a machine with `cloudflared tunnel login` done:

```bash
cloudflared tunnel create verity-oracle                    # writes <id>.json beside cert.pem; keep it like a password
cloudflared tunnel route dns verity-oracle verity-staging.example.com
```

`route dns` creates a CNAME to `<id>.cfargotunnel.com` and refuses a name that already has a record. Moving an existing
name to this host is an edit of that record's target (below). The connector runs over HTTP/2 (compose.yml): over QUIC
every connection of the staging host dropped together for three minutes and a request was answered 502.

## Build, on the VM

Native, from the commit under test, which need not be pushed. From the build machine:

```bash
git archive --format=tar.gz -o verity-<sha>.tar.gz <sha>
scp verity-<sha>.tar.gz contract-state.json ~/.cloudflared/<id>.json root@<vm>:~
```

On the VM (first time: `apt-get install -y docker.io docker-compose-v2`):

```bash
mkdir -p /opt/verity && tar -xzf ~/verity-<sha>.tar.gz -C /opt/verity
cd /opt/verity && docker build --target test -f deploy/cloud/Dockerfile.api .   # the API suite on this CPU; any failure stops here
cd deploy/cloud && cp ~/contract-state.json . && sha256sum contract-state.json    # cff26179f199…; anything else: stop
install -o 65532 -g 65532 -m 400 ~/<id>.json tunnel.json   # cloudflared runs as 65532; never in git or an image (.gitignore, .dockerignore)
cp env.example .env && chmod 600 .env                      # once: COMPOSE_PROFILES=tunnel, VERITY_TUNNEL_ID=<id>, the secret as env.example says
swapon --show                                              # nothing: no swap
sed -i '/^VERITY_TAG=/d' .env && echo VERITY_TAG=<short sha> >> .env   # in .env, not exported: a bare `up -d` later keeps it
BUILDX_NO_DEFAULT_ATTESTATIONS=1 VERITY_BUILD_SHA=<sha> docker compose build && docker compose up -d
docker builder prune -f --filter until=72h                 # build cache grows with every release on a 38 GB disk
```

Each build is kept under its commit (`docker image ls verity-*`). Keep at least the previous release's images: the way
back below needs them. Remove older ones with `docker image rm`. Compose reads `VERITY_TAG` from `.env`, but a value
exported in the shell wins over it: before any `docker compose` command, `grep ^VERITY_TAG= .env` must print the tag
that should run, and `unset VERITY_TAG` clears an old export. Without a tag compose falls back to `local`, an image
that does not exist, and builds the tree as it stands.

`WORKBENCH_APP_URL` and `WORKBENCH_CORS_ORIGINS` hold `https://` and the tunnel's name. The API's per-address limits read
`Cf-Connecting-Ip`, which Cloudflare's edge sets to the visitor's address (a client that sends its own is refused at the
edge) and only cloudflared can reach the API to pass on; this is the workstation's arrangement. A run's stream sends a
keep-alive every 15 s, inside the edge's 100-125 s. An upload that declares more than 25 MB is refused before its body is
read, since no Caddy stands in front.

## Rollback and moving the public name

- **Back to the previous release on this host:** in `/opt/verity/deploy/cloud`, `unset VERITY_TAG`, set
  `VERITY_TAG=<previous short sha>` in `.env`, then `docker compose up -d`. Seconds; the store stays. (A schema change
  in between: README.md, Rollback.) If that release's images were removed, build them in a clean directory, never by
  unpacking over `/opt/verity` (tar removes nothing, so the newer release's files would stay in the build): unpack its
  archive into `/opt/verity-<previous sha>`, copy `.env` (only; the tunnel credential is not needed to build) into its
  `deploy/cloud`, set its `VERITY_TAG` there, and run only the build there,
  `BUILDX_NO_DEFAULT_ATTESTATIONS=1 VERITY_BUILD_SHA=<previous sha> docker compose build`; then switch the tag in
  `/opt/verity/deploy/cloud/.env` and `docker compose up -d` as above.
- **Moving a live name here (cutover):** first point this stack at the name: in `.env` set
  `WORKBENCH_APP_URL=https://<name>` and `WORKBENCH_CORS_ORIGINS=https://<name>`, then `docker compose up -d`. Only
  the API recreates (the interface reads no `.env` and names no host; no rebuild); the store stays. `VERITY_SITE` is
  Caddy's and unused here, and the tunnel's ingress names no host, so nothing else changes. Then, in Cloudflare DNS,
  edit the name's CNAME target from the old tunnel's `<old id>.cfargotunnel.com` to `<this id>.cfargotunnel.com`
  (proxied); `cloudflared tunnel route dns --overwrite-dns <tunnel> <name>` does the same. Visitors start fresh here:
  no store is moved. From the `.env` change on, the API refuses changes sent from the staging name's pages (it checks
  the Origin header), so check through the new name once it moves.
- **Moving it back (rollback):** edit the same record's target back to the old tunnel. Keep the old origin running, with
  its connector up, until the move back is no longer wanted.

## Cost

The VM: about $7 a month. Modal: billed per second while a GPU container runs, from the workspace's credits; its usage
limit, set at the credits, stops the endpoint before anything is charged to a card. Measured on staging: a cold start
95-168 s, about $0.05 a question with wake-ups and idle tails, warm questions a few seconds of GPU.

A reader who adds a contract or starts a question wakes the model ahead of it (WORKBENCH_MODEL_WAKEUP; opening one from a
link or a recorded run wakes nothing): a cold start and five idle minutes after the last answer, about $0.12, answered or
not, at most WORKBENCH_MODEL_WAKEUPS_PER_DAY (10) a day and three an hour per address. A month of the worst case, every
wake-up and every one of the 15 questions on its own cold start, is more than the $30 usage limit; the limit is then the
stop: answers pause until the month renews, nothing is charged, and the pages, /break and /state keep working.
