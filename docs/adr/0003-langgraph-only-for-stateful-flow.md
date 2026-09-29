# ADR 0003: LangGraph orchestrates the review flow, and nothing else

## Context

The review flow has genuine state and branches: scope identification, retrieval, analysis,
verification, and a different ending when evidence is insufficient. A review against
guidance also fans out per topic. That is a state machine.

## Decision

One LangGraph graph owns the transitions listed in `DESIGN.md` §4. Nodes are thin: each calls
a typed service (`retrieval`, `analysis`, `verify`, `compose`). Business rules, schemas and
persistence live in those services and are tested without the graph. The graph is not shown
in the interface; the user sees stage names only.

## Alternatives considered

- **A hand-written state machine.** Sufficient for the first slice, but the per-topic fan-out
  and the retry-on-schema-error branch are where a graph library pays for itself.
- **A general agent loop with tools.** Rejected: it hides the branches we want to be explicit
  and makes runs harder to replay deterministically.

## Consequences

- LangChain is used for loaders where convenient; it does not own business logic.
- Every node writes its stage transition to the run record, which is what the SSE stream and
  the Runs surface read.
