# Casebook

Six failures, each traced to what the machine was doing. Each entry says where the failure surfaced, what was seen,
what located it, the mechanism, the fix, and the test that guards it where one exists. Five are fixed. The sixth is
measured and still open.

## 1. The API was running and accepted no one (live)

- **Seen.** Between 2026-10-09 and 2026-10-11 the supervisor restarted a silent API 18 times. Each time the process
  was up, and the site answered 502.
- **Located.** The API's log ended on an asyncio accept error, WinError 64, while the process stayed up.
- **Mechanism.** On Windows, CPython's proactor event loop closes its listening socket when one `AcceptEx` fails. A
  client that resets mid-handshake fails it with `ERROR_NETNAME_DELETED` (WinError 64). After that every connection
  fails.
- **Fix.** `app.serving.ResilientProactorEventLoop` retries an accept the client caused to fail. Any other failure is
  handled as CPython handles it. The selector loop was rejected: it caps a process at 512 sockets.
- **Test.** `backend/tests/test_accept_resets.py`. Its control shows the default loop stops accepting under the same
  resets.

## 2. A log reader killed the supervisor (live)

- **Seen.** On 2026-10-11 at 05:44 the API stopped accepting: failure 1, before its fix shipped. Nothing restarted it,
  and the site was down 17 minutes.
- **Located.** The supervisor itself had exited, with code 1, on a log write, while an operator's `tail -F` held the
  log.
- **Mechanism.** `tail -F` opened `api.supervisor.log` sharing read access only. `Add-Content` needs write access, so
  it raised. Under `$ErrorActionPreference = "Stop"` that ended the script.
- **Fix.** Every write goes through `Write-Record` in `deploy/supervise.ps1`. It retries, then gives the line up and
  counts it on the next line written.
- **Test.** `backend/tests/test_supervisor_records.py` holds the file with `CreateFileW` and the same share flags. Its
  control shows a bare `Add-Content` dies.

## 3. The model server cut a prompt and said nothing (probe)

- **Seen.** Asked directly with the product's own options, the model was given a 20,695-token prompt with a notice
  period at its start. It answered "30 days"; the text said 47. No recorded run had overflowed.
- **Located.** The server's own count: it evaluated 8,194 of the 20,695 tokens (Ollama 0.35.0).
- **Mechanism.** Left to its default, the server drops tokens to make the prompt fit and answers anyway. Nothing in
  the response says it did.
- **Fix.** Each request sends `truncate: false` and `shift: false`. The server's refusal becomes a `ContextOverflow`
  that names both token counts.
- **Test.** `backend/tests/test_model_saw.py`, the model server is told not to cut the prompt.

## 4. Concurrent questions drained the connection pool (load envelope, then cloud rehearsal)

- **Seen.** At twenty concurrent runs, reads failed with `QueuePool limit of size 5 overflow 10 reached`
  (`docs/SCALE.md`).
- **Located.** The connections were held for each run's whole length.
- **First mechanism.** FastAPI closes a request's session only after its background task ends. A read after the commit
  opened a new transaction that pinned a connection for the whole run. `create_run` now commits before it returns.
- **It came back.** On 2026-10-12, with nine visitors at once, the pool ran dry again. A run's own session holds a
  connection for its whole life, including the wait for the one model.
- **Fix.** The store uses no pool (`NullPool`, `backend/app/db.py`). Each connection is opened when needed and closed
  after.
- **Test.** `backend/tests/test_db_concurrency.py` holds fifteen connections and shows another request is still
  served.
- **Same envelope, a second failure.** Staleness recovery declared runs dead while they waited for the model. The
  window is now four model timeouts plus a minute. No test fails if the window shrinks; the load envelope is the check.

## 5. Queries grew with every row (audit)

- **Seen.** The audit of 2026-10-19 counted the statements each read sends: 2,252 for a findings list of 500. On the
  test fixture it was 11 for 2 rows and 56 for 12.
- **Mechanism.** Each row lazily loaded its spans, their sections, its reviews, its run's guidance and its document's
  name. The session holds rows weakly, so a grant read for one row was dropped and read again for the next. The poll of
  a working run also read the whole contract, to place findings the run did not have yet.
- **Fix.**
  - Eager loads.
  - A batched stall check.
  - Clause numbers found by section ids.
  - A working run reads no sections.

  Now 7 statements for 2 rows and for 12.
- **Test.** `backend/tests/test_read_cost.py` checks that 2 rows and 12 cost the same, and that a working run reads no
  sections. It fails on the old code.

## 6. Temperature 0, two answers (live, open)

- **Seen.** One recorded input (liability question, hash 312e14a1, seed 42, temperature 0) sometimes gave a verified
  answer. Other times it gave a quote that joined two sentences and was withheld.
- **Located.** The model server's log. Each request's `new prompt` line says where computation started. The answer
  follows that start point, and it reproduces on demand.
- **Mechanism.** llama-server reuses the longest prefix it already holds, in two places:
  - the slot's last prompt;
  - an 8 GiB host-RAM prompt cache ("found better prompt").

  The convenience and liability questions share their first 620 tokens: the system prompt and "QUESTION: What". So
  one asked after the other starts at token 620, not 0.

  Measured on Ollama 0.40.7, 2026-10-21, with the convenience input (hash c6f8e6af):
  - from token 0, answer 7b6a0862, with 3 quotes;
  - from token 620, answer 8c66f45e, with 1 quote.

  On 0.40.6 the two answers were the other way round.

  The server log shows 17 of 37 layers on the CPU. Inferred, not measured: a different start changes the batch
  boundaries, the floating-point sums with them, and a near-tie in the greedy choice flips.
- **Tried.** Each measure alone failed, and the log shows why:
  - The host-RAM cache at 0: the slot still reused its last prompt and started at 620.
  - A one-token raw call before each answer: the slot then shares no prefix, but the RAM cache restored the 620-token
    prefix (`f_sim = 0.328`).
- **Open.** Both together are expected to start every prompt at token 0, but this is not tested. It needs:
  - a code change: the one-token call, inside the model's admission slot, before every answer;
  - an Ollama setting and a restart on the serving machine, which is the owner's decision.
