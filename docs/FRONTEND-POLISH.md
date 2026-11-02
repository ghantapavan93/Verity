# Frontend refinement — 2026-11-01

The owner requested Apple-level attention to detail across the existing website,
preserving Verity's identity, real workflow, and engineering boundaries.

## Design contract

- Keep the graphite shell, ivory document, brass accent, and three font families.
- Give contract text, findings, and source passages the strongest reading hierarchy.
- Keep uploads, questions, reviews, memos, exports, and execution records real.
- Keep model proposals, code checks, and human decisions visibly distinct.
- Improve touch targets, keyboard operation, responsive spacing, and loading feedback.
- Use short entrance transitions and respect reduced motion. Add no decorative loops.
- Use existing tokens and dependencies. Add no theme switch, dashboard, or new product page.

The reference is Verity's own rendered landing, workbench, and evidence sheet.
These establish the visual identity; the refinement addresses observed interaction
and reading problems rather than importing another product's layout.

## Responsibility and failure behavior

1. Presentation owns typography, layout, motion, question-field sizing, and focus.
2. Verified offsets and statuses still come exclusively from the API. The frontend
   never infers evidence validity or legal support.
3. A failed read remains an actionable error. No loading state becomes fake data.
   Invalid offsets and unverified passages still get no source-context disclosure.
4. Component tests cover keyboard behavior and evidence boundaries. Browser tests
   use the real API with the explicitly selected, existing test replay provider.
5. One small shared question field earns its existence through two composers needing
   the same grow/shrink/reflow behavior. No new state layer or runtime dependency.

## Findings and changes

| Surface             | Observed issue                                                               | Refinement                                                                                                    |
| ------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Landing and upload  | Slow staggered entrances; dense upload description; tiny access action       | Faster entrances, balanced heading, clearer line spacing, 44px primary controls, more stable processing space |
| Contract            | Tight reading rhythm and undersized document title                           | Larger responsive title and 16px/1.75 paper typography                                                        |
| Questions           | Long questions clipped into a single row; composition Enter could submit     | Shared textarea grows and shrinks, reflows on resize, caps at 160px; IME confirmation does not submit         |
| Findings            | Small titles and compact review controls                                     | Clearer serif hierarchy and larger named decision controls                                                    |
| Evidence            | Context disclosure only on phones; ancestor focus scrolling could hide Close | Context at every width; fixed shell clips instead of becoming a hidden scroll container                       |
| Lists and records   | Fixed desktop padding; skeleton shape mismatched phone rows                  | Responsive padding, larger headings, mobile skeleton layout, announced loading                                |
| Command palette     | Long commands truncated; dense mobile command rows                           | Wrapping labels, 44px rows, stacked mobile metadata, explicit search label                                    |
| Split divider       | Arrow/Home scrolled the page; no End bound                                   | Prevent native page scroll for resize keys, Home/End bounds, spoken percentage                                |
| Research and Break  | Small sticky navigation targets                                              | More generous navigation hit areas and shared heading/focus treatment                                         |
| Shared interactions | Scroll chaining and mobile home-indicator proximity                          | Contained pane scrolling, safe-area composer spacing, coarse-pointer targets                                  |

## Validation scope

Audit all six surfaces: `/`, Documents, Findings, Runs, `/break`, `/state`.
Inspect them at 320, 375, 768, 1024, and 1440 CSS pixels. Check horizontal overflow,
browser errors, and WCAG A/AA axe findings. Inspect the evidence sheet separately.

The browser suite covers uploads and refusals, guidance, questions, citations,
human decisions, memo generation, execution records, refresh/reconnection,
keyboard focus, mobile pane switching, recorded failures, and research navigation.
Additional regressions cover composer grow/shrink/reflow, context inspection with
a reachable sheet header, focus return, and a delayed real contracts read.

Browser validation uses Chromium, WebKit and Firefox, including phone viewport
and touch emulation. It is not a physical iPhone or Safari certification. Replay exercises the real API and recorded model output;
it does not measure fresh model quality or production GPU latency.

## Local environment

The checkout's `node_modules` is a junction outside its directory. Turbopack refuses
that local arrangement. Browser verification therefore builds with Next's Webpack
mode using a temporary Playwright config; the product configuration is unchanged.
Backend dependencies are installed into the checkout's ignored `.venv` from the
existing lockfiles. Test databases remain separate from the public store.

The full backend mypy command reports errors in unchanged test/script files.
`docs/STATUS.md` already distinguishes this wider command from the release gate's
narrower application/exporter check. Record final check results below.

## Results — initial refinement

For the subsequent desktop session-state changes and current frontend checks,
see [SESSION-STATES.md](SESSION-STATES.md). The figures below preserve the initial checkpoint.

- Frontend unit suite: **413 passed**, 45 files.
- Production Chromium browser suite: **49 passed** (3.1 minutes), real API and
  existing explicitly selected replay provider. This includes all three new regressions.
- Two pre-existing browser tests used partial question matches and selected the
  wrong records on repeated runs. They now identify the exact run or exact question;
  the repeated full suite passes without clearing its test database.
- Chromium accessibility scan: all six surfaces at 320, 375, 768, 1024 and 1440px;
  **zero WCAG A/AA axe violations**, zero horizontal page overflow. Evidence scanned separately.
- WebKit and Firefox: all six surfaces at 320, 375 and 1440px, including touch
  emulation at phone widths; **zero page errors and zero horizontal page overflow**.
  Navigation between pages can cancel outstanding cross-origin development requests
  in WebKit; isolated, settled page checks eliminate those harness cancellations.
- Additional WebKit/Firefox smoke: real sample upload, recorded question, source
  context, review decision and growing multi-line composer work.
- Local production observation: 243,549 transferred script bytes on the landing,
  no observed layout shift during the measurement, and no tasks over 50ms while
  typing the tested question. Initial bootstrap had one 74ms task. This is a busy
  local test machine, not a before/after benchmark or production performance claim.
- Backend ruff formatting/lint: **316 files formatted; checks passed**.
- Backend release-gate application/exporter mypy scope: **107 source files passed**.
- Documentation claim checks: **22 passed** after updating the browser-flow count.
- Broader backend mypy scope: **78 errors in 30 unchanged test/script files**.
  The optional full backend pytest run was interrupted around 42%; it had already
  emitted two failures. That run is **not a passing backend gate**, and its failures
  were not investigated in this frontend-only change. No backend source changed.
- No live deployment or production-store operation was performed.
