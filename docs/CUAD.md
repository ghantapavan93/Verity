# CUAD-30: the workbench against labels that are not ours

Every label in this repository so far was written by the person who built the workbench: the
golden set, the family labels, the reading of the batch. That is the largest threat to any number
here. CUAD v1 (The Atticus Project, CC BY 4.0) is 510 commercial contracts in which lawyers marked
the spans for 41 clause categories, more than 13,000 labels. This recording runs the workbench's
ordinary question pipeline over thirty of those contracts and scores its verified citations against
the experts' spans. Nothing in the pipeline is tuned for it: same reader, same retrieval, same
prompt, same verifier, same status decision as the interface uses.

Everything below the line "Results" was written before the run. Nothing above it changes after.

## Data

- Source: `data.zip` from the CUAD repository (18.3 MB; sha256 and fetch date in `backend/data/cuad/SOURCE.txt`),
  which holds `CUADv1.json`: each contract's full text and, per category, the experts' answer spans.
- Selection, fixed in `backend/scripts/cuad_corpus.py`: contracts whose text has between 10,000 and
  150,000 characters (the middle of the length distribution; the median contract is 33,000), sorted
  by title, every k-th one from the first with k = floor(eligible / 30), the first thirty kept. Run on
  2026-09-28: 404 of 510 eligible, k = 13. The manifest `backend/app/batch/corpora/cuad-30.json` names
  the thirty with their text hashes. Experts found a span in 28 of them for governing law, 11 for
  termination for convenience, 15 for the liability cap, 7 for uncapped liability, 8 for non-compete,
  5 for change of control and 1 for most favoured nation; the rest are absence cases.
- Labels: the experts' spans for the seven categories below, per contract, in
  `backend/app/batch/corpora/cuad-30-labels.json`. A category with no span in a contract is a case
  where the experts found no such clause.

## Questions

The task `backend/app/batch/tasks/cuad-clauses.json` maps one question to one CUAD category:

| Field | Question | CUAD category |
|---|---|---|
| governing_law | What law governs this agreement and where must disputes be brought? | Governing Law |
| termination_for_convenience | May either party terminate this agreement for convenience, without cause, and on what notice? | Termination For Convenience |
| liability_cap | What is the cap on each party's liability? | Cap On Liability |
| uncapped_liability | Which liabilities are excluded from the cap or left uncapped? | Uncapped Liability |
| non_compete | Does this agreement restrict either party from competing with the other, and how? | Non-Compete |
| change_of_control | What happens to this agreement if a party undergoes a change of control? | Change Of Control |
| most_favoured_nation | Is there a most favoured nation clause? | Most Favored Nation |

Thirty contracts × seven questions = 210 runs on one laptop GPU with Qwen3 8B, about four hours at
the batch rate recorded in `docs/BATCH.md`.

## Scoring rule (`backend/scripts/score_cuad.py`)

For each contract and category, the workbench's value is the batch's value for that field: the
first finding whose citation verified, with the text the verifier located, or "not found",
"withheld" or "failed". The experts' spans are CUAD's answers for that category.

A located text **hits** an expert span when, after casefolding and collapsing whitespace, one
contains the other, or the two share at least half of their word tokens (Jaccard ≥ 0.5). Then:

| Experts | Workbench | Counted as |
|---|---|---|
| found a span | answered, and a verified citation hits a span | **correct** |
| found a span | answered, no verified citation hits a span | **cited elsewhere** |
| found a span | not found, or withheld | **missed** |
| found none | not found, or withheld | **correct absence** |
| found none | answered with a verified citation | **asserted where experts found none** |

The last row is a disagreement, not a proven error: the citation is real text and the experts may
have missed a clause; it is reported as its own count and read case by case.

Metrics, overall and per category:

- **citation precision** = correct / (correct + cited elsewhere)
- **recall** = correct / (correct + cited elsewhere + missed)
- **absence agreement** = correct absence / (correct absence + asserted where experts found none)
- **false "not found" rate** = missed / (correct + cited elsewhere + missed)
- model latency p50 and p95, verified-span rate, withheld rate, failures, as in every batch

## What the numbers will mean, decided now

The workbench's clause lookup is fit to draft a repository review of these seven categories only if
**citation precision ≥ 0.80 and recall ≥ 0.50 overall**. Below either, this document says so and
names the categories that fail; nothing is retuned to pass. BM25 retrieval is the pre-registered
trigger for a retrieval change (`docs/adr/0004-hybrid-retrieval.md`): if more than a third of the
misses are cases where the expert span sits in a section the retriever did not hand to the model,
retrieval has failed the measurement and earns its replacement. If most misses are cases where the
section was retrieved and the model answered "not found" anyway, the failure is the model's, which
matches what ContractEval reported for open-weight models on CUAD.

Thresholds do not move after the run. A second recording under a different prompt or model is
compared against this one with the same rule.

## Results

**Recorded 2026-09-29 (batch `51398ed416634c15`, task `cuad-clauses`, corpus `cuad-30`, qwen3:8b, 210 values, 210 runs,
reader v4, BM25 k = 6, answer-v2; started 16:14 local, finished 19:59; model latency p50 49.8 s, p95 147.4 s).**
The full per-case list is `backend/data/logs/cuad-30-score.log`; `scripts/score_cuad.py 51398ed416634c15` reproduces it.

| Category | expert spans | correct | cited elsewhere | missed | correct absence | asserted, experts found none | precision | recall | absence agreement |
|---|---|---|---|---|---|---|---|---|---|
| Change Of Control | 5 | 4 | 0 | 1 | 24 | 1 | 1.00 | 0.80 | 0.96 |
| Governing Law | 28 | 24 | 3 | 1 | 1 | 1 | 0.89 | 0.86 | 0.50 |
| Cap On Liability | 15 | 10 | 0 | 5 | 15 | 0 | 1.00 | 0.67 | 1.00 |
| Most Favored Nation | 1 | 0 | 0 | 1 | 29 | 0 | n/a | 0.00 | 1.00 |
| Non-Compete | 8 | 1 | 4 | 3 | 10 | 12 | 0.20 | 0.12 | 0.45 |
| Termination For Convenience | 11 | 8 | 0 | 3 | 16 | 3 | 1.00 | 0.73 | 0.84 |
| Uncapped Liability | 7 | 3 | 2 | 2 | 9 | 14 | 0.60 | 0.43 | 0.39 |
| **all** | 75 | 50 | 9 | 16 | 104 | 31 | **0.85** | **0.67** | 0.77 |

Against the floors written above the run: citation precision 0.85 (floor 0.80) and recall 0.67 (floor 0.50), so the
clause lookup is fit to draft a repository review of these seven categories, with two categories named as unfit on
their own: non-compete (precision 0.20: twelve assertions where the experts marked nothing, mostly exclusivity and
non-solicitation language read as a non-compete) and uncapped liability (precision 0.60, fourteen such assertions:
indemnities and disclaimers read as an uncapped exposure). Retrieval: 7 of the 25 misses had no expert span among
the six sections handed to the model (28%), below the one-third trigger, so BM25 did not fail this measurement; the
misses are mostly the model's, answering "not found" from sections that carried the clause, as ContractEval reported
for open-weight models. Nothing was retuned. A second recording under another prompt, retrieval depth or model is
compared with this table under the same rule; the golden runs at k = 10 and under answer-v3 that followed this
batch on the same GPU are recorded in `docs/GOLDENS.md` and `docs/RETRIEVAL.md`.

The run was started with:

```bash
cd backend
.venv/Scripts/python scripts/cuad_corpus.py
.venv/Scripts/python scripts/run_batch.py --corpus data/cuad/corpus-30 --task cuad-clauses --label cuad-30
.venv/Scripts/python scripts/score_cuad.py <batch_id>
```
