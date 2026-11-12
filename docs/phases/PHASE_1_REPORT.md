# Phase 1 — Project Foundation: completion report

| Field | Value |
|---|---|
| Date | 2026-11-12 |
| Status | Implemented and tested; awaiting owner review before Phase 2 |

## Delivered
- `apps/web`: Next.js 16.4 + TypeScript + Tailwind 4; design tokens; self-hosted IBM Plex fonts; validated public env (`lib/env.ts`); typed API client with a single `ApiError` type (`lib/api/*`); `GET /api/health`; system status page at `/`; security headers; ESLint, Prettier, Vitest.
- `apps/api`: FastAPI app factory; validated settings (CORS allowlist, async DB URL, LLM provider rules); structlog with secret redaction; error envelope; request-id middleware (pure ASGI); strict CORS; `GET /api/v1/healthz` and `/readyz`; async SQLAlchemy engine; Alembic (baseline `0001`, version table in `app` schema); ruff, mypy strict, pytest.
- `infra`: native-PostgreSQL setup script (`setup-local.sh`, no Docker needed); optional Docker Compose; idempotent role bootstrap (`sageboard_owner`, `sageboard_app`, `sageboard_ingest`, `sageboard_executor`) with database hardening.
- Tooling: Makefile, pre-commit, CI workflows (`ci-api`, `ci-web`, `secrets-scan`), `.gitignore` that excludes every real env file.
- Docs: decision log, ADR-0001…0007 (D1, D5, D8 finalised), blueprint docs updated to v0.2.

## Test results (actual, from the build workspace)
| Check | Result |
|---|---|
| Backend pytest incl. integration against PostgreSQL 16 | 36 passed, 99% line coverage |
| Role-permission tests (app role cannot create objects; executor read-only, no access to `app`, cannot SET ROLE upward) | Passed |
| Role bootstrap script run twice | Idempotent |
| ruff, ruff format, mypy --strict | Clean |
| ESLint (0 warnings), tsc, Prettier | Clean |
| Vitest | 10 passed |
| `next build` | Succeeded |
| Live: `/healthz`, `/readyz` with DB, web `/api/health` | 200 / 200 / 200 |
| Headless Chrome: page on :3000 calls API on :8000 | 2 × 200, no console errors |
| Failure states: DB stopped → "Not ready"; API stopped → "Could not reach…"; 375 px → no overflow | Verified |

## Not verified in Phase 1
- `docker compose up` (optional path; `docker compose config` validates). The primary no-Docker path (`setup-local.sh` → `alembic upgrade head` → `/readyz` ready → 36 tests) was verified end-to-end.
- GitHub Actions runs (YAML validated only) and the gitleaks hook (could not be downloaded in the workspace).
- Neon (verification items listed in ADR-0002, due before Phase 3).

## Scope note
Application tables (`users`, `user_settings`, `refresh_tokens`, `audit_log`) moved to Phase 2, together with authentication.
