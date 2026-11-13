# Sageboard API

FastAPI service that will host the agentic analysis runtime.

- **Phase 1**: foundation (config, logging, error envelope, CORS, health, Alembic).
- **Phase 3**: the database and data-ingestion layer: application tables, the synthetic e-commerce demo dataset, CSV upload with validation, the schema catalog, and read-only previews.

There are no AI agents yet (they come in a later phase).

## Setup

```bash
cd apps/api
uv sync                      # creates .venv and installs locked dependencies (incl. dev tools)
cp .env.example .env         # then edit values — four database URLs, one per role
```

The database roles and the `sageboard` database are created once, from the repository root:

```bash
bash infra/postgres/setup-local.sh          # native PostgreSQL (Homebrew / Postgres.app); no Docker
```

## Run

```bash
uv run alembic upgrade head                 # migrations (owner role, MIGRATION_DATABASE_URL)
uv run python -m app.seed                   # demo user + “E-commerce demo” dataset (idempotent)
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Seed options: `--scale small|standard` (default standard, ≈105k rows, ~2 s), `--replace` (drop and rebuild), `--csv-out DIR` (also write the demo tables as CSV files, which are handy for trying the upload flow).

| Endpoint (`/api/v1`) | Purpose |
|---|---|
| `GET /healthz` · `GET /readyz` | Liveness · readiness (app, ingest and executor connections + LLM config) |
| `GET /datasets` | Your datasets |
| `POST /datasets/uploads` | Upload a CSV → validation report and inferred types (nothing loaded yet) |
| `POST /datasets/{id}/finalize` | Confirm or override column types → load into the warehouse |
| `GET /datasets/{id}` | Tables, columns, profiles |
| `GET /datasets/{id}/schema?level=summary\|full&include_samples=` | Schema catalog for SQL generation (privacy-controlled samples) |
| `GET /datasets/{id}/tables/{table}/preview?limit=&offset=&reveal_sensitive=` | First rows, via the read-only executor; sensitive columns masked |
| `PATCH /datasets/{id}/columns/{columnId}` | Edit description / sensitivity |
| `DELETE /datasets/{id}` | Delete the dataset and drop its warehouse schema + role |
| `GET /connections` | Connection metadata (never credentials) |
| `GET /docs` | Swagger UI (disabled when `ENV=production`) |

Full contract: [docs/API_SPECIFICATION.md §3](../../docs/API_SPECIFICATION.md).

Quick try (with the API running):

```bash
curl -s localhost:8000/api/v1/datasets
curl -s -F file=@sales.csv -F name="My sales" localhost:8000/api/v1/datasets/uploads
curl -s -X POST -H 'content-type: application/json' -d '{"column_types":{}}' \
     localhost:8000/api/v1/datasets/<id>/finalize
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
| `AUTH_MODE`, `DEMO_USER_EMAIL` | `demo`, `demo@sageboard.local` | Until auth exists, requests act as the seeded user. **Refused in production** |
| `LLM_PROVIDER` | `mock` | `mock` is refused in production; adapters arrive with the agent phase |
| `LOG_LEVEL`, `LOG_JSON` | `INFO`, `true` | Use `LOG_JSON=false` locally for readable logs |

## Code layout

```
app/
├── main.py              create_app(): middleware, CORS, error handlers, lifespan (opens all pools)
├── core/                config · logging (secret redaction) · errors · middleware
├── api/deps.py          dependencies: settings, databases, session, current user, services
├── api/v1/              routes (thin: parse → service → schema): health, datasets, connections
├── schemas/             Pydantic request/response models (the public contract)
├── services/            datasets (upload/finalize/preview/delete) · catalog (rebuild from PostgreSQL)
│                        · schema_catalog (privacy-controlled view for the agent) · health
├── db/                  base (UUIDv7, naming convention) · models/ · engines (4 roles) · identifiers
├── ingestion/           csv_validation · types (inference + parsing) · identifiers (normalisation)
│                        · semantics (sensitivity, roles) · uploads (safe storage) · warehouse (DDL, COPY, inspection)
├── execution/readonly.py  the only path that runs SQL against dataset data
└── seed/                ecommerce (deterministic generator) · demo (seed + CLI)
migrations/              Alembic (schema `app` only): 0001 baseline · 0002 app tables · 0003 FK fix
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
