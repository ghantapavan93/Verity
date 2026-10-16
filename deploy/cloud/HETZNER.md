# Verity on one Hetzner server behind a Cloudflare Tunnel, the model on the same host

The compose stack of README.md on one host with no inbound port for visitors: the edge is the `tunnel` profile (a
cloudflared connector, as on the workstation), and the model is the `ollama` service beside the API. Everything
README.md says about the store, retention, recovery and limits holds here; this file says what is particular to the
host: the server, the model, releases, stores, the cutover and the cost. Nothing here has been bought or run yet for
production; a staging VM of 2026-10-13 (below) ran the same stack with the model elsewhere.

## The server

Chosen for the measured load (DECISIONS.md, 2026-10-16): an answer reads about 1,900 tokens of contract and writes
about 270 (p90 2,300 and 440, the most 880; 76 real answers of the blind stress test), one answer at a time.

- **Recommended: a dedicated AX42** (Germany): AMD Ryzen 7 PRO 8700GE, 8 cores with AVX-512, 64 GB DDR5, two 512 GB
  NVMe. CPU only. Install Ubuntu 24.04 with Hetzner's `installimage`, the two disks as software RAID 1, and delete the
  swap partition its default layout carries (`PART swap …`): no swap, below. The model runs
  on the CPU; its speed on this machine is the first thing measured once it is rented (below, What only the server can
  show), against the go/no-go of an answer's p90 within 120 s. For scale, the same container on the workstation's CPU
  (Ryzen 9 5900HX: Zen 3, 8 cores, DDR4-3200), 2026-10-16: 19.9 tokens a second read and 5.6 written, so at least
  144 s for the median answer and 194 s for the p90 (the probe's answer was short, and longer ones run slower per
  token), after a first load of 239 s. The AX42's DDR5 and AVX-512 should do better, by an amount only the server
  shows; even at the bound it is slower than the workstation's GPU today (a median 34.5 s in the blind stress test).
- **If the AX42 misses that bound: a dedicated GEX45** (Helsinki): NVIDIA RTX PRO 4000 Blackwell, 24 GB, the same
  model in GPU memory, with `compose.gpu.yml`, the NVIDIA driver and the NVIDIA Container Toolkit. An answer is then
  expected to take seconds (not measured here), and two or more could run at once (OLLAMA_NUM_PARALLEL and
  WORKBENCH_MODEL_CONCURRENCY raised together, measured first). Put `COMPOSE_FILE=compose.yml:compose.gpu.yml` in
  `/opt/verity/shared/.env` (env.example): every compose command then reads the GPU file, a rollback and a cutover
  included; without it the model is recreated on the CPU without a word.
- Not a Hetzner Cloud VM: the dedicated-vCPU line (CCX) was shown as unavailable on 2026-10-16, and its price after the
  2026 increases was above an AX42's; a shared VM of 2 vCPUs took 650-1,000 s an answer (README.md).
- No backups (a copy of the store holds visitors' contracts past the deletion the first screen promises), no swap.
- A firewall on the server (`ufw default deny incoming`, `ufw allow from <owner address> to any port 22`), or Hetzner's
  Robot firewall with the same rule: nothing serves on 80 or 443, since visitors reach the stack through the tunnel,
  which dials out. Outbound open (Cloudflare, Docker Hub, the Ollama registry, Ubuntu updates).
- SSH by key only: `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin prohibit-password`
  in `/etc/ssh/sshd_config.d/99-verity.conf`. `unattended-upgrades` on.
- The staging VM of 2026-10-13 (Hetzner Cloud CAX11, Arm64, 2 vCPU, 4 GB) cannot hold the model (its container used 6.3 GiB
  answering at the 16k context, in the rehearsal of 2026-10-16): it stays a staging host for the pages until the owner removes it.

## The model

The weights live in the `verity-models` volume, fetched once per host and checked against the pinned digest before the
host serves anyone. Once, after the first release is unpacked and `VERITY_TAG` is in `/opt/verity/shared/.env`
(Releases, below: compose checks the whole file, so the tag must be set even to start the model alone), and before the
`up` that starts the API:

```bash
cd /opt/verity/releases/<full sha>/deploy/cloud
docker compose --env-file /opt/verity/shared/.env up -d ollama
docker compose --env-file /opt/verity/shared/.env exec ollama ollama pull qwen3:8b
docker compose --env-file /opt/verity/shared/.env exec ollama ollama list   # ID must begin 500a1f067a9f; anything else: stop
```

On 2026-10-16 the registry's manifest for `qwen3:8b` hashed to 500a1f067a9f, the workstation's build. If it has moved,
do not serve it: copy the workstation's files for the pinned manifest instead. From the workstation's Ollama directory
(`~/.ollama/models`), copy `manifests/registry.ollama.ai/library/qwen3/8b` and each blob it names (`blobs/sha256-<hex>`,
the config and four layers) to `~/qwen3/` on the server, keeping their paths, then, in the release's `deploy/cloud`:

```bash
docker compose --env-file /opt/verity/shared/.env exec ollama mkdir -p /root/.ollama/models/blobs /root/.ollama/models/manifests/registry.ollama.ai/library/qwen3
for f in manifests/registry.ollama.ai/library/qwen3/8b $(cd ~/qwen3 && echo blobs/sha256-*); do   # the paths under ~/qwen3
  docker compose --env-file /opt/verity/shared/.env cp ~/qwen3/$f ollama:/root/.ollama/models/$f
done
docker compose --env-file /opt/verity/shared/.env exec ollama sh -c 'cd /root/.ollama/models && [ -s manifests/registry.ollama.ai/library/qwen3/8b ] || echo "STOP: no manifest"; for d in $(grep -o "sha256:[0-9a-f]\{64\}" manifests/registry.ollama.ai/library/qwen3/8b | sort -u); do h=${d#sha256:}; [ -f blobs/sha256-$h ] && [ "$(sha256sum blobs/sha256-$h | cut -d" " -f1)" = "$h" ] || echo "STOP: blobs/sha256-$h"; done'   # every blob the manifest names, present and whole
docker compose --env-file /opt/verity/shared/.env exec ollama ollama list   # ID must begin 500a1f067a9f
```

The API refuses to answer with any other build in either case (`WORKBENCH_MODEL_DIGEST`). A first
question after Ollama starts waits for the model to load into memory (`OLLAMA_KEEP_ALIVE=-1` keeps it there).

## The tunnel

One tunnel per host, never shared: Cloudflare sends each request to the nearest connector of a tunnel, so a second
host's connector would put a second store behind the same name. On a machine with `cloudflared tunnel login` done:

```bash
cloudflared tunnel create verity-hetzner                   # writes <id>.json beside cert.pem; keep it like a password
cloudflared tunnel route dns verity-hetzner verity-next.example.com   # a name of its own for acceptance, before any cutover
```

`route dns` creates a CNAME to `<id>.cfargotunnel.com` and refuses a name that already has a record. Moving an existing
name to this host is an edit of that record's target (below). The connector runs over HTTP/2 (compose.yml): over QUIC
every connection of the staging host dropped together for three minutes and a request was answered 502.

## Releases, on the server

A release is the committed source of one commit, unpacked once into a directory of its own and never edited:
`/opt/verity/releases/<full sha>`. What belongs to the host and outlives releases lives beside them in
`/opt/verity/shared` (mode 700): `.env`, `tunnel.json` and the frozen `contract-state.json`. `/opt/verity/current` is a
link to the release that runs. Until 2026-10-13 each archive was unpacked over `/opt/verity` itself: tar removes
nothing, so a file a commit deleted stayed in the next build's context, and `.env` and the tunnel credential sat inside
the source tree (release integration, 2026-10-13).

The public name serves only a commit that is on main and passed the release gate; the acceptance name may serve a
candidate first. On the build machine, the archive holds exactly the commit, and never a secret:

```bash
SHA=$(git rev-parse <commit>)                                   # the full commit: names the directory, the archive and the label
git archive --format=tar.gz -o verity-$SHA.tar.gz $SHA          # committed files only: no .env, no store, no build output
tar -tzf verity-$SHA.tar.gz | grep -E '(^|/)(\.env[^/]*|tunnel\.json|[^/]*\.db)$' && echo STOP   # must print nothing
scp verity-$SHA.tar.gz root@<server>:/opt/verity/archives/
```

On the server, first time only (`apt-get install -y docker.io docker-compose-v2` before it):

```bash
install -d -m 700 /opt/verity /opt/verity/shared /opt/verity/releases /opt/verity/archives
cp ~/contract-state.json /opt/verity/shared/ && sha256sum /opt/verity/shared/contract-state.json   # cff26179f199…; anything else: stop
install -o 65532 -g 65532 -m 400 ~/<id>.json /opt/verity/shared/tunnel.json && rm ~/<id>.json   # cloudflared runs as 65532; one copy on the host, never in git or an image
# .env from the release's env.example, filled in once (COMPOSE_PROFILES=tunnel, VERITY_TUNNEL_ID=<id>, the secret as
# env.example says, VERITY_SHARED=/opt/verity/shared, VERITY_STORE as under Stores below); mode 600
swapon --show                                                   # nothing: no swap
```

On the staging host as it was before 2026-10-13 (each archive unpacked over `/opt/verity`; `.env`, `tunnel.json` and
`contract-state.json` in `/opt/verity/deploy/cloud`), once, in place of the block above:

```bash
O=/opt/verity/deploy/cloud
install -d -m 700 /opt/verity/shared /opt/verity/releases /opt/verity/archives
cp -p $O/.env $O/tunnel.json $O/contract-state.json /opt/verity/shared/   # -p keeps tunnel.json's owner (65532) and mode
printf '\nVERITY_SHARED=/opt/verity/shared\nVERITY_STORE=verity_verity-data\n' >> /opt/verity/shared/.env && chmod 600 /opt/verity/shared/.env   # the leading newline: the old file may not end in one
docker volume inspect -f '{{.Name}} {{.CreatedAt}}' verity_verity-data   # the store it has; absent: stop
```

Its first release then runs as below, under the same compose project (`name: verity`), so `up` replaces the running
containers and opens the same store. Once that release is verified, `rm $O/.env $O/tunnel.json`: compose run from the
old tree reads an unnamed `verity-data` (`verity_verity-data`) and ignores `VERITY_STORE`, and without its `.env` it
cannot start at all. The rest of the old tree is read by nothing and stays until the owner removes it.

Each release:

```bash
SHA=<full sha>; TAG=${SHA:0:7}; R=/opt/verity/releases/$SHA
df -h / && docker system df                                     # before: at least 8 GB free on /, or prune old images first
test ! -e $R || { echo "$R exists: a release directory is never reused"; exit 1; }
mkdir -m 755 $R && tar -xzf /opt/verity/archives/verity-$SHA.tar.gz -C $R
cd $R && docker build --target test -f deploy/cloud/Dockerfile.api .   # the API suite on this CPU; any failure stops here
cd $R/deploy/cloud
VERITY_TAG=$TAG VERITY_BUILD_SHA=$SHA BUILDX_NO_DEFAULT_ATTESTATIONS=1 \
  docker compose --env-file /opt/verity/shared/.env build
for image in verity-api:$TAG verity-web:$TAG; do                # each image names the commit it holds, whole
  test "$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' $image)" = "$SHA" || echo "STOP: $image"
done
VERITY_TAG=$TAG docker compose --env-file /opt/verity/shared/.env run --rm --no-deps --entrypoint python api -c \
  "import sqlite3; c = sqlite3.connect('file:/data/workbench.db?mode=ro', uri=True); print(sorted(r[1] for r in c.execute('pragma table_info(run_stages)')))"
# the store's columns before the switch: compare with what the release adds (Rollback, below). Read-only: on a new
# store there is nothing yet ("unable to open database file") and nothing to compare.
sed -i "s/^VERITY_TAG=.*/VERITY_TAG=$TAG/" /opt/verity/shared/.env && grep ^VERITY_TAG= /opt/verity/shared/.env
ln -sfn $R /opt/verity/current                                  # the switch: one link
# The first release on a host only: fetch and check the model now (The model, above), before this up starts the API.
cd /opt/verity/current/deploy/cloud && docker compose --env-file /opt/verity/shared/.env up -d --no-build
docker builder prune -f --filter until=72h && df -h / && docker system df   # after: the build cache grows with every release
```

`up --no-build` runs only the images this release built and labelled; `pull_policy: never` keeps compose from asking a
registry for a `verity-api` it does not have, and a missing tag stops it (compose.yml). `unset VERITY_TAG` first if the
shell exported one: an exported value wins over `--env-file`. Every compose command on this host, those README.md gives
included (the owner's pause, logs, `down`), runs in `/opt/verity/current/deploy/cloud` with
`--env-file /opt/verity/shared/.env`; without it compose stops at the missing `VERITY_STORE` and `VERITY_TAG`.

### Stores

The store is a Docker volume named in `.env` (`VERITY_STORE`), required by compose.yml. A role has its own store: the
staging host of 2026-10-13 keeps the volume it already has, `VERITY_STORE=verity_verity-data`; serving the public name
(below) is a new store, `VERITY_STORE=verity_production`, empty, which the API creates on its first start. The new
host's acceptance, on its own name before any cutover, runs on a store of its own, `VERITY_STORE=verity_acceptance`: the
acceptance name is for the owner and invited testers, not the public, and its store is the owner's to delete at the
cutover, when its retention stops. Changing role
never moves, copies or deletes a store; the staging store stays on the disk until it is deliberately removed, by the
owner, as the visitor data it is. A visitor's data is never migrated between stores.

Each build is kept under its commit (`docker image ls verity-*`), and each release directory under its full commit.
Keep at least the previous release's images and directory: the way back below needs them. Remove older ones with
`docker image rm` and `rm -r /opt/verity/releases/<old sha>` (never the one `current` points to). Without a tag compose
refuses to start (the tag is required in compose.yml); it used to fall back to `local`, a stale build. Remove any left
over: `docker image rm verity-api:local verity-web:local`.

`WORKBENCH_APP_URL` and `WORKBENCH_CORS_ORIGINS` hold `https://` and the tunnel's name. The API's per-address limits read
`Cf-Connecting-Ip`, which Cloudflare's edge sets to the visitor's address (a client that sends its own is refused at the
edge) and only cloudflared can reach the API to pass on; this is the workstation's arrangement. A run's stream sends a
keep-alive every 15 s, inside the edge's 100-125 s. Every request body is cut off where its route's need ends, declared
or not, before its route or gate reads it (`api/body_limit.py`: 26 MiB for an upload, 1 MiB otherwise), since no Caddy
stands in front.

## Rollback and moving the public name

- **Back to the previous release on this host:** `sed -i "s/^VERITY_TAG=.*/VERITY_TAG=<previous short sha>/"
  /opt/verity/shared/.env`, `ln -sfn /opt/verity/releases/<previous full sha> /opt/verity/current`, then in
  `/opt/verity/current/deploy/cloud` `docker compose --env-file /opt/verity/shared/.env up -d --no-build`. Seconds; the
  store stays. A release may add to the store's schema: the earlier release must read the store as it now is. From
  6814c50 to the release of 2026-10-13 the only addition is one nullable column, `run_stages.rounds` (an older
  release does not select it and reads every row as before); any other schema change needs its own check before the
  switch back, and a backup is not the answer here (README.md, Backups). If the earlier release's images were
  removed, rebuild them from its own release directory, never from another's: its directory is untouched, so the
  build is the one it was.
- **Back to a release from before this layout** (6814c50 and be703a6 were unpacked over `/opt/verity` and have no
  release directory): keep `current` and change only `VERITY_TAG` to its short commit, then `up -d --no-build` as
  above. This release's compose.yml runs the old images, still on the host, against the store `VERITY_STORE` names.
  Never run compose from the old tree (`/opt/verity/deploy/cloud`): its compose.yml ignores `VERITY_STORE` and opens
  `verity_verity-data`, the staging store, whatever role the host now has.
- **Moving a live name here (cutover):** first point this stack at the name and at a store of its own: in
  `/opt/verity/shared/.env` set `WORKBENCH_APP_URL=https://<name>`, `WORKBENCH_CORS_ORIGINS=https://<name>` and
  `VERITY_STORE=verity_production`, then `docker compose --env-file /opt/verity/shared/.env up -d --no-build` in
  `/opt/verity/current/deploy/cloud`. The API recreates on an empty store (Stores, above). The store it served before
  (`verity_acceptance` on a new host, `verity_verity-data` on the staging host) stays on the disk, unused, and its
  retention stops with the switch: what it holds (the acceptance runs, or the staging visitors') is the owner's to
  delete. The interface reads no `.env` and names no host: no rebuild. `VERITY_SITE` is
  Caddy's and unused here, and the tunnel's ingress names no host, so nothing else changes. Then, in Cloudflare DNS,
  edit the name's CNAME target from the old tunnel's `<old id>.cfargotunnel.com` to `<this id>.cfargotunnel.com`
  (proxied); `cloudflared tunnel route dns --overwrite-dns <tunnel> <name>` does the same. Visitors start fresh here:
  no store is moved. From the `.env` change on, the API refuses changes sent from the staging name's pages (it checks
  the Origin header), so check through the new name once it moves.
- **Moving it back (rollback):** edit the same record's target back to the old tunnel. Keep the old origin running, with
  its connector up, until the move back is no longer wanted. A store's retention runs only while its API runs: keep the
  origin that no longer serves the name running eight days more (seven, and its hourly passes to spare), and its
  visitors' workspaces end as promised; stop it
  sooner and what its store still holds is the owner's to delete.

## What only the server can show (before any cutover)

On the acceptance name (The tunnel), with the release's images and the pinned model, before the public name moves:

1. **The model's speed on this host.** The blind stress test's fifteen questions, DOCX and PDF, timed from question to
   answer, and the first answer after Ollama starts. Go: p90 within 120 s on the AX42. Otherwise the GEX45.
2. **HTTPS and browsers.** Through the tunnel, in Chromium and in Safari/WebKit: the `__Host-` session survives a reload,
   a question is answered and its evidence opens, the evidence pack saves as `evidence-<run>.zip`, the memo's `.docx`
   opens, a phone shows one pane at a time.
3. **Two visitors at once.** Two browsers on two addresses ask together: one answers, the other waits its turn and then
   answers; neither can read the other's runs; the per-address limit reads Cf-Connecting-Ip. While an answer computes on
   the CPU, pages and a 25 MB upload still answer within their limits (not measured: the rehearsal's VM stopped
   answering before it could be); if they do not, the model's share of the cores is bounded and measured again, as a
   change of its own.
4. **The acceptance script** (`acceptance.mjs`, with `BASE` the acceptance name and `SHA` the release) on the real model,
   then fresh PDF and DOCX uploads asked about, the amendment challenge, /break and /state.
5. **Recovery on the host.** Each container restarted, Ollama stopped and started, a reboot, the API frozen (liveness),
   the owner's pause, and the retention purge of an ended workspace: the stack returns, the store intact, the model
   loaded again. The rehearsal of 2026-10-16 reached only Ollama stopped and started on this layout.
6. **Provenance.** `docker image inspect` labels of both images name the release's full commit, which is on main, and the
   Runs page names the same commit.

## Cost

One monthly price; nothing is billed per question. List prices as reported on 2026-10-16, excluding VAT, to be read
again in Hetzner's Robot before ordering (Hetzner raised prices twice in 2026):

| | Monthly | One-time setup | Notes |
|---|---|---|---|
| AX42 (recommended) | €97.30 | €49 | Germany; a primary IPv4 address may be charged on top |
| GEX45 (if the CPU misses the bound) | €214 | €209 | Helsinki |
| Staging CAX11 of 2026-10-13 | about $7 | none | already running; the owner removes it once it is not wanted |
| Cloudflare (DNS, tunnel) | free | none | the existing zone |

No backups are bought (README.md: backups and retention). A dedicated server is billed by the month, not by the hour.
