# Working in this repository

`ENGINEERING_CONSTITUTION.md` is binding: where responsibility lives (the model proposes, deterministic code verifies,
the database freezes a finished run). Answer its five questions before every meaningful change. The rule under
everything: a finding may come from the model; a claim that its evidence is verified may only come from deterministic
code. Every sophisticated component earns its existence with a measured failure it fixes or an explicit requirement
from the product. `DECISIONS.md` records why things are the way they are; `docs/SYSTEM_MAP.md` maps the subsystems.

Fixed decisions, not open for re-litigation in a session:

- The visual system is frozen (`src/app/globals.css`). No theme switching, no extra pages, no dashboard cards, no
  marketing content, no agent diagrams, no onboarding tours.
- Dependencies are earned. No Postgres, pgvector, LangGraph, queues or agents without a measurement that shows the
  current choice failing, recorded in `DECISIONS.md`.
- The primary path is never mocked. Fake providers live in `backend/tests`, with one exception: the record/replay
  provider in `backend/app/providers/replay.py`, chosen only by `WORKBENCH_PROVIDER=record|replay`, never by default, so
  the browser flows run without a GPU. Nothing else in `app/` may answer for the model.
- The backend schema is the source of truth for types. After changing `backend/app/schemas.py`, run
  `python backend/scripts/export_openapi.py` then `npm run api:types`, and commit both generated files.
- Identity goes through `backend/app/hashing.py`. A test fails otherwise.
- A version of the policy, the verifier or retrieval changes only by hand: `backend/tests/test_semantic_versions.py`
  fails until the version is bumped or the fingerprint re-recorded with a reason.
- A prompt or retrieval change is judged by the golden set (`docs/GOLDENS.md`): keep it only if the set moves in its
  favour.
- Git is the owner's. Agents do not commit or push unless asked.

Checks before saying anything is done (the release gate, `scripts/release-gate.sh`, runs most of them on a fresh clone;
`docs/STATUS.md` says which it does not):

```
cd backend && python -m ruff format --check . && python -m ruff check . && python -m mypy && python -m pytest -q
npm run typecheck && npm run lint && npm run format:check && npm test
npm run e2e   # browser flows: builds the interface, replays the model's recorded answers; about three minutes
```

Record decisions as they are taken in `DECISIONS.md`. Keep `docs/STATUS.md` true: `backend/tests/test_docs_claims.py`
holds its counts and versions to the code.

Framework and library documentation, in this order of authority:

1. **Next.js: the installed docs win** (below).
2. **Other libraries (Playwright, FastAPI, SQLAlchemy, pydantic):** the documentation of the pinned version.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Project-specific Next.js rule

The installed Next.js documentation, `node_modules/next/dist/docs/` (the version `package.json` pins), is
authoritative for framework behaviour. Read it before writing framework code; not the web, not memory.

Reading it does not override `ENGINEERING_CONSTITUTION.md`. Framework conventions decide how Next.js
code is written; they never move domain truth, evidence verification, persistence rules, model
behaviour or a legal or business decision into a React component, a Server Component, a Route
Handler, a Server Action, middleware or any other framework primitive. What a framework can do does
not decide who owns it.

| Next.js and React own | FastAPI and the application layer own |
|---|---|
| presentation, interaction, URL state, SSE consumption, document rendering, motion, the command palette | run creation, retrieval, model invocation, verification, finding decisions, idempotency, memo generation, persistence |

Before introducing a new Next.js primitive:

1. Read the installed-version documentation for it.
2. Name the application responsibility it would serve.
3. Confirm that responsibility does not already belong to the FastAPI or application layer.
4. Prefer the smallest framework mechanism that keeps the ownership boundaries above.
