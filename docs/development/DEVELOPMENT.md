# Sageboard development guide

Setup, configuration, testing, known limitations and status. For how the system works see [ARCHITECTURE.md](../architecture/ARCHITECTURE.md); for security controls see [SECURITY.md](../security/SECURITY.md); for the reasons behind choices see [DECISIONS.md](DECISIONS.md); for the evaluation framework see [eval/README.md](../eval/README.md).

## 1. Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node.js | 20.9 or newer (22 LTS recommended) | https://nodejs.org |
| pnpm | 10.x | `corepack enable` |
| Python | 3.12 or 3.13 | https://python.org |
| uv | 0.5 or newer | `pip install uv` or https://astral.sh/uv |
| PostgreSQL | 16 | `brew install postgresql@16 && brew services start postgresql@16`, or Postgres.app. Docker is optional. |

## 2. Run it locally

```bash
make install                                         # uv sync + pnpm install

cp infra/.env.example     infra/.env                 # database passwords
cp apps/api/.env.example  apps/api/.env              # same passwords; also set JWT_SECRET
cp apps/web/.env.example  apps/web/.env.local
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into JWT_SECRET

bash infra/postgres/setup-local.sh                   # database, roles, schema (safe to re-run)
make migrate                                         # Alembic, as the owner role

make api                                             # terminal 1: http://localhost:8000/api/v1/docs
make web                                             # terminal 2: http://localhost:3000
```

Open `http://localhost:3000` (not `127.0.0.1`), create an account, and use **Load sample dataset** on the Data page. Each account gets its own copy. Without an LLM key the app works except for answering questions: they stay queued and nothing is invented. Add a key (section 4) to enable the analyst. `make help` lists all commands.

`setup-local.sh` connects as your OS username. If your admin role differs, run `PG_SUPERUSER=postgres bash infra/postgres/setup-local.sh`. Re-run it after changing a password in `infra/.env`; role passwords are re-synced each time. If `psql` is not found after a Homebrew install, add `/opt/homebrew/opt/postgresql@16/bin` to `PATH`.

Optional Docker: `make db-up` starts PostgreSQL 16 in a container bound to `127.0.0.1`. On the first start with an empty volume it runs `infra/postgres/init/001_roles.sh`.

Useful extras (from `apps/api`):

```bash
uv run python -m app.seed --scale small --replace    # sample data for AUTH_MODE=demo; --csv-out DIR writes CSVs to try uploads
uv run python scripts/ask.py --email you@example.com "Why did revenue decrease last month?"   # run the agent, print its trace
uv run python scripts/schema_reference.py            # column-level table reference generated from the models
```

## 3. Configuration

All backend settings are environment variables (or `apps/api/.env`), validated at startup by `app/core/config.py`. The service refuses unsafe settings: a wildcard CORS origin, `http://` origins in production, `AUTH_MODE=demo` or the mock LLM in production. Real values live only in gitignored `.env` files; each app ships a `.env.example`.

The web app holds no secrets. Its single variable, `NEXT_PUBLIC_API_URL` (default `http://localhost:8000/api/v1`), is public by design and inlined at build time, so rebuild after changing it.

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

## 4. The language model

### Free model setup: Google Gemini

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


Asking a question (`POST /api/v1/conversations/{id}/sessions`) starts the agent in the background. The account needs a ready dataset first.

## 5. Production database (Neon outline)

1. Create a Neon project on PostgreSQL 16 and a database named `sageboard`.
2. With the project owner role (a member of `neon_superuser`) on the direct connection string, run `infra/postgres/init/001_roles.sh` with `PGHOST`, `POSTGRES_USER`, `PGPASSWORD`, `PGSSLMODE=require` and strong generated passwords.
3. Set `MIGRATION_DATABASE_URL` (owner role, direct endpoint) and `DATABASE_URL` (app role; the pooled `-pooler` endpoint is fine), then run `alembic upgrade head`.
4. Verify the items listed in ADR-0002 ([DECISIONS.md](DECISIONS.md)): that `sageboard_ingest` may `CREATE ROLE` and grant it to the executor.

Local development does not need any of this; it is not verified on Neon yet.

Database roles: `sageboard_owner` (owns `app`, runs migrations), `sageboard_app` (API runtime, DML on `app` tables only), `sageboard_ingest` (creates dataset schemas and reader roles), `sageboard_executor` (read-only; `NOINHERIT`; can only `SET ROLE` into a dataset reader role). Details in [SECURITY.md](../security/SECURITY.md).

## 6. Testing

### Commands

```bash
make check                                   # lint, types, unit tests, format check (both apps)

# Backend (apps/api)
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -m "not integration"           # no database needed
uv run pytest                                # everything, including integration tests

# Frontend (apps/web)
pnpm check                                   # ESLint, tsc, Prettier, Vitest
pnpm build
pnpm e2e                                     # Playwright (see below)
```

### Integration tests

They use a separate database, `sageboard_test`, because the migration test downgrades it to empty, and connect as the real roles so assertions are PostgreSQL's own permission errors.

```bash
bash ../../infra/postgres/setup-local.sh --db sageboard_test       # once, from apps/api
cp .env.test.example .env.test && source .env.test                 # four SAGEBOARD_TEST_* URLs
MIGRATION_DATABASE_URL="$SAGEBOARD_TEST_MIGRATION_DATABASE_URL" uv run alembic upgrade head
uv run pytest
```

Without the four `SAGEBOARD_TEST_*` variables, integration tests are skipped (reported as skipped, never as passed). CI sets them and fails on any skip.

### End-to-end (Playwright)

`apps/web/e2e/analyst-flow.spec.ts` drives the real Next.js app against the real FastAPI service and PostgreSQL, with the model replaced by the "oracle" (the reference SQL replayed through the real pipeline, see eval README). The frontend runs on port 3001 (reused if already running; otherwise Playwright starts `next dev` there). The test backend runs on 8100 using the test databases, and the browser's API calls are redirected to it, so your development database is never touched. Override with `E2E_WEB_PORT` and `E2E_API_PORT`. The E2E backend rate-limits registration in memory; restart it if you see HTTP 429 after many runs.

### What is covered and where

| Level | Location | Notes |
|---|---|---|
| Unit | `apps/api/tests/*.py` | Pure functions: identifiers, type inference, statistics, claims, routing, budgets, comparator |
| SQL safety | `tests/agent/test_sql_guard*.py`, `test_eval_attack_corpus.py` | Adversarial, benign and Cartesian-join cases; property-based fuzzing; 69 evaluation attacks |
| Agent | `tests/agent/` | Nodes and graph routing with a scripted model double (`fakes.py`); masking asserted on the payload text the model receives |
| Integration | `tests/integration/` | Real PostgreSQL and roles: migrations, ingestion, executor, permissions (including with the Guard bypassed), cross-tenant access, auth, history, reports (PDF text extraction), memory isolation, a time-zone regression, and 8 evaluation cases through API, graph and database |
| Frontend | `apps/web/src/**/*.test.ts(x)` | UI states, API client, result table, charts, formatting, dashboard and settings |
| E2E | `apps/web/e2e/` | Browser journey against the real stack |
| Evaluation | `apps/api/evals/` | 62 cases, nine metrics (see eval README) |

Principles that hold throughout: the safety boundary (Guard, executor, grounding) gets the most tests; integration tests use real PostgreSQL, never SQLite; the model is replaced only by a scripted double in tests and by the oracle in E2E and evaluation, and any reported number comes from an actual run; a new test is not trusted until it has been seen to fail for the right reason.

### CI

`.github/workflows/`: `ci-api.yml` (ruff, mypy, pytest with a PostgreSQL service; fails on skips), `ci-web.yml` (lint, typecheck, Vitest, build) and `secrets-scan.yml`. CI does not run Playwright.

## 7. Known limitations and technical debt

Product and agent:
- **A wrong answer that executes cleanly cannot be detected** (evaluation case R06: a misspelled filter value returns 0 and is reported as 0; see eval FAILURE_ANALYSIS).
- **Live-model accuracy is not measured.** The evaluation's oracle mode measures the pipeline; running live mode needs a key and several days of free-tier quota (see eval README).
- **Runs execute inside the API process.** A restart fails in-flight runs (marked `INTERRUPTED`), and rate limits are per process, so run one API instance.
- **Progress is by polling** (1.5 s). There is no streaming transport (ADR-0003 was not implemented).
- **Cancellation is cooperative:** it aborts an in-flight SQL query, but an in-flight model call completes.
- **Stored results are partial:** 50-row previews and 200-row chart data are persisted; there is no rerun or paging of full results.
- **Conversation memory is per conversation** by design (D53). Follow-up detection is rule-based.
- **Plan-cost estimates are unreliable on small datasets;** the cost gate is a guard rail and the statement timeout is the real bound.
- **CSV only.** No XLSX, multi-file datasets or declared foreign keys between uploaded tables. Ingestion runs inside the upload request (fine at 25 MB). Closing the upload review drawer discards the pending upload.
- **Sensitive-column detection is heuristic** (names and email-shaped values). Owners can toggle columns.
- **PDF limits:** scatter charts fall back to a table; fonts are Latin-only; charts show at most 40 stored rows. Reports saved by an earlier version open with a note.
- **No account deletion, password reset or email verification.** Deleting a user in the database would not drop their dataset schemas.

Security gaps (also listed in [SECURITY.md](../security/SECURITY.md)):
- Result values in stored history can contain real emails visible to the dataset owner.
- A sensitive column that is aliased in a query can reach the model (redaction works on result column names).
- No Content Security Policy or other security headers yet; no `pip-audit` / `pnpm audit` in CI.
- Cross-site cookies (`COOKIE_SAMESITE=none`) are implemented but only tested on the same site. Neon is not verified.

Code and tooling:
- Playwright is not in CI.
- `starlette` and `langchain_core` are imported directly but are only transitive dependencies.
- The PDF text says "1 insights verified" (the web copy handles the plural; `app/reports/pdf.py` does not).
- `src/lib/api/types.ts` exports some types that nothing imports.

## 8. Status and next steps

Delivered: the full application (accounts, dataset upload and sample data, the LangGraph analysis agent with SQL Guard and self-correction, result analysis and charts, grounded insights, conversation memory, history, reports with PDF export, dashboard) plus the evaluation framework and browser tests.

Not started (original roadmap): production hardening (security headers, audit checks, accessibility and visual regression tests, retention job), deployment (container image, hosting, production database runbook, smoke tests) and the demo script. External PostgreSQL connectors, team workspaces, a job queue and multi-dataset conversations are post-MVP ideas. No phase starts without the project owner's explicit approval.
