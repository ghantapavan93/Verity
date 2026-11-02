# Browser review sessions — 2026-11-01

The owner prioritized desktop web browsers: consistent reading during repeated,
demanding review sessions, with distinct populated, empty, failed and interrupted
states. This follows the initial [frontend refinement](FRONTEND-POLISH.md).

## What changed

| Observed problem                                                       | Result                                                                                                                         |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| A failed review appeared above the list, away from the clicked finding | The error stays beside that finding. Retry preserves the row and records only the API's result.                                |
| An older execution-record read could replace a newer selection         | Only the latest selection may display its result, error or busy state. Returning to the list invalidates older reads.          |
| Reading a long record and returning lost position and keyboard context | Records open at their heading. All runs restores the list's scroll position and focuses the initiating row.                    |
| An interrupted connection kept displaying live progress                | An explicit recovery panel names the last reported stage and reconnects to the same run. It does not claim the server stopped. |
| A failed question request offered only an error sentence               | The question remains available, with an explicit retry action.                                                                 |
| An empty filter required remembering the figures' toggle behavior      | Show all findings restores the existing records without another fetch.                                                         |
| An empty composer showed an available Send action                      | Send is disabled until there is non-whitespace question text.                                                                  |

These are presentation and navigation responsibilities. They enforce no evidence,
status, legal, review, or persistence rule. The backend still owns those decisions.
A failed request never becomes an empty result or a fabricated answer. The new
request guard exists because the previous selection race was reproduced by a
failing test, not as a new abstraction for its own sake.

## State inventory and evidence

| Area                          | States checked                                                                                                                   | Evidence                                                              |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Documents, Findings, Runs     | Genuinely empty, populated, failed read, retry                                                                                   | Fresh-store browser audit; loading regressions in the regular suite   |
| Findings                      | Unreviewed, reviewer name, saving, confirmed/dismissed, cleared, rejected stale decision, network refusal, retry, stable order   | Component tests, regular browser suite, failed-decision browser audit |
| Findings filters              | Populated filter and no matches, recovery to all records                                                                         | Component regression                                                  |
| Execution records             | Opening, selected, deep reading, back, repeated keyboard navigation, earlier response arriving late                              | Component regression and six repeated browser cycles per engine       |
| Questions                     | Idle, empty input, sending, stage progress, supported finding, withheld proposal, unresolved, provider failure, malformed output | Regular browser suite and component tests                             |
| Interrupted questions         | Failed create request, text retained, explicit retry, dropped stream and failed polling, reconnect, completed same run           | Browser state audit against the real API                              |
| Evidence                      | Open/close, source context, verified/unverified passages, review form, conflict, focus return                                    | Existing evidence tests and regular browser regressions               |
| Guidance                      | Edit, apply, refused save with the form retained                                                                                 | Existing component tests and browser review-against-guidance flow     |
| Memo                          | Generating, ready, later review, late response after navigation                                                                  | Existing memo tests and regular browser suite                         |
| Revision                      | Upload, unchanged file, refused check, cancel, comparison, ask again                                                             | Existing revision tests and browser comparison flow                   |
| Research and recorded failure | Loaded record, unavailable record, API failure, navigation                                                                       | Existing story tests and regular browser suite                        |

The table distinguishes component coverage from browser coverage. It does not
claim a screenshot for every possible combination of flags, network timings,
contract contents and viewport sizes. Repeated cycles are a bounded regression
check, not an hours-long soak test.

## Reproduce the browser state audit

```powershell
npm run test:sessions
```

`playwright.sessions.config.ts` runs `e2e/sessions.audit.ts` on Chromium, Firefox
and WebKit at desktop sizes, including a compact 1440 × 600 window for scroll
restoration. It creates a fresh temporary data directory for the real API and
explicitly selects the existing replay provider. No public or owner store is
opened, reset or deleted.

Only the first Chromium test checks the genuinely empty store; the two equivalent
checks in later browser projects are deliberately skipped after it is populated.
Every other scenario runs on all three engines. Network failures are induced by
aborting requests; recovery reads the real API. Responses are not replaced with
invented success records. Reconnection checks that no second question is submitted.

Each captured state gets an axe WCAG A/AA check and a page-overflow check. PNGs
are retained in `test-results/`; the HTML report is in
`playwright-report/sessions/`. Captures wait for entrance opacity to settle.

The normal `npm run e2e` suite remains separate. Run suites sequentially: both use
the existing isolated browser-test ports and `.next-e2e` build directory.

## Validation results

- **416 frontend unit tests passed**, including the reproduced selection race,
  row-local review failure/retry, and empty-filter recovery regressions.
- **49 regular production browser flows passed**, using the latest session-audit
  production bundle and the real API with its existing replay provider.
- **19 desktop session audit scenarios passed** across Chromium, Firefox and
  WebKit. Two later duplicate empty-store checks were intentionally skipped.
- Every engine completed six record-open/back cycles with a genuinely scrolled
  list in a compact desktop window. List position and keyboard focus were restored.
- A final visual review removed a redundant border around request recovery.
  That finished recovery state was rebuilt and rechecked on all three engines:
  **3 additional targeted checks passed**.
- Captured empty/error/recovery/list states had **zero axe WCAG A/AA violations**
  and **zero horizontal page overflow**.
- TypeScript, ESLint, Prettier and all **22 documentation claim checks passed**.
  Generated browser reports and traces are explicitly excluded from application lint.
- No backend source, evidence decision, persistence rule or runtime dependency changed.
  No commit, push or production deployment was performed. Earlier broader backend
  gate limitations remain recorded in [FRONTEND-POLISH.md](FRONTEND-POLISH.md).
