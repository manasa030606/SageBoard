# ADR-0001 — Monorepo layout and tooling

| Status | Accepted (2026-11-12) — resolves Open Decision **D13** |
|---|---|

## Decision
- One repository with independent apps: `apps/web` (Next.js) and `apps/api` (FastAPI). They share no code at runtime. The only contract between them is the HTTP API (OpenAPI at `/api/v1/openapi.json`; generated TypeScript types from Phase 8).
- **Python:** `uv` (lockfile `apps/api/uv.lock`, virtualenv `apps/api/.venv`), Python ≥ 3.12 (developed on 3.13). Quality: `ruff` (lint, including `S` security rules, and format) and `mypy --strict`.
- **Web:** `pnpm` (lockfile `apps/web/pnpm-lock.yaml`), Node ≥ 20.9. Quality: ESLint (`eslint-config-next` + `eslint-config-prettier`), Prettier (+ Tailwind class sorting), `tsc --noEmit` after `next typegen`, Vitest.
- Root `Makefile` for common commands. CI workflows per app (`.github/workflows/ci-api.yml`, `ci-web.yml`) plus a gitleaks secrets scan.

## Versions resolved at Phase 1 (from the lockfiles)
Next.js 16.4.6, React 19.3.0, Tailwind CSS 4.3.3, TypeScript 5.9.3, Vitest 5.1 · FastAPI 0.162.5, Starlette 1.10, Pydantic 2.14.3, pydantic-settings 2.16.2, SQLAlchemy 2.1.8, asyncpg 0.32.0, Alembic 1.20.1, structlog 26.1, ruff 0.17.4, mypy 2.4.1, pytest 9.2.

## Notes
- Next.js 16 has changed conventions (Cache Components, `LayoutProps` globals, `next typegen`). Its bundled docs in `node_modules/next/dist/docs/` are the reference, per `apps/web/AGENTS.md`.
- The Starlette test client now uses `httpx2`. `httpx2` is the backend's test HTTP dependency.
