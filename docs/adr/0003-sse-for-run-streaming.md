# ADR-0003 — Server-Sent Events for run streaming

| Status | Accepted (2026-11-12, as default) — resolves Open Decision **D7** |
|---|---|
| Implemented in | Phase 7 |

## Decision
Agent run progress is streamed with SSE (`GET /api/v1/runs/{id}/events`). Every event is persisted to `app.run_events` *before* it's published, so reconnecting with `Last-Event-ID` replays without loss. If SSE stalls behind a proxy, there's a polling fallback (`GET /runs/{id}` every 2 s).

## Why not WebSockets
The stream only goes one way (server → client). SSE uses plain HTTP, gets automatic reconnects from `EventSource`, and works with cookie auth and CORS without a custom protocol. User actions (cancel, resume) are ordinary REST calls.

## Phase 1 groundwork
The request-context middleware is pure ASGI rather than `BaseHTTPMiddleware`, so it doesn't buffer streaming responses.
