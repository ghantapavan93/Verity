# Document families

Repositories hold contracts that belong together: core terms and their schedules, an
instrument and its addendum, sibling model contracts from one drafting exercise, agreements
built on one publisher's template set. This module finds such families from structure alone,
with no model, and measures the result against hand labels. It demonstrates the class of
problem and the discipline of measuring it; it is not a reconstruction of anyone's product.

The code is `backend/app/families/` (fingerprint, similarity, clustering, evaluation), the
labels are `backend/app/families/labels.json`, the runner is `backend/scripts/cluster_corpus.py`
and the record is `GET /api/engineering/families`, shown on the Runs surface.

## Fingerprint

Three views of a document, each a set, so that similarity is an exact Jaccard index:

| View | What it holds | Why |
|---|---|---|
| headings | the normalised heading sequence (numbers and punctuation stripped, lower-cased) | the skeleton of the document |
| terms | the capitalised terms the text defines ("Deliverables" means …) | the vocabulary the drafter built |
| shingles | word 5-grams over the section texts | the wording itself |

Combined similarity is fixed and disclosed: 0.5 × shingles + 0.25 × headings + 0.25 × terms.
Families are single-linkage clusters at a threshold: two documents share a family when a chain
of pairs at or above the threshold joins them. Jaccard is exact; at twenty documents that is
cheap. MinHash sketches are the step to take when a corpus is large enough that the shingle sets
do not fit, and not before.

## Labels

Twenty public documents (the B1 and pilot corpora in `ivo-experiments`), two label sets:

- **suite** (strict): UK01 Model Services Contract Core Terms with UK02 its Consolidated
  Schedules; UK03 Mid-Tier Core Terms with UK05 its Schedule 3; UK04 Short Form Contract with
  UK06 the NHS Special Terms for it; X01 the ICO IDTA with X02 the ICO Addendum; X04 and X05
  the two Scottish Government model contracts. Five families, ten documents; everything else
  is its own family.
- **template**: the same five, plus the eight Common Paper agreements as one family, because
  they are built on one standard template set.

Evaluation is pairwise: of every pair of labeled documents, precision, recall and F1 of "same
family" at the threshold, and the threshold sweep from 0.05 to 0.95 with the best F1. The sweep
is reported so that the chosen threshold is a fact about this corpus, not a tuned claim about
another.

```bash
cd backend
.venv/Scripts/python scripts/cluster_corpus.py --corpus ../../ivo-experiments/experiments/b1-word-structure/corpus --corpus ../../ivo-experiments/experiments/pilot-redline-integrity/corpus
```

## Results (2026-09-28, 20 documents, reader v3; re-run under reader v4 with the same families and the same precision, recall and F1 to two decimals)

Threshold sweep against the two label sets (pairwise):

| Threshold | template precision | template recall | template F1 | suite F1 |
|---|---|---|---|---|
| 0.05 | 0.89 | 0.48 | 0.63 | 0.09 |
| 0.10 | 0.94 | 0.48 | 0.64 | 0.09 |
| **0.15** | **1.00** | **0.42** | **0.60** | 0.11 |
| 0.20 | 1.00 | 0.36 | 0.53 | 0.12 |
| 0.25 | 1.00 | 0.30 | 0.47 | 0.13 |
| 0.30 | 1.00 | 0.24 | 0.39 | 0.00 |

The default threshold is 0.15: the highest value at which the template set keeps precision 1.0.
Families at 0.15: CP01, CP02, CP05, CP06, CP07 and CP08 (six of the eight Common Paper
agreements; the Mutual NDA and the DPA stand apart, shorter and with their own skeleton), and
X04 with X05 (the two Scottish Government model contracts, the one labeled suite the structure
finds). At 0.10 the Mid-Tier and Short Form contracts join too: two Cabinet Office documents
that share drafting but are not labeled together, which is what costs the precision.

**What the measurement says.** Structure finds template families. A schedule and its core terms
are not structural twins: UK01 with UK02 scores 0.03, X01 with X02 under 0.05, UK04 with UK06
low; a schedule has its own skeleton and vocabulary. The signal a person would use next, a
document naming its parent, was checked before being built and is unreliable in this corpus:
the Model Services schedules mention the IDTA 190 times, the ICO addendum never names the IDTA,
the Mid-Tier charges schedule never names the Mid-Tier contract. If suite detection matters,
the next signals live outside the section text: publisher metadata (document properties) and
the document-set identifiers on cover pages. Not built; recorded.

Closest pairs under reader v4: CP01–CP08 0.66 (the Cloud Service and Software License
agreements share most of their skeleton and vocabulary), CP01–CP07 0.38, CP02–CP06 0.38,
CP07–CP08 0.36, CP01–CP02 0.34, CP06–CP08 0.34; X04–X05 0.25 is the only labeled suite in the
top of the list.
