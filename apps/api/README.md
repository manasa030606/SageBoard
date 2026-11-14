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
| `LLM_PROVIDER` | `mock` | `mock` is refused in production; adapters arrive with the agent phase |
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
├── execution/readonly.py  the only path that runs SQL against dataset data
└── seed/                ecommerce (deterministic generator) · demo (seed + CLI)
migrations/              Alembic (schema `app` only): 0001 baseline · 0002 app tables · 0003 FK fix · 0004 auth
scripts/schema_reference.py   regenerates the table reference in docs/DATABASE_DESIGN.md
tests/                   unit tests · tests/integration/ (real PostgreSQL)
```

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
