# Performance report (Phase 10)

All numbers were measured, not estimated. They are from one sandbox machine, with the real API, real Postgres and the **oracle model** (a scripted stand-in for the LLM), so model latency and token use are **not** measured here. Treat the figures as relative: they show whether a change helped or whether the system holds up, not what production will do.

Reproduce: `cd apps/api && uv run python scripts/perf_probe.py` against the E2E server (`python -m evals.e2e_server 8100`), and `scripts/perf_probe.py` prints JSON. The frontend numbers came from headless Chrome against a production build on localhost.

## Method

1. Measure the system before changing anything (baseline).
2. Change only what a measurement or the security review justified.
3. Re-measure with the same script.

## Backend latency (one user, sequential, 8 endpoints)

| Endpoint | p50 before → after (ms) | p95 before → after (ms) |
|---|---|---|
| GET /healthz | 2.2 → 2.2 | 3.7 → 2.9 |
| GET /auth/me | 3.7 → 4.0 | 5.3 → 4.3 |
| GET /datasets | 7.3 → 6.0 | 9.7 → 7.6 |
| GET /datasets/{id}/schema | 10.2 → 10.8 | 12.6 → 13.2 |
| GET /conversations | 5.6 → 5.4 | 6.6 → 6.3 |
| GET /history/sessions | 6.9 → 6.2 | 8.8 → 7.6 |
| GET /history/queries | 5.8 → 6.0 | 7.0 → 7.3 |
| GET /reports | 5.2 → 5.2 | 6.8 → 6.0 |

The differences are within run-to-run noise. The new middleware (security headers, body limit) costs nothing measurable. No endpoint needed optimising, so none was changed and no cache or index was added.

## Concurrency

| Test | Before | After |
|---|---|---|
| 20 users × 25 reads (500 requests) | 285 rps, p50 66 ms, p95 97 ms, 0 errors | 303 rps, p50 61 ms, p95 95 ms, 0 errors |
| 8 users ask one question at once | 1.26 s, 8 of 8 succeeded | 1.26 s, 8 of 8 succeeded |
| 100 simultaneous requests, one user (after only) | – | 0.45 s, p95 426 ms, 0 errors |
| 300 simultaneous requests, one user (after only) | – | 2.56 s, p95 2,268 ms, 0 errors |
| 12 users × 3 rapid questions (after only) | – | per user 202, 202, 429 (cap of 2 working) |

Latency under 300 simultaneous requests grows roughly with queue depth (one process, pools of 5+5). Nothing failed. That is acceptable for the intended scale (small teams); it is the reason the system is documented as single-instance.

## Agent

| Measure | Result |
|---|---|
| Wall time, answered question (oracle) | 289–307 ms (includes 200 ms client polling) |
| Wall time, refusal | 309 ms |
| Model calls per answered question | 9 |
| Model calls per refusal | 1 |
| SQL executions per answered question | 1 |
| Slowest nodes | `execute_sql` 17 ms, `validate_sql` 11 ms; the rest under 6 ms |
| Tokens | 0 (oracle). **Live token use and latency are unmeasured.** |

With a live model each of the 9 calls costs a network round trip, so model time will dominate. The call count, not node time, is the lever. It was not changed in this phase, because the evaluation shows no accuracy case that fewer calls would keep.

## Large CSV (20 MB, 388k rows)

Measured while a separate process polled `/healthz`, because polling from the same process hides the stall.

| `/healthz` during the upload and load | p50 | p95 | max |
|---|---|---|---|
| Before the fix | 15.4 ms | 140 ms | 2,267 ms |
| After the fix (first measurement) | 8.1 ms | 20.2 ms | 149 ms |
| After the fix (probe re-run, 130 samples) | 7.3 ms | 19.7 ms | 205 ms |

Upload review took 2.4–3.0 s and the finalize step 4.7–5.2 s, both unchanged by the fix. CPU-heavy parsing runs in worker threads, and with Python's default 5 ms thread switch interval those threads starved the event loop. The 0.2 ms interval (`GIL_SWITCH_INTERVAL_S`) let the loop keep serving requests. The cost is somewhat more thread switching; no slowdown in the CSV times was measurable.

Server memory stayed at about 35 MB while 30, 100 and 400 MB uploads were refused, because the size limit is enforced while streaming.

## Frontend (production build, headless Chrome, localhost)

| Measure | Result |
|---|---|
| First contentful paint | 80–224 ms across the pages |
| Network idle | 0.77–1.0 s |
| JavaScript per page | 15–680 KB uncompressed (the largest is the analyst page with charts) |
| API requests per page | 2–4; every page calls `/auth/me` once, and the others are needed for what the page shows |

No redundant request or oversized page stood out, so no frontend optimisation was made. A real-network, real-device test was not done.

## Resource limits in force

| Resource | Limit |
|---|---|
| Upload | 25 MB, 1,000,000 rows, 200 columns, 10,000 characters per cell |
| JSON request body | 1 MiB |
| SQL | 10 s statement timeout, row cap, plan-cost gate |
| Agent | bounded steps and retries per run |
| Analyses per user at once | 2 (`ANALYSES_CONCURRENT_PER_USER`) |
| Analyses at once, whole server | 4 |
| Database pools | app 5+5, ingest 3, executor 5 |

## Not measured

- Live model latency, tokens and cost.
- Behaviour on a hosted database (Neon) or across a real network.
- Large result sets from a large warehouse; the sample data is small.
- Multi-instance behaviour (not supported).

## Observability added

Request ids (already present), plus structured log lines with no content: `agent.run_finished` (status, termination, error code, duration, model calls, SQL executions, tokens, nodes that did not succeed), `rate_limited` (limit kind and retry delay) and `request_body_too_large`. No monitoring stack was added.
