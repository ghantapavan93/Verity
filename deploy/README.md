# Publishing the workbench for one audience

The stack that was measured is the stack that is published: the FastAPI process on this machine, the
Next production build beside it, Qwen3 8B through Ollama, one SQLite store. A named Cloudflare Tunnel
connects outward from this machine and answers `https://ivo.pavan.dev`; Cloudflare Access in front of
it decides who may open the page. Nothing in the application changes for this: the API reads its
origin settings from the environment, the interface bakes the API origin in at build time, and access
control lives at the deployment boundary, not in the product.

```
person with an allowed email
        │
        ▼
https://ivo.pavan.dev            Cloudflare Access (email allowlist), then the named tunnel
        │
        ├── /api/*     → 127.0.0.1:8000   FastAPI (uvicorn), WORKBENCH_APP_URL=https://ivo.pavan.dev
        └── /*         → 127.0.0.1:3900   Next production build, NEXT_PUBLIC_API_URL=https://ivo.pavan.dev
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
& $cf tunnel login                                                   # opens the browser; choose the pavan.dev zone
& $cf tunnel create ivo-workbench                                    # writes ~/.cloudflared/<id>.json
& $cf tunnel route dns ivo-workbench ivo.pavan.dev                   # the CNAME, proxied
```

Then, in the Cloudflare dashboard, Zero Trust → Access → Applications → add a self-hosted
application for `ivo.pavan.dev` (every path), with one policy, action Allow, include Emails:
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

1. Open `https://ivo.pavan.dev` in a private window or on a phone.
2. Authenticate at the Access page with an allowed email.
3. Load a licensed agreement: "try a sample agreement" (Common Paper CSA, CC BY 4.0), or upload one.
4. Add guidance and ask the Phase 1 question (`docs/DEMO-PROOF.md`).
5. Watch the stages arrive through the event stream, not through polling (the network panel shows
   one `/events` request held open, no `/detail` polling every three seconds).
6. Open the finding's evidence and "Why this answer?".
7. Click the citation: the document scrolls and the passage is marked.
8. Open Runs, open the run, download the evidence pack, run its `verify.py`.
9. Ask another question and reload the page while the run is checking: it reattaches.
10. Leave it running for several hours and open the URL again.

If those pass, stop. The hero run is the Phase 1 run in this store
(`/?document=7b8ed34fd627491c&run=e5a20e2283e8416e`): the model proposed `pass`, cited the wrong
part, code found the quote elsewhere and decided `needs_review` from sixty days against a ninety-day
floor. It is not to be replaced by a cleaner one.

## What is deliberately not done here

No nginx or Caddy, no second hostname, no rate limiting beyond what Access gives, no separate data
directory for the public instance: the store the Ivo engineer opens is the store the measurements
were made in, so Runs shows the real record. The four commits behind this deployment are local
until the link has been inspected; pushing is a separate decision.
