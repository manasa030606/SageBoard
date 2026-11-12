# Sageboard — System Architecture

| Field | Value |
|---|---|
| Document | SYSTEM_ARCHITECTURE v0.2 |
| Status | Approved 2026-11-12 (v0.2). Decisions: see DECISION_LOG.md |
| Depends on | PRD.md |

---

## 1. Architecture at a glance

```
┌──────────────────────────── Browser ────────────────────────────┐
│  Next.js app (Vercel)                                           │
│  • App Router pages  • Design system  • Recharts  • SSE client  │
└───────────────┬───────────────────────────────▲─────────────────┘
                │ HTTPS REST (JSON)             │ SSE (run events)
                ▼                               │
┌──────────────────────── FastAPI service (Render/Railway) ───────┐
│  API layer        routes → schemas (Pydantic) → services        │
│  ─────────────────────────────────────────────────────────────  │
│  Services         auth · datasets · ingestion · runs · reports  │
│                   dashboards · history · settings               │
│  ─────────────────────────────────────────────────────────────  │
│  Agent runtime    LangGraph StateGraph + checkpointer           │
│                   nodes/ · tools/ · prompts/ · llm/             │
│  ─────────────────────────────────────────────────────────────  │
│  Safety core      SQL Guard (SQLGlot) · Query Executor          │
│                   Analysis Engine (deterministic stats)         │
│                   Chart Spec Validator · Grounding Verifier     │
│  ─────────────────────────────────────────────────────────────  │
│  Event bus        in-process async pub/sub → SSE + DB persist   │
└──────┬───────────────────────────┬───────────────────┬──────────┘
       │ SQLAlchemy (rw, app role) │ asyncpg (ro, per- │ HTTPS
       ▼                           ▼ dataset role)     ▼
┌───────────── Managed PostgreSQL ─────────────┐   ┌───────────┐
│  schema `app`      metadata, traces, reports │   │ LLM API   │
│  schema `ds_<id>`  one per uploaded dataset  │   │ (adapter) │
│  schema `lg`       LangGraph checkpoints     │   └───────────┘
└──────────────────────────────────────────────┘
```

**Key idea (in simple terms):** the LLM is the *planner and writer*, never the *executor*. It proposes plans, SQL and wording. Deterministic Python code decides whether a proposal is safe and correct, runs it with restricted permissions, and computes the numbers. The LLM then explains numbers it was handed. It never produces them.

## 2. Components and responsibilities

### 2.1 Frontend — `apps/web` (Next.js, TypeScript, Tailwind, Recharts)

| Component | Responsibility |
|---|---|
| **App shell** | Sidebar nav, dataset switcher, user menu, toasts, command palette (⌘K). |
| **Design system** (`src/components/ui`) | Tokens (Tailwind theme), primitives: Button, Input, Select, Table, Tabs, Drawer, Dialog, Badge, Skeleton, EmptyState, ErrorState, Tooltip. Unstyled behaviour from Radix primitives, styled with our tokens (D-UI1). |
| **API client** (`src/lib/api`) | Typed client generated from the FastAPI OpenAPI schema (`openapi-typescript`) plus a thin fetch wrapper (cookies, error envelope → typed `ApiError`). |
| **Run stream client** (`src/lib/stream`) | Wraps `EventSource`; reconnects with `Last-Event-ID`; reduces events into a `RunViewModel` with a reducer that is pure and unit-tested. |
| **Server state** | TanStack Query for REST resources (caching, invalidation). The run stream feeds its own reducer, not the query cache. |
| **Charts** (`src/components/charts`) | `ChartRenderer` maps a validated `ChartSpec` → Recharts component. It only renders types in the spec enum, and every chart has a "View as table" toggle. |
| **Feature modules** (`src/features/*`) | analyst, datasets, history, reports, dashboard, settings. Each owns its components, hooks and route-level loading/error boundaries. |

Rendering strategy: marketing pages are static (SSG). App pages are client components behind an auth check in `middleware.ts` (cookie presence → otherwise redirect). The source of truth for auth is the backend's `/auth/me`.

### 2.2 Backend — `apps/api` (FastAPI, SQLAlchemy 2.x async, Pydantic v2)

| Layer | Responsibility |
|---|---|
| **Routes** (`app/api/v1/*`) | HTTP concerns only: parse, auth dependency, call service, map to response schema. |
| **Schemas** (`app/schemas/*`) | Pydantic request/response models. These are the public API contract; they are separate from the ORM models. |
| **Services** (`app/services/*`) | Business logic and transactions. Owner checks (`user_id`) are enforced here on every query. |
| **Repositories** (`app/db/repositories/*`) | SQLAlchemy queries against the `app` schema. |
| **Ingestion** (`app/ingestion/*`) | File parsing (stdlib `csv` / `openpyxl` read-only mode), type inference, identifier normalisation, `COPY` into `ds_<id>`, profiling. |
| **Agent** (`app/agent/*`) | LangGraph graph, state, nodes, tools, prompts, LLM adapter. See AGENT_WORKFLOW.md. |
| **SQL Guard** (`app/security/sql_guard/*`) | Pure function `validate(sql, catalog, policy) -> GuardResult`. No I/O, so it's easy to test exhaustively. |
| **Query Executor** (`app/execution/executor.py`) | The only code path that runs analytical SQL. Dataset role, read-only transaction, timeout, row cap, EXPLAIN cost gate. |
| **Analysis Engine** (`app/analysis/*`) | Deterministic statistics over result sets: totals, shares, period-over-period change, rank, top/bottom-N, outliers (IQR), correlation (Pearson, with n). Each output is a `ComputedFact` with an ID. |
| **Grounding Verifier** (`app/agent/verification/*`) | Extracts numeric claims from insight text and checks them against facts/result cells within tolerance. |
| **Run Manager** (`app/runs/manager.py`) | Starts graph executions as asyncio tasks, tracks cancellation, enforces the run budget, publishes events. |
| **Event Bus** (`app/runs/events.py`) | Per-run async pub/sub. Each event is persisted to `run_events` first, then fanned out to SSE subscribers. Replay comes from the DB. |
| **Core** (`app/core/*`) | Settings (pydantic-settings), logging (structlog JSON), security (password hashing argon2, JWT), rate limiting, error handlers. |

### 2.3 Data tier — PostgreSQL (managed)

| Schema | Owner role | Accessed by | Content |
|---|---|---|---|
| `app` | `sageboard_app` | SQLAlchemy (read-write) | Users, datasets metadata, conversations, runs, trace, reports, widgets |
| `ds_<dataset_uuid_hex>` | `sageboard_ingest` | Ingestion (write, once); Executor via `ds_<id>_reader` (SELECT only) | User dataset tables |
| `lg` | `sageboard_app` | LangGraph `AsyncPostgresSaver` | Graph checkpoints (enables pause/resume for clarification) |

Roles and grants are detailed in SECURITY_DESIGN.md §5.

### 2.4 External — LLM provider
- Accessed only through `app/agent/llm/client.py` (`LLMClient` protocol: `structured(prompt, schema: type[BaseModel]) -> BaseModel`, `with_tools(...)`).
- Provider implementations: `anthropic.py`, `openai.py`, `gemini.py`, `mock.py`, selected by `LLM_PROVIDER` with `LLM_MODEL` and one key per provider (D1 final, [ADR-0006](adr/0006-provider-agnostic-llm-layer.md)). Provider code is isolated from the LangGraph orchestration, so switching providers is a configuration change. The **mock** provider is allowed in development and tests, refused when `ENV=production` (settings validation, implemented in Phase 1), and every mock-produced run is labelled as such.
- Retries: exponential backoff on 429/5xx (max 3), per-call timeout 45 s, token usage recorded per call.

## 3. Primary data flows

### 3.1 Dataset ingestion
```
Browser ──multipart──▶ POST /datasets/uploads
  1. Stream to temp file; check size + extension + magic bytes
  2. Parse header + sample (first 5k rows) → infer types → normalise identifiers
  3. Persist dataset(status=pending_review) + inferred columns
◀── 201 {dataset, inferred_schema, warnings}
Browser (user reviews/overrides types) ──▶ POST /datasets/{id}/finalize
  4. Background task:
     CREATE SCHEMA ds_<id>; CREATE TABLE with final types
     COPY rows (bad rows → rejected_rows report, up to N samples)
     CREATE ROLE ds_<id>_reader; GRANT USAGE, SELECT
     ANALYZE; compute column profiles
     dataset.status = ready (or failed + reason)
  5. Temp file deleted
```

### 3.2 Analysis run (happy path)
```
POST /conversations/{cid}/runs {question}
 → RunService: create run(status=queued), check budget/rate limit
 → RunManager.start(run_id) → asyncio task: graph.ainvoke(state, config{thread_id=run_id})
◀ 202 {run_id, stream_url}

GET /runs/{id}/events  (SSE)
 ◀ run.started
 ◀ node.started understand_query ... node.completed {intent, assumptions}
 ◀ node.* retrieve_schema (tool.called get_table_schema ×n)
 ◀ node.* plan_analysis {plan}
 ◀ per step: sql.generated → sql.validated(ok) → sql.executed {row_count, preview}
 ◀ node.* analyze_results {facts}
 ◀ node.* generate_visualization {chart_spec}
 ◀ node.* generate_insights → verify_insights {verified, dropped}
 ◀ node.* compose_report
 ◀ run.completed {result_ref}
```
Every event is written to `run_events` before it's published, so a client that reconnects with `Last-Event-ID` gets a lossless replay.

### 3.3 Clarification (pause/resume)
`understand_query` returns `needs_clarification` → the graph raises a LangGraph `interrupt()` → run status becomes `awaiting_input` → SSE emits `run.awaiting_input {question, options}` → the user answers via `POST /runs/{id}/resume {answer}` → the graph resumes from its checkpoint.

### 3.4 Dashboard widget refresh
`POST /dashboard/widgets/{id}/refresh` → load stored `sql_text` + dataset → **SQL Guard re-validates against the current catalog** (the schema may have changed) → Executor → stored chart spec is re-validated against the new columns → response. No LLM involved.

## 4. Cross-cutting concerns

| Concern | Approach |
|---|---|
| **Errors** | Domain exceptions (`NotFound`, `Forbidden`, `ValidationFailed`, `BudgetExceeded`, `GuardRejected`, `UpstreamLLMError`) are mapped by one handler to the error envelope (API_SPECIFICATION §2.3). Stack traces never reach clients. |
| **Agent failure isolation** | A node exception is caught by a wrapper decorator and recorded as `node.failed` with an error class. The router then decides between retry, recover and terminate. A Python exception never kills the server task silently. |
| **Concurrency** | Max 2 concurrent runs per user and N per instance (semaphore). Further runs stay `queued` (D6). |
| **Idempotency** | `POST .../runs` accepts an `Idempotency-Key` header to avoid duplicate runs on a double click. |
| **Config** | 12-factor env vars, validated at startup (pydantic-settings). Missing secrets fail fast. |
| **Logging/trace** | structlog JSON with `request_id`, `run_id`, `node`. Optional LangSmith tracing via env (D17); the DB trace is always on. |
| **Migrations** | Alembic for the `app` schema. Dataset schemas are created dynamically by ingestion and are not part of Alembic. |
| **Time** | All timestamps are `timestamptz`, UTC. The frontend formats them in the user's timezone. |

## 5. Deployment topology

| Piece | Platform | Notes |
|---|---|---|
| Web | Vercel | `NEXT_PUBLIC_API_URL`. Preview deployments per PR. |
| API | Render Web Service (or Railway) | Dockerfile; `uvicorn --workers 1` with async (runs are in-process tasks — see D6 on scaling). Health check `/healthz`. |
| DB | **Neon PostgreSQL 16** (D5 final, [ADR-0002](adr/0002-database-topology-and-permissions.md)); local: native PostgreSQL 16 (Docker optional) | Roles are created through SQL by the Neon owner role. App runtime may use the **pooled** endpoint (PgBouncer, transaction mode, so we use only `SET LOCAL`, asyncpg statement cache off). Migrations, the LangGraph checkpointer and the executor use the **direct** endpoint. |
| Secrets | Platform env vars | `DATABASE_URL`, `DATABASE_URL_READONLY_ADMIN`, `JWT_SECRET`, `LLM_API_KEY`, `CORS_ORIGINS`. |

Cross-origin auth: web and API are on different domains, so the cookie is `SameSite=None; Secure; HttpOnly`, CORS uses an explicit origin allowlist with credentials, and CSRF is handled with a double-submit token (SECURITY_DESIGN §7). **Alternative (recommended if a custom domain is available):** serve the API at `api.<domain>` and the web app at `<domain>` with `SameSite=Lax`.

## 6. Monorepo structure

```
sageboard/
├── apps/
│   ├── web/                              # Next.js 15 (App Router) + TS + Tailwind
│   │   ├── src/
│   │   │   ├── app/
│   │   │   │   ├── (marketing)/page.tsx            # Landing
│   │   │   │   ├── (auth)/login, register/
│   │   │   │   └── app/
│   │   │   │       ├── layout.tsx                  # App shell
│   │   │   │       ├── dashboard/  analyst/[[...conversationId]]/
│   │   │   │       ├── data/[datasetId]/  history/  reports/[id]/  settings/
│   │   │   ├── components/ui/                      # Design-system primitives
│   │   │   ├── components/charts/                  # ChartRenderer + chart types
│   │   │   ├── features/{analyst,datasets,history,reports,dashboard,settings}/
│   │   │   ├── lib/api/  (generated types + client)
│   │   │   ├── lib/stream/ (SSE client + run reducer)
│   │   │   └── styles/tokens.css
│   │   ├── e2e/                                    # Playwright specs
│   │   ├── tailwind.config.ts  playwright.config.ts  next.config.ts
│   │   └── package.json
│   └── api/                              # FastAPI service
│       ├── app/
│       │   ├── main.py
│       │   ├── core/          (config.py, logging.py, security.py, errors.py, rate_limit.py)
│       │   ├── api/v1/        (auth.py, datasets.py, conversations.py, runs.py,
│       │   │                   history.py, reports.py, dashboard.py, settings.py, health.py)
│       │   ├── schemas/       (Pydantic API models)
│       │   ├── db/            (base.py, session.py, models/, repositories/)
│       │   ├── services/
│       │   ├── ingestion/     (parse.py, infer.py, identifiers.py, load.py, profile.py)
│       │   ├── security/sql_guard/ (guard.py, policy.py, rules/*.py, catalog.py)
│       │   ├── execution/     (executor.py, explain.py)
│       │   ├── analysis/      (facts.py, stats.py, timeseries.py)
│       │   ├── agent/
│       │   │   ├── graph.py   state.py   budget.py   routing.py
│       │   │   ├── nodes/     (one module per node)
│       │   │   ├── tools/     (schema_tools.py, sql_tools.py, analysis_tools.py)
│       │   │   ├── prompts/   (versioned .md templates + loader)
│       │   │   ├── llm/       (client.py, anthropic.py, openai.py, gemini.py, mock.py)
│       │   │   └── verification/ (claims.py, grounding.py)
│       │   └── runs/          (manager.py, events.py, tracing.py)
│       ├── migrations/        (Alembic)
│       ├── tests/
│       │   ├── unit/  integration/  agent/  security/  eval/
│       │   ├── fakes/         (FakeLLM — test-only)
│       │   └── conftest.py
│       ├── pyproject.toml  uv.lock  Dockerfile
├── packages/
│   └── eval-datasets/                   # Sample + evaluation datasets (CSV) + golden questions (YAML)
├── infra/
│   ├── docker-compose.yml               # Postgres 16 for local dev/test
│   └── postgres/init/001_roles.sql      # Base roles for local dev
├── docs/                                # These blueprint docs + ADRs (docs/adr/NNNN-*.md)
├── .github/workflows/                   # ci-api.yml, ci-web.yml, e2e.yml
├── Makefile                             # make dev / test / lint / gen-api-types
└── README.md
```

Tooling defaults (D13): **pnpm** for the web app, **uv** for Python, **ruff + mypy (strict on `app/security`, `app/agent`)**, **ESLint + Prettier + tsc --noEmit**, pre-commit hooks.

## 7. Dependency graph between components (build order)

```
core/config, logging ─▶ db models + Alembic ─▶ auth
                                  │
                                  ├─▶ ingestion ─▶ dataset catalog
                                  │                    │
                       SQL Guard (pure) ◀──────────────┤
                                  │                    │
                             Executor ◀────────────────┘
                                  │
             Analysis Engine (pure) ─▶ Grounding Verifier (pure)
                                  │
                    LLM adapter ─▶ Agent nodes ─▶ Graph ─▶ Run Manager ─▶ Event bus/SSE
                                                                     │
                                   Reports / Dashboard / History services
                                                                     │
                        Frontend: design system ─▶ shell ─▶ data ─▶ analyst ─▶ rest
```
The SQL Guard and Executor are built and tested **before** any LLM code exists. This is deliberate: the safety boundary shouldn't depend on agent behaviour.

## 8. Architecture Decision Records
Written in Phase 1 (`docs/adr/`), indexed in [DECISION_LOG.md](DECISION_LOG.md):
- ADR-0001 Monorepo and tooling (pnpm + uv)
- ADR-0002 Database topology and permission model (Neon, role-per-dataset, pooling)
- ADR-0003 SSE for run streaming
- ADR-0004 In-process run execution with a persisted event log
- ADR-0005 Structured outputs only; no execution of generated code
- ADR-0006 Provider-agnostic LLM layer with a mock provider
- ADR-0007 Schema retrieval before analysis planning
