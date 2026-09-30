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

## The goldens under both retrievers, 2026-09-29, reader v4, verifier v2, Qwen3 8B, answer-v2

| Retriever | Pass | Fails |
|---|---|---|
| BM25 | 37 of 44 | g08, g11, g12, g26, g35, g42, g44 |
| hybrid | 40 of 44 | g11, g12, g36, g44 |

Hybrid gains g08, g26, g35 and g42 and loses g36. On g36 the labelled section (5.3.2) was hybrid's
first candidate; the model quoted it with an ellipsis, the verifier withheld the quote, and the golden
failed. The cause is the model's quote, not retrieval, and the rule does not ask about causes: it asks
whether any golden regressed. One did.

**Decision.** BM25 stays the default. Hybrid stays available behind `WORKBENCH_RETRIEVAL=hybrid`, with
its numbers: ten points more recall on expert labels, three more goldens net, one regression. It becomes
the default the first time a run shows no regression, which, with deterministic decoding, means after
a change elsewhere, for example the prompt experiment against non-verbatim quotes that g36 and g44 both
call for, judged with hybrid on. Both recordings are in `docs/GOLDENS.md`.

## Would a larger k reach what k = 6 misses? (2026-09-29, BM25, no model call)

`eval_retrieval.py --k 10 --k 12 --ranks`. The three goldens BM25 misses at six are all reached at
ten: fees due after an invoice (§4.5 ranks 9th), the IP indemnity (§9.1 ranks 10th), how the
agreement is modified (§12.2 ranks 7th). The other four failures of Recording 4 are not retrieval's
(`docs/GOLDENS.md`).

| Set | R@6 | R@8 | R@10 | R@12 |
|---|---|---|---|---|
| CUAD-30 | 0.91 | 0.92 | 0.95 | 0.96 |
| CUAD-SkillOpt-30 | 0.81 | 0.89 | 0.89 | 0.90 |
| goldens | 0.92 | 0.95 | 1.00 | 1.00 |
| CUAD both | 0.85 | 0.90 | 0.91 | 0.93 |

By category at k = 10: uncapped liability stays at 0.50 (a vocabulary gap, not a depth problem),
non-compete 0.69 → 0.81, cap on liability and termination for convenience reach 1.00.

The cost is context: ten sections instead of six is roughly two thirds more prompt per call for an
8B model on a 6 GB GPU, and more room to pick a wrong section (noise@6 is already 0.75 on CUAD).
**Rule, fixed before the run:** `WORKBENCH_RETRIEVAL_K=10` is measured on the 44 goldens against the
same prompt at k = 6, after the prompt question in `docs/GOLDENS.md` is settled so the two are not
confounded. It becomes the default only with no regression, at least one gain, and median model
latency up by less than half. If it regresses, the three misses stay named here as retrieval's and
hybrid remains the measured alternative.

**Measured 2026-09-29 (Recording 5, `docs/GOLDENS.md`):** answer-v2 at k = 10 scores 38 of 44 against 37 at k = 6; the three
misses named above (g08, g12, g35) pass, and two goldens that passed at k = 6 fail (g39, a quote withheld; g43, the injected
instruction answered "not found"); median model latency 41.2 s against 26.2 s, +57%, four runs of the 44 slowed by other
work on the machine and the verdict not turning on them. Under the rule, k = 10 is not the default. It remains a run option,
and the three misses remain retrieval's: reachable at depth, at a price paid elsewhere.

