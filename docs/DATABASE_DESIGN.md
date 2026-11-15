# Sageboard — Database Design

| Field | Value |
|---|---|
| Document | DATABASE_DESIGN v0.6 |
| Status | v0.2 approved 2026-11-12. v0.3 (2026-11-13) records the Phase 3 implementation (D26–D33); v0.4 (2026-11-14) adds the Phase 4 auth tables (migration 0004); v0.5 (2026-11-14) adds the agent trace (migration 0005); v0.6 (2026-11-15) adds conversation memory (migration 0006, `analysis_sessions.memory`) and the report snapshot v2 (Phase 8) |
| Engine | PostgreSQL 16 — Neon in production, native PostgreSQL locally (Homebrew / Postgres.app; Docker optional). SQLAlchemy 2.x async + asyncpg, Alembic |
| Permission model | [ADR-0002](adr/0002-database-topology-and-permissions.md) — roles in `infra/postgres/init/001_roles.sh`; per-dataset schemas and reader roles in `app/ingestion/warehouse.py` |
| Source of truth | §4 is generated from the models: `uv run python scripts/schema_reference.py` (apps/api) |

---

## 1. Logical layout

| Schema | Holds | Managed by | Who can read it |
|---|---|---|---|
| `app` | Product metadata: users, connections, datasets and their catalog, conversations, messages, analysis sessions, query executions, reports | Alembic (`sageboard_owner`) | `sageboard_app` (DML only) |
| `ds_<32 hex>` | One schema per dataset: the user's actual tables | Ingestion service at runtime (`sageboard_ingest`) | Only that dataset's reader role `ds_<hex>_r` |
| `lg` | LangGraph checkpoints | `AsyncPostgresSaver.setup()` — **Phase 4+, not created yet** | — |

Conventions (as built):
- Primary keys are `uuid` **v7**, generated in the app (`app/db/base.py: uuid7`), so they're time-ordered and index-friendly.
- `created_at` / `updated_at` are `timestamptz NOT NULL DEFAULT now()`; `updated_at` is also set by the ORM on update.
- Enumerations are `varchar` + `CHECK` constraints (cheaper to migrate than native enums).
- Constraint and index names follow one convention (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`), so migrations and error messages are predictable.
- No soft deletes. Deletes are hard and cascade (privacy, FR-U3). Dataset deletion also drops its warehouse schema and role.
- `jsonb` for structured payloads (column profiles, ingestion issues, report content).

## 2. Connections and roles

| Setting | Role | Driver | Used for | Can it read dataset rows? |
|---|---|---|---|---|
| `DATABASE_URL` | `sageboard_app` | SQLAlchemy async (asyncpg) | All `app` metadata reads/writes | No — `permission denied` (tested) |
| `MIGRATION_DATABASE_URL` | `sageboard_owner` | Alembic | Schema migrations only (Neon: **direct** endpoint) | Not granted |
| `INGEST_DATABASE_URL` | `sageboard_ingest` | asyncpg pool (max 3) | `CREATE SCHEMA`, `CREATE ROLE ds_…_r`, `COPY`, catalog inspection/profiling | Owns what it creates; never runs user or agent SQL |
| `EXECUTOR_DATABASE_URL` | `sageboard_executor` | asyncpg pool (max 5) | Previews now; validated agent SQL from Phase 4 | Only via `SET LOCAL ROLE ds_<hex>_r` inside a `READ ONLY` transaction |

Every executor query runs as:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL ROLE ds_<hex>_r;                 -- privileges of this one dataset only
SET LOCAL search_path = ds_<hex>;
SET LOCAL statement_timeout = <ms>;        -- default 10 000
<prepared statement with bind parameters>;
COMMIT;
```

The executor role itself is `NOINHERIT` and `default_transaction_read_only = on`, so it has no privileges until it switches role. The integration tests prove each of these by having PostgreSQL refuse: writes (`ReadOnlySQLTransactionError`), other schemas (`InsufficientPrivilegeError`) and long queries (`QueryCanceledError`).

All pools use `statement_cache_size=0`, which is required behind Neon's transaction-mode PgBouncer and harmless on a direct connection. Credentials live only in backend environment variables. No API response includes a DSN, host or secret (`ConnectionOut` exposes id, name, kind, status, created_at).

## 3. Entity-relationship overview (as built)

```
users 1─┬─* refresh_tokens   (CASCADE; only SHA-256 hashes)     audit_log ─0..1→ users (SET NULL)
        ├─* database_connections 1─* datasets   (connection FK: NO ACTION, deferred)
        ├─* datasets 1─┬─* dataset_tables 1─* dataset_columns
        │              ├─* dataset_relationships (from/to dataset_tables)
        │              └─* ingestion_jobs
        ├─* conversations 1─┬─* messages ─0..1→ analysis_sessions (SET NULL)
        │   (dataset_id)    └─* analysis_sessions 1─┬─* query_executions (every SQL attempt)
        │                                           └─* agent_node_runs  (one row per node run)
        ├─* query_executions   (dataset_id; analysis_session_id nullable for previews)
        └─* reports            (analysis_session_id, dataset_id: SET NULL — reports outlive both)
```

Deletion behaviour (all verified in `tests/integration/test_models.py`):
- **Delete a user** → everything they own goes (connections, datasets, catalog, conversations, messages, sessions, executions, reports).
- **Delete a dataset** → its catalog, ingestion jobs, conversations, sessions and executions go. Reports stay, with `dataset_id = NULL`.
- **Delete a connection that still has datasets** → refused (`fk_datasets_connection_id_database_connections`). The check is deferred to commit so a user deletion can cascade through both paths in one statement (migration 0003).

## 4. Table reference (`app` schema, generated)

**users**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| email | varchar(320) | NOT NULL |
| full_name | varchar(200) | NOT NULL |
| password_hash | text |  |
| is_active | boolean | NOT NULL, DEFAULT true |
| last_login_at | timestamp with time zone |  |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |
| updated_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- UNIQUE INDEX `uq_users_email_lower` (lower(email))

**refresh_tokens**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| user_id | uuid | FK → users.id ON DELETE CASCADE, NOT NULL |
| family_id | uuid | NOT NULL |
| token_hash | varchar(64) | NOT NULL, UNIQUE |
| expires_at | timestamp with time zone | NOT NULL |
| revoked_at | timestamp with time zone |  |
| replaced_by_id | uuid |  |
| user_agent | varchar(300) |  |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- UNIQUE `uq_refresh_tokens_token_hash` (token_hash)
- INDEX `ix_refresh_tokens_family_id` (family_id)
- INDEX `ix_refresh_tokens_user_id` (user_id)

**audit_log**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| actor_id | uuid | FK → users.id ON DELETE SET NULL |
| action | varchar(64) | NOT NULL |
| target_type | varchar(32) |  |
| target_id | varchar(64) |  |
| ip | inet |  |
| meta | jsonb | NOT NULL |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- INDEX `ix_audit_log_actor_id` (actor_id)
- INDEX `ix_audit_log_created_at` (created_at)

**database_connections**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| owner_id | uuid | FK → users.id ON DELETE CASCADE, NOT NULL |
| name | varchar(120) | NOT NULL |
| kind | varchar(32) | NOT NULL |
| status | varchar(16) | NOT NULL, DEFAULT active |
| host | varchar(255) |  |
| port | integer |  |
| database_name | varchar(128) |  |
| secret_ref | varchar(255) |  |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |
| updated_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- CHECK `ck_database_connections_kind`: `kind IN ('internal_warehouse', 'postgres_external')`
- CHECK `ck_database_connections_port`: `port IS NULL OR (port > 0 AND port < 65536)`
- CHECK `ck_database_connections_status`: `status IN ('active', 'disabled', 'error')`
- UNIQUE `uq_database_connections_owner_id_name` (owner_id, name)
- INDEX `ix_database_connections_owner_id` (owner_id)

**datasets**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| owner_id | uuid | FK → users.id ON DELETE CASCADE, NOT NULL |
| connection_id | uuid | FK → database_connections.id ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, NOT NULL |
| name | varchar(120) | NOT NULL |
| description | text |  |
| source_type | varchar(16) | NOT NULL |
| file_name | varchar(255) |  |
| schema_name | varchar(40) | NOT NULL, UNIQUE |
| reader_role | varchar(40) | NOT NULL, UNIQUE |
| status | varchar(16) | NOT NULL |
| status_reason | text |  |
| version | integer | NOT NULL, DEFAULT 1 |
| total_rows | bigint |  |
| size_bytes | bigint |  |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |
| updated_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- CHECK `ck_datasets_reader_role`: `reader_role ~ '^ds_[0-9a-f]{32}_r$'`
- CHECK `ck_datasets_schema_name`: `schema_name ~ '^ds_[0-9a-f]{32}$'`
- CHECK `ck_datasets_source_type`: `source_type IN ('demo', 'upload_csv')`
- CHECK `ck_datasets_status`: `status IN ('pending_review', 'loading', 'ready', 'failed', 'deleting')`
- UNIQUE `uq_datasets_owner_id_name` (owner_id, name)
- UNIQUE `uq_datasets_reader_role` (reader_role)
- UNIQUE `uq_datasets_schema_name` (schema_name)
- INDEX `ix_datasets_connection_id` (connection_id)
- INDEX `ix_datasets_owner_id_created_at` (owner_id, created_at DESC)

**dataset_tables**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| dataset_id | uuid | FK → datasets.id ON DELETE CASCADE, NOT NULL |
| table_name | varchar(63) | NOT NULL |
| display_name | varchar(255) | NOT NULL |
| description | text |  |
| row_count | bigint | NOT NULL |
| primary_key | jsonb | NOT NULL |

- UNIQUE `uq_dataset_tables_dataset_id_table_name` (dataset_id, table_name)
- INDEX `ix_dataset_tables_dataset_id` (dataset_id)

**dataset_columns**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| table_id | uuid | FK → dataset_tables.id ON DELETE CASCADE, NOT NULL |
| column_name | varchar(63) | NOT NULL |
| display_name | varchar(255) | NOT NULL |
| ordinal | integer | NOT NULL |
| data_type | varchar(16) | NOT NULL |
| inferred_type | varchar(16) |  |
| is_nullable | boolean | NOT NULL |
| is_primary_key | boolean | NOT NULL |
| semantic_role | varchar(16) |  |
| description | text |  |
| is_sensitive | boolean | NOT NULL, DEFAULT false |
| profile | jsonb | NOT NULL |

- CHECK `ck_dataset_columns_data_type`: `data_type IN ('integer', 'bigint', 'numeric', 'boolean', 'date', 'timestamptz', 'text')`
- CHECK `ck_dataset_columns_semantic_role`: `semantic_role IS NULL OR semantic_role IN ('identifier', 'measure', 'dimension', 'time', 'currency')`
- UNIQUE `uq_dataset_columns_table_id_column_name` (table_id, column_name)
- INDEX `ix_dataset_columns_table_id` (table_id)

**dataset_relationships**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| dataset_id | uuid | FK → datasets.id ON DELETE CASCADE, NOT NULL |
| from_table_id | uuid | FK → dataset_tables.id ON DELETE CASCADE, NOT NULL |
| from_column | varchar(63) | NOT NULL |
| to_table_id | uuid | FK → dataset_tables.id ON DELETE CASCADE, NOT NULL |
| to_column | varchar(63) | NOT NULL |
| origin | varchar(16) | NOT NULL |
| constraint_name | varchar(63) |  |

- CHECK `ck_dataset_relationships_origin`: `origin IN ('declared', 'inferred')`
- UNIQUE `uq_dataset_relationships_dataset_id_from_table_id_from_column_to_table_id_to_column` (dataset_id, from_table_id, from_column, to_table_id, to_column)
- INDEX `ix_dataset_relationships_dataset_id` (dataset_id)
- INDEX `ix_dataset_relationships_from_table_id` (from_table_id)
- INDEX `ix_dataset_relationships_to_table_id` (to_table_id)

**ingestion_jobs**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| dataset_id | uuid | FK → datasets.id ON DELETE CASCADE, NOT NULL |
| status | varchar(16) | NOT NULL |
| file_name | varchar(255) |  |
| file_size | bigint |  |
| upload_token | varchar(64) | UNIQUE |
| rows_total | bigint |  |
| rows_loaded | bigint |  |
| rows_rejected | bigint |  |
| issues | jsonb | NOT NULL |
| inferred_schema | jsonb | NOT NULL |
| error | text |  |
| started_at | timestamp with time zone |  |
| finished_at | timestamp with time zone |  |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- CHECK `ck_ingestion_jobs_status`: `status IN ('pending', 'running', 'succeeded', 'failed')`
- UNIQUE `uq_ingestion_jobs_upload_token` (upload_token)
- INDEX `ix_ingestion_jobs_dataset_id` (dataset_id)

**conversations**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| owner_id | uuid | FK → users.id ON DELETE CASCADE, NOT NULL |
| dataset_id | uuid | FK → datasets.id ON DELETE CASCADE, NOT NULL |
| title | varchar(200) | NOT NULL |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |
| updated_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- INDEX `ix_conversations_dataset_id` (dataset_id)
- INDEX `ix_conversations_owner_id_updated_at` (owner_id, updated_at DESC)

**messages**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| conversation_id | uuid | FK → conversations.id ON DELETE CASCADE, NOT NULL |
| analysis_session_id | uuid | FK → analysis_sessions.id ON DELETE SET NULL |
| role | varchar(16) | NOT NULL |
| content | text | NOT NULL |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- CHECK `ck_messages_role`: `role IN ('user', 'assistant', 'system')`
- INDEX `ix_messages_analysis_session_id` (analysis_session_id)
- INDEX `ix_messages_conversation_id_created_at` (conversation_id, created_at)

**analysis_sessions**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| conversation_id | uuid | FK → conversations.id ON DELETE CASCADE, NOT NULL |
| owner_id | uuid | FK → users.id ON DELETE CASCADE, NOT NULL |
| dataset_id | uuid | FK → datasets.id ON DELETE CASCADE, NOT NULL |
| dataset_version | integer | NOT NULL |
| question | text | NOT NULL |
| status | varchar(16) | NOT NULL |
| termination_reason | varchar(32) |  |
| understanding | jsonb |  |
| plan | jsonb |  |
| final_summary | text |  |
| error_code | varchar(64) |  |
| error_message | text |  |
| llm_calls | integer | NOT NULL, DEFAULT 0 |
| sql_executions | integer | NOT NULL, DEFAULT 0 |
| tokens_in | integer | NOT NULL, DEFAULT 0 |
| tokens_out | integer | NOT NULL, DEFAULT 0 |
| duration_ms | integer |  |
| started_at | timestamp with time zone |  |
| finished_at | timestamp with time zone |  |
| result | jsonb |  |
| memory | jsonb |  |
| llm_provider | varchar(32) |  |
| llm_model | varchar(120) |  |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- CHECK `ck_analysis_sessions_question_length`: `char_length(question) BETWEEN 1 AND 2000`
- CHECK `ck_analysis_sessions_status`: `status IN ('queued', 'running', 'awaiting_input', 'succeeded', 'partial', 'failed', 'cancelled')`
- `memory` (migration 0006): the compact per-turn record conversation memory reads (question, restated question, intent, metrics, dimensions, time range, headline figures, answer, dataset version). Built by code in `app/agent/memory.py`; NULL for sessions that finished before Phase 8 (the runner rebuilds it on the fly)
- INDEX `ix_analysis_sessions_active` (status) WHERE `status IN ('queued', 'running', 'awaiting_input')`
- INDEX `ix_analysis_sessions_conversation_id` (conversation_id)
- INDEX `ix_analysis_sessions_dataset_id` (dataset_id)
- INDEX `ix_analysis_sessions_owner_id_created_at` (owner_id, created_at DESC)

**agent_node_runs**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| analysis_session_id | uuid | FK → analysis_sessions.id ON DELETE CASCADE, NOT NULL |
| owner_id | uuid | FK → users.id ON DELETE CASCADE, NOT NULL |
| seq | integer | NOT NULL |
| node | varchar(40) | NOT NULL |
| status | varchar(16) | NOT NULL |
| started_at | timestamp with time zone | NOT NULL |
| duration_ms | integer | NOT NULL |
| summary | jsonb | NOT NULL |
| tool_calls | jsonb | NOT NULL |
| llm_calls | jsonb | NOT NULL |
| error | text |  |

- CHECK `ck_agent_node_runs_status`: `status IN ('succeeded', 'failed', 'degraded')`
- UNIQUE INDEX `uq_agent_node_runs_session_seq` (analysis_session_id, seq)

**query_executions**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| analysis_session_id | uuid | FK → analysis_sessions.id ON DELETE CASCADE |
| owner_id | uuid | FK → users.id ON DELETE CASCADE, NOT NULL |
| dataset_id | uuid | FK → datasets.id ON DELETE CASCADE, NOT NULL |
| origin | varchar(16) | NOT NULL |
| plan_step_id | varchar(16) |  |
| attempt | integer | NOT NULL |
| generated_sql | text |  |
| executed_sql | text |  |
| sql_fingerprint | varchar(64) |  |
| guard_status | varchar(16) | NOT NULL |
| guard_violations | jsonb | NOT NULL |
| exec_status | varchar(16) | NOT NULL |
| error_code | varchar(16) |  |
| error_message | text |  |
| row_count | bigint |  |
| truncated | boolean | NOT NULL |
| exec_ms | integer |  |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- CHECK `ck_query_executions_exec_status`: `exec_status IN ('not_run', 'ok', 'error', 'timeout', 'cancelled')`
- CHECK `ck_query_executions_guard_status`: `guard_status IN ('accepted', 'rejected', 'not_applicable')`
- CHECK `ck_query_executions_origin`: `origin IN ('agent', 'preview', 'widget_refresh', 'rerun')`
- INDEX `ix_query_executions_analysis_session_id` (analysis_session_id)
- INDEX `ix_query_executions_dataset_id` (dataset_id)
- INDEX `ix_query_executions_owner_id_created_at` (owner_id, created_at DESC)

**reports**

| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| owner_id | uuid | FK → users.id ON DELETE CASCADE, NOT NULL |
| analysis_session_id | uuid | FK → analysis_sessions.id ON DELETE SET NULL |
| dataset_id | uuid | FK → datasets.id ON DELETE SET NULL |
| title | varchar(200) | NOT NULL |
| summary | text | NOT NULL |
| summary_edited_by_user | boolean | NOT NULL |
| content | jsonb | NOT NULL |
| created_at | timestamp with time zone | NOT NULL, DEFAULT now() |
| updated_at | timestamp with time zone | NOT NULL, DEFAULT now() |

- `content` holds the report snapshot: v1 = question, dataset, SQL list; **v2 (Phase 8)** adds dataset tables, methodology, per-step SQL and rows, findings, recommendations, chart data and limitations (API_SPECIFICATION §7)
- INDEX `ix_reports_analysis_session_id` (analysis_session_id)
- INDEX `ix_reports_dataset_id` (dataset_id)
- INDEX `ix_reports_owner_id_created_at` (owner_id, created_at DESC)

## 5. Dataset schemas (`ds_<hex>`)

Lifecycle (`app/ingestion/warehouse.py`, all in **one** ingest transaction — PostgreSQL DDL is transactional, so a failure leaves nothing behind):

```sql
CREATE SCHEMA "ds_<hex>";
REVOKE ALL ON SCHEMA "ds_<hex>" FROM PUBLIC;
CREATE ROLE "ds_<hex>_r" NOLOGIN NOINHERIT;
CREATE TABLE "ds_<hex>"."<table>" (...);          -- PK if declared, else _row_id identity
COPY ... (asyncpg copy_records_to_table, 5 000-row batches)
-- demo only: ALTER TABLE ... ADD CONSTRAINT fk_<table>_<col> FOREIGN KEY ...; CREATE INDEX ix_<table>_<col> ...; ANALYZE
GRANT USAGE ON SCHEMA "ds_<hex>" TO "ds_<hex>_r";
GRANT SELECT ON ALL TABLES IN SCHEMA "ds_<hex>" TO "ds_<hex>_r";
GRANT "ds_<hex>_r" TO sageboard_executor;          -- PG16: CREATEROLE grants ADMIN on roles it created
```

- **Names.** Uploaded headers go through `normalize_identifier`: ASCII snake_case, camelCase split, `ß→ss`, accents stripped, `c_` prefix for a leading digit, `_col` suffix for reserved words, ≤ 63 bytes. Names that collide after normalisation are **rejected** with a message naming both headers (no silent `_2` suffixes). The original header is kept as `display_name`.
- **Surrogate key.** Uploaded tables without a primary key get `_row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY`. It gives previews a stable order and later gives evidence a row reference, and it is hidden from the catalog and the agent.
- **Identifier safety.** Schema, table, column and role names are validated against `^[a-z_][a-z0-9_]{0,62}$` (and the `ds_` patterns) and then double-quoted (`app/db/identifiers.py`). Values are never interpolated: they go through bind parameters or COPY.
- **Deletion.** `DROP SCHEMA … CASCADE; DROP ROLE …` in a transaction, then the metadata row. Tests assert that the schema and role are gone.

## 6. Demo dataset — “E-commerce demo”

Generated by `app/seed/ecommerce.py` (deterministic, seed `20261113`), loaded by `uv run python -m app.seed` (`--scale small|standard`, `--replace`, `--csv-out DIR`).

| Table | Standard scale rows | Key columns |
|---|---|---|
| customers | 3 000 | customer_id PK; region, segment, signup_date; first_name/last_name/email (**sensitive**) |
| products | 160 | product_id PK; sku, category, unit_price, is_active, launched_on |
| orders | 26 082 | order_id PK; customer_id → customers; order_date (timestamptz), status, channel, shipping_fee |
| order_items | 48 141 | order_item_id PK; order_id → orders; product_id → products; quantity, unit_price, discount |
| payments | 27 833 | payment_id PK; order_id → orders; method, status (captured/failed/voided/refunded), amount, paid_at |

The window is Nov 2024 – Oct 2026, across six US regions and six categories. Built-in, documented patterns give later evaluation known answers: seasonality, a Midwest slowdown from Q3 2026, channel and segment mixes, refunds and failed payments. There is deliberately **no cost/margin data**, so the agent must say it can't compute profit. Real FKs and indexes are created, so the catalog reports declared relationships.

## 7. Schema catalog (metadata for SQL generation)

`app/services/catalog.py` rebuilds the catalog from the **live** PostgreSQL catalog after every load. It never trusts the CSV header alone.

| Recorded | Where | Notes |
|---|---|---|
| Tables, row counts, descriptions | `dataset_tables` | Exact counts after load |
| Columns, ordinal, type, nullability, PK flag | `dataset_columns` | `inferred_type` kept when the user overrode it |
| Primary keys | `dataset_tables.primary_key` (jsonb list) | From `pg_constraint` |
| Foreign keys / relationships | `dataset_relationships` (`origin = declared`) | From `pg_constraint` |
| Semantic role | `dataset_columns.semantic_role` | identifier / measure / dimension / time / currency (heuristic, editable later) |
| Profile | `dataset_columns.profile` | null %, distinct count, min/max, top values (≤ 10 when ≤ 50 distinct) or 5 examples |
| Sensitivity | `dataset_columns.is_sensitive` | By name (email, phone, names, address, IDs, …) or by value shape (all e-mail addresses). **Sensitive columns get counts only — no samples, no min/max.** Owners can toggle it (PATCH). Turning it on erases stored samples |

`GET /datasets/{id}/schema` serves it at two levels. `summary` gives tables, descriptions and counts, for the understanding step (ADR-0007). `full` gives columns, types, keys, FKs, relationships and privacy-controlled samples, for SQL generation. `include_samples=false` strips all values.

## 8. Migrations

| Revision | Content |
|---|---|
| 0001 | `app` schema, extensions, baseline (Phase 1) |
| 0002 | All 12 application tables, FKs, CHECKs, indexes (Phase 3) |
| 0003 | `datasets.connection_id` FK → `NO ACTION DEFERRABLE INITIALLY DEFERRED` (found by the cascade test) |
| 0004 | `refresh_tokens` (hashed, rotating, family id), `audit_log` (INET ip, jsonb meta), `users.last_login_at` (Phase 4) |
| 0005 | `agent_node_runs` (node, status, duration, summary, tool and LLM calls; unique per session + seq) and `analysis_sessions.result` / `llm_provider` / `llm_model` (Phase 5) |
| 0006 | `analysis_sessions.memory` (JSONB, nullable): the per-turn conversation-memory record (Phase 8, D53) |

Alembic manages `app` only. `ds_%` schemas are excluded by `include_object`, and the version table is `app.alembic_version`. Tests run `downgrade base → upgrade head` and `alembic check` (models == migrations) against a dedicated `sageboard_test` database.

## 9. Planned tables (not built yet)

These stay as designed in v0.2 and arrive with the phase that needs them. Nothing in Phase 3 depends on them.

| Table(s) | Phase | Note |
|---|---|---|
| ~~`run_steps`, `tool_calls`, `llm_calls`~~ | built in Phase 5 as one table | `agent_node_runs` holds each node's tool and LLM calls as JSONB (one row per node run). `analysis_sessions` is the as-built name for v0.2's `analysis_runs` |
| `run_events` | 8 (streaming) | SSE replay log |
| `query_results` | later | Full result sets. Phase 5 stores each step's ≤50-row preview and chart data (≤200 rows) in `analysis_sessions.result`; `query_executions` (as built) is v0.2's `sql_queries` |
| ~~`visualizations`, `insights`, `insight_evidence`~~ | built in Phase 5 inside `result` | charts, facts, insights with evidence refs and the verification report are part of `analysis_sessions.result` (JSONB) |
| `dashboard_widgets` | 8 | |
| `user_settings`, `usage_counters` | Settings & hardening | `users.password_hash` stays nullable: the CLI demo user has no password and can't sign in |
