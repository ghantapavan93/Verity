# Publishing the workbench for one audience

The stack that was measured is the stack that is published: the FastAPI process on this machine, the
Next production build beside it, Qwen3 8B through Ollama, one SQLite store. A named Cloudflare Tunnel
connects outward from this machine and answers `https://ivo.pavankg.dev`; Cloudflare Access in front of
it decides who may open the page. Nothing in the application changes for this: the API reads its
origin settings from the environment, the interface bakes the API origin in at build time, and access
control lives at the deployment boundary, not in the product.

```
person with an allowed email
        │
        ▼
https://ivo.pavankg.dev            Cloudflare Access (email allowlist), then the named tunnel
        │
        ├── /api/*     → 127.0.0.1:8000   FastAPI (uvicorn), WORKBENCH_APP_URL=https://ivo.pavankg.dev
        └── /*         → 127.0.0.1:3900   Next production build, NEXT_PUBLIC_API_URL=https://ivo.pavankg.dev
                                │
                                └── 127.0.0.1:11434   Ollama, qwen3:8b
```

One hostname carries both, by path (`deploy/cloudflared.yml`), rather than an `ivo-api` hostname
beside it. With Access in front, a second API hostname would answer the browser's `fetch` and
`EventSource` calls with a redirect to the login page, which cross-origin requests cannot follow;
on one hostname every API call is same-origin, carries the Access session, and the event stream
that follows a run works as it does locally. A temporary `trycloudflare.com` quick tunnel is not
used: it does not carry server-sent events, and the run follower depends on them.

## Once, by Pavan (the Cloudflare account is his)

```powershell
$cf = "$env:LOCALAPPDATA\Programs\cloudflared\cloudflared.exe"    # cloudflared 2026.9.1, portable
& $cf tunnel login                                                   # opens the browser; choose the pavankg.dev zone
& $cf tunnel create ivo-workbench                                    # writes ~/.cloudflared/<id>.json
& $cf tunnel route dns ivo-workbench ivo.pavankg.dev                   # the CNAME, proxied
```

Then, in the Cloudflare dashboard, Zero Trust → Access → Applications → add a self-hosted
application for `ivo.pavankg.dev` (every path), with one policy, action Allow, include Emails:
Pavan's address and the addresses the link is sent to; or Emails ending in `@ivo.ai` if any Ivo
employee should be able to open it. Session duration: a day is enough. Nothing else on the account
needs to change; the tunnel opens no inbound port and the machine's address is not published.

## Every time

```powershell
cd <the checkout>
powershell -ExecutionPolicy Bypass -File deploy\up.ps1        # API in production settings, Next build + start, the tunnel
powershell -ExecutionPolicy Bypass -File deploy\down.ps1      # stops the three
powershell -ExecutionPolicy Bypass -File deploy\up.ps1 -Local # the same without the tunnel, against localhost, to check the build
```

`up.ps1` refuses to start over a dev server on 8000 or 3900, writes each process's output under
`backend/data/logs/deploy/`, waits until both the API and the interface answer, and records the
process ids for `down.ps1`. Ollama must already be running with `qwen3:8b` pulled; the API's health
line says so. The machine must stay awake for as long as the link is live (power settings, or the
desktop app's keep-awake).

## Before the link is sent: the smoke test, from a device that is not the development browser

1. Open `https://ivo.pavankg.dev` in a private window or on a phone.
2. Authenticate at the Access page with an allowed email.
3. Load a licensed agreement: "try a sample agreement" (Common Paper CSA, CC BY 4.0), or upload one.
4. Add guidance and ask the Phase 1 question (`docs/DEMO-PROOF.md`).
5. Watch the stages arrive through the event stream, not through polling (the network panel shows
   one `/events` request held open, no `/detail` polling every three seconds).
6. Open the finding's evidence: the four layers (Model proposed · Source · Code decided · Human), then "Prove it".
7. Click the citation: the document scrolls and the passage is marked.
8. Open Runs, open the run, download the evidence pack, run its `verify.py`.
9. Ask another question and reload the page while the run is checking: it reattaches.
10. Leave it running for several hours and open the URL again.

If those pass, stop. The hero run is the Phase 1 run in this store
(`/?document=7b8ed34fd627491c&run=e5a20e2283e8416e`): the model proposed `pass`, cited the wrong
part, code found the quote elsewhere and decided `needs_review` from sixty days against a ninety-day
floor. It is not to be replaced by a cleaner one.

## The gate inside the application (built 2026-10-02; switched on only by the steps below)

Cloudflare Access asks a reader for an email and then a one-time code. For someone following a link in a message
that is two screens too many. The application now has a gate of its own (`backend/app/api/access.py`), so the tunnel
can publish the host without Access and the store is still not public:

```
invite link     https://ivo.pavankg.dev/?document=…&run=…#invite=<token>     one per reader, made by scripts/access.py
on arrival      the page exchanges the token for a session cookie and removes it from the address bar
session         __Host-verity_session: Secure, HttpOnly, SameSite=Strict, seven days
every route     401 without the session: /api/documents, /api/runs, the event stream, memos, evidence packs, all of them
open routes     /api/health (says only up or down, and that an invite is needed) and /api/access (the exchange)
```

The token is in the fragment, which a browser never sends, so it is in no server log, no Cloudflare log and no
Referer; a link scanner that fetches the URL exchanges nothing. It is not single-use, on purpose: mail and chat
clients open links before people do. It expires (14 days by default), names one reader, and that reader can be
revoked. There is no password, no account and no signup. The exchange is limited to ten attempts in ten minutes per
address and run creation to twenty in ten minutes per reader.

The gate is on when `backend/data/access.secret` exists (the supervisor reads it into `WORKBENCH_ACCESS_SECRET` at
every start) and off when it does not, which is how a laptop, the tests and the browser flows run. `/api/health`
reports `access`: `off`, `required` or `entered`.

### Switching over, in this order, so the store is never open

```powershell
cd backend
.venv\Scripts\python scripts\access.py secret                      # 1. writes backend\data\access.secret; never printed
cd ..
powershell -ExecutionPolicy Bypass -File deploy\down.ps1
powershell -ExecutionPolicy Bypass -File deploy\install-supervision.ps1 -Build   # 2. new build, API restarted with the gate on, Access still in front
curl.exe -s http://127.0.0.1:8000/api/health                        # 3. must say "access":"required"
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/api/runs # 4. must say 401; so must /api/documents and a run's /events
cd backend
.venv\Scripts\python scripts\access.py invite pavan --path "/?document=7b8ed34fd627491c&run=e5a20e2283e8416e"
```

5. Open that link in a browser that is already through Access: the hero run opens, the address bar has no
   `#invite`, a new question runs, the stages arrive over the event stream, the memo and the evidence pack download.
6. Only now, in the Cloudflare dashboard: remove the Access application for `ivo.pavankg.dev` (or set its policy to
   Bypass). The tunnel stays as it is.
7. In a private window, with no invite: the page shows "Private engineering preview" and nothing else.
8. From anywhere: `curl.exe -s -o NUL -w "%{http_code}" https://ivo.pavankg.dev/api/runs` says 401, and so do
   `/api/documents` and `/api/runs/<id>/events`.
9. In that private window, open the invite link: the hero run, an upload and a real run all work.
10. Make one invite per reader (`scripts\access.py invite <name> --path "…"`), send each to that reader only, and stop.

To take one reader's access away, add the name to `backend\data\access.revoked` (one per line) and restart the API;
to take everyone's, `scripts\access.py secret --replace` and restart. If anything in steps 3 to 5 is not as written,
leave Access where it is: with Access on, the gate being on or off exposes nothing.

What the gate does not do: it does not tell the application who a reviewer is (a finding is still confirmed under
a typed name), it does not add the security headers listed below, and it is a signed link, so whoever holds the
link holds the access until it expires or is revoked.

## What is deliberately not done here

No nginx or Caddy, no second hostname, no rate limiting beyond what Access gives, no separate data
directory for the public instance: the store the Ivo engineer opens is the store the measurements
were made in, so Runs shows the real record.

## What protects it, and what does not (measured 2026-10-02)

At the edge, Cloudflare: HTTPS only (`http://` answers 301; `.dev` is on the browsers' HSTS preload
list), and Access in front of every path, so a request without a session is a 302 to the sign-in
page, for the interface and for `/api` alike, and a preflight from another origin is a 403. Nothing
is cached at the edge (`cf-cache-status: DYNAMIC` on the page, the API and an evidence pack).

In the application: no authentication of its own. Whoever passes Access can do everything, and the
application does not read who passed (a reviewer's name is what the browser sent). CORS allows the
one public origin; both servers listen on 127.0.0.1 only. The application sends no
`Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options` or `Referrer-Policy`, and the
interface still says `X-Powered-By: Next.js`: known, not fixed here.

Logs under `backend/data/logs/deploy/` carry request ids, paths without query strings, statuses,
durations, run and document ids, stages and restart events, and no contract text, guidance, prompt,
model output or credential (searched for each on 2026-10-02). There is no rotation: one file per
start, 745 KB after two days.

## Keeping the two servers up (2026-10-01)

On 2026-10-01 the API process ended at 02:37 with no log line and no event in Windows' logs, and the link was down
until a person noticed. The published stack now runs under two supervisors, one per server, registered as Scheduled
Tasks that start at logon under the signed-in account (the laptop stays logged in for the outreach window):

```powershell
powershell -ExecutionPolicy Bypass -File deploy\install-supervision.ps1 -Build    # build for the public origin (and the finished review the first screen offers, -ProofRun, default the Phase 1 run), register "Verity API" and "Verity Web", start both, wait for health
powershell -ExecutionPolicy Bypass -File deploy\down.ps1                          # write the stop files and stop both servers; the supervisors exit instead of restarting
powershell -ExecutionPolicy Bypass -File deploy\install-supervision.ps1           # start again (removes the stop files; no rebuild)
powershell -ExecutionPolicy Bypass -File deploy\install-supervision.ps1 -Uninstall
```

`-Build` also bakes the commit it builds from into the interface (`NEXT_PUBLIC_BUILD_SHA`), which the Runs surface shows
as "Interface built from commit …", so a reader can check that the deployed interface is the committed HEAD without
an endpoint for it. Both servers listen on 127.0.0.1 only; the connector is their only client.

Replaying the browser flows on this machine (`npm run e2e`) no longer touches the served bundle: they build into
`.next-e2e` (playwright.config.ts sets `NEXT_DIST_DIR`), so `.next` stays the build the supervisor started.

What this is, and is not: a laptop that restarts a server that died, while its owner is logged in. It is
not high availability. Measured on a second instance with its own tag, port and store (2026-10-02): a
port held by another process was retried at 5, 10, 20 and 40 s and the server came up by itself when
the port was freed; a killed server was restarted; a stale pid file was overwritten; a stop file kept
a new supervisor from starting. And the limits: if the supervisor itself is killed, the server it
started keeps answering and nothing restarts that server when it dies (the tasks have no
restart-on-failure setting and one trigger, logon). A logoff ends both tasks; after a reboot nothing
runs until the account logs in, and until then the connector, a system service, answers 502.

Copying the store: the database runs in WAL mode, and on 2026-10-02 the `-wal` file beside it held
4 MB that a copy of `workbench.db` alone would have missed. A copy that is whole is made with SQLite's
online backup (`sqlite3 workbench.db ".backup copy.db"`, or `Connection.backup` in Python) plus the
`documents/` and `memos/` directories. That was tested, not automated: the copy opened under the
application in another directory, the proof run and its explanation read back, its input rebuilt to
the recorded hash, all four memos served with matching hashes, and 31 evidence packs from old and new
runs verified themselves. Nothing schedules a backup.

`deploy/supervise.ps1 -Name api|web` is the whole mechanism: start the server with its stdout and stderr in a stamped
file under `backend/data/logs/deploy/`, wait for it to exit, write the exit code and how long it ran to
`<name>.supervisor.log`, start it again after a delay that doubles from 5 s to 60 s while it keeps dying within a
minute. A stop file ends the supervisor. The pid of the running server is in `<name>.pid`. No service manager, no
wrapper binary: a 70-line script and the task scheduler that ships with Windows. The connector (`cloudflared`) is
already a Windows service started by the system and is not part of this.

Demonstrated on 2026-10-01 (`<name>.supervisor.log`): a forced exit of the API restarted it within five seconds with
both the exit and the restart recorded; `down.ps1` stopped it and the supervisor exited on the stop file; a server
that cannot start (its port held by another process) was retried at 5, 10, 20, 40 and 60 s, never in a tight loop.
