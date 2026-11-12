# ADR-0007 — Schema retrieval before analysis planning

| Status | Accepted (2026-11-12) — resolves Open Decision **D8** |
|---|---|
| Implemented in | Phase 5 |

## Context
The original requirement listed analytical planning before schema retrieval. A plan written without knowing the real columns tends to reference fields that don't exist, which wastes repair attempts and invites hallucinated analysis.

## Decision
Node order: `load_context → understand_query → retrieve_schema → plan_analysis → …`

- `understand_query` receives only a **lightweight table catalog**: table names, one-line descriptions and row counts. That's enough to tell answerable from out-of-scope or ambiguous questions.
- `retrieve_schema` collects the **detailed schema** for the relevant tables: columns, data types, profiles, descriptions, sample values for low-cardinality columns, and join paths. It uses a bounded tool loop (≤ 6 tool calls).
- `plan_analysis` **must** receive `schema_context`. Enforced in code:
  1. The graph edge `retrieve_schema → plan_analysis` is fixed. No route reaches `plan_analysis` any other way (asserted by `test_graph_structure`).
  2. `plan_analysis` raises if `schema_context` is missing or empty.
  3. Each `PlanStep` may name the tables/columns it intends to use. These are checked against `schema_context`, and an unknown reference triggers one re-ask before the plan is accepted.

## Consequences
Plans are grounded in the actual schema from the start. Retrieving the schema costs one more LLM interaction for questions that turn out to be out of scope. To avoid that, out-of-scope questions are caught by `understand_query` first.
