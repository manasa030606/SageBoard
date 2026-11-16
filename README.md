# Sageboard

Ask questions about your data in plain language. Sageboard plans the analysis, writes read-only SQL, checks it, runs it, charts the result and writes findings that are verified against the query results.

Built for business analysts, data analysts, students and small businesses who want answers without writing SQL.

## Features

- **Ask in plain language.** The analyst plans one or more queries, runs them, and explains the result with charts and findings.
- **Safe by construction.** The model never executes anything. Its SQL is parsed and validated, then run read-only under a per-dataset database role with timeouts and a cost check. Sensitive columns are hidden from the model.
- **Evidence for every claim.** Each number in a finding must match a cited query result; unsupported findings are removed.
- **Self-correcting.** Failed or empty queries are classified and retried within fixed limits. Unsafe SQL is never retried.
- **Your data.** Upload a CSV, review the inferred column types, or load the built-in sample dataset.
- **Conversations, history and reports.** Ask follow-ups, reopen past analyses, inspect every SQL statement, and save an analysis as a report with PDF and Markdown export.

## Stack

| Part | Technology |
|---|---|
| Frontend (`apps/web`) | Next.js 16, TypeScript, Tailwind CSS 4, Recharts |
| Backend (`apps/api`) | FastAPI, SQLAlchemy (async), Alembic, LangGraph, SQLGlot |
| Database | PostgreSQL 16 |
| Model | Google Gemini (free tier), or Anthropic / OpenAI, chosen by configuration |
| Tooling | pnpm, uv, ruff, mypy, ESLint, Vitest, pytest, Playwright |

## Architecture

```
Browser ── Next.js ── HTTPS/JSON ── FastAPI ── PostgreSQL (app data + one schema per dataset)
                                        └────── LLM provider (plans and writes; never executes)
```

The language model proposes plans, SQL and wording. Deterministic code validates every proposal, runs it with read-only permissions and computes the numbers. See [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md).

## Prerequisites

Node.js 20.9+, pnpm 10, Python 3.12 or 3.13, uv, PostgreSQL 16. Docker is optional. A Google AI Studio API key is needed to answer questions; the rest of the app works without one.

## Run it

```bash
make install
cp infra/.env.example infra/.env
cp apps/api/.env.example apps/api/.env        # same passwords as infra/.env; set JWT_SECRET
cp apps/web/.env.example apps/web/.env.local
bash infra/postgres/setup-local.sh            # database, roles, schema
make migrate
make api                                      # http://localhost:8000/api/v1/docs
make web                                      # http://localhost:3000
```

Open http://localhost:3000, create an account and load the sample dataset from the Data page. To enable the analyst, add a model key (see the development guide). `make help` lists every command.

## Tests

```bash
make check                 # lint, types, unit tests, formatting (both apps)
make test-integration      # backend tests against PostgreSQL
pnpm e2e                   # browser tests, from apps/web
```

Setup for the integration and browser tests, and the evaluation framework, are in the docs below.

## Documentation

| Document | Content |
|---|---|
| [Architecture](docs/architecture/ARCHITECTURE.md) | Components, data flow, database, API, the analysis agent |
| [Security](docs/security/SECURITY.md) | Threat model, SQL validation, database roles, application security |
| [Security review](docs/security/SECURITY_REVIEW.md) | Phase 10 audit: findings by severity, fixes, remaining risks |
| [Development](docs/development/DEVELOPMENT.md) | Setup, configuration, testing, known limitations, deployment checklist, status |
| [Performance report](docs/development/PERFORMANCE_REPORT.md) | Phase 10 measurements before and after, limits, what was not measured |
| [Decisions](docs/development/DECISIONS.md) | Decision log and architecture decision records |
| [Evaluation](docs/eval/README.md) | Evaluation framework, results, failure analysis |
| [Original PRD](docs/archive/PRD.md) | Archived product brief |
