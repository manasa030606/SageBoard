# Sageboard API

FastAPI service that will host the agentic analysis runtime.

- **Phase 1**: foundation (config, logging, error envelope, CORS, health, Alembic).
- **Phase 3**: the database and data-ingestion layer: application tables, the synthetic e-commerce demo dataset, CSV upload with validation, the schema catalog, and read-only previews.
- **Phase 4**: the full REST API with real accounts: sign-up/sign-in, user-level ownership on every route, conversations, analysis sessions (stored, not yet executed), history and reports.

There are no AI agents yet (they come in a later phase).

## Setup

```bash
cd apps/api
uv sync                      # creates .venv and installs locked dependencies (incl. dev tools)
cp .env.example .env         # then edit values — four database URLs, one per role, and JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste the output into JWT_SECRET
```

The database roles and the `sageboard` database are created once, from the repository root:

```bash
bash infra/postgres/setup-local.sh          # native PostgreSQL (Homebrew / Postgres.app); no Docker
```

## Run

```bash
uv run alembic upgrade head                 # migrations (owner role, MIGRATION_DATABASE_URL)
uv run python -m app.seed                   # optional: demo user + dataset for AUTH_MODE=demo
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Seed options: `--scale small|standard` (default standard, ≈105k rows, ~2 s), `--replace` (drop and rebuild), `--csv-out DIR` (also write the demo tables as CSV files, which are handy for trying the upload flow).

Sign up at http://localhost:3000/register, then use **Load sample dataset** on the Data page: each account gets its own copy.

| Endpoint group (`/api/v1`) | Routes |
|---|---|
| Health | `GET /healthz`, `GET /readyz` (app, ingest and executor connections, migration head, LLM config) |
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me` |
| Datasets | `GET /datasets`, `POST /datasets/uploads` → `POST /datasets/{id}/finalize`, `POST /datasets/demo`, `GET/PATCH/DELETE /datasets/{id}`, `GET /datasets/{id}/schema`, `GET /datasets/{id}/jobs`, `GET /datasets/{id}/tables/{table}/preview`, `PATCH /datasets/{id}/tables/{tableId}`, `PATCH /datasets/{id}/columns/{columnId}` |
| Connections | `GET /connections` (never credentials) |
| Conversations | `GET/POST /conversations`, `GET/PATCH/DELETE /conversations/{id}`, `POST /conversations/{id}/sessions` |
| Analysis sessions | `GET /analysis-sessions/{id}`, `POST /analysis-sessions/{id}/cancel` |
| History | `GET /history/sessions`, `GET /history/queries` |
| Reports | `GET/POST /reports`, `GET/PATCH/DELETE /reports/{id}`, `GET /reports/{id}/export.md` |
| Docs | `GET /docs` (Swagger UI; disabled when `ENV=production`), `GET /openapi.json` |

Full contract: [docs/API_SPECIFICATION.md §3](../../docs/API_SPECIFICATION.md).

Quick try with curl (the CSRF token comes back in the sign-up response):

```bash
curl -s -c jar -H 'content-type: application/json' localhost:8000/api/v1/auth/register \
     -d '{"email":"me@example.com","password":"correct horse battery staple","full_name":"Me"}'
CSRF=$(grep sb_csrf jar | awk '{print $7}')
curl -s -b jar -c jar -X POST -H "X-CSRF-Token: $CSRF" localhost:8000/api/v1/datasets/demo
curl -s -b jar localhost:8000/api/v1/datasets
```

## Configuration

All settings are environment variables (or `.env`), validated at startup by `app/core/config.py`. The service won't start with an invalid configuration.

| Variable | Default | Notes |
|---|---|---|
| `ENV` | `development` | `development`, `test` or `production` |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated explicit origins; `*` is rejected; production requires `https://` |
| `DATABASE_URL` | unset | `sageboard_app`: application metadata (schema `app`) only |
| `MIGRATION_DATABASE_URL` | unset | `sageboard_owner`: Alembic only; on Neon use the **direct** endpoint |
| `INGEST_DATABASE_URL` | unset | `sageboard_ingest`: creates dataset schemas and reader roles, loads data |
| `EXECUTOR_DATABASE_URL` | unset | `sageboard_executor`: read-only queries, always under a dataset's reader role |
| `EXECUTOR_MAX_PLAN_COST` | `5000000` | Refuse agent queries whose EXPLAIN plan cost exceeds this (cost units; 0 = off). One "aggregate earlier" retry is allowed |
| `EXECUTOR_STATEMENT_TIMEOUT_MS` | `10000` | Per-query timeout for the executor |
| `UPLOAD_MAX_BYTES` / `_ROWS` / `_COLUMNS` | 25 MB / 1,000,000 / 200 | Upload limits |
| `UPLOAD_DIR`, `UPLOAD_TTL_MINUTES` | system temp, `60` | Private (0700) staging dir; unreviewed uploads are swept |
| `PREVIEW_MAX_ROWS` | `100` | Hard cap on preview page size |
| `AUTH_MODE` | `session` | `session` = real accounts. `demo` = every request is the seeded demo user (local only; **refused in production**) |
| `JWT_SECRET` | unset | **Required** in session mode, ≥ 32 bytes. Signs access tokens; rotating it signs everyone out |
| `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS` | `15`, `14` | Session lifetimes |
| `COOKIE_SAMESITE`, `COOKIE_SECURE`, `COOKIE_DOMAIN` | `lax`, auto, unset | Secure is automatic in production; cross-site deployments need `none` |
| `LOGIN_ATTEMPTS_PER_MINUTE`, `REGISTRATIONS_PER_HOUR`, `UPLOADS_PER_HOUR` | `5`, `10`, `20` | In-process rate limits |
| `DEMO_DATASET_SCALE`, `DEMO_USER_EMAIL` | `standard`, `demo@sageboard.local` | Sample dataset size; demo-mode user |
| `LLM_PROVIDER` | `mock` | `google` (Gemini, free tier via AI Studio; `gemini` also accepted), `anthropic`, `openai` or `mock`. **`mock` = no model**: questions stay queued (nothing is invented); refused in production |
| `LLM_MODEL` + one of `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | unset | Required for a real provider, e.g. `gemini-3.8-flash`. `GEMINI_API_KEY` is accepted as an alias of `GOOGLE_API_KEY` |
| `LLM_REQUESTS_PER_MINUTE` | `10` | Client-side pacing shared by all runs (keep ≤ your free-tier RPM). `0` = off |
| `LLM_DAILY_REQUEST_LIMIT` | `200` | No new analyses after this many model calls since midnight Pacific (keep ≤ your free-tier RPD). `0` = off |
| `LLM_BASE_URL`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_SEND_TEMPERATURE` | provider URL, `60`, `8192`, `true` | A cut-off reply is retried once with double the token budget. Set `LLM_SEND_TEMPERATURE=false` for models that reject a temperature |
| `LLM_REASONING_EFFORT` | unset | Gemini/OpenAI: `none`/`minimal`/`low`/`medium`/`high`. `low` makes reasoning models faster and lighter on quota |
| `AGENT_MAX_LLM_CALLS`, `AGENT_MAX_SQL_EXECUTIONS`, `AGENT_DEADLINE_SECONDS`, `AGENT_MAX_RESULT_ROWS` | `30`, `14`, `180`, `5000` | Per-question budgets |
| `ANALYSES_PER_HOUR` | `30` | Questions per user per hour |
| `LOG_LEVEL`, `LOG_JSON` | `INFO`, `true` | Use `LOG_JSON=false` locally for readable logs |

## Code layout

```
app/
├── main.py              create_app(): middleware, CORS, error handlers, lifespan (opens all pools)
├── core/                config · logging (secret redaction) · errors · middleware
├── api/deps.py          dependencies: settings, databases, session, current user, CSRF, rate limits, services
├── api/pagination.py    keyset cursors
├── api/v1/              one router per resource (thin: parse → service → schema): health, auth,
│                        datasets, connections, conversations, history, reports
├── auth/                passwords (argon2id) · tokens (JWT, refresh, CSRF) · cookies · ratelimit
├── schemas/             Pydantic request/response models (the public contract)
├── services/            auth · datasets · analysis (conversations, sessions) · history · reports
│                        · catalog · schema_catalog · connections · audit · health
├── db/                  base (UUIDv7, naming convention) · models/ · engines (4 roles) · identifiers
├── ingestion/           csv_validation · types (inference + parsing) · identifiers (normalisation)
│                        · semantics (sensitivity, roles) · uploads (safe storage) · warehouse (DDL, COPY, inspection)
├── agent/               the LangGraph analysis workflow (docs/AGENT_WORKFLOW.md)
│   ├── graph.py         StateGraph assembly: 15 nodes, explicit + conditional edges
│   ├── state.py         typed AgentState and every structured output
│   ├── routing.py       routers (bounded retries, global stop → final response)
│   ├── runtime.py       traced_node wrapper: status, duration, tool/LLM calls, contained failures
│   ├── nodes/           understanding · schema · planning · sql · recovery · analysis
│   │                    · visualization · insights · verification · response
│   ├── tools/           sql_guard (SQLGlot) · executor · schema · errors · analysis · charts · grounding
│   ├── llm/             StructuredLLM (validate + re-ask) · HTTP adapters · factory
│   ├── prompts/         versioned prompt files <node>.v<N>.md
│   └── runner.py        AgentRunner (load → run → persist) · RunManager (background tasks)
├── execution/readonly.py  the only path that runs SQL against dataset data
└── seed/                ecommerce (deterministic generator) · demo (seed + CLI)
migrations/              Alembic (schema `app` only): 0001 baseline · 0002 app tables · 0003 FK fix · 0004 auth · 0005 agent trace
scripts/schema_reference.py   regenerates the table reference in docs/DATABASE_DESIGN.md
scripts/ask.py           ask the agent from the terminal and print its trace (real model only)
scripts/check_llm.py     test the configured key/model with one request (--list: Google models)
tests/                   unit tests · tests/integration/ (real PostgreSQL)
```

## The analysis agent

### Free setup: Google Gemini (Google AI Studio)

1. Open [Google AI Studio](https://aistudio.google.com), choose **Get API key**, and create a key in a Google Cloud project with **no billing account linked**. Without billing, Google can't charge: requests over the free quota are refused (429), not billed. Don't enable billing on that project.
2. In `apps/api/.env` (never committed; the key stays on the server and is never sent to the browser):

   ```bash
   LLM_PROVIDER=google
   LLM_MODEL=gemini-3.8-flash
   GOOGLE_API_KEY=<your AI Studio key>
   AGENT_DEADLINE_SECONDS=420        # free-tier pacing makes runs slower
   LLM_REQUESTS_PER_MINUTE=10        # ≤ your model's free-tier RPM (AI Studio → Usage)
   LLM_DAILY_REQUEST_LIMIT=200       # ≤ your model's free-tier RPD
   ```
3. Check the key and model with **one** request: `uv run python scripts/check_llm.py`
   (`--list` shows the models your key can call). If the model has no free-tier quota, it reports `LLM_MODEL_NOT_FREE`; pick another Flash model.

How free-tier limits are handled:
- **Pacing:** requests are spaced to `LLM_REQUESTS_PER_MINUTE`.
- **Per-minute 429:** Sageboard waits the `retryDelay` Google returns (≤ 65 s, ≤ 3 times).
- **Daily quota used up** (`LLM_QUOTA_EXCEEDED`), **model not on the free tier** (`LLM_MODEL_NOT_FREE`) or a **rejected key** stops the run immediately, with that reason in the answer and in `error_code`. Verified findings are kept.
- **Daily cap:** `LLM_DAILY_REQUEST_LIMIT` refuses new analyses (`429 DAILY_BUDGET_EXCEEDED`) before Google's quota runs out.
- **No automatic paid fallback:** Sageboard never switches provider, model or tier on its own.

Privacy: Google may use prompts and responses sent on the free tier to improve its products. Sageboard never sends sensitive columns' values, but use the sample dataset or non-sensitive data on the free tier.

### Paid providers

```bash
LLM_PROVIDER=anthropic          # or openai
LLM_MODEL=<model id from your provider's docs>
ANTHROPIC_API_KEY=<your key>    # only the key for the provider you chose
```

asking a question (`POST /api/v1/conversations/{id}/sessions`) starts the agent in the background. Follow it with `GET /api/v1/analysis-sessions/{id}` (status and `result`) and `GET /api/v1/analysis-sessions/{id}/trace` (every node: status, duration, tool and model calls). From the terminal:

```bash
uv run python scripts/ask.py --email you@example.com "Why did revenue decrease last month?"
```

The account needs a ready dataset: add the sample dataset on the Data sources page first.

## Quality

```bash
uv run ruff check .                  # lint (incl. bandit security rules)
uv run ruff format --check .         # formatting
uv run mypy                          # strict type checking (app, tests, scripts)
uv run pytest -m "not integration"   # unit tests, no database needed
```

### Integration tests (real PostgreSQL)

They run against a **separate** database, because the migration test downgrades it to empty. They connect as the real roles and assert PostgreSQL's own permission errors.

```bash
bash ../../infra/postgres/setup-local.sh --db sageboard_test     # once, from apps/api
source .env.test                                                 # copy from .env.test.example first
MIGRATION_DATABASE_URL="$SAGEBOARD_TEST_MIGRATION_DATABASE_URL" uv run alembic upgrade head
uv run pytest
```

Without the four `SAGEBOARD_TEST_*` variables the integration tests are **skipped**, not passed, and pytest reports them as skipped. CI sets them and fails if anything is skipped.
