# Sageboard developer commands. Run `make help` for the list.
API := apps/api
WEB := apps/web
COMPOSE := docker compose -f infra/docker-compose.yml --env-file infra/.env

.PHONY: help install db-up db-down db-logs migrate api web lint typecheck format test test-integration check

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

migrate:  ## Apply database migrations (owner role)
	cd $(API) && uv run alembic upgrade head

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

test-integration:  ## Backend tests incl. PostgreSQL (needs db-up + migrate + SAGEBOARD_TEST_* vars)
	cd $(API) && uv run pytest

check: lint typecheck test  ## Everything CI runs (except integration)
	cd $(API) && uv run ruff format --check .
	cd $(WEB) && pnpm format:check
