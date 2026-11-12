# ADR-0002 — Database topology and permission model

| Status | Accepted (2026-11-12) — resolves Open Decision **D5** |
|---|---|
| Implemented in | Phase 1 (base roles, `app` schema, hardening) · Phase 3 (per-dataset schemas/roles) · Phase 4 (executor sessions) |

## Context
Sageboard runs SQL written by an LLM against user data. Whatever the SQL says, it must not be able to write data, read application metadata (users, sessions, traces), or read another user's dataset. Prompts can be wrong and validators can have bugs, so PostgreSQL's own privilege system has to be a real security boundary, not an afterthought.

## Decision

### Hosting
- **Production:** Neon PostgreSQL 16. Neon supports creating roles and granting privileges through SQL. Roles created that way do **not** get `neon_superuser` membership; they start with only the basic privileges of a new role in standalone Postgres. That's what we want for restricted roles. The project owner role (a `neon_superuser` member, holding `CREATEROLE`) runs the bootstrap script.
- **Local development:** native PostgreSQL 16 (Homebrew or Postgres.app), prepared by `infra/postgres/setup-local.sh`. **Docker is optional** (`infra/docker-compose.yml`). **CI:** a PostgreSQL 16 service container in GitHub Actions.

### One database, separated by schema and role
| Schema | Owner | Holds |
|---|---|---|
| `app` | `sageboard_owner` | Application metadata (users, datasets, runs, traces, reports…), managed by Alembic |
| `lg` | `sageboard_owner` | LangGraph checkpoints (Phase 5) |
| `ds_<32-hex>` | `sageboard_ingest` | One schema per uploaded dataset (Phase 3) |
| `public` | — | Unused; `ALL` is revoked from `PUBLIC` |

### Roles
| Role | Login | Used by | Can | Cannot |
|---|---|---|---|---|
| `sageboard_owner` | yes | Alembic migrations, bootstrap | Own and alter `app`/`lg` objects | Superuser, create databases |
| `sageboard_app` | yes | FastAPI runtime (SQLAlchemy pool) | `SELECT/INSERT/UPDATE/DELETE` on `app` tables (default privileges) | DDL anywhere; any access to `ds_*`; create schemas/temp tables |
| `sageboard_ingest` | yes | Ingestion code path only (Phase 3) | Create `ds_*` schemas, load data, create per-dataset reader roles (`CREATEROLE`) | Access `app` |
| `sageboard_executor` | yes, `NOINHERIT` | Query Executor pool only (Phase 4) | `SET ROLE` into a `ds_<id>_r` it has been granted | Anything on its own: it has no direct privileges; sessions default to read-only with a 10 s statement timeout |
| `ds_<id>_r` | no | Assumed by the executor per query | `USAGE` on one `ds_<id>` schema + `SELECT` on its tables | Everything else |

Because `sageboard_executor` is `NOINHERIT`, being a member of every dataset reader role gives it nothing until it explicitly does `SET ROLE ds_<id>_r`. It can never `SET ROLE` to the app, owner or ingest roles because it isn't a member of them. (This is verified by `tests/test_db_permissions.py`.)

### Session safety for analytical SQL (Phase 4)
Every analytical query runs in one transaction on an executor connection:
```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL ROLE ds_<id>_r;            -- identifier from the datasets row, regex-checked, quoted
SET LOCAL search_path = ds_<id>;
SET LOCAL statement_timeout = '10s';
EXPLAIN (FORMAT JSON) <validated sql>;  -- cost gate
<validated sql>;                         -- fetch up to row_limit + 1
ROLLBACK;
```
Only `SET LOCAL` is used. It's scoped to the transaction, so a pooled connection can never carry a dataset role or `search_path` over to the next query.

### Connection pooling
- **Application pool:** SQLAlchemy async pool (asyncpg) as `sageboard_app`. On Neon it may use the **pooled** endpoint (`-pooler` host). Neon's PgBouncer runs in transaction mode, which drops session-level `SET`. We don't depend on session state, and asyncpg's statement cache is disabled (`statement_cache_size=0`) for compatibility.
- **Executor pool:** a separate asyncpg pool as `sageboard_executor` (Phase 4). The transaction-scoped `SET LOCAL` design above works through a transaction-mode pooler. We'll still default the executor to the **direct** endpoint so `pg_cancel_backend` can target the right backend when a run is cancelled. This gets re-checked in the Phase 4 spike.
- **Migrations and LangGraph checkpointer:** the **direct** (non-pooled) endpoint, because migrations and checkpoint setup rely on session behaviour the pooler doesn't keep.

### Hardening applied in Phase 1 (`infra/postgres/init/001_roles.sh`)
- `REVOKE ALL ON DATABASE … FROM PUBLIC`, then `CONNECT` granted only to Sageboard roles. `CREATE` on the database is granted only to owner and ingest. `TEMP` is not granted to anyone.
- `REVOKE ALL ON SCHEMA public FROM PUBLIC`.
- No role has `SUPERUSER`, `CREATEDB`, `REPLICATION` or `BYPASSRLS`.
- Per-role defaults: app `statement_timeout=30s`; executor `statement_timeout=10s`, `default_transaction_read_only=on`, `idle_in_transaction_session_timeout=15s`.
- Passwords come from environment variables. The script contains none.

## Verified in Phase 1 (real PostgreSQL 16, see the phase report)
- The app role can read `app.alembic_version` (default privileges work) but can't create tables in `app` or `public`, create schemas, or drop the migration table.
- Executor sessions are read-only by default (a temp table fails with `ReadOnlySQLTransactionError`), can't read `app.*`, and can't `SET ROLE` to `sageboard_app`, `sageboard_owner`, `sageboard_ingest` or `postgres`.

## Open items to verify on Neon before Phase 3
1. Whether Neon requires a password for `NOLOGIN` roles created through SQL (its docs say SQL-created roles need a password). If it does, the per-dataset reader roles get a random password that's never stored.
2. That a `neon_superuser` member can grant SQL-created roles to `sageboard_executor` and that `sageboard_ingest` (with `CREATEROLE`) can administer the reader roles it creates (PostgreSQL 16 `ADMIN OPTION` semantics).
3. Plan limits on roles/schemas per project.

If (2) fails, the fallback is a single `sageboard_reader` role with `SELECT` on all `ds_*` schemas. The SQL Guard's schema allowlist then becomes the only cross-tenant control above the database, and this reduced-assurance mode is flagged in SECURITY_DESIGN §5.

## Consequences
- Strong isolation: even a validator bypass yields at most a read-only `SELECT` on the user's own dataset.
- Role management is extra operational work (the bootstrap script; per-dataset role lifecycle in Phase 3).
- Two kinds of connection strings per environment (pooled for the app, direct for migrations and the executor), documented in `apps/api/.env.example`.
