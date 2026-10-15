# Verity on one small VM behind a Cloudflare Tunnel (Hetzner CAX11, staging since 2026-10-13)

The same compose stack as README.md, on a host with no inbound port for visitors: the edge is the `tunnel` profile (a
cloudflared connector, as on the workstation) instead of Caddy. The model is the Modal endpoint of README.md
(modal_ollama.py). Everything README.md says about the store, retention, recovery and spend holds here; this file says
only what differs. The file keeps its first name: it was written for Oracle Always Free, which on 2026-10-13 had no A1
capacity in any availability domain for any size (Oracle's Compute Capacity Report API), so the host is a Hetzner VM.

## The VM

- Hetzner Cloud CAX11 in hel1 (Helsinki): Arm64, 2 vCPU, 4 GB, 40 GB, Ubuntu 24.04, about $7 a month with its IPv4
  address, billed by the hour; the x86 CX23 was unavailable. No backups (a copy of the store holds visitors' contracts past the deletion the
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

## Releases, on the VM

A release is the committed source of one commit, unpacked once into a directory of its own and never edited:
`/opt/verity/releases/<full sha>`. What belongs to the host and outlives releases lives beside them in
`/opt/verity/shared` (mode 700): `.env`, `tunnel.json` and the frozen `contract-state.json`. `/opt/verity/current` is a
link to the release that runs. Until 2026-10-13 each archive was unpacked over `/opt/verity` itself: tar removes
nothing, so a file a commit deleted stayed in the next build's context, and `.env` and the tunnel credential sat inside
the source tree (release integration, 2026-10-13).

Native, from the commit under test, which need not be pushed. On the build machine, the archive holds exactly the
commit, and never a secret:

```bash
SHA=$(git rev-parse <commit>)                                   # the full commit: names the directory, the archive and the label
git archive --format=tar.gz -o verity-$SHA.tar.gz $SHA          # committed files only: no .env, no store, no build output
tar -tzf verity-$SHA.tar.gz | grep -E '(^|/)(\.env[^/]*|tunnel\.json|[^/]*\.db)$' && echo STOP   # must print nothing
scp verity-$SHA.tar.gz root@<vm>:/opt/verity/archives/
```

On the VM, first time only (`apt-get install -y docker.io docker-compose-v2` before it):

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
(below) is a new store, `VERITY_STORE=verity_production`, empty, which the API creates on its first start. Changing role
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
  `/opt/verity/current/deploy/cloud`. The API recreates on an empty store (Stores, above); the staging store stays on
  the disk, unused, until it is deliberately removed. The interface reads no `.env` and names no host: no rebuild. `VERITY_SITE` is
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
