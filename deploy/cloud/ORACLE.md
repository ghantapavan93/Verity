# Verity on Oracle Always Free: one ARM VM behind a Cloudflare Tunnel

The same compose stack as README.md, on a host with no inbound port: the edge is the `tunnel` profile (a cloudflared
connector, as on the workstation) instead of Caddy. The model is the Modal endpoint of README.md (modal_ollama.py),
unchanged. Everything README.md says about the store, retention, recovery and rollback holds here; this file says only
what differs.

## The VM

- Shape `VM.Standard.A1.Flex`, 2 OCPUs and 12 GB (the Always Free allowance since June 2026), Ubuntu 24.04 aarch64,
  the default boot volume, no backup policy: a copy of the store holds visitors' contracts past the deletion the first
  screen promises (README.md: what the disk keeps).
- A public IPv4 address for SSH only. The security list keeps its single ingress rule, TCP 22, and that from the
  owner's address alone; nothing serves on 80 or 443. Visitors reach the stack through the tunnel, which dials out.
- An account with no payment method cannot be charged; an upgraded one bills anything beyond the allowance. Check the
  shape says "Always Free-eligible" before Create.
- Oracle may stop an Always Free VM that stays idle for seven days (CPU p95, network and memory all under 20%). Nothing
  here generates load to prevent it. A stop keeps the boot volume; start the VM from the console and the stack comes
  back by itself (`restart: unless-stopped`, Docker enabled at boot).

## The tunnel

One tunnel per host, never shared: Cloudflare sends each request to the nearest connector of a tunnel, so a second
host's connector would put a second store behind the same name. On a machine with `cloudflared tunnel login` done:

```bash
cloudflared tunnel create verity-oracle                    # writes <id>.json beside cert.pem; keep it like a password
cloudflared tunnel route dns verity-oracle verity-staging.example.com
```

`route dns` creates a CNAME to `<id>.cfargotunnel.com` and refuses a name that already has a record. Moving an existing
name to this host is an edit of that record's target, made once the host has passed its acceptance; until then the
name's current origin keeps it.

## Build, on the VM

Native arm64; the image is built where it runs, from the commit under test, which need not be pushed. From the build
machine, the commit's tree, the frozen record and the tunnel's credentials:

```bash
git archive --format=tar.gz -o verity-<sha>.tar.gz <sha>
scp verity-<sha>.tar.gz contract-state.json ~/.cloudflared/<id>.json ubuntu@<vm>:~
```

On the VM:

```bash
sudo apt-get install -y docker.io docker-compose-v2 && sudo usermod -aG docker ubuntu   # then log in again
sudo mkdir -p /opt/verity && sudo chown ubuntu: /opt/verity && tar -xzf ~/verity-<sha>.tar.gz -C /opt/verity
cd /opt/verity && docker build --target test -f deploy/cloud/Dockerfile.api .   # the API suite on arm64; any failure stops here
cd deploy/cloud && mv ~/contract-state.json ~/<id>.json .
sha256sum contract-state.json                              # cff26179f199…; anything else: stop
mv <id>.json tunnel.json && sudo chown 65532:65532 tunnel.json && sudo chmod 400 tunnel.json   # cloudflared runs as 65532
cp env.example .env && chmod 600 .env                      # COMPOSE_PROFILES=tunnel, VERITY_TUNNEL_ID=<id>; the secret as env.example says
swapon --show                                              # nothing: no swap (README.md: the droplet)
BUILDX_NO_DEFAULT_ATTESTATIONS=1 VERITY_BUILD_SHA=<sha> docker compose build
docker compose up -d
```

`WORKBENCH_APP_URL` and `WORKBENCH_CORS_ORIGINS` hold `https://` and the tunnel's name. The API's per-address limits read
`Cf-Connecting-Ip`, which Cloudflare's edge sets to the visitor's address and only cloudflared can reach the API to
pass on; this is the workstation's arrangement. A run's stream sends a keep-alive every 15 s, inside the edge's 125 s.

## Cost

Oracle: nothing, within the allowance. Modal: billed per second while a GPU container runs, from the workspace's
credits; its usage limit, set at the credits, stops the endpoint before anything is charged to a card. The day's new
questions start at 15 (env.example) and rise only after the measured cost of a question, cold starts included, says the
month's limit holds.

A reader who adds a contract or starts a question wakes the model ahead of it (WORKBENCH_MODEL_WAKEUP; opening one from a
link or a recorded run wakes nothing): a cold start of about
three minutes and five idle minutes after the last answer, about $0.12 a visit at the L4's $0.96 an hour, answered or
not, and at most WORKBENCH_MODEL_WAKEUPS_PER_DAY (10) a day, about $1.20. Every further question in the same visit is
a few seconds of GPU. A month of the worst case, every wake-up and every one of the 15 questions on its own cold start,
is more than the $30 usage limit; the limit is then the stop: answers pause until the month renews, nothing is charged,
and the pages, /break and /state keep working. Measured demo traffic is a small fraction of that.
