@AGENTS.md

# Working in this repository

`ENGINEERING_CONSTITUTION.md` is binding. Read it before changing anything, and answer its five
questions before every meaningful change. The rule under everything: a finding may come from the
model; a claim that its evidence is verified may only come from deterministic code. The second
rule: every sophisticated component must earn its existence with either a measured failure it
fixes or an explicit requirement from the product.

Before broad repository exploration, read `docs/SYSTEM_MAP.md`. Re-read source files only for the
subsystem being changed or when the map's recorded commit is stale. Never perform a broad rewrite
because the map is stale: first update the relevant map entry by reading the owning implementation,
then make the smallest change inside the existing ownership boundary.

Fixed decisions, not open for re-litigation in a session:

- The visual system is frozen (shell C in `src/app/globals.css`). No theme switching, no extra
  pages, no dashboard cards, no marketing content, no agent diagrams, no onboarding tours.
- Dependencies are earned. No Postgres, pgvector, LangGraph, queues or agents without a
  measurement that shows the current choice failing. Record the measurement in `DECISIONS.md`.
- The primary path is never mocked. Fake providers live in `backend/tests`, with one exception: the
  record/replay provider in `backend/app/providers/replay.py`, chosen only by `WORKBENCH_PROVIDER=record|replay`,
  never by default, so the browser flows run without a GPU. Nothing else in `app/` may answer for the model.
- The backend schema is the source of truth for types. After changing `backend/app/schemas.py`,
  run `backend/.venv/Scripts/python backend/scripts/export_openapi.py` then `npm run api:types`,
  and commit both generated files.
- Identity goes through `backend/app/hashing.py`. A test fails otherwise.
- Git is Pavan's. Do not commit or push.

- A prompt or retrieval change is judged by the golden set (`docs/GOLDENS.md`): run
  `backend/scripts/run_goldens.py` and keep the change only if the set moves in its favour.

Checks before saying anything is done (CI runs the same):

```
cd backend && .venv/Scripts/python -m ruff format --check . && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m mypy && .venv/Scripts/python -m pytest -q
npm run typecheck && npm run lint && npm run format:check && npm test
npm run e2e   # browser flows; builds the interface, replays the model's recorded answers; about two minutes
```

Record decisions as they are taken in `DECISIONS.md`. Keep `README.md`'s release checklist true.

Framework and library documentation, in this order of authority:

1. **Next.js: the installed docs win.** Before changing anything that touches the App Router, layouts
   or pages, caching, route handlers, Server Components, Server Actions, metadata, navigation,
   streaming, image or font handling, proxy or middleware behaviour, or build and config behaviour,
   read the matching file under `node_modules/next/dist/docs/01-app/` first. Not the web, not memory.
   The rule and the ownership table it must not override are in `AGENTS.md`.
2. **Other libraries (Playwright, FastAPI, SQLAlchemy, pydantic): the Context7 MCP server** declared in
   `.mcp.json` (Upstash, MIT, no key needed at the default rate) gives the current API of the pinned
   version; ask it before writing against one.

The hierarchy this repository runs on: installed framework docs decide framework correctness;
`ENGINEERING_CONSTITUTION.md` decides architectural ownership; the generated OpenAPI types are the
frontend-backend contract; the domain and database invariants are the system's truth.
