# Phase 6 Report — SQL safety, execution and self-correction

| Field | Value |
|---|---|
| Date | 2026-11-15 |
| Scope | Owner-defined (D51): verify the full validation pipeline, harden it, and finish the self-correction policy. Full reference: [docs/SQL_SAFETY.md](../SQL_SAFETY.md) |
| Result | 518 backend tests pass (101 on PostgreSQL), strict mypy + ruff clean. Web app untouched |

## 1. Spec → status

Most of the requested pipeline was built and tested in Phase 5; Phase 6 verified each
point against the code and closed the real gaps.

| Requirement | Status |
|---|---|
| Parse with SQLGlot; read-only only; reject DML and multi-statements; validate tables/columns; row limits; timeouts; read-only credentials; structured results | already built (Phase 5), re-verified; mapping table in SQL_SAFETY.md §2 |
| Distinguish syntax / missing table / missing column / type mismatch / invalid join / empty result / timeout | already built (deterministic classifier); `fan_out` covers invalid joins, `check_result` covers empty results |
| Keep original SQL, corrected SQL, validation results, duration, error details, retry count, final status | already built (`SQLAttempt` history per step, persisted to `query_executions`) |
| **Only retry recoverable errors; never permission errors or unsafe queries** | **new (D51):** `unsafe_query` category (writes, DDL, other schemas, server functions, stacked statements, SQLSTATE 25006) and `permission_denied` are never retried: no model call, nothing sent to the database, honest failure explanation |
| **Destructive-SQL tests proving blocks** | **extended:** corpus grew to 45 attacks + 20 benign; new Guard-bypass tests feed destructive SQL directly to the executor on real PostgreSQL — the database refuses all of it (25006/42501) and row counts stay unchanged |
| **Validation independent of the LLM** | the Guard is a pure function (no model, no I/O); fuzzing now proves it under generated inputs |
| **Document the workflow** | new [docs/SQL_SAFETY.md](../SQL_SAFETY.md); SECURITY_DESIGN §4 annotated with as-built deviations |

## 2. New protections

1. **No-retry policy for unsafe SQL** (`app/agent/tools/errors.py`): recovery is for
   honest mistakes. A `DELETE` attempt now fails its step in one attempt — proven at
   graph level (`test_unsafe_sql_is_never_retried`).
2. **Design caps enforced** (SECURITY_DESIGN §4.2/§4.6, previously design-only):
   recursive CTEs rejected (`RECURSIVE_CTE`), joins ≤ 6 (`TOO_MANY_JOINS`), subquery
   depth ≤ 4 (`TOO_DEEP`) — the last two classified `too_expensive` (one repair).
3. **EXPLAIN cost gate** (`executor.py`): plans costlier than `EXECUTOR_MAX_PLAN_COST`
   (default 5M units, 0 = off) are refused *before* execution with `COST_LIMIT`;
   recoverable, with an "aggregate earlier" hint. Fails open on unparseable plans — the
   statement timeout stays the hard stop.
4. **In-flight cancellation** (`executor.py`): the run's cancel event aborts the asyncio
   task running the query; asyncpg sends PostgreSQL a cancel request for the statement
   (the `pg_cancel_backend` mechanism). Integration test: `pg_sleep(8)` cancelled in
   < 4 s with `status="cancelled"`; the attempt and `query_executions` row record it.
5. **Property-based fuzzing** (`tests/agent/test_sql_guard_fuzz.py`, Hypothesis,
   deterministic): writes rejected under random mangling; post-`;` tails only pass when
   they parse to nothing; random table names only pass when in the catalog; arbitrary
   text never crashes the Guard; accepted ⇒ normalised SQL re-validates as one capped
   SELECT over catalog tables.
6. **Prompt fix carried over from Phase 5's real runs:** `verify_insights.v2` scopes
   uncertainty notes to *this analysis* (the judge once claimed the dataset "only
   covers September–October" when only the queries did).

The fuzzer paid for itself immediately: it found that a bare trailing semicolon
(`SELECT …; `) was accepted. Analysis showed that's correct behaviour (the tail parses
to nothing, models emit trailing semicolons constantly), so it's now an explicit corpus
case and a tightened property, not a bug fix.

## 3. Files

- **Changed:** `app/agent/tools/{errors,executor,sql_guard}.py`, `app/agent/state.py`
  (categories, `cancelled` status), `app/agent/nodes/recovery.py` (wording),
  `app/agent/runner.py` (wires cost gate + cancel event), `app/core/config.py` +
  `.env.example` + `README.md` (`EXECUTOR_MAX_PLAN_COST`), `pyproject.toml`/`uv.lock`
  (dev dep: hypothesis)
- **New:** `app/agent/prompts/verify_insights.v2.md`,
  `tests/agent/test_sql_guard_fuzz.py`, `tests/integration/test_sql_safety_pg.py`
- **Tests updated:** `tests/agent/{test_tools,test_nodes,test_sql_guard,test_graph_mock}.py`
- **Docs:** `docs/SQL_SAFETY.md` (new), SECURITY_DESIGN §4 note, AGENT_WORKFLOW §6,
  DECISION_LOG D51, DEVELOPMENT_ROADMAP v0.6 (evaluation moves to Phase 7), this report

## 4. Test results (sandbox, 2026-11-15)

| Suite | Count | Result |
|---|---|---|
| Guard corpus | 70 | pass (45 attacks rejected, 20 benign accepted, 5 behaviour tests) |
| Guard fuzzing (Hypothesis) | 6 properties × 150 examples | pass |
| Guard-bypass + cost gate + cancel (real PostgreSQL) | 4 | pass |
| Whole backend | **518** (101 on PostgreSQL) | pass; ruff + strict mypy clean |

## 5. Limitations (honest)

- Plan-cost estimates are unreliable on small datasets; the gate is a guard rail with a
  generous default, not a budget. The timeout remains the real bound.
- Fuzzing covers the Guard (pure function); the executor is covered by integration
  tests, not fuzzing.
- Cancellation is cooperative: the cancel lands between the EXPLAIN and the query, or
  mid-query; an in-flight *model* call still completes (node boundary, as in Phase 5).
- The cost gate and new caps haven't been exercised by a real model yet (the free-tier
  quota was exhausted today); nothing in the agent's prompts changed except
  `verify_insights.v2`, so Phase 5's real-run evidence stands.

## 6. Suggested commit message

```
feat(sql-safety): Phase 6 — hardening and self-correction policy

- unsafe queries and permission errors are never retried (D51)
- recursive-CTE, join (≤6) and subquery-depth (≤4) caps enforced
- EXPLAIN cost gate before execution (EXECUTOR_MAX_PLAN_COST)
- in-flight SQL cancellation via asyncpg cancel request
- Hypothesis fuzzing of the Guard; Guard-bypass isolation tests on PostgreSQL
- docs/SQL_SAFETY.md: consolidated security & recovery reference
```
