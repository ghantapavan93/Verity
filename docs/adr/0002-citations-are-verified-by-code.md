# ADR 0002: Citations are verified by deterministic code before anything is shown

## Context

The two prompt baselines showed that a capable model reads contracts well and quotes
accurately most of the time. "Most of the time" is not good enough for a product whose
value is that a reviewer can trust the evidence beside a conclusion.

## Decision

The model proposes spans (quotes and section hints). A span matcher written in Python
locates each quote in the stored section text after whitespace and typographic-quote
normalisation and records `(section, start, end)`. A finding is shown only if every span
verifies. Otherwise the finding is `unresolved`: the conclusion is withheld, the raw model
output is kept in the run, and the interface says evidence was insufficient.

## Consequences

- The click-to-highlight interaction is exact by construction: it targets verified offsets,
  not a re-search of the text.
- Some correct answers will be withheld when the model paraphrases instead of quoting. The
  prompt asks for verbatim quotes, and the withheld cases are visible in Runs, so the rate is
  measurable.
- The verifier is small, pure and heavily tested; it is the one component that must never
  be wrong in the direction of showing an unverified citation.
