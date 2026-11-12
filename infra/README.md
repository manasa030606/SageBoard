# Infrastructure

## Local PostgreSQL 16 without Docker (recommended)

```bash
brew install postgresql@16            # skip if PostgreSQL is already installed
brew services start postgresql@16
cp infra/.env.example infra/.env      # passwords; keep them equal to apps/api/.env
bash infra/postgres/setup-local.sh    # creates DB + roles + schema; safe to re-run
```

`setup-local.sh` connects as your macOS username (the admin role that Homebrew and Postgres.app create). If your admin role is different, use `PG_SUPERUSER=postgres bash infra/postgres/setup-local.sh`. Re-run it whenever you change a password in `infra/.env`: role passwords are re-synced on every run.

If `psql` is not found after a Homebrew install:
```bash
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

## Optional: PostgreSQL in Docker

```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d --wait   # or: make db-up
```
On the first start (empty volume) the container runs `postgres/init/001_roles.sh` automatically. Bound to `127.0.0.1` only.

## Neon (production) — runbook outline

1. Create a Neon project on PostgreSQL 16 and a database named `sageboard`.
2. Using the project owner role (a member of `neon_superuser`) over the **direct** connection string, run `001_roles.sh` with `PGHOST`, `PGUSER` (via `POSTGRES_USER`), `PGPASSWORD` and `PGSSLMODE=require`, and strong generated passwords.
3. Set the API's `MIGRATION_DATABASE_URL` (owner role, direct endpoint) and `DATABASE_URL` (app role; the pooled `-pooler` endpoint is fine), then run `alembic upgrade head`.
4. Before Phase 3, complete the Neon verification items in `docs/adr/0002-database-topology-and-permissions.md`.

## Role model

See [ADR-0002](../docs/adr/0002-database-topology-and-permissions.md). Summary:

| Role | Purpose |
|---|---|
| `sageboard_owner` | Owns `app`/`lg` schemas; runs migrations |
| `sageboard_app` | API runtime; DML on `app` tables only |
| `sageboard_ingest` | Creates per-dataset schemas and reader roles (Phase 3) |
| `sageboard_executor` | Runs analytical SQL; read-only, `NOINHERIT`, may only `SET ROLE` into a dataset reader role |
