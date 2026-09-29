# Retrieval, measured against labels

The pipeline hands the model six sections chosen by BM25 over section text with the heading counted
three times (`backend/app/retrieval/lexical.py`). ADR 0004 says vectors are added when a measurement
shows lexical retrieval missing the section the answer lives in. This is that measurement, made with
`backend/scripts/eval_retrieval.py` and no model call.

## Labels and metric

| Set | Cases | Label |
|---|---|---|
| CUAD-30 | 75 (contract, category) pairs with an expert span | the experts' spans; a section is a hit when it carries a span (`cuad_match.retrieved_carries`) |
| CUAD-SkillOpt-30 | 89 pairs, the disjoint SkillOpt contracts | same |
| goldens | 38 present goldens on the sample | the section numbers the golden names |

Recall@k: a hit among the top k, over cases where some section carries the label at all ("reachable";
here every case is). MRR: mean reciprocal rank of the first hit. noise@6: share of the six production
candidates that carry no label, averaged over cases; six candidates for one or two relevant sections
makes it high by construction, and it is reported so a change can be seen.

## Rule, fixed before the dense and hybrid numbers were computed

Recall@6 on the two CUAD sets together is the number. At 0.90 or above, BM25 stands. Below 0.75, one
hybrid candidate is tested on the same labels. In between, BM25 stands and the categories below 0.75
are named; a hybrid is still measured, and it earns a place in the pipeline only if it raises CUAD
Recall@6 by at least 0.05 without lowering the goldens' Recall@6, and then only after the 44 goldens are
re-run under it with no regression, because a retrieval change changes every run's candidates.

## Results, 2026-09-29

**BM25, heading ×3**

| Set | cases | R@1 | R@3 | R@5 | R@6 | R@8 | MRR | noise@6 |
|---|---|---|---|---|---|---|---|---|
| CUAD-30 | 75 | 0.63 | 0.84 | 0.91 | 0.91 | 0.92 | 0.74 | 0.72 |
| CUAD-SkillOpt-30 | 89 | 0.56 | 0.73 | 0.79 | 0.81 | 0.89 | 0.67 | 0.77 |
| goldens | 38 | 0.71 | 0.89 | 0.89 | 0.92 | 0.95 | 0.80 | 0.83 |
| **CUAD both** | 164 | 0.59 | 0.78 | 0.84 | **0.85** | 0.90 | 0.70 | 0.75 |

By category on CUAD, Recall@6: cap on liability 0.94, change of control 1.00, governing law 0.91,
termination for convenience 0.92, most favoured nation 0.67 (3 cases), non-compete 0.69, **uncapped
liability 0.44**. The two weak categories are the ones whose questions share no vocabulary with the
clause: a clause that lifts the cap says "shall not apply" or "nothing in this section limits", not
"uncapped"; a non-compete says "shall not, directly or indirectly, engage in".

0.85 is between the two lines: BM25 stands, the weak categories are named, and the hybrid is measured
below.

**Dense (nomic-embed-text through Ollama, cosine) and hybrid (BM25 + dense, reciprocal rank fusion, k = 60)**

| Ranking | Set | R@1 | R@3 | R@5 | R@6 | R@8 | MRR | noise@6 |
|---|---|---|---|---|---|---|---|---|
| dense | CUAD both | 0.57 | 0.81 | 0.90 | 0.92 | 0.95 | 0.70 | 0.80 |
| dense | goldens | 0.92 | 0.97 | 0.97 | 0.97 | 0.97 | 0.95 | 0.81 |
| hybrid | CUAD-30 | 0.67 | 0.87 | 0.92 | 0.92 | 0.96 | 0.78 | 0.79 |
| hybrid | CUAD-SkillOpt-30 | 0.53 | 0.88 | 0.96 | 0.97 | 0.98 | 0.70 | 0.78 |
| hybrid | goldens | 0.87 | 0.95 | 0.97 | 0.97 | 0.97 | 0.91 | 0.81 |
| **hybrid** | **CUAD both** | 0.59 | 0.87 | 0.94 | **0.95** | 0.97 | 0.74 | 0.78 |

Hybrid by category, Recall@6: uncapped liability 0.44 → 0.88, non-compete 0.69 → 0.75, most favoured
nation 0.67 → 1.00 (3 cases), change of control 1.00 → 0.92, the rest at or above 0.97.

**Decision.** Hybrid raises CUAD Recall@6 by 0.10 and does not lower the goldens' (0.92 → 0.97), so it
has earned the goldens re-run, not yet the pipeline. It runs behind `WORKBENCH_RETRIEVAL=hybrid`, the
retrieval mode is part of a run's identity when it is not the default, and the 44 goldens are re-run
under it. It becomes the default only with no regression there. The embedding model is local
(nomic-embed-text, 274 MB, $0); a missing model fails the run with a reason, never silently falls back.
