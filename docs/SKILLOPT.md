# SkillOpt over the answer prompt

SkillOpt (Microsoft Research, MIT, arXiv 2605.23904) treats an agent's instruction document as the
trainable state of a frozen model: an optimizer model turns scored rollouts into a few bounded edits,
and an edit is kept only when it strictly improves a held-out validation score. This repository's own
rule for a prompt change is the same idea done by hand, so the tool is run here against the workbench
itself, under conditions that keep the result meaningful. Everything above "Results" was written
before the run.

## What is optimised, and against what

- **The skill** is the system prompt, seeded with `answer-v2.md` as it stands. Nothing else in the
  pipeline moves: the same reader, retrieval (BM25, six candidates), JSON schema, verifier and status
  decision the interface uses. The rollout is `backend/experiments/skillopt/workbench_env/rollout.py`,
  which calls those production functions and the workbench's own Ollama provider (temperature 0, a
  fixed seed, thinking off).
- **The target model** is Qwen3 8B on the local GPU. **The optimizer model** is the same Qwen3 8B,
  through Ollama's OpenAI-compatible endpoint with thinking switched off (`reasoning_effort: none`;
  the paper uses a frontier model here, and this is the $0 substitute).
- **The training data** are CUAD v1 contracts disjoint from CUAD-30: same eligibility and stride,
  six positions later (`backend/experiments/skillopt/build_data.py`; manifest
  `backend/app/batch/corpora/cuad-skillopt.json`). SkillOpt trains on the whole training split, so the split is
  the budget: three contracts (21 items over the seven `cuad-clauses` questions), three more as the
  validation set that gates every edit (21 items), twenty-four in reserve that no run reads.
- **The score** per item is the CUAD rule of `docs/CUAD.md`: 1 when the verified citation hits an
  expert span or the model correctly reports absence, 0 otherwise (soft credit 0.5 for a real
  citation from the wrong clause, used only for reporting; the gate is on the hard score).

## Budget, fixed in `config.yaml`

Two epochs, three steps of seven training items each, at most three edits per step, the whole
validation set at every gate. About 21 + 6 × (7 + 21) = 189 target-model calls, plus the optimizer's
analysis and edit calls; roughly three hours on this GPU at the batch rate. Slow update and meta-skill
on, with eight samples.

## How the result is judged, decided now

SkillOpt's own gate is not the judgment. The best skill it writes becomes a candidate prompt version,
`answer-v3-skillopt`, and is judged where every prompt is judged: on the 44 goldens, which no part of
this run has read, under the standing rule in `docs/GOLDENS.md`: kept only with no regression against
answer-v2 and at least one improvement. Its CUAD-30 score is recorded beside answer-v2's once the
CUAD-30 baseline exists. If it fails either, the run is still reported: the edits it proposed, the
validation curve, and why they did not carry.

## Results

**Run `20260929-023859-real`, 2026-09-28, config as committed.** 67 minutes, not the three hours budgeted:
no candidate ever reached the gate, so the 21-item gate rollouts never happened.

| What | Value |
|---|---|
| Baseline, answer-v2 on the 21 validation items | 14 correct (hard 0.667): 4 correct, 10 correct absence, 6 asserted where experts found none, 1 cited elsewhere |
| Training rollouts, six steps of seven | 5/7, 6/7, 6/7, 5/7, 6/7, 4/7: 32 of 42 |
| Training outcomes | 13 correct, 19 correct absence, 5 asserted where experts found none, 5 missed |
| Optimizer calls | 12 analyst (a failure and a success analysis every step), 1 meta-skill, 1 slow update; 38,530 tokens |
| Edits proposed | 0, in every one of the 12 analyst replies; all parsed as valid JSON |
| Candidates, gate evaluations, accepts | 0, 0, 0; six steps recorded as "skip: no usable patches" |
| Best skill | the seed; `best_skill.md` is byte-identical to answer-v2 |
| Target model | 63 calls, p50 53.4 s, p95 87.7 s; reflection 90 to 126 s per step |

**Judgment.** There is no candidate prompt, so there is nothing to run on the goldens. answer-v2 stands.

**What the failures were.** The dominant "failure" is disagreement with the CUAD labels, not an invented
clause: six of the seven baseline failures and five of the ten training failures are cases where the
model cited a real passage (§1.4 terminating for convenience on ninety days' notice; §9 and §1 on
liabilities outside a cap) that the annotators did not mark. The gate counts those as zero, which would
push any optimizer toward answering "not found" more often; that nothing was accepted is a relief, not
a loss. The five misses split three and two: three where a retrieved section carried the expert span and
the model still said "not found" (the kind a prompt rule can address), two where retrieval never handed
the span over. The validation split is absence-heavy, five of its 21 items carry a span, so the hard
score is mostly a measure of absence handling.

**A check on the zero.** The same two failures of step 1, fed to the same optimizer outside the loop with
a shorter framing, produced one generic edit ("ensure the quoted passage directly supports the
conclusion"). Inside the loop, with the full trajectories and at temperature 0.7, it produced none. The
zero is therefore a property of a small local optimizer under a long context, not a parsing fault: the
tool's malformed-JSON warning never fired, and `json_repair` was installed mid-run without effect.

**What would change the outcome, written down so a second run is a decision and not a drift:** a
stronger optimizer model (the paper's setting; it costs money, Pavan's call); a training and validation
split drawn from span-present items so the failures are of the fixable kind; the disagreements with the
labels reviewed by hand or counted as neutral instead of zero; a larger validation set. None of that
changes the rule: whatever a run produces is judged on the untouched goldens.

The run was started with:

```bash
cd backend
data/skillopt/venv/Scripts/python experiments/skillopt/build_data.py
data/skillopt/venv/Scripts/python experiments/skillopt/run.py
```
