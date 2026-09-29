# Interface performance, measured

The workspace renders the whole contract as one column of sections and highlights citations by
slicing stored offsets. Virtualisation is added only when a measurement demands it; this is the
measurement.

## Method

A synthetic agreement of 2,001 numbered clauses (923 KB of text, generated, not meant to be
read) was uploaded and opened by URL in the production build (`next build`, `next start`) in
the desktop app's browser pane, alongside the 123-section sample. Numbers come from the page's
own timers: `performance.now()` polled until every section node exists (time to paper),
navigation and resource timing for the document fetch, `document.querySelectorAll("*")` for
node count, `performance.memory` for heap, and `scrollIntoView` followed by two animation
frames for a citation jump (the same call the interface makes when a citation is clicked).

## Results (2026-09-28, production build, one laptop)

| | 123 sections (sample) | 2,001 sections (fixture) |
|---|---|---|
| Document fetch | 44 ms | 138 ms |
| Paper on screen after navigation start | 474 ms | 1,598 ms |
| DOM nodes | 563 | 8,094 |
| JS heap | 42 MB | 39 MB |
| Citation jump (scroll + two frames) | 9 ms | 35 ms |
| Jump back | 13 ms | 36 ms |

Sixteen times the sections cost 3.4 times the time to paper; the initial render of the fixture
is about 1.1 s after the fetch ends, roughly 0.55 ms per section. Jumps stay within two frames
at both sizes.

## Lighthouse (2026-09-28, production build, desktop preset, Chrome headless)

| Page | Performance | Accessibility | Best practices | SEO | FCP | LCP | TBT | CLS |
|---|---|---|---|---|---|---|---|---|
| Landing | 100 | 100 | 100 | 100 | 0.3 s | 0.7 s | 0 ms | 0.001 |
| Workspace with a completed run | 99 | 100 | 100 | 100 | 0.3 s | 1.0 s | 0 ms | 0.003 |

One finding was real and cheap: the API sent the document JSON uncompressed, 55,971 bytes for the
sample. Responses over 1 KB now go out gzipped (16,393 bytes for the same document); Starlette leaves
the event stream alone, and one test holds both facts. The rest are diagnostics, left as they are
with the reason: one render-blocking CSS chunk (Next's own stylesheet), unused JavaScript inside the
framework bundle, legacy polyfills for Next's default browser targets (a narrower browserslist would
drop them; no measured need at a score of 99), and one forced reflow on the workspace with a total
blocking time of 0 ms. No Lighthouse gate in CI yet: the scores sit at the ceiling, and a gate earns
its place the first time a change moves one. Re-run: `npx lighthouse <url> --preset=desktop`.

## Decision

No virtualisation. Scrolling and citation navigation are frame-bound at 2,001 sections, and the
only cost that scales is the first render, which is 1.6 s on a document ten times larger than
most contracts (the largest real document in the public corpus, the Model Services Contract
schedules, parses to 2,659 sections). The number that earns virtualisation is a first render
over 3 s on a real document, which by this measurement means about 5,000 sections. When such a
document appears, this file is rerun and the decision revisited.
