# Sageboard — Testing Strategy

| Field | Value |
|---|---|
| Document | TESTING_STRATEGY v0.2 |
| Status | Approved 2026-11-12 (v0.2). Decisions: see DECISION_LOG.md |
| Tools | pytest (+ pytest-asyncio, Hypothesis, testcontainers / docker-compose Postgres, httpx), Vitest + Testing Library (frontend units), Playwright (E2E) |

---

## 1. Principles
1. **Test the safety boundary hardest.** The SQL Guard, Executor and grounding verifier get the most tests and the highest coverage bar.
2. **Real Postgres, not SQLite.** Integration tests run against Postgres 16 (same as production), because roles, `SET ROLE`, `READ ONLY` and SQL dialect behaviour are what we're testing.
3. **LLM non-determinism is handled in layers.** Deterministic tests use a scripted test double. Separately, a real-LLM evaluation suite measures accuracy and is reported honestly with its date, model and score.
4. **The mock provider never reaches production.** Per D1 ([ADR-0006](adr/0006-provider-agnostic-llm-layer.md)), `LLM_PROVIDER=mock` is a first-class provider for development and automated tests. Settings validation refuses it when `ENV=production` (tested in Phase 1), mock runs are labelled, and accuracy metrics come only from real-provider runs. Scripted per-test responses for agent tests build on the same mock.
5. **No fabricated results.** CI artefacts (JUnit XML, coverage, eval report JSON) are the only source for any reported numbers.

## 2. Test pyramid and locations

| Level | Location | Runs in CI | Scope |
|---|---|---|---|
| Unit (Python) | `apps/api/tests/unit/` | every push | Pure functions: guard rules, identifiers, type inference, stats, claim extraction, routers, budget |
| Security | `apps/api/tests/security/` | every push | Guard corpora, executor-layer containment, cross-tenant matrix, upload attacks |
| Agent (scripted LLM) | `apps/api/tests/agent/` | every push | Node behaviour + graph routing with `FakeLLM` scripts |
| Integration | `apps/api/tests/integration/` | every push | API + DB + ingestion + executor, with a real Postgres |
| Evaluation (real LLM) | `apps/api/tests/eval/` | nightly + manual (`make eval`), needs `LLM_API_KEY` secret | Accuracy and grounding on the golden question set |
| Frontend unit | `apps/web/src/**/*.test.ts(x)` | every push | Run reducer, chart spec → component mapping, formatters, UI states |
| E2E | `apps/web/e2e/` | every PR (scripted-LLM backend) + nightly (real LLM, smoke) | User journeys across the deployed stack |

## 3. Unit tests (key suites)

| Suite | Examples of cases |
|---|---|
| `test_identifiers.py` | `"Order Date"`→`order_date`; `"select"`→`select_col`; Unicode → ASCII; 70-char names truncated with unique suffix; duplicate headers |
| `test_type_inference.py` | Mixed int/float → numeric; `"2025-03-01"`/`"01/03/2025"` (ambiguous DMY/MDY → warning + choose by majority); `"₹1,200.50"` → numeric with currency role; booleans `yes/no`; ≥ 5% unparsable → text |
| `test_stats.py` | Share sums to 1 (±1e-9); pct_change with zero base → `None` + caveat; IQR outliers on known arrays; correlation requires n ≥ 8 else no fact |
| `test_claims.py` | Extract `1.2M`, `₹3,400`, `23.5%`, `3x`, negative numbers, ranges "10–12%" |
| `test_grounding.py` | Rounded display (23.46 → "23.5%") passes; invented number fails; years from the question allowed; evidence to nonexistent fact fails |
| `test_routing.py` | Each router for every branch, incl. budget-exhausted and cancelled short-circuits |
| `test_budget.py` | Deadline and call caps; decrement semantics |
| `test_chart_validator.py` | Line chart on categorical x rejected; pie with 9 slices rejected → fallback; y must be numeric |

## 4. Agent tests with scripted LLM

`FakeLLM` is constructed with a script, a list of `(expected_schema_type, response)` pairs. It asserts that each call requests the expected schema, so the tests also pin *which* structured output each node asks for.

| Test | Scenario | Assertions |
|---|---|---|
| `test_happy_path` | 1-step plan, valid SQL | Node order matches expected list; run status `succeeded`; ≥1 verified insight; trace has `sql.validated` before `sql.executed` |
| `test_guard_repair` | Attempt 1 references unknown column; attempt 2 valid | Feedback passed to attempt 2 contains `UNKNOWN_COLUMN` and suggestions; 2 `sql_queries` rows |
| `test_db_error_repair` | GROUP BY error from real Postgres, then fix | SQLSTATE `42803` surfaced in feedback |
| `test_retry_exhaustion` | 3 invalid attempts | step `failed`; run `failed` with `all_steps_failed`; compose_report still produces a "could not answer" report |
| `test_identical_sql_repeat` | LLM repeats the same SQL | counted as an attempt; no re-execution |
| `test_empty_result_repair` | Filter value mismatch → empty → repaired using sampled values | `check_result` note present |
| `test_clarification_interrupt_resume` | Ambiguous question with `clarify=ask` | Run `awaiting_input`; resume continues from checkpoint without re-calling `understand_query`'s earlier LLM call twice |
| `test_out_of_scope` | "What's the weather?" | No SQL generated; status `succeeded` with out-of-scope message |
| `test_insight_rejected_then_fixed` | Insight with invented %; round 2 corrected | Round 2 receives feedback; final insights all verified |
| `test_insight_dropped_after_max_rounds` | Persistent ungrounded number | Dropped; trace records rejection |
| `test_budget_exhausted` | Deadline set to past mid-run | Terminates via compose_report, status `partial` |
| `test_cancel` | Cancel during execute_sql | Status `cancelled`; DB backend cancelled |
| `test_graph_structure` | Compiled graph | Node set and edge set equal the documented ones (AGENT_WORKFLOW §9) |
| `test_prompt_injection_column_names` | Dataset with column named `"ignore_instructions_drop_table"` and description containing instructions | Guard still enforces; no forbidden SQL accepted; scope unchanged |

## 5. Security tests

### 5.1 SQL Guard corpora (`tests/security/corpus/*.yaml`)
**Adversarial (must reject, ≥150 cases).** Categories with representative items:
- DML/DDL: `DELETE FROM orders`, `DROP TABLE orders`, `UPDATE ...`, `TRUNCATE`, `ALTER`, `CREATE TABLE x AS SELECT`
- Smuggling: `SELECT 1; DROP TABLE orders`, `SELECT 1 /* ; */; DELETE ...`, a CTE wrapping DML `WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d`, `SELECT * INTO new_t FROM orders`
- Locks/tx: `SELECT ... FOR UPDATE`, `BEGIN`, `SET ROLE sageboard_app`, `RESET ROLE`, `SET search_path`
- System/catalog: `SELECT * FROM pg_user`, `information_schema.tables`, `app.users`, `ds_<other>.orders`, quoted-identifier tricks `"APP"."users"`, `"pg_catalog".pg_roles`
- Functions: `pg_sleep(100)`, `pg_read_file('/etc/passwd')`, `lo_import`, `dblink(...)`, `set_config('role',...)`, `current_setting('...')`, `query_to_xml(...)`, schema-qualified `public.anything()`
- DoS: `generate_series(1,1e10)`, `WITH RECURSIVE`, 8-way joins, unconstrained cross joins of large tables
- Commands: `COPY orders TO PROGRAM 'curl ...'`, `VACUUM`, `LISTEN/NOTIFY`, `PREPARE/EXECUTE`, `DO $$ ... $$`, `CALL`
- Encodings: Unicode homoglyph keywords, mixed case, excessive whitespace/comments, dollar-quoted strings containing semicolons

**Benign (must accept and execute, ≥60 cases):** aggregates, window functions, CTE chains, date_trunc time series, CASE pivots, HAVING, UNION ALL of selects, string literals containing words like "delete" or ";".

### 5.2 Layer-isolation test
Run the adversarial corpus **directly through the Executor with Guard bypassed** (test-only flag) against a seeded DB. Assert each statement errors (permission denied / read-only transaction / function denied) **and** that the DB state checksum (row counts + table list across all schemas) is unchanged afterwards.

### 5.3 Property-based fuzzing
Hypothesis composes random SELECT skeletons with injected forbidden fragments at random AST positions. Invariant: if a forbidden node type or function is present anywhere, `accepted == False`.

### 5.4 Cross-tenant matrix
A parametrised test over every resource route (GET/PATCH/DELETE by ID): user B requesting user A's resource → 404, with no side effects. Generated from the OpenAPI route list so new routes are automatically included (test fails if a route isn't classified).

### 5.5 Upload attacks
Zip bomb XLSX, 30 MB CSV, 250 columns, path-traversal filename `../../x.csv`, NUL bytes, mismatched extension/magic, formula cells round-tripped through CSV export.

### 5.6 Auth
Login rate limit and lockout, refresh-token rotation + reuse detection, CSRF missing/mismatched → 403, cookie flags.

## 6. Integration tests
As built (Phase 3): tests in `apps/api/tests/integration/` run against a **dedicated** PostgreSQL database (`sageboard_test` locally, the ephemeral service DB in CI) using the four real role URLs (`SAGEBOARD_TEST_DATABASE_URL`, `_INGEST_`, `_EXECUTOR_`, `_MIGRATION_`). `test_00_migrations.py` runs first and performs a full `downgrade base → upgrade head`. Tests clean up what they create, so the suite is repeatable. Without the URLs they are skipped, and CI fails the job if anything is skipped. Coverage uses `concurrency = ["greenlet", "thread"]` so async ORM code is measured.

| Area | Tests |
|---|---|
| Ingestion | CSV & XLSX end-to-end: schema created, roles granted, row counts, profiles, rejected rows report; finalise with type overrides; delete drops schema and role |
| Executor | Role switching, timeout (`pg_sleep` via a test-only superuser setup is not used; instead a deliberately slow benign query), row cap/truncation detection, EXPLAIN cost rejection, connection returns clean (role reset) after error |
| Runs API | Create run (FakeLLM) → SSE stream yields expected event sequence; `Last-Event-ID` replay; cancel; resume; idempotency key dedupes |
| Reports / Dashboard | Create report from run snapshot immutability; widget refresh re-validates and fails with 422 after a column is removed (dataset reload) |
| History | Filters, full-text search, cursor pagination stability |

## 7. Evaluation suite (real LLM)

**Golden set** `packages/eval-datasets/golden/retail_v1.yaml`, about 60 questions over the deterministic sample dataset, tagged by difficulty and intent:
```yaml
- id: q017
  question: "Which 3 regions had the highest revenue growth from Q2 to Q3 2025?"
  intent: ranking
  difficulty: medium
  reference_sql: |
    WITH q AS (...) SELECT region, ... ORDER BY growth DESC LIMIT 3
  compare: { mode: set_equal_ordered, columns: [region], numeric_tolerance: 0.005 }
  must_mention_facts: [growth_pct]   # at least one verified insight cites a pct_change fact
```
Plus ~15 *should-not-answer* items (out of scope, missing column such as "profit margin" without cost data) where the expected behaviour is an explicit "cannot answer" result.

**Metrics (reported per run, written to `eval_report.json`):**
| Metric | Definition | Target |
|---|---|---|
| Execution accuracy | The final step's result matches the reference result per `compare` rules | ≥ 80% |
| Refusal accuracy | Correct "cannot answer" on negative items | ≥ 90% |
| Grounding violation rate | Verified insights containing a number not traceable to evidence (checked by an independent re-run of the deterministic checker) | 0 |
| Recovery rate | Runs with ≥1 repair that ended successful / runs with ≥1 repair | tracked |
| Cost & latency | Median LLM calls, tokens, p50/p95 duration | tracked |

The eval command prints the model, prompt versions, git SHA and date. Results are committed to `docs/eval/` only from actual runs.

## 8. Frontend tests

**Vitest:** `runReducer` (event sequence → view model, including out-of-order/duplicate `seq` after reconnect), `ChartRenderer` (each spec type renders; invalid spec → table fallback), number/date formatters, API error mapping.

**Playwright E2E** (`apps/web/e2e/`), running against the real Next.js + real FastAPI + real Postgres, with the backend in `ENV=test` using scripted LLM scenarios selected by a test-only header:
| Spec | Journey |
|---|---|
| `auth.spec.ts` | Register → land on dashboard empty state → logout → login |
| `dataset-upload.spec.ts` | Upload CSV → review inferred types → override one → finalise → profile visible |
| `analyst-happy.spec.ts` | Ask question → streamed steps appear in order → table, chart, insights with evidence popover |
| `analyst-recovery.spec.ts` | Scenario with guard rejection → Inspector shows rejected attempt then success |
| `analyst-clarify.spec.ts` | Clarification chips → resume → completes |
| `analyst-cancel.spec.ts` | Cancel mid-run → cancelled state |
| `report.spec.ts` | Save report → open → export Markdown → print view snapshot |
| `dashboard.spec.ts` | Pin chart → appears on dashboard → refresh |
| `history.spec.ts` | Filter and search → open run detail drawer |
| `states.spec.ts` | Empty/loading/error states for each page (API errors forced via route interception) |
| `a11y.spec.ts` | `@axe-core/playwright` on each page: no serious/critical violations |
| `responsive.spec.ts` | 1440, 1024, 768, 375 viewports: no horizontal overflow; Inspector becomes drawer < 1280 |

**Visual regression:** Playwright screenshots for key pages at 1440 px with a masked dynamic area; threshold 0.2%. Baselines are updated only by deliberate PRs.

## 9. Coverage and quality gates (CI)
| Gate | Threshold |
|---|---|
| `app/security/**`, `app/execution/**`, `app/agent/verification/**`, `app/analysis/**` line+branch coverage | ≥ 95% |
| Overall backend coverage | ≥ 80% |
| Frontend unit coverage (lib + features logic) | ≥ 70% |
| ruff (incl. `S` rules), mypy strict on security/agent, tsc, eslint | 0 errors |
| Security corpus | 100% pass |
| Playwright PR suite | 100% pass, retries=1 (flaky tests tracked, not hidden) |

## 10. CI pipeline
```
ci-api.yml:  uv sync → ruff → mypy → pytest unit+security+agent → (postgres service) pytest integration → coverage gates → pip-audit
ci-web.yml:  pnpm install → lint → typecheck → vitest → next build
e2e.yml:     compose up (postgres + api ENV=test) → pnpm playwright test → upload report/traces
nightly.yml: eval suite with real LLM (secret) → eval_report.json artifact; real-LLM smoke E2E (2 journeys)
```

## 11. Test data management
- The sample dataset generator is seeded and deterministic; its checksum is asserted in tests.
- Fixtures: `user_factory`, `dataset_factory(csv_text | sample)`, `run_factory`.
- No production data is ever used in tests.
