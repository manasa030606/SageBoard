# ADR-0005 — Structured outputs only; no execution of generated code

| Status | Accepted (2026-11-12) |
|---|---|
| Implemented in | Phases 4–6 (enforced by lint rules from Phase 1) |

## Decision
- Every LLM call returns JSON validated against a Pydantic schema. Free text is never parsed for control flow.
- LLM output is never executed as code. SQL goes through the SQL Guard and the restricted executor (ADR-0002). Analysis uses a fixed set of typed Python functions the model can only *select*. Charts are declarative `ChartSpec` objects rendered by the frontend.
- From Phase 1, ruff's `S` (bandit) rules run in CI. They flag `eval`/`exec`, `subprocess` with a shell, unsafe deserialisation, hardcoded secrets and similar.

## Consequences
Model mistakes show up as validation failures that can be retried, never as arbitrary execution. Analyses are limited to the toolset we implement. That's a deliberate trade-off.
