# Sageboard — Evaluation summary

Generated 2026-11-15 15:51 UTC by `uv run python -m evals report`. Every figure below is computed from the result files listed at the end; nothing is typed in by hand.

## Agent pipeline — oracle-small

> **Oracle mode.** The language model is replaced by a script that replays each case's reference SQL. Guard, executor, analysis engine, verification, grounding, API and persistence are real. These numbers measure the *pipeline*. They say nothing about how well any language model writes SQL.

Scale `small` · cases run **62** of 62 · not run: 0 · overall correct outcome **98.4% (61/62)**

| # | Metric | Result | Definition (denominator) |
|---|---|---|---|
| 1 | SQL execution accuracy | 98.0% (48/49) | answerable cases whose result matches the independently computed truth |
| 1b | SQL execution success | 100.0% (49/49) | answerable cases where at least one step ran without error |
| 2 | Numerical result accuracy | 99.4% (157/158) | expected numeric cells found in the agent's result (integers exact, others 0.01 % / 0.01) |
| 3 | Schema grounding (first attempt) | 98.1% (53/54) | generated steps whose first SQL used only real tables and columns |
| 3b | Cases with every step schema-valid first try | 98.0% (48/49) | answerable cases |
| 4 | Task completion (answerable) | 100.0% (49/49) | answerable cases ending with an answer and ≥ 1 successful query |
| 4b | Correct refusal (invalid schema) | 100.0% (5/5) | questions about data that does not exist |
| 4c | Fabricated answers on invalid schema | 0.0% (0/5) | same cases (lower is better) |
| 5 | Error recovery success | 100.0% (5/5) | steps that needed more than one attempt and ended successful |
| 5b | First failure classified as expected | 100.0% (5/5) | error-recovery cases |
| 6 | Insight faithfulness | 100.0% (49/49) | saved reports whose every number re-verifies against stored results |
| 6b | Tampered summary detected | 100.0% (49/49) | reports edited to include an invented number |
| 7 | Query execution latency (ms) | p50 2 · p95 6 · mean 3 · max 7 (n=56) | successful SQL executions (database time) |
| 8 | End-to-end response latency (ms) | p50 284 · p95 316 · mean 294 · max 648 (n=62) | question submitted → run finished, all cases |
| 9 | SQL safety (pipeline security cases) | 100.0% (8/8) | security cases: nothing unsafe executed, database unchanged, no sensitive values sent to the model |
| 9b | Sensitive values sent to the model | 0.0% (0/1) | security cases that ask for personal data (lower is better) |
| 9c | Sensitive values in the stored result shown to the owner | 100.0% (1/1) | same cases; a product decision, see FAILURE_ANALYSIS.md |
| – | Follow-up: earlier turn passed to the agent | 100.0% (4/4) | follow-up cases (oracle only) |
| – | Model calls per case / tokens | 8.0 / 0 | all cases |

**By category**

| Category | Correct outcome |
|---|---|
| simple | 100.0% (6/6) |
| aggregation | 100.0% (7/7) |
| filtering | 100.0% (6/6) |
| join | 100.0% (7/7) |
| time | 100.0% (8/8) |
| multi_step | 100.0% (5/5) |
| follow_up | 100.0% (4/4) |
| invalid_schema | 100.0% (5/5) |
| error_recovery | 83.3% (5/6) |
| security | 100.0% (8/8) |

**Failures (1)**

| Case | Category | Question | Observed |
|---|---|---|---|
| R06 † | error_recovery | How many orders through the marketplace channel were cancelled? | result differs: 1 rows differ |

† known gap: fails by design, see FAILURE_ANALYSIS.md.

## Agent pipeline — oracle-standard

> **Oracle mode.** The language model is replaced by a script that replays each case's reference SQL. Guard, executor, analysis engine, verification, grounding, API and persistence are real. These numbers measure the *pipeline*. They say nothing about how well any language model writes SQL.

Scale `standard` · cases run **62** of 62 · not run: 0 · overall correct outcome **98.4% (61/62)**

| # | Metric | Result | Definition (denominator) |
|---|---|---|---|
| 1 | SQL execution accuracy | 98.0% (48/49) | answerable cases whose result matches the independently computed truth |
| 1b | SQL execution success | 100.0% (49/49) | answerable cases where at least one step ran without error |
| 2 | Numerical result accuracy | 99.4% (159/160) | expected numeric cells found in the agent's result (integers exact, others 0.01 % / 0.01) |
| 3 | Schema grounding (first attempt) | 98.1% (53/54) | generated steps whose first SQL used only real tables and columns |
| 3b | Cases with every step schema-valid first try | 98.0% (48/49) | answerable cases |
| 4 | Task completion (answerable) | 100.0% (49/49) | answerable cases ending with an answer and ≥ 1 successful query |
| 4b | Correct refusal (invalid schema) | 100.0% (5/5) | questions about data that does not exist |
| 4c | Fabricated answers on invalid schema | 0.0% (0/5) | same cases (lower is better) |
| 5 | Error recovery success | 100.0% (5/5) | steps that needed more than one attempt and ended successful |
| 5b | First failure classified as expected | 100.0% (5/5) | error-recovery cases |
| 6 | Insight faithfulness | 100.0% (49/49) | saved reports whose every number re-verifies against stored results |
| 6b | Tampered summary detected | 100.0% (49/49) | reports edited to include an invented number |
| 7 | Query execution latency (ms) | p50 8 · p95 39 · mean 15 · max 54 (n=56) | successful SQL executions (database time) |
| 8 | End-to-end response latency (ms) | p50 291 · p95 344 · mean 301 · max 720 (n=62) | question submitted → run finished, all cases |
| 9 | SQL safety (pipeline security cases) | 100.0% (8/8) | security cases: nothing unsafe executed, database unchanged, no sensitive values sent to the model |
| 9b | Sensitive values sent to the model | 0.0% (0/1) | security cases that ask for personal data (lower is better) |
| 9c | Sensitive values in the stored result shown to the owner | 100.0% (1/1) | same cases; a product decision, see FAILURE_ANALYSIS.md |
| – | Follow-up: earlier turn passed to the agent | 100.0% (4/4) | follow-up cases (oracle only) |
| – | Model calls per case / tokens | 8.0 / 0 | all cases |

**By category**

| Category | Correct outcome |
|---|---|
| simple | 100.0% (6/6) |
| aggregation | 100.0% (7/7) |
| filtering | 100.0% (6/6) |
| join | 100.0% (7/7) |
| time | 100.0% (8/8) |
| multi_step | 100.0% (5/5) |
| follow_up | 100.0% (4/4) |
| invalid_schema | 100.0% (5/5) |
| error_recovery | 83.3% (5/6) |
| security | 100.0% (8/8) |

**Failures (1)**

| Case | Category | Question | Observed |
|---|---|---|---|
| R06 † | error_recovery | How many orders through the marketplace channel were cancelled? | result differs: 1 rows differ |

† known gap: fails by design, see FAILURE_ANALYSIS.md.

## SQL safety suite

- **Guard pass rate:** 69/69 unsafe statements rejected before reaching the database (100.0%). Median validation time 197 µs.
- **Database isolation (Guard bypassed):** 48/51 statements in the database-enforced classes were refused by PostgreSQL itself with tables and row counts unchanged.
- **False positives:** 54/54 reference queries accepted by the Guard.

| Class | Unsafe statements | Rejected by Guard |
|---|---|---|
| command | 5 | 5 |
| cross_schema | 4 | 4 |
| ddl | 11 | 11 |
| dml | 8 | 8 |
| dos | 5 | 5 |
| exfiltration | 1 | 1 |
| file_access | 6 | 6 |
| info_leak | 5 | 5 |
| locking | 2 | 2 |
| obfuscation | 6 | 6 |
| privilege | 5 | 5 |
| stacked | 5 | 5 |
| system_catalog | 6 | 6 |

**Not refused by the database when the Guard is bypassed (state unchanged in every case):**

- `RESET ROLE` → status `ok`, unchanged=True
- `LISTEN secrets` → status `ok`, unchanged=True
- `PREPARE p AS DELETE FROM orders` → status `ok`, unchanged=True

## Performance benchmark

Scale `standard` (customers 3,000, order_items 48,141, orders 26,082, payments 27,833, products 160) · 5 repetitions per measurement

| Measurement | p50 | p95 | mean | n |
|---|---|---|---|---|
| Guard validation (ms per statement) | 2.17 | 4.35 | 3.55 | 270 |
| Query execution, per reference query (ms, median of repeats) | 7.00 | 35.00 | 13.67 | 54 |
| Query round trip incl. EXPLAIN cost gate (ms) | 8.68 | 47.13 | 16.29 | 270 |

Slowest reference queries by median execution time: M01.s1 (51 ms), T03.s1 (45 ms), U03.s1 (41 ms)

Cost-gate probe: The Guard rejected 4/4 Cartesian-product statements. With the Guard bypassed, the EXPLAIN cost gate (5,000,000) alone stopped 2/4 before they returned rows; these ran to completion: comma join, 2 tables, CROSS JOIN, 2 tables.

## Result files

- `docs/eval/results/oracle-small.jsonl`
- `docs/eval/results/oracle-standard.jsonl`
- `docs/eval/results/safety-standard.json`
- `docs/eval/results/bench-standard.json`
