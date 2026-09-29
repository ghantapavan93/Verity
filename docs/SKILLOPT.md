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

Not recorded yet. The run is started with:

```bash
cd backend
data/skillopt/venv/Scripts/python experiments/skillopt/build_data.py
data/skillopt/venv/Scripts/python experiments/skillopt/run.py
```
