# Sageboard API

FastAPI service that will host the agentic analysis runtime. **Phase 1** provides the foundation: validated configuration, structured logging, the error envelope, request ids, secure CORS, the database engine, Alembic, and health endpoints.

## Setup

```bash
cd apps/api
uv sync                      # creates .venv and installs locked dependencies (incl. dev tools)
cp .env.example .env         # then edit values
```

`uv sync` creates the virtual environment in `apps/api/.venv`. Run tools through `uv run …`, or activate it with `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`).

## Run

```bash
uv run alembic upgrade head                                     # needs MIGRATION_DATABASE_URL
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/healthz` | Liveness: the process is up (always 200 while serving) |
| `GET /api/v1/readyz` | Readiness: required dependencies are usable. 200 `ready`, or 503 `not_ready` with per-check detail |
| `GET /api/v1/docs` | Swagger UI (disabled when `ENV=production`) |
| `GET /api/v1/openapi.json` | OpenAPI 3.1 schema |

## Configuration

All settings are environment variables (or `.env`), validated at startup by `app/core/config.py`. The service won't start with an invalid configuration.

| Variable | Default | Notes |
|---|---|---|
| `ENV` | `development` | `development`, `test` or `production` |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated explicit origins; `*` is rejected; production requires `https://` |
| `DATABASE_URL` | unset | `postgresql+asyncpg://sageboard_app:…` (app role). Unset ⇒ `/readyz` is 503 |
| `MIGRATION_DATABASE_URL` | unset | `postgresql+asyncpg://sageboard_owner:…`; on Neon use the **direct** endpoint |
| `LLM_PROVIDER` | `mock` | `mock`, `anthropic`, `openai` or `gemini`. `mock` is refused in production |
| `LLM_MODEL`, `*_API_KEY` | unset | Required for real providers (adapter arrives in Phase 5) |
| `LOG_LEVEL`, `LOG_JSON` | `INFO`, `true` | Use `LOG_JSON=false` locally for readable logs |

## Code layout

```
app/
├── main.py            create_app(): middleware, CORS, error handlers, lifespan, routers
├── core/              config · logging (with secret redaction) · errors · middleware
├── api/deps.py        FastAPI dependencies
├── api/v1/            route modules (thin: parse → call service → return schema)
├── schemas/           Pydantic request/response models (the public contract)
├── services/          business logic (route handlers contain none)
└── db/session.py      async engine for the application role
migrations/            Alembic (manages the `app` schema only)
tests/                 pytest
```

## Quality

```bash
uv run ruff check .            # lint (incl. bandit security rules)
uv run ruff format --check .   # formatting
uv run mypy                    # strict type checking
uv run pytest -m "not integration"   # unit tests, no database needed
```

### Integration tests (real PostgreSQL)

They connect as the real roles and assert PostgreSQL's own permission errors.

```bash
export SAGEBOARD_TEST_DATABASE_URL=postgresql+asyncpg://sageboard_app:<pw>@localhost:5432/sageboard
export SAGEBOARD_TEST_EXECUTOR_DATABASE_URL=postgresql+asyncpg://sageboard_executor:<pw>@localhost:5432/sageboard
uv run alembic upgrade head
uv run pytest
```

Without these variables the integration tests are **skipped**, not passed. pytest reports them as skipped.
