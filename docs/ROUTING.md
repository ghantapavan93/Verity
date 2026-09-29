# Model routing, by measurement

A run is one of two tasks: a **clause lookup** (a question about the contract, no guidance) or a
**guidance comparison** (the contract's position against a stated policy). The router
(`backend/app/routing/router.py`) picks the model for the task from a policy table. The model is
part of a run's identity (it is in the recorded options and the fingerprint), so runs under
different models are different runs and can be compared like prompt versions.

## The rule

A smaller or faster model is routed a task only when it has been measured on the golden set
for that task and passes every golden the default model passes, with the latency saving
recorded. The policy table is empty until then; the run record's routing reason says which case
applied. No entry is added on judgement, and none is kept when a later golden recording shows a
regression.

## How a model is measured

```bash
cd backend
.venv/Scripts/python scripts/run_goldens.py --prompt answer-v2                      # the default model
.venv/Scripts/python scripts/run_goldens.py --prompt answer-v2 --model qwen3:4b     # a candidate
```

Both recordings share the golden set, the reader version, the prompt and the decoding options;
only the model differs. The comparison is read per task: `clause_lookup` goldens are those
without guidance, `guidance_comparison` goldens the four with it. Pass counts, the failing
goldens and mean model latency go in the table below; the policy is set with
`WORKBENCH_ROUTING_POLICY='{"clause_lookup": "qwen3:4b"}'` only if the rule above holds.

## Record

| Date | Task | Default model | Candidate | Goldens passed (default → candidate) | Regressions | Mean latency (default → candidate) | Policy |
|---|---|---|---|---|---|---|---|
| 2026-09-28 | clause_lookup | qwen3:8b | qwen3:4b | 31/38 → 33/38 | g37 (answered "not found" for the lost-profits waiver) | 39.1 s → 9.8 s | default stands |
| 2026-09-28 | guidance_comparison | qwen3:8b | qwen3:4b | 3/4 → 3/4 | g31 (decided pass where needs review was expected, on the assignment clause) | 39.1 s → 9.8 s | default stands |

Recording: 42 goldens, prompt answer-v2, reader v3 parse, decoding options identical, one run per
golden per model. qwen3:4b was better on four goldens (g11 non-compete asserted by the default,
g23 survival, g30 and g35 the dispute window, both withheld by the default) and worse on two.
Per category it matched or beat the default everywhere except negation (3/4 against 4/4).

**What the rule does with this.** The candidate is not routed for either task, because in each
task it fails a golden the default passes, and the two it fails are the kind that matter: a
"no" read as "not found", and a "pass" where a person should have been asked to review. That
the candidate is better overall and four times faster is recorded, not acted on. It becomes a
routing decision only when one of two things happens: the negation and guidance categories are
extended and the candidate passes what the default passes there (then the regressions were
noise of a two-golden sample), or a person accepts the two regressions in writing as the price
of the latency, which is a change of default rather than routing and goes through the golden
rule's "accepted in writing" clause.

The comparison itself is one command and no new code path:
`run_goldens.py --compare-models qwen3:8b qwen3:4b` prints it per task from the recorded runs.

This is the same engineering question Ivo's researchers describe publicly, used here as an
opportunity to measure when a smaller local model is sufficient. It is not a reconstruction of
anyone's routing.
