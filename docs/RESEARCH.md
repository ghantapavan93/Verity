# What the best contract-review systems do, and what this one takes from it

Research notes of 2026-10-01, written before the day's changes and kept as they were written. Every item is marked
by how it was read: **[fetched]** (the page itself), **[search summary]** (a search engine's digest only) or
**[not reachable]**. Vendor claims and evidence are kept apart throughout. Part E ranks ten additions for this
repository under its own rules: $0, local, every component earns its place by a measurement, and the record is
never rewritten.

What happened to the ranked list on the day it was written, so this file does not drift from the record:

- **#2, the alias table**: built as data (`backend/app/retrieval/aliases.py`, seven concept groups, versioned by its
  hash, off by default) and measured without a model first (`docs/RETRIEVAL.md`): Recall@6 on CUAD-30 0.91 to 0.99
  and on SkillOpt 0.81 to 0.96, the Uncapped-liability category 0.44 to 1.00, Non-compete 0.69 to 0.94; the golden
  set's Recall@6 unchanged at 0.92, which earned the model run whose verdict is in `DECISIONS.md`.
- **#1, segmentation and the window**: measured, not built. The 6,000 / 5,000 mismatch became a run option
  (`WORKBENCH_SECTION_WINDOW`, recorded on the run when it is not the default) so the window could be measured
  rather than assumed; the census of spans the window cuts is in `docs/RETRIEVAL.md`. Typed numbering as headings
  is still a reader change, gated by the parser tournament (`docs/PARSER-COMPARISON.md`).
- **#5, typed rules**: the duration rule got the part the hostile review found wrong (the sentence about the
  finding's topic, the nearest comparison word, floors and ceilings as a range, zero notice, hyphenated and
  fortnight forms; `backend/tests/test_policy_rules.py`). The typed rule schema is not built.
- **#3, #4, #6 to #10**: not built. Each has its measurement written here; none runs before its measurement set exists.

---

Date: 2026-10-01. Method: web search + fetch of primary pages where reachable. Each item is marked
**[fetched]** (page read directly), **[search summary]** (only the search engine's digest was available), or
**[not reachable]** (403/404). Claims are separated from evidence throughout.

Pages that could not be fetched: Morningstar PR copy (403; PRNewswire copy was fetched instead),
Ivo job post on welcometothejungle (403; the Lever copy was fetched), G2 Ivo reviews (403; search digest only),
Luminance "Legal-Grade" blog and white paper (404; search digest only).

---

## Part A. Systems: claim vs evidence

### A1. Ivo (formerly Latch)

| Item | Status | Source |
|---|---|---|
| "Review chains together 400+ model calls for each review" with a "proprietary data structure" | **Claim.** No architecture, call graph, or per-step accuracy published. | [fetched] https://www.ivo.ai/product/review |
| Multi-agent: "assigns a separate AI agent to evaluate each topic in your agreement. A superior agent sits above them, reconciling conflicts and consolidating their findings." | **Claim.** No mechanics. | [fetched] https://www.ivo.ai/blog/introducing-review-2-0-contract-review-that-knows-what-your-team-has-agreed-to ; [fetched] https://www.prnewswire.com/news-releases/ivo-updates-ivo-review-delivering-contract-intelligence-and-real-legal-judgment-that-performs-on-par-with-experienced-human-lawyer-in-a-head-to-head-study-302761041.html |
| Playbooks: positions + fallbacks; "when to apply them, which fallbacks to recommend, and when the deal context means a position simply doesn't apply"; up to 3 playbooks layered (MSA + DPA, global + regional); governing-law detection | **Claim.** | Review 2.0 blog; product page |
| Playbook Builder: positions drafted from executed agreements, "with a citation back to the contract it came from" | **Claim.** Clustering mechanics not disclosed. | [fetched] https://www.ivo.ai/blog/introducing-playbook-builder-a-playbook-from-your-own-contracts-in-minutes |
| Review 2.0 "Benchmarks": every clause compared to what the team historically agreed; comparables narrowed by "contract type, governing law, your role as a party, and the counterparty's industry" | **Claim.** | Review 2.0 blog |
| "97% accuracy on CUAD … evaluated against 30,000 human lawyer annotations" | **Claim.** Metric undefined (span F1? detection? which split?). Not on the comparison page. | [fetched] product page |
| Engineering direction (job post): "Ditching imprecise embeddings models in favor of agentic RAG" (2023); "Large-scale LLM-based legal fact extraction" (2024); "Clustering legal documents descended from the same family" (2025); "Automatic deviation analysis to locate buried risk in huge contract databases" (2025); "Merging contracts with their amendments to make a time series of 'composite' contracts" (2025) | **Evidence of direction only.** Says embeddings were replaced by LLM-driven retrieval; no numbers. | [fetched] https://jobs.lever.co/ivo/1629cbb2-c07c-4214-a1e2-b4e96c9cc66c |
| Error taxonomy in Ivo's own guide: "legal reasoning errors … when the AI struggles with complex nested logic" (e.g. liability exclusions) and "issues spotting errors … when the relevant part of the document isn't processed by the AI"; advice: "narrow down the scope of their queries by only passing relevant passages" | Useful framing; matches Verity's retrieval-vs-judgement split. | [fetched] https://www.ivo.ai/blog/a-guide-to-using-generative-ai-for-reviewing-contracts |
| Head-to-head study: 19 anonymized contracts (NDAs, MSAs, DPAs); three attorney judges; five criteria (issue spotting, surgical redlining, formatting retention, commenting, judgment); "judged on a scale of 1-10"; blind; **Human 4.56, Ivo 4.52, Claude for Word (Opus 4.6) 3.50**; Ivo 2m45s/contract vs ~32 min human | **Evidence, vendor-run.** "Ivo conducted a research project." Judges unnamed. No inter-judge agreement reported (criticism from legalbenchmarks.ai). Means of ~4.5 on a 1-10 scale are not explained. Ivo did release redlines and scoring playbooks. | [fetched] https://www.ivo.ai/blog/independent-benchmark-study-ivo-matches-an-experienced-attorney-and-outperforms-claude-for-word ; [fetched] https://www.ivo.ai/contract-review-comparison ; [fetched] https://www.legalbenchmarks.ai/resources/articles/legal-ai-benchmarks-compared-harvey-lab-ivo-and-gc-ai |
| "41% higher accuracy vs. Ivo Review 1.0" | **Claim**, method undisclosed. | PRNewswire |
| CEO on hallucinations: "Ivo is built to minimize hallucinations … its reasoning is transparent and easy to find; you can see why it draws its conclusions" | **Claim.** No mechanics in the interview. | [fetched] https://www.unite.ai/min-kyu-jung-ceo-and-co-founder-of-ivo-interview-series/ |
| User complaints (G2 digest): "occasionally has hallucinations", bugs, platform "moves too quickly" | Secondary. | [search summary] https://www.g2.com/products/ivoai/reviews?qs=pros-and-cons |
| Quora case study: landing page only; white paper not public | No data extractable. | [fetched] https://www.ivo.ai/resources/quora-shares-learnings-and-best-practices-when-selecting-an-ai-contract-review-solution |

Net: Ivo's differentiators are (1) a playbook with standard + fallback + conditional application, (2) clause-level comparison to a precedent set, (3) per-topic decomposition with a reconciler, (4) provenance to the source contract, (5) Word-native "surgical" tracked changes. Nothing beyond a vendor-run 19-contract judged study is evidenced. The "400 calls" number is marketing for "many decomposed steps, each evaluated"; nothing says what those steps are.

### A2. Harvey

Harvey publishes the most engineering detail of any vendor.

- **BigLaw Bench** [fetched] https://github.com/harveyai/biglaw-bench : rubric per task, "answer quality" + "source reliability"; negative points for "errors or missteps (e.g. hallucinations)"; score = "what % of a lawyer-quality work product does the model complete". Sample rubrics public, full set private.
- **Retrieval eval** [fetched] https://www.harvey.ai/blog/biglaw-bench-retrieval : metric is **recall at a fixed token budget** against expert-labelled ground truth; claims "up to 30% more relevant content" than OpenAI/Voyage/Cohere embeddings and conventional rerankers; attributes gains to metadata integration, feature engineering (recency, jurisdiction), and LLM-based relevance. Vendor-run; contracts (merger agreements, SPAs) singled out as needing structure awareness.
- **Hallucination measurement** [fetched] https://www.harvey.ai/blog/biglaw-bench-hallucinations : definition "a factual claim made by an LLM that can be demonstrably disproven by reference to a source of truth"; measured by claim extraction then per-claim verification against sources, calibrated on human review; rate = hallucinated sentences / total sentences. Reported 0.2% (Harvey) vs 0.7% Claude, 1.3% ChatGPT, 1.9% Gemini. Vendor-run.
- **Multi-agent playbook review** [fetched] https://www.harvey.ai/blog/rebuilding-playbook-review-as-a-multi-agent-system : rule schema = **standard position, acceptable deviations, unacceptable deviations, guidance, optional (absence OK?)**. The document gets "unique identifiers for components" so an agent can "cite and edit a specific element unambiguously"; each worker searches, follows references to exhibits, picks standard or fallback, drafts edits on an isolated branch; "every proposed edit is a tracked change on that branch, tagged with the rule that produced it"; collisions escalate to the lead. Eval: risk classification 59%→77%, redline rubric 53%→87%, latency 2.6→3.8 min; graded by "a committee of three frontier models". Harvey itself says results are "evidence of improvement within Harvey's evaluation setup, not … an independently audited measure" (ZenML digest [fetched] https://www.zenml.io/llmops-database/multi-agent-contract-playbook-review-with-conflict-aware-redlining).
- **Review-table citations** [fetched] https://www.harvey.ai/blog/rebuilding-harveys-review-algorithm : old citations used "an algorithm that combined model-generated text and fuzzy matching" at cell level; new ones point "to indices throughout the document" at sentence level; output split into **answer + reasoning**. Side-by-side preference 4x overall, 7x on credit agreements and trial exhibits; "reviewers consistently preferred responses that showed their reasoning". This is direct evidence that index-based citation beats fuzzy quote matching for verification UX and latency.
- **Eval practice** [fetched] https://www.zenml.io/llmops-database/building-and-evaluating-legal-ai-at-scale-with-domain-expert-integration : three prongs (human side-by-side on a 7-point scale, LLM auto-eval, workflow decomposition); for RAG they "separately evaluate query rewriting, document retrieval, answer generation, and citation creation".
- **Independent:** Vals VLAIR Feb 2025 [fetched] https://www.vals.ai/industry-reports/vlair-2-27-25 : Harvey top on Document Q&A (94.8%) and Data Extraction (75.1% vs lawyers 71.1%); **Redlining: lawyers 79.7% vs Harvey 65.0%**, and performance "improved only when clauses were provided as clearly labeled plain text". Vals used LLM-as-judge with pass/fail checks and noted verbose answers scored higher.

### A3. Spellbook
- Buyer guide [fetched] https://spellbook.com/learn/how-to-evaluate-legal-ai-vendors : "Every output must use RAG … to point to a specific paragraph in a specific document"; "logs every AI suggestion and the specific playbook rule that triggered it"; confidence scoring. No architecture or eval numbers published. Third-party reviews report occasional wrong citations ([search summary] https://www.hyperstart.com/blog/spellbook-alternatives/).

### A4. Luminance
- Blog and white paper **[not reachable]** (404). Search digest: "Legal-Grade", multi-model "panel of judges", "Recursive Legal Contextual Understanding" (whole-contract rather than clause-by-clause), citations to source passages, "returns questions when it doesn't have enough information rather than guessing". All **claims**; no numbers found. https://www.luminance.com/resources/blog/what-makes-luminances-ai-legal-grade/

### A5. Robin AI
- Company entered receivership; managed-services arm sold to Scissero (Dec 2025); engineering team acqui-hired by Microsoft (Jan-Mar 2026). [search summary] https://www.artificiallawyer.com/2026/01/09/microsoft-to-acqui-hire-robin-ai-tech-team/ ; https://spellbook.com/learn/robin-ai-pricing . Product had clickable citations to provisions. A third-party review's "85-90% of playbook deviations" is unverified. Nothing architectural published.

### A6. LegalOn
- [fetched] https://www.geeklawblog.com/2025/09/building-consistent-ai-for-contract-review-with-legalons-daniel-lewis.html : 100+ attorney-defined issues per contract type; motivation is **consistency** ("asking ChatGPT to review the same contract twice yields different issues"); suggestions are **attorney-drafted language + a practice note**, not model-generated; i.e., the model matches, deterministic content answers. 135+ playbooks ([search summary] https://www.legalontech.com/resources/product-sheet-playbooks). Inline Citations with hover preview card, Spring 2026 ([search summary] https://www.legalontech.com/post/whats-new-in-legalon-spring-2026). No eval numbers.

### A7. Hebbia
- "Goodbye RAG" post [fetched] https://www.hebbia.com/blog/goodbye-rag-how-hebbia-solved-information-retrieval-for-llms : despite the title, the pipeline chunks into "contextually dense … components … smaller than a context window", runs parallel full-attention passes, synthesizes, then "reverse engineer[s] the highlight worthy document text" and validates using "token level log-likelihoods and text/character level heuristics". The "92% vs 68%" ISD number circulates only in secondary sources ([search summary] note.com) and is not in Hebbia's own posts I could fetch. "Deeper" agent post [fetched] https://www.hebbia.com/blog/inside-hebbias-deeper-research-agent gives only "reduces context size by over 90%".

### A8. Lexion / DocuSign
- Acquired May 2024 for $165M ([search summary] https://www.docusign.com/company/news-center/docusign-completes-acquisition-of-lexion-to-accelerate-intelligent-agreement-management). NLP → structured contract data; "AI Contract Assist" compares against playbooks. No architecture or accuracy publications found.

### A9. Casetext CoCounsel / Thomson Reuters
- TR blog [fetched] https://legal.thomsonreuters.com/blog/benchmarking-and-evaluating-ai-solutions-in-legal-work/ : cites Vals (73.2-89.6% on four tasks) and "1,200 bar-admitted attorneys"; no hallucination definition or citation-verification method described. Secondary sources say multi-model orchestration plus "rules-based validation tools" and citation checkers ([search summary] https://theneuralbase.com/ai-for-legal/learn/advanced/thomson-reuters-cocounsel/).
- **Stanford RegLab / HAI** [fetched] https://hai.stanford.edu/news/ai-trial-legal-models-hallucinate-1-out-6-or-more-benchmarking-queries ; paper https://arxiv.org/abs/2405.20362 (JELS 2025 https://onlinelibrary.wiley.com/doi/full/10.1111/jels.12413): preregistered, 202 queries, Lexis+ AI >17%, Ask Practical Law AI >17% (with >60% refusals), Westlaw AI-AR >34%; GPT-4 58-82%. Two hallucination kinds: **incorrect** and **misgrounded** ("describes the law correctly, but cites a source which does not in fact support its claims"). Error causes: failed retrieval, inapplicable authority, **sycophancy to false premises** (a dedicated false-premise query category). "RAG is not a panacea."

### A10. Benchmarks and meta-evidence
- **Vals VLAIR** (Feb 2025, above): AI beats lawyers on extraction/Q&A/summarization; loses on redlining; LLM-judge with checks; verbosity correlates with score. Oct 2025 VLAIR is legal research only, no contract tasks ([fetched] https://www.vals.ai/industry-reports/vlair-10-14-25).
- **legalbenchmarks.ai** [fetched]: all three vendor benches (Ivo 19-contract, GC AI 100-task LLM-judged, Harvey 1,200-task) were "scoped, designed, and graded by the company whose product sits on the leaderboard".
- **Citation grounding depends on the oracle** [fetched] https://arxiv.org/abs/2606.00898 : the same 400 answers scored 79-86% "accurate" against a sparse citation DB and 98.9-99.9% against a 10x denser one; "no two systems are distinguishable at 95% confidence". Lesson: a hallucination rate is only meaningful when the verifier's corpus is complete. Verity's quote-locate ladder runs against the full stored text, so its "unlocated quote" rate is a sound oracle; keep it that way (never verify against a subset).
- **Who checks the citations** [fetched] https://arxiv.org/abs/2606.21155 : 1,300 brief excerpts with injected errors; best agentic GPT-5 only 84.4% recall / 55.0% F1 at 15.3 steps per excerpt; "all models struggle with subtle error categories". Model-based citation checking is expensive and weak; code-based exact location (Verity's approach) is the cheap, strong part.
- **Legal warrant position paper** [fetched] https://arxiv.org/abs/2609.17546 : systems should "answer, narrow, ask, warn, correct a false premise, or abstain"; sentence-citation alignment alone misses "material failures". Supports keeping a separate "conclusion supported by quote?" judgement from "quote exists?".

---

## Part B. Techniques with evidence

### B1. Retrieval
| Technique | Evidence | Fit for Verity |
|---|---|---|
| **Contextual retrieval** (prepend an LLM-written 50-100 token context to each chunk before BM25 and embedding) | [fetched] https://www.anthropic.com/engineering/contextual-retrieval : top-20 failure 5.7%→3.7% (contextual embeddings), →2.9% (+contextual BM25), →1.9% (+rerank). Also: top-20 beat top-5/10; BM25 needed for exact matches; skip RAG under ~200k tokens. CRAwLeR [fetched] https://arxiv.org/abs/2606.21676 (Danish/Polish legal cross-references): "contextualized baselines (Anthropic-style) outperform traditional retrieval", but best Recall@10 only 55-59%: cross-reference-dependent queries stay hard. | $0 with local Qwen; context strings become part of the index so must be stored in the run record with model+seed. Deterministic at temp 0 with seed. |
| **Hybrid + cross-encoder rerank** | Anthropic (above). [fetched] https://arxiv.org/html/2604.01733v1 (financial text+tables, 10 methods): **BM25 beat dense on every metric except Recall@20**; hybrid RRF + cross-encoder best (Recall@5 0.816, MRR@3 0.433→0.605, +40% rel.); reranker gain "negligible with only 20 candidates but improved sharply at 50+"; **HyDE and multi-query underperformed** because hypothetical docs "hallucinate plausible but incorrect … figures". One LongEval report in the search digest found off-the-shelf bge-reranker-base **hurt** nDCG by 0.3-3.1 pts on technical corpora ([search summary] https://ceur-ws.org/Vol-4038/paper_276.pdf, not individually verified). | Local candidates: Qwen3-Reranker-0.6B (Apache-2.0, MTEB-R 65.80 vs bge-reranker-v2-m3 57.03, 100+ languages, instruction-tunable) [fetched] https://huggingface.co/Qwen/Qwen3-Reranker-0.6B ; bge-reranker-v2-m3 (0.6B, Apache-2.0) [fetched] https://huggingface.co/BAAI/bge-reranker-v2-m3 . Deterministic (no sampling). Needs a wider BM25 pool (≥30-50) to pay off. |
| **Late interaction (ColBERT)** | answerai-colbert-small-v1: 33M params, Apache-2.0, BEIR avg 53.79 vs bge-base 53.25 and ColBERTv2 50.02 [fetched] https://huggingface.co/answerdotai/answerai-colbert-small-v1 . Storage/latency penalties ([search summary] Vespa, CLERC) are irrelevant for a single contract of <200 sections. | Plausible but Verity already measured dense+RRF as "+3 goldens, 1 regression"; a reranker over BM25 is the cheaper test. Try only if rerank fails. |
| **HyDE / query rewriting** | Negative on precise domains (financial paper above); general surveys positive on vague queries ([search summary] https://arxiv.org/pdf/2412.17558). | Verity's gap is vocabulary (non-compete ↔ restrictive covenant; uncapped ↔ unlimited / "shall not be limited"). A **curated, deterministic alias table** addresses that at $0 with no model in the loop. |
| **Clause-level segmentation** | Harvey assigns unique IDs per document component so agents cite "unambiguously"; Vals: redlining only worked with "clearly labeled plain text"; Ivo: issue-spotting errors are "when the relevant part of the document isn't processed". DOCX: numbered outline headings carry `w:numPr`/outline level in the style rather than a Heading-N name ([search summary] https://github.com/python-openxml/python-docx/issues/180 , https://github.com/docling-project/docling/issues/4281 ). | Direct fix for Verity's "typed numbering not seen as headings" and the 6k/5k mismatch. |

### B2. Grounding and verification
| Technique | Evidence | Fit |
|---|---|---|
| **Quote-first, then judge** | LLMQuoter [fetched] https://arxiv.org/abs/2501.05554 : LLaMA-3B LoRA quoter, "quote-first-then-answer", ">20-point accuracy gains across both small and large" models vs full-context. Hebbia's pipeline is also quote-then-synthesize with post-hoc highlight recovery. | Verity already does quote-first in one call; a two-stage split (extract candidate quotes per section → judge over located quotes only) is the natural extension. |
| **Attribution / NLI entailment** (AutoAIS) | Attributed QA [fetched] https://arxiv.org/abs/2212.08037 ; ExpertQA ([search summary] https://arxiv.org/abs/2309.07852 ): NLI-based AutoAIS correlates ~0.96 with humans at system level; TRUE-style NLI F1 ≈ .86 vs human attribution labels; "high precision but low recall". VeriCite [fetched] https://arxiv.org/abs/2510.11394 : NLI claim check + evidence selection, works on five open-source LLMs. HHEM (Vectara) open-weights NLI-style consistency model [fetched] https://www.vectara.com/blog/do-smaller-models-hallucinate-more . | A local DeBERTa-MNLI / HHEM check "is the finding's conclusion entailed by its located quote?" closes the Stanford "misgrounded citation" hole that exact-quote location cannot. Classifier is deterministic. |
| **Index-pointer citations** | Harvey moved off "model-generated text and fuzzy matching" to index pointing; 4x preference. | Verity's ladder is the fuzzy approach. Returning section-id + char offsets (which Verity already computes) to the UI is the same move. |
| **False premise** | Stanford: sycophancy is a distinct error class. DecoPrompt [fetched] https://arxiv.org/abs/2411.07457 : "entropy of the false-premise prompt is closely related to its likelihood to elicit hallucination"; cross-model transferable. Premise verification via retrieval [search summary] https://arxiv.org/pdf/2504.06438 . Warrant paper: "correct a false premise" is a first-class response. | 8B models repeat premises; a **code-side premise check** (does the asserted entity/number locate in the text?) is $0 and deterministic. |

### B3. Generation and evaluation
| Topic | Evidence | Fit |
|---|---|---|
| **Structured output on Ollama** | Ollama `format` = JSON schema compiled to llama.cpp GBNF grammar, token-masked sampling ([search summary] https://news.ycombinator.com/item?id=42346344 , https://blog.danielclayton.co.uk/posts/ollama-structured-outputs/ ). Docs [fetched] https://docs.ollama.com/capabilities/structured-outputs recommend temperature 0 **and** "pass the JSON schema as a string in the prompt". XGrammar-2 ([search summary] https://arxiv.org/pdf/2601.04426 ): schema validity 22%→100% on 1B models; but constrained decoding "can degrade content quality if the model's probability mass … lies outside the grammar". | Verity already does this. Check the prompt includes the schema text; keep "withhold" as a legal schema value so the grammar never forces a finding. |
| **Thinking mode, quantization, laziness** | ContractEval [fetched] https://arxiv.org/abs/2508.03080 (19 models on CUAD, 41 risk categories): "Reasoning ('thinking') mode improves output effectiveness but reduces correctness"; quantization costs accuracy; open models "generate 'no related clause' responses more frequently even when relevant clauses are present" (laziness metric). Metrics: correctness F1/F2, Jaccard effectiveness, laziness rate ([fetched] https://github.com/olivialiu121/ContractEval). | Verity's thinking-off choice is supported. Laziness = Verity's recall ceiling (0.67); measure it explicitly. |
| **Small-model CUAD numbers** | [fetched] https://github.com/Ihtesham-star/cuad_llm_finetuning : zero-shot **Qwen3-8B strict F1 0.540** (as cited from ContractEval), Qwen3-14B 0.410 strict / 0.816 detection, GPT-4.1 0.641, Claude Sonnet 4 0.523; **QLoRA Qwen3-4B 0.678 strict / 0.900 detection F1, 97.2% verbatim**, 45 min on one RTX 5090, served via Ollama JSON grammar at temp 0; ~70% of (contract, clause) pairs are absences and empty lists are explicit training targets. Data curve: 50 contracts → 0.746 detection F1, 150 → 0.862, 408 → 0.900. | A $0 fine-tune is feasible and the biggest single lift on the same benchmark Verity uses. Risk: CUAD-30 must be disjoint from training contracts; adapter hash must go in the run record. |
| **Self-consistency vs temp 0** | Decoding survey [search summary] https://arxiv.org/html/2402.06925v3 : greedy ≈ sampling on average; greedy chosen "given … superior reproducibility". Self-consistency gains require sampling at T≈0.7 and voting. | Sampling breaks Verity's seed/temperature-0 reproducibility. A **deterministic ensemble** (same model, 2-3 different context orderings or prompt variants, intersect by located span) keeps determinism and can be measured. |
| **LLM-as-judge pitfalls** | Survey [search summary] https://arxiv.org/pdf/2412.05579 ; self-preference [search summary] https://arxiv.org/pdf/2410.21819 : position, verbosity, self-preference biases. Vals observed verbosity-score correlation. Harvey mitigates with a 3-model committee and human calibration. | Keep code-graded goldens and expert spans as the deciders; use a local LLM judge only as a triage signal, never as the adoption gate. |
| **Legal-specific vs general models** | [fetched] https://arxiv.org/html/2508.07849v1 : 110M Legal-BERT/Contracts-BERT set SOTA on LEDGAR/UNFAIR-ToS vs 355M general encoders; LEDGAR paragraphs truncated to 128 tokens lost only 0.1-0.4%. MAUD zero-shot is weak even for GPT-4 ([search summary] https://arxiv.org/pdf/2301.00876v2). LegalBench small models ~49-58% ([search summary] https://arxiv.org/pdf/2509.22472). | Small encoders are strong at clause *classification*; a clause-type classifier could pre-tag sections for retrieval, but it is a new dependency and should be measured against the alias table first. |
| **Multilingual** | Little non-English contract benchmark data ([search summary] https://arxiv.org/pdf/2605.29738 , https://arxiv.org/pdf/2509.22472 ); bge-m3 / Qwen3 rerankers are multilingual. | Verity's casefold ladder needs NFKC normalization and the duration parser needs locale rules before any non-English claim. Not a near-term priority absent a measurement set. |

---

## Part C. Playbook / guidance comparison systems

- **Rule schema** (Harvey, fetched): standard position, acceptable deviations (fallbacks), unacceptable deviations, guidance (deal-context conditions), optional (absence allowed). Edits are tagged with the rule that produced them.
- **Deterministic content** (LegalOn, fetched): the suggested replacement language and practice note are attorney-authored; the model only decides which rule fires. Motivation is run-to-run consistency.
- **Precedent comparison** (Ivo, fetched claim): each clause is compared to the team's historical positions filtered by contract type / governing law / role / counterparty industry; positions and fallbacks are drafted from precedents with citations to the source contract.
- **Audit trail** (Spellbook guide, fetched): log every suggestion with "the specific playbook rule that triggered it".
- **Redlining reality** (Vals, fetched): AI lost to lawyers on redlining (65.0 vs 79.7) and needed clearly labelled plain-text clauses to work at all.

Verity today: "guidance" is effectively a notice-period duration check; status is code-computed only when durations are present in the quote, else the model's hint. The gap to the field is a typed rule schema where the *check type* (duration, presence/absence, cap amount, party direction, regex) is explicit, so status is code-computed for most rules and the model's hint is the exception.

---

## Part D. Evidence UX and user complaints

- **Harvey**: sentence-level citations by index pointer; answer + reasoning fields; 4x preference, 7x on complex documents; "reviewers consistently preferred responses that showed their reasoning" (fetched).
- **GC AI "Exact Quote"**: "click the citation in chat, the source passage highlights in Doc View"; evaluation criterion "can it produce a character-level verbatim citation back to the source document?" ([fetched] https://gc.ai/blog/legal-ai-tools).
- **LegalOn**: hover card with source title/type, click to exact passage (search summary).
- **Spellbook**: numbered links to passages (search summary).
- **Complaints** ([fetched] https://www.vaquill.ai/blog/what-lawyers-really-think-of-legal-ai digest of r/legaltech, r/LawFirm, r/paralegal; secondary): "upload the contract, read the AI summary, then read the whole contract anyway to verify" — tools that do not cut verification time are abandoned "within two weeks"; hallucinated citations are the top complaint; "overpriced wrapper"; low login rates. Surveys: 81% of mid-size firm leaders report reliability concerns; 40% of sceptics cite accuracy as the main reason ([search summary] https://www.lawnext.com/2026/03/legal-industry-reaches-ai-tipping-point-majority-of-lawyers-now-using-gen-ai-despite-persistent-reliability-concerns.html , https://legal.thomsonreuters.com/blog/genai-report-executive-summary-for-legal-professionals-tri/ ).
- Implication: the measurable UX variable is **seconds to verify a finding**. Verity already has char offsets for every located quote; surfacing them in-document, with the rule that fired and the count of withheld findings, is the cheapest route to that metric.

---

## Part E. Ranked additions for Verity (fit: $0, local, measured, records immutable)

Effort: S = ≤2 days, M = 3-7 days, L = >1 week. "Goldens" = the 44 golden questions on one contract; "CUAD-30" = the 30-contract expert-span set (P 0.85 / R 0.67; Recall@6 0.85/0.92).

### 1. Structure-faithful segmentation: numbered headings + clause tree + window alignment
- **What**: In the DOCX reader, treat paragraphs with `w:numPr` / outline level or a typed `^\d+(\.\d+)*\s` prefix as headings; build a parent/child clause tree with stable IDs (`7.2(b)`); make the retrieval unit the leaf clause with its ancestor headings prepended; set the per-section cap and the model's window from one constant so 6,000 vs 5,000 cannot diverge; add a boundary census to the run record (sections truncated, chars dropped).
- **Why**: Harvey gives every component a unique ID so agents "cite and edit a specific element unambiguously"; Vals found AI redlining works only on "clearly labeled plain text"; Ivo names "the relevant part of the document isn't processed" as one of its two error classes. Known Verity bug.
- **Measure**: (a) CUAD-30 *span containment*: % of expert spans that fall wholly inside one section (new metric, code-graded); (b) Recall@6 on CUAD-30 ≥ 0.85/0.92 with no golden regression; (c) chars-dropped-by-window = 0 on all 30 contracts. Adopt if (a) rises by ≥10 points and (b),(c) hold.
- **Effort**: M. **Risk**: changes section numbering in new runs only; old run records untouched. No new dependency.

### 2. Deterministic legal alias expansion for the retrieval query
- **What**: A versioned, hand-curated alias table (non-compete ↔ non-competition, covenant not to compete, restrictive covenant, restraint of trade, non-solicit; uncapped liability ↔ unlimited liability, "no cap", "shall not be limited", "notwithstanding the foregoing … limitation"; etc.) applied to BM25 query terms, with the table hash in the run record.
- **Why**: The two known weak categories are vocabulary gaps. HyDE/multi-query hurt on precise domains (financial RAG paper); BM25 beat dense there; hybrid gave Verity +3/-1 already. Aliases are the $0, model-free version of query expansion.
- **Measure**: CUAD-30 Recall@6 on the Non-Compete and Uncapped-Liability categories (per-category, code-graded) and overall; goldens. Adopt if per-category Recall@6 rises ≥0.15 and overall precision on CUAD-30 stays ≥0.85 with 0 golden regressions.
- **Effort**: S. **Risk**: none to provenance; table is data in the record.

### 3. Code-side false-premise guard
- **What**: Before the model call, parse the question for asserted facts (a number, a duration, a party, a clause name); run each through the existing locate ladder; if the premise does not locate, prepend a hard instruction ("The question asserts X; X was not found in the contract. Do not assume it.") and allow a schema value `premise_unverified` that the UI renders as a correction. After the call, if a finding's quote only matches the question text and not the contract, withhold.
- **Why**: Stanford RegLab treats false-premise sycophancy as a distinct error class and found commercial tools fail it; the legal-warrant paper lists "correct a false premise" as a required response mode; DecoPrompt shows false-premise prompts are detectable; Verity's 8B model is known to repeat premises.
- **Measure**: Add 10 false-premise goldens (same contract, Stanford-style: "Why is the 90-day notice period one-sided?" when it is 30 days). Metric: % answered with an explicit correction or abstention and zero fabricated quotes. Adopt at ≥8/10 with 0 regressions on the 44.
- **Effort**: S-M. **Risk**: none to provenance; adds a documented response mode to the record.

### 4. Local cross-encoder rerank over a wider BM25 pool
- **What**: BM25 top-40 → Qwen3-Reranker-0.6B (or bge-reranker-v2-m3) → top-6. Model name + weights hash + scores stored in the run record; deterministic (no sampling).
- **Why**: Reranking gave the largest single gain in both the Anthropic study (2.9%→1.9% failure) and the financial-RAG benchmark (+40% MRR@3), but only with ≥50 candidates; one report found an older bge-reranker hurt on technical corpora, so it must be measured, not assumed.
- **Measure**: Recall@6 on CUAD-30 (0.85/0.92) and goldens. Adoption bar = the one hybrid retrieval failed: ≥+3 goldens with 0 regressions, and CUAD-30 Recall@6 +≥0.03. Also record latency per contract on the local box.
- **Effort**: M. **Risk**: new dependency (transformers/sentence-transformers + 0.6B weights, ~1.2 GB); must be pinned; CPU latency may be seconds per contract.

### 5. Typed playbook rules with code-computed status
- **What**: Replace free-text guidance with rule objects: `{topic, standard, fallbacks[], unacceptable[], optional, check: {type: duration|presence|amount|direction|regex, params}}`. Status is computed in code whenever `check` can be evaluated on the located quote (durations already work; add presence/absence, monetary cap, mutuality); model hint only for untyped rules; the rule ID that fired is stored with each finding.
- **Why**: Harvey's rule schema (standard / acceptable / unacceptable / guidance / optional); LegalOn's deterministic suggested language for consistency; Spellbook's "log … the specific playbook rule that triggered it"; Ivo's positions + fallbacks. Vals shows redlining is the weak task, so position *comparison* with deterministic status is where the value is.
- **Measure**: (a) % of findings with code-computed status (today: durations only) on CUAD-30 topics — target ≥50%; (b) status accuracy vs a hand-labelled key on the 44 goldens ≥ current model-hint accuracy; (c) run-to-run status identity = 100%.
- **Effort**: M. **Risk**: none; strengthens the "status computed by code" claim.

### 6. Entailment gate: conclusion must be supported by the located quote
- **What**: After quote location, run a local NLI classifier (DeBERTa-v3 MNLI or Vectara HHEM-2.1-open) with premise = located quote (+ heading), hypothesis = finding's one-sentence conclusion. Below threshold → finding kept but labelled "quote located, conclusion not entailed" (never silently dropped); score and model hash in the record.
- **Why**: Stanford's "misgrounded citation" class (right text, wrong support) is exactly what exact-quote location cannot catch; AutoAIS/NLI attribution correlates ~0.96 with humans at system level and is high-precision; Harvey verifies per claim; VeriCite shows NLI gating works with open models. Model-based citation checkers are weak and expensive (55% F1 at 15 steps); a classifier is cheap and deterministic.
- **Measure**: Hand-label every finding in the 44 goldens as supported / not supported by its quote. Gate precision/recall on that label. Adopt if it flags ≥50% of unsupported findings with ≤5% of supported findings flagged.
- **Effort**: M. **Risk**: one new dependency (~0.4-0.7 GB weights); classifier output is deterministic; adds a field, never rewrites history.

### 7. Contextual section prefixes (stored, deterministic)
- **What**: Once per document, ask local Qwen (temp 0, seed) for a 50-100 token "where this sits in the contract" prefix per section (parent headings, defined terms used, what it cross-references); prepend to the BM25 text; store prefixes + prompt hash in the run record.
- **Why**: Anthropic: contextual BM25+embeddings cut top-20 failure 5.7%→2.9%; CRAwLeR: contextualised baselines win on cross-reference-dependent legal queries; Harvey credits "metadata integration: contextualizing passages within complicated documents".
- **Measure**: Same as #4; adopt only if it beats the alias table (#2) alone by ≥+2 goldens / ≥+0.03 CUAD-30 Recall@6 with 0 regressions. Also measure index build time.
- **Effort**: M. **Risk**: index now depends on model output; mitigated by storing prefixes verbatim. N extra model calls per document (the "many calls" pattern Ivo markets).

### 8. Two-stage quote-first review (extract → judge over located quotes only)
- **What**: Stage 1: per retrieved section, a schema-constrained call returns candidate verbatim quotes for the topic (or an explicit empty list). Code locates them. Stage 2: one call sees only located quotes with IDs and returns findings that must reference quote IDs. Everything the judge sees is already provenance-checked.
- **Why**: LLMQuoter: quote-first gives >20-pt gains for small models; ContractEval: open models are "lazy" (false "no related clause"), which a per-section extraction pass with explicit empty-list handling targets; the CUAD fine-tune repo trained on absences for the same reason. Removes the 5,000-char window from the judgement step.
- **Measure**: CUAD-30 precision/recall and a new *laziness* metric (ContractEval definition: false "none" when a gold span exists). Adopt if recall 0.67→≥0.72 at precision ≥0.85 and laziness drops; goldens 0 regressions. Record calls-per-review.
- **Effort**: M-L. **Risk**: more calls = more places for nondeterminism; keep temp 0 + seed; store every stage output.

### 9. In-document provenance view and a verification-time metric
- **What**: Render each finding's located span with its char offsets highlighted in the stored text, the rule ID that fired, the entailment label (#6), and the count of withheld findings per topic. "Why this answer?" becomes answer + reasoning + pointer, Harvey-style.
- **Why**: Harvey's index-pointer, sentence-level citations were preferred 4x (7x on complex docs); GC AI and LegalOn ship click-to-highlight / hover provenance; the dominant user complaint is "read the whole contract anyway to verify".
- **Measure**: Timed verification task: one reviewer verifies all findings for 10 goldens with vs without the view; metric = median seconds per finding and % of findings verified correctly. Adopt if median time falls ≥30% with no accuracy loss. Record the protocol with the results.
- **Effort**: M. **Risk**: UI only; reads the immutable record.

### 10. QLoRA fine-tune of Qwen3-4B/8B on CUAD (held-out CUAD-30)
- **What**: Replicate the public recipe (QLoRA r=16, 2 epochs, ~45 min on one consumer GPU, Ollama JSON grammar, temp 0) on CUAD training contracts strictly disjoint from CUAD-30; adapter hash in the run record.
- **Why**: Public, reproducible numbers on the benchmark Verity already uses: Qwen3-8B zero-shot strict F1 0.540 → Qwen3-4B fine-tuned 0.678 strict / 0.900 detection, 97.2% verbatim. Fine-tuning on explicit absences also attacks laziness.
- **Measure**: CUAD-30 precision/recall vs 0.85/0.67; goldens (A1-lite-style frozen protocol: freeze adapter before reading held-out). Adopt if recall ≥0.75 at precision ≥0.85 and goldens ≥ current.
- **Effort**: L (data prep, training, contamination audit). **Risk**: model identity changes (must version the adapter like a dependency); contamination if any CUAD-30 contract is in training; GPU availability; ContractEval warns quantized models lose accuracy, so the served quantization must be the measured one.

### Considered and not recommended now
- **HyDE / LLM query rewriting**: negative evidence on precise domains; #2 covers the vocabulary gap deterministically.
- **Self-consistency sampling**: needs T>0; breaks reproducibility; a deterministic ensemble can be tested after #8 if precision is still the issue.
- **ColBERT**: only if #4 fails; a 33M model is cheap but Verity already saw marginal gains from dense retrieval.
- **LLM-as-judge for adoption decisions**: position/verbosity/self-preference biases; keep code-graded sets as the gate.
- **Cross-document search and redlining**: Ivo's repository features and Vals' weakest AI task respectively. Cross-doc BM25 over stored run records is $0 and could be a later item once a measurement set exists; redlining should wait for #5 (typed positions) since Vals shows it only works with labelled clauses and loses to lawyers today.

---

## Source list (all URLs used)
Ivo: https://www.ivo.ai/product/review ; https://www.ivo.ai/blog/introducing-review-2-0-contract-review-that-knows-what-your-team-has-agreed-to ; https://www.ivo.ai/blog/introducing-playbook-builder-a-playbook-from-your-own-contracts-in-minutes ; https://www.ivo.ai/blog/independent-benchmark-study-ivo-matches-an-experienced-attorney-and-outperforms-claude-for-word ; https://www.ivo.ai/contract-review-comparison ; https://www.ivo.ai/ppc/review-competition ; https://www.ivo.ai/blog/a-guide-to-using-generative-ai-for-reviewing-contracts ; https://www.ivo.ai/resources/quora-shares-learnings-and-best-practices-when-selecting-an-ai-contract-review-solution ; https://jobs.lever.co/ivo/1629cbb2-c07c-4214-a1e2-b4e96c9cc66c ; https://www.prnewswire.com/news-releases/ivo-updates-ivo-review-delivering-contract-intelligence-and-real-legal-judgment-that-performs-on-par-with-experienced-human-lawyer-in-a-head-to-head-study-302761041.html ; https://www.unite.ai/min-kyu-jung-ceo-and-co-founder-of-ivo-interview-series/ ; https://www.g2.com/products/ivoai/reviews?qs=pros-and-cons (403) ; https://www.legalbenchmarks.ai/resources/articles/legal-ai-benchmarks-compared-harvey-lab-ivo-and-gc-ai
Harvey: https://github.com/harveyai/biglaw-bench ; https://www.harvey.ai/blog/biglaw-bench-retrieval ; https://www.harvey.ai/blog/biglaw-bench-hallucinations ; https://www.harvey.ai/blog/rebuilding-playbook-review-as-a-multi-agent-system ; https://www.harvey.ai/blog/rebuilding-harveys-review-algorithm ; https://www.zenml.io/llmops-database/multi-agent-contract-playbook-review-with-conflict-aware-redlining ; https://www.zenml.io/llmops-database/building-and-evaluating-legal-ai-at-scale-with-domain-expert-integration
Others: https://spellbook.com/learn/how-to-evaluate-legal-ai-vendors ; https://www.luminance.com/resources/blog/what-makes-luminances-ai-legal-grade/ (404) ; https://www.artificiallawyer.com/2026/01/09/microsoft-to-acqui-hire-robin-ai-tech-team/ ; https://www.geeklawblog.com/2025/09/building-consistent-ai-for-contract-review-with-legalons-daniel-lewis.html ; https://www.legalontech.com/post/whats-new-in-legalon-spring-2026 ; https://www.hebbia.com/blog/goodbye-rag-how-hebbia-solved-information-retrieval-for-llms ; https://www.hebbia.com/blog/inside-hebbias-deeper-research-agent ; https://www.docusign.com/company/news-center/docusign-completes-acquisition-of-lexion-to-accelerate-intelligent-agreement-management ; https://legal.thomsonreuters.com/blog/benchmarking-and-evaluating-ai-solutions-in-legal-work/ ; https://gc.ai/blog/legal-ai-tools ; https://www.vaquill.ai/blog/what-lawyers-really-think-of-legal-ai
Benchmarks/studies: https://hai.stanford.edu/news/ai-trial-legal-models-hallucinate-1-out-6-or-more-benchmarking-queries ; https://arxiv.org/abs/2405.20362 ; https://www.vals.ai/industry-reports/vlair-2-27-25 ; https://www.vals.ai/industry-reports/vlair-10-14-25 ; https://arxiv.org/abs/2606.00898 ; https://arxiv.org/abs/2606.21155 ; https://arxiv.org/abs/2609.17546 ; https://arxiv.org/abs/2508.03080 ; https://github.com/olivialiu121/ContractEval ; https://github.com/Ihtesham-star/cuad_llm_finetuning ; https://arxiv.org/html/2508.07849v1 ; https://arxiv.org/abs/2511.00340 ; https://arxiv.org/pdf/2301.00876v2
Techniques: https://www.anthropic.com/engineering/contextual-retrieval ; https://arxiv.org/abs/2606.21676 ; https://arxiv.org/html/2604.01733v1 ; https://huggingface.co/Qwen/Qwen3-Reranker-0.6B ; https://huggingface.co/BAAI/bge-reranker-v2-m3 ; https://huggingface.co/answerdotai/answerai-colbert-small-v1 ; https://arxiv.org/abs/2501.05554 ; https://arxiv.org/abs/2212.08037 ; https://arxiv.org/abs/2309.07852 ; https://arxiv.org/abs/2510.11394 ; https://www.vectara.com/blog/do-smaller-models-hallucinate-more ; https://arxiv.org/abs/2412.17056 ; https://arxiv.org/abs/2411.07457 ; https://arxiv.org/pdf/2504.06438 ; https://docs.ollama.com/capabilities/structured-outputs ; https://news.ycombinator.com/item?id=42346344 ; https://arxiv.org/pdf/2601.04426 ; https://arxiv.org/html/2402.06925v3 ; https://arxiv.org/pdf/2412.05579 ; https://arxiv.org/pdf/2410.21819 ; https://arxiv.org/pdf/2412.17558 ; https://github.com/python-openxml/python-docx/issues/180 ; https://github.com/docling-project/docling/issues/4281 ; https://ceur-ws.org/Vol-4038/paper_276.pdf (search digest only)
