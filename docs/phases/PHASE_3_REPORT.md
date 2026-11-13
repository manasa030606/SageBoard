# Phase 3 — Database and data ingestion: completion report

| Field | Value |
|---|---|
| Date | 2026-11-13 |
| Status | Implemented and tested; awaiting owner review. **Phase 4 not started** |
| Scope | Backend (`apps/api`), DB setup tooling, docs. No AI agents. No frontend changes (web suite re-run: unaffected) |

## Delivered (mapped to the request)

| # | Requirement | Where | Notes |
|---|---|---|---|
| 1 | Connection management | `app/db/engines.py`, `app/main.py` lifespan | Four separate credentials. App role → SQLAlchemy async; ingest and executor → asyncpg pools; owner → Alembic only. `/readyz` checks all three runtime connections. `statement_cache_size=0` for Neon's pooler |
| 2 | Migrations | `migrations/versions/0002`, `0003` | 12 application tables. 0003 fixes a cascade bug the tests found (below). Round trip `base → head` and `alembic check` tested |
| 3 | SQLAlchemy models | `app/db/models/` | users, database_connections, datasets, dataset_tables, dataset_columns, dataset_relationships, ingestion_jobs, conversations, messages, analysis_sessions, query_executions, reports |
| 4 | PK/FK relationships | models + migration | UUIDv7 PKs; cascade / SET NULL / deferred NO ACTION chosen per relationship (DATABASE_DESIGN §3) |
| 5 | Indexes | models + migration | Owner-scoped listing indexes, FK indexes, case-insensitive unique email, partial index on active analysis sessions; demo warehouse tables get FK indexes |
| 6 | Synthetic dataset generation | `app/seed/ecommerce.py` | customers, products, orders, order_items, payments; deterministic (seed 20261113); two scales; documented patterns |
| 7 | Seed scripts | `app/seed/demo.py`, `python -m app.seed`, `make seed` | Idempotent; `--replace`; `--csv-out` |
| 8 | Dataset metadata inspection | `ingestion/warehouse.py: inspect_schema, profile_table`, `services/catalog.py` | Read from the live PostgreSQL catalog after every load |
| 9 | Table/column discovery | same + `GET /datasets/{id}` | Types, nullability, PKs, FKs, row counts, profiles |
| 10 | CSV upload and validation | `ingestion/csv_validation.py`, `ingestion/uploads.py`, `POST /datasets/uploads` | Streaming size limit; strict UTF-8 and CSV parsing; review step before anything loads |
| 11 | CSV-to-database ingestion | `services/datasets.py: finalize`, `ingestion/warehouse.py` | One transaction: schema + reader role + typed table + COPY + grants + catalog. Optional type overrides |
| 12 | Dataset preview APIs | `GET /datasets/{id}/tables/{table}/preview` | Through the read-only executor; paginated; sensitive columns masked; recorded in `query_executions` |
| — | Schema metadata service | `services/schema_catalog.py`, `GET /datasets/{id}/schema` | Tables, columns, types, PKs, FKs, relationships, samples subject to privacy controls; `summary` and `full` levels for the agent |

**Data quality controls**

| Required | How |
|---|---|
| Missing values | Recognised missing-value tokens; per-column missing counts; `EMPTY_COLUMN` and `HIGH_MISSING` warnings; null % in profiles |
| Duplicate column names | Exact and case-insensitive duplicates, and names that collide after normalisation (`Order Date` vs `order-date`), are rejected with both names shown |
| Supported data types | integer, bigint, numeric, boolean, date, timestamptz, text. Unknown overrides are rejected. Ambiguous dates (`28/02/2026`) aren't guessed |
| Malformed CSV | Unclosed quotes (strict parser), oversized cells, ragged rows (≤ 5 % skipped and reported, more rejects the file), binary content, bad encoding |
| File size limits | 25 MB enforced while streaming; plus row, column and cell limits |
| Unsafe file handling | Random 256-bit server file names, `O_EXCL` 0600 files in a 0700 directory, traversal-proof paths, display-name sanitising, `.csv` only, deletion after use + TTL sweep |
| Meaningful errors | Every issue has a stable `code` and a plain-language `message` with the line or column and what to do (e.g. “Save it as ‘CSV UTF-8’ and upload again.”) |

**Security constraints you set**

| Constraint | Status |
|---|---|
| Parameterized queries for application operations | ORM / bind parameters for all `app` access; previews use `$1/$2` binds; data loads use COPY records. Identifiers (never values) are validated and quoted |
| Separate application and analytical credentials | Four roles and four URLs; the app role is refused when reading dataset data (tested) |
| Read-only analytical access | Executor is NOINHERIT, default read-only, `READ ONLY` transaction, `SET LOCAL ROLE` to a per-dataset reader role, statement timeout. Writes, other schemas and long queries are refused by PostgreSQL (tested) |
| No database credentials in the frontend | Credentials exist only in backend env vars; `/connections` returns id, name, kind, status, created_at only (tested); logs redact secrets (Phase 1) |

## Test results (actual, 2026-11-13)

Environment: PostgreSQL 16 (native) with the real roles from `infra/postgres/init/001_roles.sh`; Python 3.13 via uv.

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 66 files already formatted |
| `uv run mypy` (strict: app, tests, scripts) | No issues in 64 source files |
| `uv run pytest` (all `SAGEBOARD_TEST_*` set) | **203 passed, 0 skipped**, 22.6 s; line + branch coverage of `app/`: **95 %** |
| `uv run pytest -m "not integration"` (no database) | 148 passed |
| `uv run pytest -m integration` | 55 passed |
| CI path simulated: DB bootstrapped by the role script at revision 0001 → `alembic upgrade head` → full suite | 203 passed, 0 skipped |
| Same suite run twice in a row | Both green; test DB left with only the demo dataset (no orphaned schemas or roles) |
| Web (`pnpm typecheck`, `lint`, `test`) | Clean; 55 tests passed (no frontend changes) |

| Area requested | Test file | Tests |
|---|---|---|
| Migrations | `tests/integration/test_00_migrations.py` | downgrade base → upgrade head; models match migrations (`alembic check`); indexes and FKs exist; app-role grants are DML only |
| Relationships | `tests/integration/test_models.py` | relationship loading; dataset delete cascade (reports survive, SET NULL); user delete removes everything; in-use connection can't be deleted; case-insensitive email uniqueness; CHECK constraints; question length |
| Dataset seeding | `tests/test_seed_generator.py`, `tests/integration/test_seed_and_permissions.py` | determinism and checksum; unique PKs; every FK resolves; date window; business rules; CSV export; catalog row counts, PKs and 4 FKs; idempotent; `--replace` drops the old schema and role; sensitive columns profiled without values |
| CSV uploads | `tests/test_csv_validation.py`, `tests/integration/test_datasets_api.py` | 76 validation, parsing, storage and sensitivity unit tests; upload → review → finalize → preview → delete over HTTP; type overrides; >5 % bad rows → clean failure with nothing left behind; size limit → 413; non-CSV → 415; duplicate name → 409; demo CSVs round-trip through upload |
| Schema inspection | `tests/integration/test_datasets_api.py`, `test_seed_and_permissions.py` | full and summary catalog; PKs, FKs, relationships; samples redacted for sensitive columns; `include_samples=false`; marking a column sensitive erases its samples |
| Security | across the above + `tests/test_identifiers.py` | identifier injection rejected; app role can't read data; executor refused without role switch; writes / foreign schema / `pg_sleep` refused; reader roles can't log in; other users' datasets return 404; previews only serve catalogued tables; no secrets in `/connections` |

### Bugs found by the tests and fixed

1. **Deleting a user failed.** Both `database_connections` and `datasets` cascade from `users`, but `datasets.connection_id` was `RESTRICT`. PostgreSQL runs each cascade as a nested statement, so neither RESTRICT nor plain NO ACTION works here. Fix: migration 0003 makes the FK `NO ACTION DEFERRABLE INITIALLY DEFERRED`. Deleting an in-use connection is still refused (tested).
2. **Unclosed quote went undetected.** Python's lenient CSV mode swallowed the rest of the file into one cell. Fix: one shared reader with `strict=True` for both analysis and loading.
3. **Upload response crashed (500).** The route read a lazy relationship after commit, which isn't possible in async SQLAlchemy. Fix: re-load with eager loading before returning.
4. **camelCase headers collapsed** (`customerName` → `customername`). The normaliser now splits camelCase and PascalCase.
5. **Primary keys came back empty.** asyncpg returns PostgreSQL's `"char"` type as bytes. Fix: explicit `::text` casts in the catalog query.
6. **Coverage under-reported** async ORM code (57 % → 88 % for the dataset service once measured correctly). Fix: coverage `concurrency = ["greenlet", "thread"]`.

## New concepts (short mentor notes)

- **Four database identities.** *What:* separate PostgreSQL logins for the app, migrations, loading and querying. *Why:* a bug or a bad generated query in one part can only do what that login is allowed to do. *How:* `infra/postgres/init/001_roles.sh` plus one URL each. *Where:* everything that touches PostgreSQL goes through `app/db/engines.py`.
- **Schema-per-dataset + reader role.** *What:* every dataset lives in its own `ds_<hex>` schema with a no-login role that can only SELECT there. *Why:* isolation is enforced by PostgreSQL, not by our code remembering to add `WHERE owner_id = …`. *How:* `warehouse.provision_schema` / `grant_reader`. *Where:* the executor switches into that role for every query, and the agent will use the same path in Phase 4+.
- **Transactional DDL.** *What:* in PostgreSQL, `CREATE SCHEMA/ROLE/TABLE` can be rolled back. *Why:* a failed load leaves no half-built dataset. *How:* the whole finalize runs in one ingest transaction.
- **Two-step upload.** *What:* analyse first, load after review. *Why:* users can fix types before data is written, and bad files never reach the database. *How:* the file is held privately with a random token between the two calls.
- **Schema catalog.** *What:* a stored, privacy-filtered description of tables, columns, keys and sample values. *Why:* the agent can't write correct SQL without knowing the real schema, and must not see sensitive values. *How:* rebuilt from `pg_catalog` after every load; served at two levels.
- **Deferred constraints.** *What:* a foreign key checked at commit instead of per statement. *Why:* it lets one delete cascade through two paths while still blocking a dangerous delete.

## Limitations (honest)

- **No real authentication.** Every request is the seeded demo user (D27); startup refuses this in production. Auth is the next backend concern.
- **CSV only.** XLSX, multi-file datasets and declaring FKs between uploaded tables are not built. Uploaded datasets are one table each.
- **Ingestion runs inside the request.** Fine at 25 MB (the demo's ~105k rows load in about 2 s); a background worker and job polling are planned.
- **Sensitivity detection is heuristic** (column names + e-mail-shaped values). It can miss a sensitive column with a neutral name. Owners can toggle columns, and nothing is sent to an LLM yet.
- **Deleting a user doesn't drop their warehouse schemas** (only metadata cascades). Account deletion must call the dataset delete path; this is planned with auth.
- **Not yet verified on Neon.** Everything ran on local PostgreSQL 16. On Neon, check that `sageboard_ingest` may `CREATE ROLE` and `GRANT` it to the executor (ADR-0002 fallback otherwise), and use the direct endpoint for migrations.
- **No SQL Guard yet.** The executor runs only catalog-built preview SQL today; the guard for generated SQL is a later phase.

## Run commands

See the final message of this phase or `apps/api/README.md`.
