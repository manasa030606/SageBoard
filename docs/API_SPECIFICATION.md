# Sageboard — API Specification

| Field | Value |
|---|---|
| Document | API_SPECIFICATION v0.2 |
| Status | Approved 2026-11-12 (v0.2). Decisions: see DECISION_LOG.md |
| Base URL | `https://<api-host>/api/v1` |
| Format | JSON (UTF-8); `multipart/form-data` for uploads; `text/event-stream` for run events |
| Source of truth | FastAPI-generated OpenAPI 3.1 at `/api/v1/openapi.json`. The frontend types are generated from it. |

---

## 1. Conventions

### 1.1 Authentication
- Session cookie `sb_session` (JWT access token, 15 min, HttpOnly, Secure) plus `sb_refresh` (opaque, 14 days, rotated, path `/api/v1/auth/refresh`).
- State-changing requests (POST/PUT/PATCH/DELETE) must send `X-CSRF-Token` equal to the `sb_csrf` cookie (double-submit).
- Unauthenticated → `401 AUTH_REQUIRED`. Accessing another user's resource → `404 NOT_FOUND` (it doesn't leak existence).

### 1.2 Pagination
Cursor-based: `?limit=25&cursor=<opaque>` → `{ "items": [...], "next_cursor": "..." | null }`. Max `limit` is 100.

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

## 2. Auth

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/register` | `{email, password (≥10 chars), full_name}` | `201 {user}` + cookies |
| POST | `/auth/login` | `{email, password}` | `200 {user}` + cookies; `401 INVALID_CREDENTIALS` (same message whether the email exists or not) |
| POST | `/auth/refresh` | — (refresh cookie) | `204` + new cookies |
| POST | `/auth/logout` | — | `204` (revokes refresh token, clears cookies) |
| GET | `/auth/me` | — | `200 {user}` |

`User = {id, email, full_name, created_at}`

## 3. Datasets

| Method | Path | Description |
|---|---|---|
| GET | `/datasets` | List the user's datasets → `Page<DatasetSummary>` |
| POST | `/datasets/uploads` | multipart: `file`, `name`, `description?`, `sheet?` → `201 {dataset: Dataset(status=pending_review), inferred: InferredSchema, warnings: string[]}` |
| POST | `/datasets/{id}/finalize` | `{columns: [{table, column, data_type, display_name?}]}` overrides → `202 {dataset, job_id}` |
| GET | `/datasets/{id}` | `Dataset` with tables and columns (profiles included) |
| PATCH | `/datasets/{id}` | `{name?, description?}` |
| PATCH | `/datasets/{id}/tables/{tableId}` | `{description?}` |
| PATCH | `/datasets/{id}/columns/{columnId}` | `{description?, semantic_role?, is_sensitive?}` |
| GET | `/datasets/{id}/tables/{tableId}/preview?limit=50` | `{columns, rows}` — fixed parameterised query; no user SQL |
| GET | `/datasets/{id}/jobs/{jobId}` | `IngestionJob` |
| DELETE | `/datasets/{id}` | `202` → status `deleting`; cascades conversations/runs/widgets |

```ts
type Dataset = {
  id: string; name: string; description: string | null;
  source_type: "upload_csv" | "upload_xlsx" | "sample";
  status: "pending_review" | "loading" | "ready" | "failed" | "deleting";
  status_reason: string | null; version: number;
  total_rows: number | null; size_bytes: number | null;
  tables: DatasetTable[]; created_at: string; updated_at: string;
};
type DatasetTable = { id: string; table_name: string; display_name: string;
  description: string | null; row_count: number; columns: DatasetColumn[] };
type DatasetColumn = { id: string; column_name: string; display_name: string;
  data_type: "integer"|"bigint"|"numeric"|"boolean"|"date"|"timestamptz"|"text";
  inferred_type: string; description: string | null;
  semantic_role: "identifier"|"measure"|"dimension"|"time"|"currency"|null;
  is_sensitive: boolean;
  profile: { null_pct: number; distinct_count: number; min: string|null; max: string|null;
             top_values: { value: string; count: number }[] } | null };
```

## 4. Conversations & runs

| Method | Path | Description |
|---|---|---|
| GET | `/conversations?dataset_id=` | `Page<ConversationSummary>` |
| POST | `/conversations` | `{dataset_id, title?}` → `201 Conversation` |
| GET | `/conversations/{id}` | Conversation + ordered `RunSummary[]` |
| PATCH | `/conversations/{id}` | `{title}` |
| DELETE | `/conversations/{id}` | `204` |
| POST | `/conversations/{id}/runs` | `{question (1..2000 chars)}` → `202 {run: RunSummary, stream_url}` · `409 DATASET_NOT_READY` · `429` |
| GET | `/runs/{id}` | `RunDetail` (full, once finished; partial while running) |
| GET | `/runs/{id}/events` | **SSE** (see §5). Supports `Last-Event-ID`. |
| POST | `/runs/{id}/resume` | `{answer: string}` → `202`; `409 RUN_NOT_RESUMABLE` unless `awaiting_input` |
| POST | `/runs/{id}/cancel` | `202`; idempotent |
| POST | `/runs/{id}/rerun` | `{mode: "same_sql" | "reanalyze"}`. `same_sql` re-validates and executes the stored SQL (no LLM) → new run; `reanalyze` runs the full agent again with the same question. |
| GET | `/runs/{id}/trace` | `{steps: RunStep[], tool_calls: ToolCall[], llm_calls: LlmCall[], sql_queries: SqlQuery[]}` |
| GET | `/sql-queries/{id}/result?offset=0&limit=100` | Paged rows from the stored result |
| GET | `/sql-queries/{id}/result.csv` | CSV download (streams the stored result; formula-injection-safe, see SECURITY §8) |

```ts
type RunStatus = "queued"|"running"|"awaiting_input"|"succeeded"|"partial"|"failed"|"cancelled";
type RunSummary = { id: string; conversation_id: string; dataset_id: string; question: string;
  status: RunStatus; duration_ms: number | null; created_at: string };
type RunDetail = RunSummary & {
  understanding: QueryUnderstanding | null;
  plan: AnalysisPlan | null;
  steps: { step_id: string; purpose: string; status: "succeeded"|"failed"|"skipped"|"pending";
           final_sql_query_id: string | null; row_count: number; truncated: boolean; notes: string[] }[];
  visualizations: { id: string; sql_query_id: string; spec: ChartSpec }[];
  insights: Insight[];            // verified only; ?include_rejected=true for all
  final_summary: string | null;
  limitations: string[];
  termination_reason: string | null;
  error: { code: string; message: string } | null;
  usage: { llm_calls: number; sql_executions: number; tokens_in: number; tokens_out: number };
  report_id: string | null;
};
```
`QueryUnderstanding`, `AnalysisPlan`, `ChartSpec`, `Insight` and `EvidenceRef` mirror the Pydantic models in AGENT_WORKFLOW §3. They are exported through OpenAPI, so TypeScript and Python can't drift.

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

## 6. History

| Method | Path | Description |
|---|---|---|
| GET | `/history/runs?status=&dataset_id=&q=&from=&to=&cursor=&limit=` | `Page<RunSummary & {query_count, insight_count}>` |
| GET | `/history/queries?dataset_id=&guard_status=&exec_status=&cursor=` | `Page<SqlQuery>` (an SQL-level audit view) |

## 7. Reports

| Method | Path | Description |
|---|---|---|
| GET | `/reports` | `Page<ReportSummary>` |
| POST | `/reports` | `{run_id, title?}` → `201 Report`; `409` if the run isn't `succeeded`/`partial` |
| GET | `/reports/{id}` | `Report` |
| PATCH | `/reports/{id}` | `{title?, summary?}` (sets `summary_edited_by_user`) |
| GET | `/reports/{id}/export.md` | Markdown download |
| DELETE | `/reports/{id}` | `204` |

```ts
type Report = { id: string; title: string; summary: string; summary_edited_by_user: boolean;
  run_id: string | null; created_at: string; updated_at: string;
  content: { question: string; dataset: { name: string; version: number };
    sections: { heading: string; chart?: ChartSpec; table?: { columns: string[]; rows: unknown[][] };
                insights: Insight[] }[];
    limitations: string[]; methodology: { step_id: string; purpose: string; sql: string }[] } };
```

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

## 10. Operational

| Method | Path | Description |
|---|---|---|
| GET | `/healthz` | Liveness: `{status:"ok"}` |
| GET | `/readyz` | DB reachable, migrations at head, LLM key configured → `200` / `503` |

## 11. Rate limits (defaults; D20)
| Scope | Limit |
|---|---|
| `/auth/login` | 5 / min / IP + email; exponential lockout after 10 failures |
| Run creation | 10 / min / user, 100 runs / day / user, 2 concurrent |
| Uploads | 10 / hour / user |
| Everything else | 120 / min / user |

## 12. Versioning
The path version is `/api/v1`. Additive changes are non-breaking. A breaking change means `/api/v2`. SSE event types are additive; clients must ignore unknown event types.
