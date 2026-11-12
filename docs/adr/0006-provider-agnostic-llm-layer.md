# ADR-0006 — Provider-agnostic LLM layer with a mock provider

| Status | Accepted (2026-11-12) — resolves Open Decision **D1** |
|---|---|
| Implemented in | Phase 1 (configuration and validation only) · Phase 5 (adapter, providers, mock) |

## Context
The team hasn't confirmed which LLM API credits are available. The agent workflow must not depend on any one vendor, and the early phases must not be blocked by this.

## Decision
1. **One interface, many providers.** The agent nodes depend only on an `LLMClient` protocol in `app/agent/llm/client.py`:
   - `structured(messages, schema: type[BaseModel], *, purpose) -> BaseModel`
   - `with_tools(messages, tools, *, max_calls) -> ToolLoopResult`

   Provider modules (`anthropic.py`, `openai.py`, `gemini.py`, `mock.py`) implement it. The LangGraph graph, nodes and prompts never import a provider SDK.
2. **Configured by environment only.** `LLM_PROVIDER` (`mock | anthropic | openai | gemini`), `LLM_MODEL`, and one API key per provider. Settings validation (already implemented in Phase 1) refuses:
   - a real provider without its key or a model name
   - `LLM_PROVIDER=mock` when `ENV=production`

   No key or model name appears in code.
3. **Mock provider for development and automated tests.** It returns deterministic, schema-valid outputs from scripted fixtures (keyed by node purpose) so the graph, SQL Guard, executor and UI can be built and tested without credentials. Rules that keep it honest (project instruction #8):
   - Only the *model's* outputs are simulated. SQL validation, execution against the real database, statistics and verification all run for real.
   - Every run produced with the mock is labelled (`llm_calls.provider = "mock"`, a visible "Mock model" badge in the Run Inspector). It must never be presented as real model output in a demo or evaluation.
   - Accuracy metrics (the eval suite) are only reported from real-provider runs.
4. **Provider evaluation gate (start of Phase 5).** Before integrating a real provider, we record in `docs/LLM_PROVIDER_EVALUATION.md`: available API access and credits, pricing per 1M input/output tokens, tool-calling support, native structured output (JSON Schema) support and its limits, rate limits, context window, and data-retention terms. Default model selection is decided from that table and approved by you.
5. **Per-purpose model selection (optional).** `LLM_MODEL` is the default. Optional overrides (`LLM_MODEL_SQL`, `LLM_MODEL_JUDGE`) let a cheaper model handle classification or verification. These are added in Phase 5 only if the evaluation supports it.

## Consequences
- Switching providers is a configuration change plus that provider's own conformance tests. There are no workflow changes.
- Each provider's structured-output differences (JSON Schema subset, tool-call formats) are absorbed by its adapter. A shared conformance test suite runs against every adapter.
- The mock adds a module we have to maintain. It's kept deliberately small and covered by the "never in production" validator test (`tests/test_config.py::test_mock_llm_is_refused_in_production`).

## Amends
- TESTING_STRATEGY §1 previously placed the fake LLM only under `tests/`. Per your decision, the mock becomes a first-class provider usable in **development** too. It stays forbidden in production by settings validation.
