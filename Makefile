# Sageboard developer commands. Run `make help` for the list.
API := apps/api
WEB := apps/web
COMPOSE := docker compose -f infra/docker-compose.yml --env-file infra/.env

.PHONY: help install db-up db-down db-logs db-setup db-setup-test migrate migrate-test seed api web lint typecheck format test test-integration check

help:  ## Show available targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

install:  ## Install backend (uv) and frontend (pnpm) dependencies
	cd $(API) && uv sync
	cd $(WEB) && pnpm install

db-up:  ## Start local PostgreSQL 16 (Docker)
	$(COMPOSE) up -d --wait

db-down:  ## Stop local PostgreSQL (data volume is kept)
	$(COMPOSE) down

db-logs:  ## Tail PostgreSQL logs
	$(COMPOSE) logs -f postgres

db-setup:  ## Create roles + `sageboard` database on a native PostgreSQL (no Docker)
	bash infra/postgres/setup-local.sh

db-setup-test:  ## Same, for the separate `sageboard_test` database used by integration tests
	bash infra/postgres/setup-local.sh --db sageboard_test

migrate:  ## Apply database migrations (owner role)
	cd $(API) && uv run alembic upgrade head

migrate-test:  ## Apply migrations to sageboard_test (needs SAGEBOARD_TEST_MIGRATION_DATABASE_URL)
	cd $(API) && MIGRATION_DATABASE_URL="$$SAGEBOARD_TEST_MIGRATION_DATABASE_URL" uv run alembic upgrade head

seed:  ## Load the synthetic e-commerce demo dataset (idempotent; `make seed ARGS=--replace`)
	cd $(API) && uv run python -m app.seed $(ARGS)

api:  ## Run the FastAPI dev server on :8000
	cd $(API) && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

web:  ## Run the Next.js dev server on :3000
	cd $(WEB) && pnpm dev

lint:  ## Lint backend and frontend
	cd $(API) && uv run ruff check .
	cd $(WEB) && pnpm lint

typecheck:  ## Type-check backend (mypy strict) and frontend (tsc)
	cd $(API) && uv run mypy
	cd $(WEB) && pnpm typecheck

format:  ## Auto-format backend and frontend
	cd $(API) && uv run ruff format . && uv run ruff check --fix .
	cd $(WEB) && pnpm format

test:  ## Unit tests (no database needed)
	cd $(API) && uv run pytest -m "not integration"
	cd $(WEB) && pnpm test

test-integration:  ## Backend tests incl. PostgreSQL (needs db-setup-test + migrate-test + SAGEBOARD_TEST_* vars)
	cd $(API) && uv run pytest

check: lint typecheck test  ## Everything CI runs (except integration)
	cd $(API) && uv run ruff format --check .
	cd $(WEB) && pnpm format:check
