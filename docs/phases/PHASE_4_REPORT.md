# Phase 4 — Backend API, authentication and frontend wiring: completion report

| Field | Value |
|---|---|
| Date | 2026-11-14 |
| Status | Implemented and tested; awaiting owner review. **Phase 5 not started** |
| Scope | FastAPI routers and services, authentication and user-level ownership (added to this phase at the owner's request, D34), migration 0004, Next.js connected to the live API. No AI agents |

## Completed endpoints (36 operations, all under `/api/v1`)

| Router | Endpoints |
|---|---|
| health | `GET /healthz` · `GET /readyz` (app, ingest, executor, **migration head**, LLM config) |
| auth | `POST /auth/register` · `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout` · `GET /auth/me` |
| datasets: CSV upload | `POST /datasets/uploads` (analyse only) · `POST /datasets/{id}/finalize` (load with type overrides) |
| datasets: data and metadata | `GET /datasets` · `GET /datasets/{id}` · `PATCH /datasets/{id}` · `DELETE /datasets/{id}` · `GET /datasets/{id}/jobs` · `PATCH /datasets/{id}/tables/{table_id}` · `PATCH /datasets/{id}/columns/{column_id}` · `POST /datasets/demo` |
| datasets: schema inspection | `GET /datasets/{id}/schema?level=summary\|full&include_samples=` · `GET /datasets/{id}/tables/{table}/preview` |
| connections | `GET /connections` |
| conversations | `GET /conversations` · `POST /conversations` · `GET /conversations/{id}` · `PATCH /conversations/{id}` · `DELETE /conversations/{id}` |
| analysis sessions | `POST /conversations/{id}/sessions` · `GET /analysis-sessions/{id}` · `POST /analysis-sessions/{id}/cancel` |
| query history | `GET /history/sessions` · `GET /history/queries` |
| reports | `GET /reports` · `POST /reports` · `GET /reports/{id}` · `PATCH /reports/{id}` · `DELETE /reports/{id}` · `GET /reports/{id}/export.md` |

Contracts: [API_SPECIFICATION.md](../API_SPECIFICATION.md) §0–§11 and the served OpenAPI document (`/api/v1/openapi.json`, Swagger at `/api/v1/docs`).

## How the requirements were met

| Requirement | Implementation |
|---|---|
| Separate routers | `app/api/v1/{health,auth,datasets,connections,conversations,history,reports}.py`, aggregated in `router.py` |
| Service classes | `AuthService`, `DatasetService`, `AnalysisService`, `HistoryService`, `ReportService`, `ConnectionService`, `HealthService`. Route handlers only parse input, call one service method and build the response schema |
| Pydantic schemas | `app/schemas/*`. Request bodies use `extra="forbid"` and length limits; every route declares `response_model` |
| Dependency injection | `app/api/deps.py`: settings, databases, DB session, `CurrentUser`, `csrf_protect`, rate limits, one provider per service |
| No DB operations in routes | `/connections` was moved into `ConnectionService`; no route module imports SQLAlchemy |
| Consistent errors | One envelope `{error: {code, message, details, request_id}}` for app errors, validation, 404/405, rate limits (with `Retry-After`), CSRF, auth, **database outages (503 `DATABASE_UNAVAILABLE`)** and unexpected errors (500) |
| Structured logging | structlog JSON with `request_id` on every line; `user_id` bound once authenticated; audit events; database failures logged by error type only |
| OpenAPI | Every operation has a summary, tag, success schema and documented error responses (401 on protected routes). Enforced by `tests/test_api_contract.py` |
| Validate inputs | Typed UUIDs, enums, lengths, `extra="forbid"`, validated cursors, password and email policy, CSV validation (Phase 3) |
| Dataset ownership | Every service query filters by `owner_id`; other users' resources are 404. Tested across all 19 routes that take an id (`tests/integration/test_ownership.py`) |
| Upload limits | Size, rows, columns and cell limits (Phase 3) plus **20 uploads/hour per user** |
| No stack traces or secrets | Generic 500/503 messages; tests assert no host, user, password, driver text or `Traceback` in responses |
| CORS explicit | Allowlist with credentials, `X-CSRF-Token` allowed, `Retry-After` exposed; unknown origins get no CORS headers (tested) |
| Auth and authorisation | Implemented, not just prepared: argon2id; JWT access cookie; rotating, hashed refresh tokens with reuse detection; CSRF double-submit; login and registration rate limits; audit log; `AUTH_MODE=demo` refused in production |

**Frontend connected** (`apps/web`):
- `/login` and `/register`.
- A session guard over `/app/*` that redirects to `/login?next=…`.
- The user's name and a sign-out button in the shell.
- Data sources: list, upload → server analysis → type review → load, sample dataset, table preview with masking and a reveal toggle, column description and sensitivity edits, delete.
- Query history: the real SQL audit trail, with filters and Load more.
- Reports: list, detail, Markdown export, delete.

Dashboard and Analyst keep their labelled sample runs, because they need the agent.

## Test results (actual, 2026-11-14)

| Command | Result |
|---|---|
| `uv run ruff check .` / `ruff format --check .` / `mypy` (strict) | Clean: 93 files formatted, no type issues in 91 files |
| `uv run pytest` (PostgreSQL 16, all four role URLs) | **283 passed, 0 skipped** (44 s); line and branch coverage of `app/`: **95 %** |
| `pytest -m "not integration"` / `-m integration` | 192 passed / 91 passed |
| CI path: database bootstrapped from 0001 → `alembic upgrade head` → full suite | 283 passed |
| Web: `pnpm lint` · `tsc` · `format:check` · `test` · `build` | Clean · clean · clean · **66 passed** · build OK |
| Browser journey (Chrome, production build, live API) | 10/10 steps (below); no page errors; the only error responses were the intended 401s and the 422 |

Coverage of the requested test areas:

| Area | Where |
|---|---|
| Valid requests | `test_workspace_api.py` (conversation lifecycle, sessions, history, reports, dataset metadata), `test_datasets_api.py`, `test_auth_api.py` |
| Invalid requests | Register validation (6 cases), question validation, bad cursors and limits, unknown fields, bad overrides, bad UUIDs, rename conflicts |
| Missing resources | 404 for unknown conversation, session, report, table, dataset, analysis session |
| Database failures | `test_api_contract.py`: unreachable DB → clean 503 in both auth modes; missing config → 503; leak checks |
| CSV validation | `test_csv_validation.py` (76) and API-level upload tests (Phase 3), plus the upload rate limit |
| Unauthorized access | No, expired, forged and tampered tokens; inactive user; CSRF missing or wrong; refresh reuse; logout revocation; the cross-user matrix over every route with an id |
| API response schemas | Responses parsed back into the Pydantic models (`SessionOut`, `ConversationDetail`, `SessionAccepted`, `SessionDetail`, `Page[...]`, `QueryHistoryItem`, `ReportDetail`); OpenAPI inventory and documentation checks |

Browser journey: (1) `/app/data` redirects to sign-in. (2) A weak password is refused, then registration lands on the empty state. (3) Load sample dataset. (4) The customers preview shows names and emails as «redacted». (5) Upload a CSV, review the inferred types, override one, load 3 rows. (6) History shows the preview queries and their SQL. (7) Reports shows its empty state. (8) The mobile layout (390 px) has no horizontal overflow. (9) Sign out; protected pages redirect. (10) A wrong password is refused, then sign-in returns to the page you were going to.

### Bugs found by testing and fixed
1. **Silent refresh was blocked by CSRF.** After a reload the browser has no CSRF token yet, so once the 15-minute access token expired the user would have been signed out. Refresh is now CSRF-exempt (D36), and an integration test covers the reload case.
2. **A stale "signed out" state survived re-login.** Next.js keeps visited pages alive in the background. Sign-in, sign-out and expiry now do a full page load (D41), which also guarantees no data from a previous user stays in memory.
3. **The audit log rejected non-IP client addresses** (`INET`). Only parseable IPs are recorded now.
4. **Alembic needed `JWT_SECRET` just to migrate.** Migrations now read only `MIGRATION_DATABASE_URL`.
5. **Importing `app.main` built the app from the developer's `.env`** (CI would have failed). The app is now created lazily; `uvicorn app.main:app` still works.
6. **The production build failed** on a URL read outside `<Suspense>` (Cache Components).
7. **Next.js warned that the app pages were "dropped from rendering"** (instant-navigation insight, reported by the owner). The fix from item 6 wrapped the whole app area in one Suspense boundary, and the session gate hid each page until `/auth/me` answered. The shell and pages now render immediately. Only the active-nav highlight (reads the URL) and the report detail (reads its id) sit behind small boundaries, and the session redirect reads `window.location` in an effect. Verified in `next dev`: no insights after client-side navigation across every page. Trade-off: a signed-out visit makes one or two extra 401 requests before the redirect; no data is ever returned without a session.

## New concepts (mentor notes)
- **Access and refresh tokens.** *What:* a short-lived pass (15 min) and a long-lived renewal ticket (14 days). *Why:* a stolen access token expires quickly, and the refresh token is only ever sent to `/auth`. *How:* JWT in an HttpOnly cookie; the refresh token is random and stored only as a hash. *Where:* `app/auth/tokens.py`, `services/auth.py`.
- **Rotation and reuse detection.** Every refresh swaps the ticket. If an old ticket shows up later, someone copied it, so every ticket from that login is revoked.
- **CSRF double-submit.** Another site can make your browser *send* cookies but can't *read* them. Requiring a header that copies the cookie proves the request came from our page.
- **Ownership by query, not by check.** Services never fetch "by id" alone; they always add `owner_id = me`. Forgetting a permission check can't leak data, because the row is simply never found (404).
- **Keyset pagination.** "Give me items older than this one" instead of "skip 50", so pages don't shift when new rows arrive and stay fast on big tables.

## Limitations
- **No AI agent:** sessions stay `queued`. Reports can only come from finished sessions, which the API can't produce yet (tests create them directly in the database).
- **Rate limits are per process**; run one API instance (ADR-0004) or move the counters to the database later.
- **Not built yet:** email verification, password reset, account deletion, settings and usage APIs, CSP headers. Deleting a user in the database removes metadata but not their warehouse schemas.
- **Settings page** is still the Phase 2 sample (except live system status).
- **Not verified on Neon or a deployed domain:** cross-site cookies (`COOKIE_SAMESITE=none`) are implemented and validated by settings, but only tested locally (same site).
- **The upload review** happens in one drawer session: closing the drawer discards the pending upload; there's no "resume review" later.

## Run commands
See `apps/api/README.md` and the Phase 4 checklist in the chat.
