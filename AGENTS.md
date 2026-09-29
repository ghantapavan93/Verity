# Working in this repository

Start with `CLAUDE.md` (the working rules and the check commands) and `ENGINEERING_CONSTITUTION.md`
(where responsibility lives: the model proposes, deterministic code verifies, the database freezes a
finished run). `DECISIONS.md` records why things are the way they are. The block below is written
and maintained by Next.js; leave it as it is.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Project-specific Next.js rule

The installed Next.js documentation, `node_modules/next/dist/docs/` (this tree runs 16.3.6), is
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
