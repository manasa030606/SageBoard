# Phase 5 Report — Agentic AI core (LangGraph)

| Field | Value |
|---|---|
| Date | 2026-11-14 |
| Scope | Owner-defined (D43): the full agent workflow, the former roadmap Phases 5–7 |
| Result | Built and tested: 476 backend tests pass (97 against PostgreSQL), 94% coverage; strict mypy, ruff and format clean; web 66 tests and build pass |
| Not yet done | No real LLM has been called (no API key in the build sandbox). See §6 |

## 1. What was built

A stateful, multi-step LangGraph `StateGraph` with **15 nodes**: the 12 requested responsibilities plus 3 control nodes (`load_context`, `check_result`, `finish_step`). It has 3 fixed and 34 conditional edges. Full design, state and transition tables: `docs/AGENT_WORKFLOW.md` v0.3.

| Requirement | How it is met |
|---|---|
| Typed shared state | `AgentState` TypedDict whose nested values are all Pydantic models; `trace`/`errors` use an append reducer |
| Separate nodes, explicit edges, conditional routing | `graph.py` `NODES` / `CONDITIONAL_EDGES`; pure routers in `routing.py`; a structure test pins every node and edge |
| Bounded retries | 3 SQL attempts per step, 2 verification rounds, 6 schema tool calls, 1 structured-output re-ask, 2 transport retries, run budgets (30 model calls, 14 queries, 180 s) |
| Preserve intermediate results | every SQL attempt (SQL, Guard verdict, SQLSTATE, diagnosis) kept per step; every node event kept in `trace`; full rows in the run's result store |
| Node status and duration | `traced_node` wrapper → `NodeEvent` (status, duration, summary, tool calls, model calls, error), persisted live to `agent_node_runs` |
| Errors don't crash the workflow | fallbacks degrade (charts → tables, analysis → deterministic facts…); critical failures end with an explained response; the runner catches crashes |
| Conversation context | last 3 turns passed to understanding and planning; a clarification answer resumes the original question |
| Observable, debuggable | `GET /analysis-sessions/{id}/trace`, `result` on the session, `query_executions` rows, `scripts/ask.py`, versioned prompts recorded per call |
| Planning | question → 1–6 SQL steps (purpose, expected output, dependencies) + analysis tasks |
| SQL generation | real schema context (types, descriptions, samples, ranges, joins), structured output, earlier steps' SQL, dependency previews |
| Error recovery | capture → classify in code (Guard code/SQLSTATE) → error-specific schema context → regenerate → revalidate → retry ≤ 3 → explanation |
| Verification | numbers vs cited evidence (code, authoritative); metrics and time-period checks; reject-only model judge; unsupported insights removed; uncertainty notes |
| No generic-LLM shortcut | validation and execution nodes contain no model calls (tested); analysis numbers come from code |

Safety: the SQL Guard (SQLGlot) accepts only one read-only SELECT over the dataset's own tables, with real columns, safe functions and a capped LIMIT. It then runs through the Phase 3 read-only executor (reader role, READ ONLY transaction, timeout). All dataset text is wrapped in `<data>` boundaries.

## 2. Files

**New — `apps/api/app/agent/`:**
- `state.py`, `graph.py`, `routing.py`, `runtime.py`, `runner.py`
- `llm/{client,providers,factory}.py`
- `nodes/{common,understanding,schema,planning,sql,recovery,analysis,visualization,insights,verification,response}.py`
- `tools/{sql_guard,executor,schema,errors,analysis,charts,grounding}.py`
- `prompts/` (10 versioned prompts plus a shared data-boundary suffix)

**New — migration, script and tests:**
- `migrations/versions/20261114_0005_agent_runs.py`
- `scripts/ask.py`
- `tests/agent/{fakes,scenarios,test_sql_guard,test_tools,test_llm,test_nodes,test_routing_and_structure,test_graph_mock}.py`
- `tests/integration/test_agent_pg.py`

**Changed:**
- `app/core/config.py` (LLM and agent settings)
- `app/main.py` (RunManager, interrupted-run cleanup)
- `app/api/deps.py` (run manager, analysis rate limit)
- `app/api/v1/conversations.py` (starts the agent, cancel, trace)
- `app/schemas/analysis.py`, `app/services/analysis.py`
- `app/db/models/{__init__,analysis}.py`
- `app/execution/readonly.py` (returns column types)
- `scripts/schema_reference.py`, `pyproject.toml` + `uv.lock` (langgraph, sqlglot, httpx)
- `.env.example`, `README.md`
- tests updated for migration 0005: `test_00_migrations`, `test_db_permissions`, `test_workspace_api`, `test_api_contract`
- web copy only: `run-view.tsx`, `analyst-workspace.tsx`, `reports-list.tsx`

**Docs:**
- `AGENT_WORKFLOW` v0.3
- `API_SPECIFICATION` v0.5
- `DATABASE_DESIGN` v0.5
- `DECISION_LOG` D42–D49
- `DEVELOPMENT_ROADMAP` v0.5
- ADR-0006 amendment 2
- this report

## 3. Tests (sandbox run, 2026-11-14)

| Suite | Count | Result |
|---|---|---|
| `tests/agent/test_sql_guard.py` | 64 | pass |
| `tests/agent/test_tools.py` | 44 | pass |
| `tests/agent/test_llm.py` | 17 | pass |
| `tests/agent/test_nodes.py` | 35 | pass |
| `tests/agent/test_routing_and_structure.py` | 16 | pass |
| `tests/agent/test_graph_mock.py` | 11 | pass |
| `tests/integration/test_agent_pg.py` (real PostgreSQL) | 6 | pass |
| Whole backend | 476 (97 on PostgreSQL) | pass, 94% coverage |
| Web (`pnpm test`, lint, format, build) | 66 | pass |

Key behaviour proven by these tests:
- **Agent code against real PostgreSQL.** A query that passes the Guard but fails in PostgreSQL (`SUM(text)`, SQLSTATE 42883) is classified and repaired, and the computed per-category numbers equal an independent SQL query.
- **No destructive SQL reaches the database.** `DROP TABLE orders; SELECT 1` never reaches it, and the table is intact afterwards.
- **The API runs the agent end to end.** It exposes the result, a live trace and history rows; another user gets 404.

How the model is simulated: a scripted provider (tests only) replaces the model. Everything else is real.

## 4. Problems found and fixed during the phase

1. **Outliers missed.** The outlier tool used `statistics.quantiles`' default "exclusive" method, which on small samples missed an obvious outlier. Switched to the inclusive method.
2. **Wrong trend endpoints.** Trend sorted numeric x values as text ("10" before "2"). It now sorts numbers numerically.
3. **Unreadable tool errors.** Tool-error observations reached the model with escaped Unicode (`“`). They now stay readable.
4. **`version()` slipped past the Guard.** SQLGlot types it as `CURRENT_VERSION`, which escaped the denylist. The denylist now covers typed server-info functions (`current_user`, `uuid`…).
5. **Good result discarded.** When later corrections failed, a step discarded an earlier usable (flagged) result. It now keeps it, with a note.
6. **Mixed sync/async tool calls.** mypy (strict) found the tool recorder mixing sync and async callables. It is now split into `tool` / `atool`.
7. **Mistakes in my own test data.** An unrealistic routing fixture and two malformed SQL strings. In both SQL cases the Guard correctly rejected the bad SQL.

## 5. Endpoints changed or added

- `POST /api/v1/conversations/{id}/sessions` now starts the agent when a model is configured (`agent_available: true`); limited to 30 questions per hour per user.
- `GET /api/v1/analysis-sessions/{id}` now includes `result`, `llm_provider` and `llm_model`.
- `POST /api/v1/analysis-sessions/{id}/cancel` also stops a running agent at its next node.
- **New:** `GET /api/v1/analysis-sessions/{id}/trace`.

## 6. Limitations (honest)

- **No real model has run yet.**
  - The sandbox has no API key. The Anthropic, OpenAI and Gemini adapters are tested against a mock HTTP transport that uses each API's documented request and response shapes, not against the live services.
  - The prompts are untuned. Real accuracy is unknown until Phase 6.
- **The web workspace isn't wired to the agent yet.** It still shows labelled sample runs. Use the API or `scripts/ask.py`.
- **Progress is by polling.** There is no SSE stream yet (Phase 8).
- **Cancellation takes effect at node boundaries.** An in-flight SQL query runs to its 10 s timeout, and an in-flight model call completes.
- **Results are partially persisted.** Full results stay in memory for the run; only 50-row previews and 200-row chart data are saved. No rerun or paging yet.
- **No EXPLAIN cost gate.** Cost is controlled by the statement timeout, the row cap and one "aggregate" repair (Phase 7).
- **The time-period check is shallow.** It confirms a date column is used, not that the bounds are right. The model judge checks the meaning.
- **Restarts and rate limits are per process.** A restart fails in-flight runs, and rate limits are per process (single instance, ADR-0004).

## 7. Commit message

```
feat(agent): Phase 5 — LangGraph agentic analysis core

- 15-node StateGraph: understanding, schema retrieval (tool loop), planning,
  SQL generation, SQL Guard validation, read-only execution, result checks,
  error recovery, analysis engine, visualization, insights, verification,
  final response; typed state, conditional routing, bounded retries
- SQL Guard (SQLGlot) with adversarial/benign corpora
- provider-agnostic LLM layer (Anthropic/OpenAI/Gemini over HTTP; mock = no model)
- run manager, live node trace (migration 0005), trace endpoint, scripts/ask.py
- 187 agent tests with scripted model + fake tools; 6 on real PostgreSQL
```

## 8. Addendum (2026-11-14): free Google Gemini configuration (D50)

**Configuration.** `LLM_PROVIDER=google`, `LLM_MODEL=gemini-3.8-flash`, `GOOGLE_API_KEY` in `apps/api/.env`.

**What it adds:**
- Classification of Google's 429s (per-minute wait-and-retry; daily quota, `limit: 0` and bad key stop the run with the reason).
- Fatal model errors end the run as `llm_unavailable`, keeping any verified findings.
- A client-side request pacer and a daily model-call cap (`429 DAILY_BUDGET_EXCEEDED`).
- A Google schema-compatibility fallback.
- `scripts/check_llm.py`, and docs in `apps/api/README.md` and `.env.example`.

**Tests:** 493 backend tests pass (17 new). The new tests cover Google error bodies, pacing, aliases, a mid-run quota stop, the daily cap on PostgreSQL and the schema fallback.

**Still unverified:** no live Gemini request has been made from the build sandbox (no key), so the request and error shapes are tested against Google's documented formats only.
