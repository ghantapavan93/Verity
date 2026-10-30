# One contract changes: release notes

`/state` tells the contract-state experiment in five moments, from one committed record. Research on the experiment
is frozen; this page adds no new result.

## What the page reads

One file, through one endpoint: `GET /api/engineering/contract-state` reads
`ivo-experiments/experiments/contract-lineage/results/contract-state.json` (schema `contract-state/2`), checks the
sha256 the record carries for its own body, and returns it as it is. The page computes only sums and differences of
recorded counts. Nothing calls a model; the page works with Ollama stopped.

Evidence at lab commit `822f107` (`contract-state` branch), file sha256:

| file | sha256 |
|---|---|
| contract-state.json (the record the page reads; its body hash `637f658daa4c…`) | `cff26179f199d6d58768df968fbf4af5fda3e446e6fbe04844bf73c057290f1d` |
| audit4_labels.json (set 4, frozen at `c6d0255`) | `532ee491fe535dc3df734ab40f9b68fe0b8d576462e333b5c258008dc9873888` |
| audit4_eval.json (set 4, scored once at `cf4f874`) | `ee6ff5a2faca3b5c5dc900970a9bc3b2367216dee9c07c9050422a86eddb431b` |
| audit4_misses.json | `0053ee9703f42f70b490b3aa4ca252310b9b8136f31db6baca9a12093c6923a9` |
| certificate_mutations.json | `afdff6c7c150ce7d1a69e0fa9d29f8cbd3577be4f9e3251ca2cae043a5274caa` |
| state_arrivals.json (certificates) | `97e527812d5cf91b14d4cbc816c4367a586017d4283537c5d238d26d34e949b5` |
| state_arrivals_bucket.json (predecessor) | `e6e95fff2d8d365392894a43e57b6c42977f15691074ae1ca8f52db72a42ae6c` |
| state_arrivals_positive.json (ablation) | `e499c33b2cd9d2d3217f23392915aeee1c36c2d6d9fd2675ebb7bf5d525d2c57` |
| state_revisions.json | `959cbef789b3f99c8e0058aa8abcf2737e8adf9f4fae232ba33b65522650d95d` |
| state_authorization.json | `6f0c71240cbe32e9bfbe41e53b0c0996efd13574f870cd9b7571935c2f60cef8` |
| crash_resume.json | `e6f2ca14492f05a50f5412e864230e9d6d8e1a2df379d92389b8debd56b35c9d` |
| faults.json | `21b1441a7af6b756b0a7bcf7993f9cb6b5dcfffc866ab3d374426f615913dcf5` |

## Claims the evidence supports

- On 60 real amendments arriving one at a time into 5,414 real SEC Exhibit 10 documents (57,121 derived objects): on
  average the impact envelope held 295 objects, 27.3 were recomputed and 2.9 changed.
- 0 objects changed outside the impact envelope over the 8 arrivals checked object by object against a full rebuild;
  the state after all 60 arrivals equals a full rebuild.
- Against the predecessor engine on the same arrivals: 238 adjudications per arrival against 874, a recompute plan of
  27.3 objects against 54.4, 410 relationships re-evaluated against 1,378.
- In the 19-scenario mutation suite: 0 missed and 0 unnecessary invalidations, the rebuild state in 19 of 19; the
  predecessor missed 3 (all from a change of rules it does not declare) and re-evaluated 5 without need.
- The result is stored with the evidence that justified it: support, guard (exactly one visible text satisfies the
  reference) and scope, replayed for every accepted arrival and checked against the recorded edge.
- Set 4 (212 pairs, blind model readers): precision 1.000, recall 0.836, false families 0, direction 1.000. The
  preregistered gate required recall 0.85; it was not met, and the result stands.
- Authorization first: 0 observed cross-scope changes in the recorded test, against 53 observable leaks for global
  state filtered afterwards.

## Claims not to make

- Any speed multiple as the headline. Wall times come from single runs on one machine (1.44 s against 4.05 s
  recorded medians; a full rebuild 320 to 354 s).
- "Secure", "isolated" or "leak-free": timing side channels were not tested; the claim is what the recorded test observed.
- That the relationship engine passed its gate, or that its labels were checked by people.
- That the certificate design is a new algorithm: dynamic dependencies, early cut-off, truth maintenance and incremental
  view maintenance are prior art. What is specific is the legal domain: evidence spans, uniqueness guards, scope.
- That hash-based invalidation is broken in general: only the whole-document-hash cache defined in the experiment
  was measured.
- Anything about how Ivo's product works.

## Known limitations

- The positive-only ablation missed nothing on the real arrivals and refilings; guards show their value only in the
  mutation suite, which uses a generated portfolio.
- Refilings: the certificate engine re-evaluated 102 relationships against the predecessor's 98.
- 12 set-4 relationships were missed: 8 before binding (reading), 1 binder gap, 3 the engine cannot represent
  (one instrument acting on several agreements; a consent).
- The record lives in the experiment's checkout beside this one; the deployment reads it there.

## Future work (none built)

Reference and instrument reading; one-to-many relationships for omnibus instruments; consent and other non-mutating
relationships; human labels for set 4. See `FUTURE_WORK.md` in the experiment.
