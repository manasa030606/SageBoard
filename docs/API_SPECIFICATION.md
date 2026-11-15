# Sageboard — API Specification

| Field | Value |
|---|---|
| Document | API_SPECIFICATION v0.6 |
| Status | v0.2 approved 2026-11-12. v0.3 (2026-11-13): §3 Datasets as built. v0.4 (2026-11-14): auth, conversations, analysis sessions, history, reports and readiness as built in Phase 4 (§0 lists every endpoint). v0.5 (2026-11-14): sessions run the LangGraph agent; result and trace (Phase 5). v0.6 (2026-11-15): `follow_up_questions` and the full chart-type enum (Phase 7, D52). Decisions: see DECISION_LOG.md |
| Base URL | `https://<api-host>/api/v1` |
| Format | JSON (UTF-8); `multipart/form-data` for uploads; `text/event-stream` for run events |
| Source of truth | FastAPI-generated OpenAPI 3.1 at `/api/v1/openapi.json`. The frontend types are generated from it. |

---

## 0. Implementation status (Phase 5)

37 operations are live. Each is listed in the OpenAPI document and covered by tests (`tests/test_api_contract.py` fails if the route list changes without this doc).

| Area | Live endpoints | Planned |
|---|---|---|
| Health | `GET /healthz`, `GET /readyz` | — |
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me` | settings, password change, account deletion (§9) |
| Datasets | list, upload, finalize, get, `PATCH`, delete, schema, preview, jobs, table `PATCH`, column `PATCH`, `POST /datasets/demo` | — |
| Connections | `GET /connections` | external PostgreSQL (post-MVP) |
| Conversations | list, create, get, rename, delete | — |
| Analysis sessions | `POST /conversations/{id}/sessions` (starts the agent), `GET /analysis-sessions/{id}` (incl. `result`), `POST /analysis-sessions/{id}/cancel`, `GET /analysis-sessions/{id}/trace` | SSE stream (§5), rerun, paged results |
| History | `GET /history/sessions`, `GET /history/queries` | — |
| Reports | list, create, get, `PATCH`, delete, `GET /reports/{id}/export.md` | — |
| Dashboard, settings, usage | — | §8, §9 |

Naming: the v0.2 "runs" are called **analysis sessions** in the API, at `/analysis-sessions/…`. Plain `/sessions` would be confused with sign-in sessions.

## 1. Conventions

### 1.1 Authentication (as built)
- Cookies set by register, login and refresh:
  - `sb_session`: JWT access token, HS256, 15 min, HttpOnly, path `/`.
  - `sb_refresh`: opaque random token, 14 days, HttpOnly, path `/api/v1/auth`. It rotates on every use and only its SHA-256 hash is stored.
  - `sb_csrf`: CSRF token, readable by JS. The same token is also returned as `csrf_token` in the response body.
- All three are `SameSite=Lax` by default (`COOKIE_SAMESITE`). They are `Secure` automatically when `ENV=production`.
- Every POST/PUT/PATCH/DELETE must send `X-CSRF-Token` equal to the `sb_csrf` cookie. Otherwise the response is `403 CSRF_FAILED`. Exempt endpoints:
  - `/auth/register` and `/auth/login`, because there is no session yet.
  - `/auth/refresh`, because a reloaded page has no token in memory and gets one from refresh. A forged refresh only rotates the victim's own cookies, and the attacker can't read the response.
- `401` codes:
  - `AUTH_REQUIRED`: no or invalid session.
  - `TOKEN_EXPIRED`: the access token expired. The client calls `/auth/refresh` once and retries.
  - `INVALID_CREDENTIALS`: on login, the same message whether or not the email exists.
- A refresh token presented again after it was rotated revokes its whole family. The exception is a 30-second grace window for two tabs refreshing at once.
- Another user's resource → `404 NOT_FOUND` on every route. This is tested over the full route list.
- `AUTH_MODE=demo` (local only, refused in production) makes every request act as the seeded demo user, with no cookies and no CSRF.

### 1.2 Pagination
Cursor (keyset) based: `?limit=25&cursor=<opaque>` → `{ "items": [...], "next_cursor": "..." | null }`. `limit` is 1–100. A malformed cursor → `422 INVALID_CURSOR`. As built for conversations, history and reports; `GET /datasets` returns all of a user's datasets.

### 1.3 Errors — single envelope
```json
{
  "error": {
    "code": "DATASET_NOT_READY",
    "message": "This dataset is still loading. Try again in a moment.",
    "details": { "dataset_id": "..." },
    "request_id": "req_01J..."
  }
}
```
| HTTP | Codes |
|---|---|
| 400 | `VALIDATION_ERROR` (details = field errors), `UNSUPPORTED_FILE`, `FILE_TOO_LARGE` (413 also allowed) |
| 401 | `AUTH_REQUIRED`, `INVALID_CREDENTIALS`, `TOKEN_EXPIRED` |
| 403 | `CSRF_FAILED` |
| 404 | `NOT_FOUND` |
| 409 | `CONFLICT` (duplicate name), `RUN_NOT_RESUMABLE`, `DATASET_NOT_READY` |
| 422 | `GUARD_REJECTED` (widget refresh / re-run whose SQL no longer validates) |
| 429 | `RATE_LIMITED`, `DAILY_BUDGET_EXCEEDED` (with `Retry-After`) |
| 502/503 | `LLM_UNAVAILABLE`, `DATABASE_UNAVAILABLE` |
| 500 | `INTERNAL_ERROR` (no internals in message) |

### 1.4 Common headers
`X-Request-ID` (echoed or generated), `Idempotency-Key` (optional on run creation and uploads).

## 2. Auth (as built)

| Method | Path | Body | Response | Errors |
|---|---|---|---|---|
| POST | `/auth/register` | `{email, password, full_name}` (no other fields) | `201 Session` + cookies | 409 `EMAIL_TAKEN`, 422 `INVALID_EMAIL` / `WEAK_PASSWORD` / `INVALID_NAME`, 429 |
| POST | `/auth/login` | `{email, password}` | `200 Session` + cookies | 401 `INVALID_CREDENTIALS`, 429 (5/min per IP+email, 20/min per IP) |
| POST | `/auth/refresh` | — (refresh cookie) | `200 Session` + rotated cookies | 401 `AUTH_REQUIRED` / `TOKEN_EXPIRED` |
| POST | `/auth/logout` | — | `204`, revokes this login's refresh tokens and clears cookies | 403 |
| GET | `/auth/me` | — | `200 Session` (re-issues a lost CSRF cookie) | 401 |

```ts
type User = { id: string; email: string; full_name: string; created_at: string };
type Session = { user: User; csrf_token: string; auth_mode: "session" | "demo" };
```
Password policy: 10–128 characters; not a common password; at least 4 distinct characters; not the email address. Stored as argon2id. Emails are trimmed, lower-cased and unique.

## 3. Datasets — *implemented in Phase 3*

All paths are under `/api/v1`. Until authentication lands, the caller is the seeded demo user (D27). Another user's dataset always answers `404 NOT_FOUND`, never `403`, so the API doesn't reveal which IDs exist. Endpoints not listed here (`PATCH /datasets/{id}`, table PATCH, `/jobs/{id}`) remain **planned**.

| Method | Path | Request | Success | Errors (`error.code`) |
|---|---|---|---|---|
| GET | `/datasets` | — | `200 {items: DatasetSummary[]}` (newest first) | 503 |
| POST | `/datasets/uploads` | multipart: `file` (.csv), `name?` (≤120), `description?` (≤2000) | `201 UploadReview` — file analysed and stored privately; **nothing loaded**; dataset `pending_review` | 409 `NAME_TAKEN`, 413 `FILE_TOO_LARGE`, 415 `UNSUPPORTED_FILE`, 422 `CSV_INVALID` (`details.issues[]`) |
| POST | `/datasets/{id}/finalize` | `{column_types: {column: type}}` (optional overrides) | `200 DatasetDetail` (`ready`) — synchronous load | 409 `DATASET_NOT_PENDING` / `UPLOAD_EXPIRED`, 422 `VALIDATION_ERROR` (bad override) / `INGESTION_FAILED` (>5 % bad rows; dataset → `failed`, nothing left in the warehouse) |
| GET | `/datasets/{id}` | — | `200 DatasetDetail` (tables, columns, profiles) | 404 |
| GET | `/datasets/{id}/schema` | `level=summary\|full` (default full), `include_samples=true\|false` | `200 SchemaCatalog` | 404 |
| GET | `/datasets/{id}/tables/{table}/preview` | `limit` 1–1000 (capped by `PREVIEW_MAX_ROWS`, 100), `offset` ≥0, `reveal_sensitive=false` | `200 PreviewResponse` | 404 (table not in catalog), 409 `DATASET_NOT_READY`, 503 |
| PATCH | `/datasets/{id}/columns/{columnId}` | `{description?, is_sensitive?}` | `200 ColumnOut` | 404 |
| DELETE | `/datasets/{id}` | — | `204` — warehouse schema + reader role dropped, metadata cascades | 404 |
| GET | `/connections` | — | `200 ConnectionOut[]` | — |

Response shapes (from the served OpenAPI document, `/api/v1/openapi.json`):

```ts
type DatasetSummary = {
  id: string; name: string; description: string | null;
  source_type: "demo" | "upload_csv"; file_name: string | null;
  status: "pending_review" | "loading" | "ready" | "failed" | "deleting";
  status_reason: string | null;            // user-safe failure reason
  version: number; total_rows: number | null; size_bytes: number | null;
  table_count: number; created_at: string; updated_at: string;
};
type DatasetDetail = DatasetSummary & { tables: TableOut[] };
type TableOut = { id: string; table_name: string; display_name: string; description: string | null;
  row_count: number; primary_key: string[]; columns: ColumnOut[] };
type ColumnType = "integer" | "bigint" | "numeric" | "boolean" | "date" | "timestamptz" | "text";
type ColumnOut = { id: string; column_name: string; display_name: string; ordinal: number;
  data_type: ColumnType; inferred_type: ColumnType | null; is_nullable: boolean; is_primary_key: boolean;
  semantic_role: "identifier" | "measure" | "dimension" | "time" | "currency" | null;
  description: string | null; is_sensitive: boolean;
  profile: { null_pct?: number; distinct_count?: number; min?: string; max?: string;
             top_values?: { value: string; count: number }[]; examples?: string[] } };  // value fields absent when sensitive

type UploadReview = {
  dataset: DatasetSummary; row_count: number;        // rows that will load
  rejected_count: number; rejected_samples: { line: number; reason: string }[];  // ≤ 20 shown
  columns: { name: string; display_name: string; inferred_type: ColumnType;
             missing_count: number; sample_values: string[] }[];
  issues: { severity: "error" | "warning"; code: string; message: string;
            column: string | null; line: number | null }[];
};

type PreviewResponse = { table: string; columns: { name: string; data_type: ColumnType; is_sensitive: boolean }[];
  rows: unknown[][];          // JSON-safe: numerics → number (or string if ≥ 1e15), dates → ISO strings
  limit: number; offset: number; has_more: boolean;
  masked_columns: string[];   // values shown as "«redacted»"
  exec_ms: number };

type SchemaCatalog = { dataset_id: string; dataset_name: string; dataset_version: number;
  level: "summary" | "full";
  tables: TableSchema[] | { name: string; description: string | null; row_count: number; column_count: number }[];
  relationships: { from_table: string; from_column: string; to_table: string; to_column: string;
                   origin: "declared" | "inferred" }[] };
type TableSchema = { name: string; description: string | null; row_count: number; primary_key: string[];
  foreign_keys: { column: string; references_table: string; references_column: string }[];
  columns: { name: string; display_name: string; data_type: ColumnType; nullable: boolean;
    is_primary_key: boolean; semantic_role: string | null; description: string | null;
    is_sensitive: boolean; null_pct: number | null; distinct_count: number | null;
    min: string | null; max: string | null;      // null when sensitive
    sample_values: string[];                     // ≤ 10; [] when sensitive or include_samples=false
    samples_redacted: boolean }[] };

type ConnectionOut = { id: string; name: string; kind: "internal_warehouse" | "postgres_external";
  status: "active" | "disabled" | "error"; created_at: string };    // never host, user or secret
```

CSV validation codes (in `issues[]` or `error.details.issues[]`):
- Errors: `EMPTY_FILE`, `BINARY_FILE`, `ENCODING`, `NO_HEADER`, `BLANK_COLUMN_NAME`, `DUPLICATE_COLUMN` (exact or after normalisation), `TOO_MANY_COLUMNS`, `TOO_MANY_ROWS`, `NO_ROWS`, `CELL_TOO_LARGE`, `MALFORMED_CSV` (unbalanced quotes, or > 5 % ragged rows).
- Warnings: `EMPTY_COLUMN`, `HIGH_MISSING` (> 50 % missing), `ROWS_REJECTED` (≤ 5 % ragged rows, skipped).

Values treated as missing: empty, `NA`, `N/A`, `NULL`, `None`, `NaN`, `-`, `#N/A` (case-insensitive, trimmed).

Readiness (`GET /readyz`) now reports `database`, `ingest_database`, `executor_database` and `llm_config`. It is `ready` only when all four are `ok`.

## 4. Conversations & analysis sessions (as built)

| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| GET | `/conversations` | `?dataset_id=&limit=&cursor=` | `200 Page<ConversationSummary>` (most recently active first) | 422 |
| POST | `/conversations` | `{dataset_id, title?}` | `201 ConversationDetail` | 404 (dataset not yours), 409 `DATASET_NOT_READY` |
| GET | `/conversations/{id}` | — | `200 ConversationDetail` (messages + sessions) | 404 |
| PATCH | `/conversations/{id}` | `{title}` | `200 ConversationDetail` | 404, 422 |
| DELETE | `/conversations/{id}` | — | `204` (messages and sessions cascade) | 404 |
| POST | `/conversations/{id}/sessions` | `{question}` (1–2000 chars, trimmed) | `202 SessionAccepted` | 404, 409 `DATASET_NOT_READY`, 422 `EMPTY_QUESTION`, 429 |
| GET | `/analysis-sessions/{id}` | — | `200 SessionDetail` | 404 |
| POST | `/analysis-sessions/{id}/cancel` | — | `200 SessionDetail` (idempotent; a running agent stops at its next node) | 404, 409 `SESSION_NOT_CANCELLABLE` |
| GET | `/analysis-sessions/{id}/trace` | — | `200 NodeRun[]` in execution order (written live) | 404 |

```ts
type ConversationSummary = { id: string; dataset_id: string; title: string; created_at: string; updated_at: string };
type ConversationDetail = ConversationSummary & { messages: Message[]; sessions: SessionSummary[] };
type Message = { id: string; role: "user" | "assistant" | "system"; content: string;
  analysis_session_id: string | null; created_at: string };
type SessionStatus = "queued" | "running" | "awaiting_input" | "succeeded" | "partial" | "failed" | "cancelled";
type SessionSummary = { id: string; conversation_id: string; dataset_id: string; question: string;
  status: SessionStatus; duration_ms: number | null; created_at: string };
type SessionDetail = SessionSummary & { dataset_version: number; termination_reason: string | null;
  understanding: object | null; plan: object | null; final_summary: string | null;
  error_code: string | null; error_message: string | null; llm_calls: number; sql_executions: number;
  tokens_in: number; tokens_out: number; started_at: string | null; finished_at: string | null;
  llm_provider: string | null; llm_model: string | null; result: RunResult | null };
type SessionAccepted = { session: SessionSummary; agent_available: boolean; message: string };
type NodeRun = { seq: number; node: string; status: "succeeded" | "failed" | "degraded";
  started_at: string; duration_ms: number; summary: object; tool_calls: object[];
  llm_calls: object[]; error: string | null };
type RunResult = {
  response: { status: "answered" | "partial" | "clarification_needed" | "out_of_scope" | "failed";
    summary: string; key_findings: Insight[]; caveats: string[]; assumptions: string[];
    clarification_question: string | null; clarification_options: string[];
    follow_up_questions: string[];   // ≤ 3 suggested next questions; any whose numbers aren't grounded in facts/rows are dropped (Phase 7)
    summary_source: "model" | "template" };
  steps: { step_id: string; purpose: string; expected_output: string; depends_on: string[];
    status: "succeeded" | "failed" | "skipped" | "pending"; sql: string | null; explanation: string | null;
    attempts: object[]; columns: { name: string; type: string }[]; row_count: number; truncated: boolean;
    rows: unknown[][]; notes: string[]; failure_explanation: string | null }[];
  facts: { fact_id: string; step_id: string; kind: string; description: string; value: unknown;
    unit: string | null; inputs: object }[];
  charts: (ChartSpec & { data: unknown[][]; columns: string[] })[];
  // ChartSpec = { chart_type: "bar" | "grouped_bar" | "horizontal_bar" | "line" | "area" | "scatter"
  //   | "pie" | "donut" | "histogram" | "kpi" | "table"; step_id: string; x: string | null; y: string[];
  //   series: string | null; title: string; subtitle: string | null; value_format: "number" | "integer"
  //   | "currency" | "percent"; fallback_reason: string | null }  — validated against the step's real
  //   columns/rows; an invalid spec falls back to "table" with the reason recorded (Phase 7 added
  //   horizontal_bar, pie/donut, scatter as first-class, histogram, and the fallback contract).
  verification: { round: number; metrics_check: string; time_period_check: string;
    verified_insights: number; rejected_insights: number; removed: object[]; uncertainty: string[] } | null;
  schema_tables: string[]; budget: object; errors: string[]; model: { provider: string; name: string } };
```

**The agent (Phase 5).** Asking a question stores a user message and a `queued` session.
- **With a model configured**, the API starts the LangGraph agent in the background and returns `agent_available: true`. The session moves `queued → running →` `succeeded` | `partial` | `awaiting_input` (a clarification question; the next message answers it and resumes the original question) | `failed` | `cancelled`.
- **With `LLM_PROVIDER=mock`** no model exists: the session stays `queued`, with `agent_available: false` and a message saying so. Nothing is invented.

Poll `GET /analysis-sessions/{id}` (every 1–2 s) for the outcome and `…/trace` for node-by-node progress. On completion the assistant's summary is added to the conversation, and every SQL attempt appears in `GET /history/queries` (`origin = "agent"`). Runs left `running` by a server restart become `failed` with `error_code = "INTERRUPTED"`. If the model becomes unavailable, the run stops with `termination_reason = "llm_unavailable"` and `error_code` set to `LLM_QUOTA_EXCEEDED`, `LLM_MODEL_NOT_FREE`, `LLM_RATE_LIMITED`, `LLM_AUTH_FAILED` or `LLM_MODEL_NOT_FOUND`. A run started after the daily cap is reached ends `LLM_DAILY_LIMIT_REACHED` without calling the model. The first question becomes the conversation's title if it still has the default one. Workflow details: AGENT_WORKFLOW.md.

**Still planned:** `GET /analysis-sessions/{id}/events` (SSE, §5, Phase 8), rerun, and paged query results.

## 5. Run event stream (SSE)

`GET /runs/{id}/events` · `Content-Type: text/event-stream` · heartbeat comment every 15 s.

Wire format:
```
id: 17
event: sql.validated
data: {"run_id":"...","seq":17,"ts":"2026-11-11T13:10:02.114Z","node":"validate_sql","payload":{...}}
```

| Event | Payload |
|---|---|
| `run.started` | `{question, dataset_id}` |
| `node.started` | `{node, plan_step_id?, attempt?}` |
| `node.completed` | `{node, latency_ms, output_summary}` (summary shape per node, e.g. `{intent, assumptions}` for understand_query) |
| `node.failed` | `{node, error_class, message, will_retry: bool}` |
| `tool.called` / `tool.completed` | `{tool, invoked_by, args_summary}` / `{tool, latency_ms, result_summary}` |
| `llm.called` | `{node, model, prompt_version, input_tokens, output_tokens, latency_ms}` |
| `sql.generated` | `{sql_query_id, plan_step_id, attempt, sql, explanation}` |
| `sql.validated` | `{sql_query_id, normalized_sql, explain_cost}` |
| `sql.rejected` | `{sql_query_id, violations: [{code, message}]}` |
| `sql.executed` | `{sql_query_id, row_count, truncated, exec_ms, columns, preview_rows (≤20)}` |
| `sql.failed` | `{sql_query_id, error_code, message}` |
| `step.completed` / `step.failed` | `{plan_step_id, notes}` |
| `facts.computed` | `{facts: ComputedFact[]}` |
| `chart.generated` | `{visualization_id, spec}` |
| `insights.generated` | `{count, round}` |
| `insights.verified` | `{verified: Insight[], rejected: [{insight_id, reason}]}` |
| `run.awaiting_input` | `{clarification_question, options}` |
| `run.resumed` | `{answer}` |
| `run.completed` | `{status: "succeeded" | "partial", report_id, duration_ms}` |
| `run.failed` | `{error_code, message}` |
| `run.cancelled` | `{}` |

The stream closes after a terminal event. A client connecting after completion gets a full replay followed by the terminal event.

## 6. History (as built)

| Method | Path | Query | Response |
|---|---|---|---|
| GET | `/history/sessions` | `status`, `dataset_id`, `q` (case-insensitive substring of the question; `%` and `_` are literal), `limit`, `cursor` | `Page<SessionSummary>` newest first |
| GET | `/history/queries` | `dataset_id`, `analysis_session_id`, `origin` (`agent`/`preview`/`widget_refresh`/`rerun`), `exec_status`, `limit`, `cursor` | `Page<QueryHistoryItem>` newest first |

```ts
type QueryHistoryItem = { id: string; dataset_id: string; dataset_name: string; analysis_session_id: string | null;
  origin: "agent" | "preview" | "widget_refresh" | "rerun"; attempt: number; executed_sql: string | null;
  guard_status: "accepted" | "rejected" | "not_applicable"; guard_violations: { code: string; message: string }[];
  exec_status: "not_run" | "ok" | "error" | "timeout" | "cancelled"; error_code: string | null;
  error_message: string | null; row_count: number | null; truncated: boolean; exec_ms: number | null; created_at: string };
```
Today the query history holds table previews. Agent SQL will be recorded in the same table.

## 7. Reports (as built)

| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| GET | `/reports` | `?limit=&cursor=` | `200 Page<ReportSummary>` | 422 |
| POST | `/reports` | `{analysis_session_id, title?}` | `201 ReportDetail` | 404, 409 `SESSION_NOT_FINISHED` (only `succeeded` / `partial`) |
| GET | `/reports/{id}` | — | `200 ReportDetail` | 404 |
| PATCH | `/reports/{id}` | `{title?, summary?}` | `200 ReportDetail` (a changed summary sets `summary_edited_by_user`) | 404, 422 |
| DELETE | `/reports/{id}` | — | `204` | 404 |
| GET | `/reports/{id}/export.md` | — | `200 text/markdown` attachment: title, question, dataset, summary, methodology (SQL) | 404 |

```ts
type ReportSummary = { id: string; title: string; analysis_session_id: string | null; dataset_id: string | null;
  created_at: string; updated_at: string };
type ReportDetail = ReportSummary & { summary: string; summary_edited_by_user: boolean;
  content: { question: string; status: string; dataset: { name: string | null; version: number };
    understanding: object | null; plan: object | null; final_summary: string | null;
    queries: { sql: string; row_count: number | null; truncated: boolean }[]; finished_at: string | null } };
```
`content` is an immutable snapshot taken when the report is saved. Charts and insights join it in the agent phases. Reports outlive their session and dataset (`SET NULL`).

## 8. Dashboard

| Method | Path | Description |
|---|---|---|
| GET | `/dashboard?dataset_id=` | `{widgets: Widget[], stats: {datasets, runs_30d, reports}}` |
| POST | `/dashboard/widgets` | `{visualization_id | sql_query_id, kind, title}` → `201 Widget` |
| PATCH | `/dashboard/widgets/{id}` | `{title?, position?}` |
| PUT | `/dashboard/layout` | `{positions: [{id, x, y, w, h}]}` (batch reorder) |
| POST | `/dashboard/widgets/{id}/refresh` | `200 {widget, result}` · `422 GUARD_REJECTED` if the schema changed |
| DELETE | `/dashboard/widgets/{id}` | `204` |

## 9. Settings & usage

| Method | Path | Description |
|---|---|---|
| GET / PATCH | `/settings` | `{clarification_mode, default_row_limit, auto_charts, timezone}` |
| PATCH | `/settings/profile` | `{full_name}` |
| POST | `/settings/password` | `{current_password, new_password}` → `204` (revokes other sessions) |
| GET | `/usage` | `{today: {runs, tokens}, month: {runs, tokens}, limits: {runs_per_day, tokens_per_day}}` |
| DELETE | `/account` | `{password}` → `202` (async full deletion) |

## 10. Operational (as built)

| Method | Path | Description |
|---|---|---|
| GET | `/healthz` | Liveness: `{status: "ok", service, version, environment, timestamp}` |
| GET | `/readyz` | `200 ready` only when all five checks are `ok`: `database`, `ingest_database`, `executor_database`, `migrations` (the database is at this build's Alembic head), `llm_config`. Otherwise `503 not_ready` with per-check detail. No hosts or secrets are ever included |

Database failures on any other route return `503 DATABASE_UNAVAILABLE` with a generic message. The driver error, host, user and SQL are logged with the request id, never returned.

## 11. Rate limits (as built: in-process, one API instance)
| Scope | Limit | Setting |
|---|---|---|
| `POST /auth/login` | 5 / min per IP + email, 20 / min per IP | `LOGIN_ATTEMPTS_PER_MINUTE` |
| `POST /auth/register` | 10 / hour per IP | `REGISTRATIONS_PER_HOUR` |
| `POST /datasets/uploads` | 20 / hour per user | `UPLOADS_PER_HOUR` |
| `POST /conversations/{id}/sessions` | 30 / hour per user (each run spends model tokens) | `ANALYSES_PER_HOUR` |
| Model calls per day (all users) | 200 since midnight Pacific → `429 DAILY_BUDGET_EXCEEDED` with `Retry-After` until the reset | `LLM_DAILY_REQUEST_LIMIT` |
| Model requests per minute | paced client-side (requests wait, they're not refused) | `LLM_REQUESTS_PER_MINUTE` |
| Per run | ≤ 30 model calls, ≤ 14 SQL executions, 180 s, ≤ 5,000 result rows | `AGENT_MAX_LLM_CALLS`, `AGENT_MAX_SQL_EXECUTIONS`, `AGENT_DEADLINE_SECONDS`, `AGENT_MAX_RESULT_ROWS` |
| General API | planned (D20) | — |

Over the limit → `429 RATE_LIMITED` with a `Retry-After` header (exposed through CORS) and `details.retry_after_seconds`.

## 12. Versioning
The path version is `/api/v1`. Additive changes are non-breaking. A breaking change means `/api/v2`. SSE event types are additive; clients must ignore unknown event types.
