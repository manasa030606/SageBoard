# ADR-0004 — In-process run execution with a persisted event log

| Status | Accepted (2026-11-12, as default) — resolves Open Decision **D6** |
|---|---|
| Implemented in | Phase 7 |

## Decision
Agent runs execute as asyncio tasks inside the API process, managed by a Run Manager. Limits: 2 concurrent runs per user and a per-instance semaphore. State survives in two places: the LangGraph Postgres checkpointer (`lg` schema) and `app.run_events`. One API instance is deployed.

## Consequences
- Simple deployment: no Redis or worker process.
- A restart interrupts in-flight runs. On startup, runs still marked `running` are set to `failed` with reason `interrupted`, and the UI offers a re-run.
- Upgrade path, if needed later: move graph execution to an `arq` worker (Redis) without changing the API contract, since clients only see the event stream.
