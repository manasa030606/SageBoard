# Phase 9 — Testing and evaluation

Status: implemented 2026-11-15. Decisions D56–D61. **Live-model accuracy has not been measured**: the build sandbox cannot reach the model API. Every figure below comes from a run that was executed; the live run is yours to do (step 8 of the checklist).

## What was delivered

| Requested | Delivered |
|---|---|
| Evaluation dataset, ≥ 50 questions | 62 cases in 10 categories (6 simple, 7 aggregation, 6 filtering, 7 join, 8 time, 5 multi-step, 4 follow-up, 5 invalid-schema, 6 error-recovery, 8 security), `apps/api/evals/cases.py` |
| Expected results | Computed in plain Python from the seeded generator, exported to `docs/eval/dataset/retail_v1.{small,standard}.json`; every reference query checked against them on PostgreSQL |
| Automated evaluation scripts | `python -m evals run / safety / bench / dataset / report`; oracle and live modes; resumable |
| Evaluation summary | `docs/eval/EVALUATION_SUMMARY.md` (generated from the result files) |
| Failure analysis | `docs/eval/FAILURE_ANALYSIS.md` |
| Performance benchmark | `docs/eval/PERFORMANCE_BENCHMARK.md` |
| Testing levels | backend unit, agent nodes, SQL validation, LangGraph and API integration, frontend components, Playwright E2E, adversarial/security (table in TESTING_STRATEGY §10b) |

## Results (oracle mode, so pipeline only, not model accuracy)

| Metric | Small | Standard |
|---|---|---|
| Expected outcome reached | 61 / 62 | 61 / 62 |
| 1 SQL execution accuracy | 48 / 49 | 48 / 49 |
| 2 Numerical accuracy | 157 / 158 | 159 / 160 |
| 3 Schema grounding, first attempt | 53 / 54 | 53 / 54 |
| 4 Task completion (answerable) / correct refusals | 49 / 49 · 5 / 5 | 49 / 49 · 5 / 5 |
| 5 Error recovery | 5 / 5 | 5 / 5 |
| 6 Insight faithfulness / tamper detected | 49 / 49 · 49 / 49 | 49 / 49 · 49 / 49 |
| 7 Query execution, p50 / p95 | 2 / 6 ms | 8 / 39 ms |
| 8 End-to-end, p50 / p95 | 284 / 316 ms | 291 / 344 ms |
| 9 Safety: pipeline security cases | 8 / 8 | 8 / 8 |

The single miss everywhere is R06, a wrong answer that executes cleanly (F4 in the failure analysis). Latencies exclude all model time. Exact current values are in the generated summary; the table above is a copy and the summary wins if they ever differ.

SQL safety suite (standard): Guard rejected 69 / 69 attack statements; 54 / 54 reference queries accepted; with the Guard bypassed PostgreSQL refused 48 / 51 and left the other 3 (harmless) with the database unchanged.

Tests executed in the final run: backend 669 passed; web 94 passed (was 75); Playwright 5 passed on Chrome for Testing 153; ruff, ruff format, mypy (174 files), ESLint, tsc, Prettier and `next build` clean.

## Defects found and fixed
1. **Customer emails were sent to the model** (eval case X02) → masked in all model-bound payloads (D58).
2. **Session time zone not pinned** → UTC per transaction, regression test fails without it (D59).
3. **Cartesian joins not rejected** (safety suite; design said they would be) → `CARTESIAN_JOIN` rule (D60).
4. Four defects in the evaluation tooling itself, listed in the failure analysis (F6), including one that understated the numerical-accuracy denominator.

## Open items (decisions for you)
- **Stored results still show real emails to the owner.** Mask in the UI too?
- **R06 silent wrong zero** is unsolved; see F4 for ideas.
- Aliased sensitive columns can still reach the model (name-based matching).
- CI does not run Playwright yet (needs Chrome and a PostgreSQL service); add in Phase 15 hardening.
- The earlier safety output from before the Guard change was overwritten; its figures are quoted from the observed run.

## Checklist for you (from the repository root)
1. Copy the files over your tree. New dependency: from `apps/web` run `pnpm install` (adds `@playwright/test`).
2. `cd apps/api && uv sync && uv run ruff check . && uv run mypy . && uv run pytest -q` (expect 669 passed).
3. `cd apps/web && pnpm lint && pnpm typecheck && pnpm test && pnpm build` (expect 94 tests).
4. Oracle evaluation, from `apps/api` with the test database env set as for pytest:
   `uv run python -m evals run --mode oracle --scale standard`, then `uv run python -m evals safety --scale standard` and `uv run python -m evals bench --scale standard`.
5. Rebuild the summary: `uv run python -m evals report --results ../../docs/eval/results/oracle-standard.jsonl ../../docs/eval/results/safety-standard.json ../../docs/eval/results/bench-standard.json`. Your numbers will differ slightly in latency only.
6. Browser tests: `cd apps/web && pnpm exec playwright install chromium && pnpm e2e` (or `PLAYWRIGHT_CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" pnpm e2e`). It reuses the frontend you already run on 3001 (no need to stop it), starts the test backend on 8100, and reroutes the browser's calls from your API on 8000 to 8100, so your development database is never touched. If nothing is on 3001 it starts `next dev` there itself. The test environment variables from `tests/conftest.py` (`SAGEBOARD_TEST_*`) must be set.
7. Check the Save-as-report fix yourself: the second Playwright test fails if `method: "POST"` is removed from `reports.create`.
8. **Live evaluation (the real model numbers):** follow `docs/eval/README.md`. Expect about three days on the Gemini free tier. Then `uv run python -m evals report --results ../../docs/eval/results/live-small.jsonl` and tell me the output so the failure analysis can cover real-model failures.

## Suggested commit
```
Phase 9: evaluation framework, safety suite, E2E tests, and fixes

- 62-case dataset with independently computed expected results, oracle/live runner, nine metrics
- Mask sensitive result columns in model-bound payloads; pin session time zone to UTC;
  reject join-without-condition (CARTESIAN_JOIN)
- Component tests, Playwright E2E against the real stack with the oracle model
- Docs: evaluation summary, failure analysis, benchmark; D56-D61

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019GdH5K4DJ3v9k3odQrnKTh
```

Phase 10 (run streaming, formerly Phase 9) has not been started and needs your approval.
