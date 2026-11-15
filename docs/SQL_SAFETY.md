# Sageboard — SQL Safety & Self-Correction (as built)

| Field | Value |
|---|---|
| Document | SQL_SAFETY v1.0 (Phase 6, 2026-11-15) |
| Scope | The complete path from model-generated SQL to structured results: validation, execution, error recovery. Supersedes SECURITY_DESIGN §4 as the as-built reference; the design rationale stays there |
| Code | `app/agent/tools/sql_guard.py` (validation) · `app/agent/tools/executor.py` + `app/execution/readonly.py` (execution) · `app/agent/tools/errors.py` + `app/agent/nodes/recovery.py` + `app/agent/routing.py` (self-correction) |
| Tests | `tests/agent/test_sql_guard.py` (corpus) · `tests/agent/test_sql_guard_fuzz.py` (property-based) · `tests/integration/test_sql_safety_pg.py` (Guard bypassed, real PostgreSQL) · `tests/integration/test_agent_pg.py` (end to end) |

## 1. Principle: never trust the model's SQL

The validation layer is **independent of the LLM**: the Guard is a pure function over the
SQL text and the dataset catalog — no model, no network, no database. Even a fully
compromised model output faces three layers, each sufficient on its own:

| Layer | Mechanism | Proven by |
|---|---|---|
| 1. SQL Guard | SQLGlot parse + rules below; only the *normalised* output can execute | corpus + fuzzing |
| 2. Database role | per-dataset reader role (`SELECT` only, own schema only), `NOINHERIT` executor, `SET LOCAL ROLE` inside a `READ ONLY` transaction | `test_sql_safety_pg.py` feeds destructive SQL **directly to the executor, skipping the Guard**: PostgreSQL refuses every one (SQLSTATE 25006/42501) and row counts are unchanged |
| 3. Session limits | `statement_timeout`, row cap (`LIMIT` ≤ cap injected by the Guard), EXPLAIN cost gate, connection pinned to the dataset's `search_path` | integration tests (timeout, cost gate, cancel) |

Credentials: the agent only ever holds the executor pool (`EXECUTOR_DATABASE_URL`,
read-only by role design, ADR-0002). The app/ingest/owner credentials never reach agent
code, and nothing database-related reaches the frontend.

## 2. The validation pipeline (requirement → implementation)

| # | Step | Where | Notes |
|---|---|---|---|
| 1 | Receive generated SQL | `generate_sql` / `recover_error` nodes | stored verbatim as `SQLAttempt.sql` |
| 2 | Parse with SQLGlot | `_parse_single_select` | PostgreSQL dialect; ≤ 20,000 chars; parse failure → `SYNTAX_ERROR` |
| 3 | Permitted read-only query | root must be `SELECT` / set operation; CTEs allowed | `NOT_A_SELECT` otherwise |
| 4 | Reject data modification | walk of **every** node (CTEs and subqueries included): INSERT/UPDATE/DELETE/MERGE/DDL/COPY/SET/GRANT/transactions → `FORBIDDEN_STATEMENT`; `SELECT … INTO`; `FOR UPDATE/SHARE` | plus `RECURSIVE_CTE`, ≤ 6 joins (`TOO_MANY_JOINS`), subquery depth ≤ 4 (`TOO_DEEP`) |
| 5 | Reject multiple statements | exactly one statement; a bare trailing `;` (or trailing comment) is tolerated because models emit it on benign SQL — fuzzing proves a tail only passes when it parses to *nothing* | `MULTIPLE_STATEMENTS` |
| 6 | Validate table & column access | tables must exist in this dataset's catalog (no other schema, no db qualifier, no table functions); every column resolved against the real catalog via SQLGlot's qualifier, with "did you mean / lives in table X" feedback | `UNKNOWN_TABLE`, `FORBIDDEN_SCHEMA`, `UNKNOWN_COLUMN`, `AMBIGUOUS_COLUMN` |
|   | Function policy | typed SQLGlot functions pass; untyped ones must be on a small allowlist; a denylist regex blocks server/system functions (`pg_*`, `lo_*`, `dblink`, `set_config`, `current_setting`, `version`, `generate_series`, …) even if typed | `FORBIDDEN_FUNCTION` |
| 7 | Enforce row limits | outer `LIMIT` must be a literal ≤ cap+1; injected when missing (cap+1 lets the executor detect truncation) | `NON_LITERAL_LIMIT` for `LIMIT ALL`/subqueries |
| 8 | Enforce timeouts | `SET LOCAL statement_timeout` per transaction (default 10 s) → SQLSTATE 57014 | plus the EXPLAIN cost gate (§4) |
| 9 | Read-only credentials | executor role `NOINHERIT`, `default_transaction_read_only=on`; per query: `BEGIN … READ ONLY; SET LOCAL ROLE ds_<hex>_r; SET LOCAL search_path` | ADR-0002, SECURITY_DESIGN §5 |
| 10 | Structured results | `ExecutionOutcome{status, columns(name,type), rows, truncated, exec_ms, error_code, error_message, plan_cost}`; DB errors are sanitised (message+hint only — `detail` can leak row values) | `executor.py` |

Only the Guard's **normalised** SQL (comments stripped, schema qualifier removed, LIMIT
applied, re-rendered from the AST) is ever executed — never the model's raw text.

## 3. Self-correction (bounded, classified, never for unsafe SQL)

Failures are classified **in code** — Guard violation code or SQLSTATE → category — so
retry behaviour is deterministic, not a model choice:

| Category | Trigger | Retried? | Hint given to the recovery agent |
|---|---|---|---|
| `syntax_error` | 42601, parse failure, non-literal LIMIT | yes | fix syntax, keep it simple |
| `unknown_table` | 42P01, Guard | yes | only catalog tables |
| `unknown_column` | 42703, Guard | yes | which table holds the column |
| `ambiguous_column` | 42702, Guard | yes | qualify with aliases |
| `grouping_error` | 42803 | yes | non-aggregated columns into GROUP BY |
| `type_mismatch` | 42804, 22P02/22007/22008/22003 | yes | explicit casts, date literals |
| `undefined_function` | 42883 | yes | standard functions, cast arguments |
| `division_by_zero` | 22012 | yes | `NULLIF(denominator, 0)` |
| `timeout` | 57014 | yes | aggregate before joining, filter earlier |
| `too_expensive` | cost gate (`COST_LIMIT`), `TOO_MANY_JOINS`, `TOO_DEEP` | yes | cheaper plan |
| `empty_result` / `fan_out` | result checks (`check_result`) | once per problem | check sampled filter values / join keys |
| `repeated_query` | normalised SQL identical to an earlier attempt | counts as a wasted attempt | write a materially different query |
| **`unsafe_query`** | Guard: `NOT_A_SELECT`, `FORBIDDEN_STATEMENT`, `MULTIPLE_STATEMENTS`, `SELECT_INTO`, `LOCKING_CLAUSE`, `FORBIDDEN_SCHEMA`, `FORBIDDEN_FUNCTION`; DB: 25006 | **never** | — |
| **`permission_denied`** | 42501 | **never** | — |

Policy (Phase 6): recovery exists for honest mistakes. A query that tried to write,
touch another schema or call server functions fails its step immediately — no model
call is spent on it, nothing reaches the database, and the step's failure explanation
says correction was not attempted. SQLSTATE 25006 (the database's own read-only defence
fired) means something passed the Guard that shouldn't have: never retried, worth
investigating as a bug.

Bounds enforced in `routing.py`, not by the model: **3 attempts per step**, ≤ 14
executions per run, one repair per result problem, global deadline — then
`finish_step` closes the step with an explanation and dependent steps are skipped.

Everything is kept per attempt in `SQLAttempt` (persisted to `app.query_executions`,
shown in History): original SQL, the Guard's verdict + violations, normalised SQL,
execution status, SQLSTATE, sanitised error, duration, `origin="recovery"` for
corrected attempts, the deterministic diagnosis, and the step's final status.

## 4. EXPLAIN cost gate (Phase 6)

Before executing, the executor runs `EXPLAIN (FORMAT JSON)` under the same read-only
role and timeout, and refuses plans whose estimated total cost exceeds
`EXECUTOR_MAX_PLAN_COST` (default 5,000,000 cost units; 0 disables). The refusal is
`error_code="COST_LIMIT"` → category `too_expensive` → one recovery attempt with the
hint to aggregate earlier. Cost estimates are rough, so the ceiling is generous and the
statement timeout remains the hard stop; an unparseable plan fails open for the same
reason.

## 5. Cancelling in-flight SQL (Phase 6)

Cancelling an analysis (`POST /analysis-sessions/{id}/cancel`) sets the run's cancel
event. Between nodes, routers stop the run; **during** a query, the executor's wait on
that event cancels the asyncio task running the statement, which makes asyncpg send
PostgreSQL a cancel request for the in-flight query (the `pg_cancel_backend` mechanism,
scoped to our own backend). The integration test cancels `pg_sleep(8)` and completes in
under 4 s with `status="cancelled"`.

## 6. Adversarial testing

- **Corpus** (`test_sql_guard.py`): 45 attacks (DML/DDL, stacked statements, CTE-hidden
  DML, system schemas, other datasets, server functions, system columns, recursive
  CTEs, join/depth bombs, non-literal limits) must be rejected with the expected code;
  20 realistic analytics queries must pass.
- **Property-based fuzzing** (`test_sql_guard_fuzz.py`, Hypothesis, deterministic):
  writes stay rejected under random casing/whitespace/comment mangling; a tail after
  `;` passes only if it parses to nothing; random table names only pass if they're in
  the catalog; arbitrary text never crashes the Guard; and *accepted ⇒ safe*: the
  normalised SQL re-validates, is a single SELECT over catalog tables, and carries a
  capped literal LIMIT.
- **Guard bypass** (`test_sql_safety_pg.py`): destructive statements sent straight to
  the executor are refused by PostgreSQL itself, classified non-retryable, and leave
  row counts untouched; `app.users` and `pg_shadow` stay unreachable.
- **End to end** (`test_agent_pg.py`): a Guard-passing query that fails in PostgreSQL
  is classified and repaired within bounds; `DROP TABLE` never reaches the database.

## 7. Known limits

- Cost estimates come from the planner's statistics; tiny datasets underestimate badly,
  so the gate is a guard rail, not a budget.
- The Guard's function policy is hybrid (typed pass + untyped allowlist + denylist),
  not the pure allowlist of SECURITY_DESIGN §4.5; the denylist covers the known server
  surface, and fuzzing plus the database role back it up.
- Rate limiting of attempts is per run; a hostile *user* is limited by the API's
  per-user caps (API_SPECIFICATION §11), not by this layer.
