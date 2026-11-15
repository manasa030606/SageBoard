# Sageboard evaluation

Everything lives in `apps/api/evals/` (development tooling; nothing in `app/` imports it).
Run from `apps/api`. Results are written to `docs/eval/results/`.

```bash
# 62-question dataset + expected results, as JSON for review
uv run python -m evals dataset --scale standard      # docs/eval/dataset/retail_v1.standard.json

# Oracle mode: reference SQL replayed through the real pipeline. Measures the PIPELINE only.
uv run python -m evals run --mode oracle --scale small
uv run python -m evals run --mode oracle --scale standard

uv run python -m evals safety --scale standard       # 69 attack statements: Guard + database layer
uv run python -m evals bench  --scale standard       # latency, Guard throughput, cost gate

# Summary built only from the result files
uv run python -m evals report --results ../../docs/eval/results/oracle-standard.jsonl \
    ../../docs/eval/results/safety-standard.json ../../docs/eval/results/bench-standard.json
```

Oracle runs need the test databases (`source` your test env, as for `pytest`). A subset run
(`--ids S01,A01`) writes to the same default file, so give it `--out` unless you mean to replace it.

## Live mode: measuring the real model

This is the only way to get model accuracy numbers. It cannot be run in a sandbox without model access.

1. In `apps/api/.env`: `LLM_PROVIDER=google`, `GOOGLE_API_KEY=…` (free tier), and the model name you want to evaluate.
2. Make sure the development database is up and migrated (`--db dev` is the default for live).
3. Start with a small batch to check wiring and quota:
   `uv run python -m evals run --mode live --scale small --max-cases 5`
4. Continue in as many sessions as the free tier needs. Results are appended, finished cases are skipped:
   `uv run python -m evals run --mode live --scale small --resume`
5. Build the summary: `uv run python -m evals report --results ../../docs/eval/results/live-small.jsonl`

Notes: a case makes about 8 model calls on the oracle path (8.0 measured; real runs add repairs), so 62 cases is roughly 500 calls; the default
`LLM_DAILY_REQUEST_LIMIT` is 200, so expect about three days on the free tier. The run stops
cleanly on a quota or auth error and tells you to re-run with `--resume`; cases that finished are kept and skipped. Do not put the key in any
file that is committed. Live results are labelled with the model name and are not comparable
with oracle results.

## Metrics

| # | Metric | Definition |
|---|---|---|
| 1 | SQL execution accuracy | Share of answerable cases whose result equals the independently computed truth (1b: share that ran without error) |
| 2 | Numerical result accuracy | Share of expected numeric cells present in the result (integers exact; others within 0.01 or 0.01 %) |
| 3 | Schema grounding | Share of generated steps whose first SQL used only real tables and columns |
| 4 | Task completion | Answerable: ended with an answer and a successful query. Invalid-schema: correct refusal (4b), fabricated answers (4c, lower is better) |
| 5 | Error recovery | Steps that needed more than one attempt and ended successful |
| 6 | Insight faithfulness | Saved reports whose every number re-verifies; 6b: an edited report with an invented number must be flagged |
| 7 | Query latency | Database execution time of successful queries |
| 8 | End-to-end latency | Question submitted to run finished |
| 9 | SQL safety | Guard rejection rate on the attack corpus; database-layer isolation with the Guard bypassed; pipeline security cases |

Ground truth is computed in plain Python from the seeded generator, never with SQL, so a wrong
reference query is caught (`tests/integration/test_eval_dataset.py`).
