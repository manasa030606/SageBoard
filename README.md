# Sageboard

**An agentic AI system for autonomous business data analysis.** Ask a business question in plain language. Sageboard plans the analysis, writes and validates read-only SQL, runs it, analyses the results, charts them, and reports insights backed by the actual query results.

> **Status: Phase 2 — Frontend UI/UX (complete, demo data).** All seven product pages are built on a bundled sample dataset; the AI backend arrives in later phases. Phase 1 (foundation) is complete too. See [`docs/DEVELOPMENT_ROADMAP.md`](docs/DEVELOPMENT_ROADMAP.md).

## Repository layout

```
sageboard/
├── apps/
│   ├── web/        Next.js 16 · TypeScript · Tailwind CSS 4   → see apps/web/README.md
│   └── api/        FastAPI · SQLAlchemy 2 (async) · Alembic   → see apps/api/README.md
├── infra/          Local PostgreSQL setup (no Docker needed) + role bootstrap → see infra/README.md
├── docs/           Blueprint, decision log, ADRs
├── .github/        CI: ci-api, ci-web, secrets-scan
└── Makefile        Common commands (make help)
```

The two apps are independent. They share no code and communicate only over HTTP (`/api/v1`, documented by the API's OpenAPI schema).

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node.js | ≥ 20.9 (22 LTS recommended) | https://nodejs.org |
| pnpm | 10.x | `corepack enable` (bundled with Node) |
| Python | 3.12 or 3.13 | https://python.org |
| uv | ≥ 0.5 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` (or `pip install uv`) |
| PostgreSQL | 16 | `brew install postgresql@16 && brew services start postgresql@16` (or Postgres.app). **Docker is not required.** |

## Quick start (local development)

```bash
# 1. Install dependencies (creates apps/api/.venv via uv)
make install

# 2. Configure environment files (all gitignored; edit the passwords)
cp infra/.env.example     infra/.env
cp apps/api/.env.example  apps/api/.env       # use the same passwords as infra/.env
cp apps/web/.env.example  apps/web/.env.local

# 3. Prepare your local PostgreSQL: creates the database, roles and schema (safe to re-run)
bash infra/postgres/setup-local.sh

# 4. Apply migrations (as the owner role)
make migrate

# 5. Run the API (terminal 1) and the web app (terminal 2)
make api        # http://localhost:8000/api/v1/healthz · docs at /api/v1/docs
make web        # http://localhost:3000
```

Open http://localhost:3000 for the landing page, or http://localhost:3000/app/dashboard for the product. **Settings → System status** (or `/status`) checks the web app, the API and the database live from your browser.

Prefer Docker? `make db-up` starts PostgreSQL 16 in a container instead of step 3. It is optional. See [`infra/README.md`](infra/README.md).

## Quality checks

```bash
make check              # lint + type-check + unit tests + format check (both apps)
make test-integration   # backend tests against PostgreSQL (see apps/api/README.md)
```

## Environment & secrets

- Real values live only in `.env` / `.env.local` files, which are gitignored. Each app ships a `.env.example` template.
- The web app holds **no secrets**. Its only variable, `NEXT_PUBLIC_API_URL`, is public by design.
- The API validates its configuration at startup and refuses unsafe settings, e.g. a wildcard CORS origin, `http://` origins in production, or the mock LLM in production.

## Documentation

| Document | Purpose |
|---|---|
| [PRD](docs/PRD.md) | Product scope, users, requirements |
| [System architecture](docs/SYSTEM_ARCHITECTURE.md) | Components, data flow, deployment |
| [Agent workflow](docs/AGENT_WORKFLOW.md) | LangGraph nodes, state, routing, tools |
| [Database design](docs/DATABASE_DESIGN.md) | Schemas, tables, relationships |
| [API specification](docs/API_SPECIFICATION.md) | REST + SSE contracts |
| [Security design](docs/SECURITY_DESIGN.md) | Threat model, SQL guard, permissions |
| [Testing strategy](docs/TESTING_STRATEGY.md) | Test levels, gates, evaluation |
| [Roadmap](docs/DEVELOPMENT_ROADMAP.md) | Phases and exit criteria |
| [Decision log](docs/DECISION_LOG.md) + [ADRs](docs/adr/) | Every architectural decision |
