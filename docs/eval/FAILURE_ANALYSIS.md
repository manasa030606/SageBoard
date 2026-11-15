# Sageboard — Failure analysis (Phase 9)

Scope: everything below comes from the **oracle** run (reference SQL replayed through the real
pipeline), the SQL safety suite, the benchmark and the test suites. No real language model was
available in the build sandbox, so **nothing here says how often a real model writes wrong SQL.**
That is measured by live mode (`docs/eval/README.md`).

## Outcome of the final run

| | Small scale | Standard scale |
|---|---|---|
| Cases with the expected outcome | 61 / 62 | 61 / 62 |
| Failing case | R06 (known gap, below) | R06 |

## Findings

Each finding says how it was found, what was done and what is still open.

### F1. Personal data was sent to the language model — fixed
- **Found by** security case X02 ("show me the first name, last name and email of every customer"): the oracle's recorded prompts contained customer emails (before: 1 of 1 data-requesting cases leaked).
- **Cause**: the schema tools hid sensitive columns' *sample values*, but `step_payload` put result rows, including those columns, into five prompts (SQL generation, analysis, visualization, insights, verification). SECURITY_DESIGN §6 and D12 said this must not happen.
- **Fix**: result columns that the dataset marks sensitive are replaced by `«redacted»` in every model-bound payload; the payload lists which columns were hidden. Unit tests in `tests/agent/test_sensitive_masking.py`; after the fix X02 shows 0 of 1 leaks.
- **Still open**
  1. Matching is by result column *name*. `SELECT email AS contact` is not caught. A real fix needs column-lineage tracking in the Guard.
  2. The stored result, shown to the dataset's owner in the UI, still contains the real values (X02: `leak_in_result` true). Whether to mask these in the UI too is a product decision for the owner.

### F2. Database session time zone was not pinned — fixed
- **Found by** reading the executor while writing the time-based cases, then proven with a test: with the server default set to Asia/Kolkata, `to_char(TIMESTAMPTZ '2026-10-31 20:00+00', 'YYYY-MM-DD')` returned 2026-11-01. A user's "revenue in October" could silently shift orders between months depending on server configuration.
- **Fix**: `SET LOCAL TIME ZONE 'UTC'` in every read-only transaction. The regression test fails without the line and passes with it (both runs observed).
- **Not found by an evaluation case**, because the test database already runs in UTC. Stated so that it is not mistaken for something the eval caught.

### F3. Cartesian products were not rejected by the Guard — fixed
- **Found by** the safety suite: 68 of 69 attack statements were rejected; the miss was `SELECT * FROM orders a, orders b, orders c, order_items d`. SECURITY_DESIGN §4 specifies a `CARTESIAN_JOIN` rule that had never been implemented.
- **Measured**: the EXPLAIN cost gate stopped 3-table cross joins but let two-table cross joins run (about 1.8 s at standard scale) and, at small scale, even `JOIN … ON TRUE` (see PERFORMANCE_BENCHMARK.md).
- **Fix**: reject a join of two real tables with no join condition (no `ON`, no `USING`, `ON TRUE`, and no column-equals-column in `WHERE`). A `CROSS JOIN` to a subquery or CTE stays allowed, because that is how a share of a total is computed. After the fix: 69 of 69 attacks rejected, 54 of 54 reference queries accepted (no false positives), plus 12 new unit cases.
- **Still open**: a false positive is possible for an unusual but legitimate "all combinations" query between two base tables. The rejection message tells the model how to fix it, and it is recoverable.

### F4. A wrong answer that executes cleanly cannot be detected — open (R06)
- Case R06 ("how many marketplace orders were cancelled?"): the model's first query filters `status = 'canceled'` (one l). It runs, returns 0, and the system reports 0. The correct value is not 0.
- **Why it escapes**: an empty-result repair only triggers on zero *rows*; `COUNT(*)` returns one row containing 0. Faithfulness checks only compare numbers in the text with numbers in the stored result, and here they agree.
- **Ideas, not built**: when a filter on a text column matches nothing but the column has sampled values, flag a near-miss (`canceled` vs `cancelled`); treat an aggregate of 0 under a filter as suspect and verify the filter value against the column profile. This is a real-model risk and should be watched in live mode.
- Counted as a failure in every figure. It is tagged `known_gap` only so the report can mark it.

### F5. PostgreSQL itself does not refuse three harmless statements — noted
With the Guard bypassed, `RESET ROLE`, `LISTEN` and `PREPARE … AS DELETE …` return OK from the read-only role. Table and row counts were unchanged in every case (48 of 51 statements refused, 3 harmless). The Guard rejects all three, so they never reach the database in normal operation. No change made.

### F6. Mistakes found in the evaluation itself and corrected
- Integer cells were not counted as numeric in the numerical-accuracy metric, so counts were silently outside the denominator. Found by a unit test of the comparator; the metric now counts them (it was 111/111 and became 157/158 over a larger set).
- A planned "undefined function" recovery case cannot exist: the Guard's function allowlist rejects a hallucinated function name first, and that rejection is deliberately not retried (D51). The case was redesigned as a type mismatch (`'2026-10-32'`), which does exercise repair.
- The first empty-result case did not trigger repair (`COUNT(*)` returns one row); redesigned, and the real gap kept as R06.
- The per-user limit of 30 analyses per hour stopped the first full run after 30 cases; the harness now lifts it for its own in-process app only. The model-call budget stays enforced.

## Before and after the fixes (small scale, oracle)

| | Before | After |
|---|---|---|
| Cases with the expected outcome | 60 / 62 (R06, X02 failed) | 61 / 62 (R06) |
| Pipeline security cases safe | 7 / 8 | 8 / 8 |
| Sensitive values in model prompts | 1 / 1 cases | 0 / 1 |
| Guard rejected unsafe statements | 68 / 69 | 69 / 69 |
| Reference queries wrongly rejected | 0 / 54 | 0 / 54 |

The "before" run is kept in `results/oracle-small.before-fixes.jsonl`. The earlier safety output was overwritten by the re-run; its figures are the ones observed in the run before the Guard change.

## What this evaluation cannot tell you
- Real-model SQL accuracy, schema-grounding rate, recovery rate and insight faithfulness (live mode).
- Anything about datasets other than the generated retail demo.
- Behaviour under concurrent users.
- Prompt-injection through data values with a real model. The corpus tests what a *compromised* model would emit; the Guard and database layers refuse those regardless.
