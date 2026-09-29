# ADR 0001: The default model runs locally, behind a provider interface

## Context

The budget for model calls is $0. Qwen3 8B through Ollama already produced schema-valid
structured output across 250 calls in the A1-lite experiment. Contracts are confidential, and
a reviewer will not send drafts to an unknown service to try a prototype.

## Decision

Analysis calls go through one `ModelProvider` interface (`generate(messages, schema)`,
`embed(texts)`). `OllamaProvider` with `qwen3:8b` is the default; embeddings use
`nomic-embed-text` locally. Anthropic, OpenAI and Gemini providers implement the same
interface and are selected by configuration, never by code paths.

## Consequences

- The demo works offline and costs nothing to run.
- Prompt versions, model tags and parameters are recorded on every run, so switching
  providers is visible in the run history rather than silent.
- Quality is bounded by an 8B model; the interface exists so that a stronger model can be
  measured against it on the same fixtures.
