# Sageboard — Database Design

| Field | Value |
|---|---|
| Document | DATABASE_DESIGN v0.2 |
| Status | Approved 2026-11-12 (v0.2). Decisions: see DECISION_LOG.md |
| Engine | PostgreSQL 16: Neon in production, Docker Compose locally (D5 final). SQLAlchemy 2.x (async, asyncpg) + Alembic |
| Permission model | [ADR-0002](adr/0002-database-topology-and-permissions.md): base roles implemented in Phase 1 by `infra/postgres/init/001_roles.sh` |

---

## 1. Logical layout

| Schema | Purpose | Managed by |
|---|---|---|
| `app` | Product metadata: users, datasets, conversations, runs, trace, results, reports, dashboards | Alembic migrations |
| `ds_<32-hex>` | One schema per dataset, holding the user's tables | Ingestion service at runtime |
| `lg` | LangGraph checkpoint tables (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`) | `AsyncPostgresSaver.setup()` |

Conventions:
- PKs are `uuid` (UUIDv7, generated in the app so they're time-ordered and index-friendly).
- `created_at` / `updated_at` are `timestamptz NOT NULL DEFAULT now()`.
- Enums are Postgres `text` + `CHECK` constraints. That's easier to migrate than native enums; Python `StrEnum` mirrors them.
- Soft deletes are **not** used. Deletes are hard deletes with `ON DELETE CASCADE` (privacy: FR-U3).
- JSON payloads use `jsonb`, and each one has a matching Pydantic model in code.

## 2. Entity-relationship overview

```
users 1─┬─* datasets 1─┬─* dataset_tables 1─* dataset_columns
        │              ├─* dataset_relationships (between dataset_tables)
        │              └─* ingestion_jobs
        ├─* conversations 1─* analysis_runs 1─┬─* run_events
        │        (dataset_id FK)               ├─* run_steps 1─* tool_calls
        │                                      ├─* llm_calls
        │                                      ├─* sql_queries 0..1─1 query_results
        │                                      ├─* visualizations
        │                                      ├─* insights 1─* insight_evidence
        │                                      └─0..1 reports
        ├─* reports
        ├─* dashboard_widgets (→ sql_queries, visualizations)
        ├─1 user_settings
        └─* usage_counters
audit_log (actor user_id nullable)
```

## 3. Table definitions (`app` schema)

### 3.1 Identity
**users**
| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| email | citext | UNIQUE NOT NULL |
| password_hash | text | NOT NULL (argon2id) |
| full_name | text | NOT NULL |
| is_active | boolean | DEFAULT true |
| last_login_at | timestamptz | |
| created_at, updated_at | timestamptz | |

**user_settings** (1:1)
| Column | Type | Notes |
|---|---|---|
| user_id | uuid | PK, FK users ON DELETE CASCADE |
| clarification_mode | text | CHECK in ('ask','assume') DEFAULT 'ask' |
| default_row_limit | int | DEFAULT 1000, CHECK 10..10000 |
| auto_charts | boolean | DEFAULT true |
| timezone | text | DEFAULT 'Asia/Kolkata' |
| updated_at | timestamptz | |

**refresh_tokens** (if the refresh-token rotation in D3 is adopted)
| id uuid PK | user_id FK | token_hash text UNIQUE | expires_at | revoked_at | created_at | user_agent text |

### 3.2 Datasets
**datasets**
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| owner_id | uuid | FK users ON DELETE CASCADE, indexed |
| name | text | NOT NULL; UNIQUE (owner_id, name) |
| description | text | |
| source_type | text | CHECK in ('upload_csv','upload_xlsx','sample','postgres_external') |
| schema_name | text | UNIQUE NOT NULL, `ds_<hex>`; CHECK `~ '^ds_[0-9a-f]{32}$'` |
| reader_role | text | `ds_<hex>_r` |
| status | text | CHECK in ('pending_review','loading','ready','failed','deleting') |
| status_reason | text | |
| version | int | DEFAULT 1; incremented on reload (reports record the version they used) |
| total_rows | bigint | |
| size_bytes | bigint | |
| created_at, updated_at | | |

**dataset_tables**
| id uuid PK | dataset_id FK CASCADE | table_name text (safe ident) | display_name text | description text | row_count bigint | UNIQUE(dataset_id, table_name) |

**dataset_columns**
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| table_id | uuid | FK dataset_tables CASCADE |
| column_name | text | safe ident; UNIQUE(table_id, column_name) |
| display_name | text | original header |
| ordinal | int | |
| data_type | text | CHECK in ('integer','bigint','numeric','boolean','date','timestamptz','text') |
| inferred_type | text | what inference suggested (for audit when overridden) |
| description | text | user glossary (FR-D6) |
| semantic_role | text | nullable CHECK in ('identifier','measure','dimension','time', 'currency') — inferred, editable |
| profile | jsonb | {null_pct, distinct_count, min, max, mean?, top_values:[{v,c}]≤10} |
| is_sensitive | boolean | DEFAULT false — if true, sample values are never sent to the LLM (SECURITY §6) |

**dataset_relationships** (join paths for the agent)
| id | dataset_id FK | from_table_id FK | from_column_id FK | to_table_id FK | to_column_id FK | origin text CHECK ('declared','inferred') | confidence numeric(3,2) |

**ingestion_jobs**
| id | dataset_id FK CASCADE | status ('queued','running','succeeded','failed') | file_name | file_size | rows_loaded | rows_rejected | rejected_samples jsonb (≤50) | warnings jsonb | started_at | finished_at | error text |

### 3.3 Conversations and runs
**conversations**
| id | owner_id FK CASCADE | dataset_id FK datasets CASCADE | title text | created_at | updated_at | INDEX(owner_id, updated_at DESC) |

**analysis_runs**
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK — also the LangGraph `thread_id` |
| conversation_id | uuid | FK CASCADE |
| owner_id | uuid | FK users CASCADE (denormalised for owner filtering) |
| dataset_id | uuid | FK datasets CASCADE |
| dataset_version | int | |
| question | text | NOT NULL, ≤ 2000 chars (CHECK) |
| status | text | CHECK in ('queued','running','awaiting_input','succeeded','partial','failed','cancelled') |
| termination_reason | text | mirrors AgentState |
| understanding | jsonb | QueryUnderstanding |
| plan | jsonb | AnalysisPlan |
| final_summary | text | |
| error_code, error_message | text | user-safe |
| llm_calls, sql_executions, tokens_in, tokens_out | int | |
| duration_ms | int | |
| idempotency_key | text | UNIQUE(owner_id, idempotency_key) |
| started_at, finished_at, created_at | timestamptz | |
| search_tsv | tsvector | GENERATED from question; GIN index (history search) |
Indexes: (owner_id, created_at DESC), (status) partial WHERE status IN ('queued','running').

**run_events** (append-only, SSE replay source)
| run_id FK CASCADE | seq int | type text | node text | payload jsonb | created_at | **PK(run_id, seq)** |

**run_steps** (one row per node execution)
| id | run_id FK | node text | plan_step_id text NULL | attempt int | status ('started','completed','failed') | input_summary jsonb | output jsonb | error_class text | latency_ms | started_at | finished_at |

**tool_calls**
| id | run_id FK | run_step_id FK | tool_name | invoked_by ('llm','node') | arguments jsonb | result_summary jsonb | status | latency_ms | created_at |

**llm_calls**
| id | run_id FK | run_step_id FK | provider | model | prompt_name | prompt_version | input_tokens | output_tokens | latency_ms | status ('ok','invalid_output','error') | retry_count | created_at |

Prompt/response bodies are **not** stored by default. A `DEBUG_STORE_PROMPTS` env flag (dev only) writes them to `llm_payloads` with a 7-day TTL.

**sql_queries**
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| run_id | uuid | FK CASCADE (nullable for widget refreshes → `origin`) |
| owner_id, dataset_id | uuid | |
| origin | text | ('agent','widget_refresh','rerun') |
| plan_step_id | text | |
| attempt | int | |
| generated_sql | text | raw LLM output |
| normalized_sql | text | Guard output (executed form) |
| sql_fingerprint | text | sha256 of normalised SQL (dedupe/repeat detection) |
| guard_status | text | ('accepted','rejected') |
| guard_violations | jsonb | [{code, message}] |
| explain_cost | numeric | |
| exec_status | text | ('not_run','ok','error','timeout','cancelled') |
| exec_error_code | text | SQLSTATE |
| exec_error_message | text | sanitised |
| row_count | int | |
| truncated | boolean | |
| exec_ms | int | |
| created_at | | INDEX(owner_id, created_at DESC) |

**query_results**
| id | sql_query_id FK UNIQUE CASCADE | columns jsonb [{name, pg_type}] | rows jsonb (≤ default_row_limit; the full fetched result up to the 10k cap is stored compressed) | row_count | byte_size | expires_at (D19 retention) |

Storage note: results ≤ 10k rows × typical widths fit comfortably in jsonb. Larger results are truncated and flagged. The retention job deletes expired results that aren't referenced by a report or widget.

### 3.4 Outputs
**visualizations**
| id | run_id FK CASCADE | sql_query_id FK | spec jsonb (ChartSpec) | created_at |

**insights**
| id | run_id FK CASCADE | ordinal | headline | detail | category | confidence | verification ('verified','rejected') | rejection_reason | verify_round int |

Rejected insights are stored too, for traceability; the UI shows only verified ones by default.

**insight_evidence**
| id | insight_id FK CASCADE | kind ('fact','cell','rows') | fact jsonb (ComputedFact snapshot) | sql_query_id FK | row_indices int[] | column_name |

**reports**
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| owner_id | uuid | FK CASCADE |
| run_id | uuid | FK analysis_runs ON DELETE SET NULL (report survives run deletion) |
| title | text | |
| summary | text | |
| summary_edited_by_user | boolean | |
| content | jsonb | immutable snapshot: sections, charts specs, table data (capped), insights + evidence, SQL appendix, dataset name/version |
| created_at, updated_at | | |

**dashboard_widgets**
| id | owner_id FK CASCADE | dataset_id FK CASCADE | title | kind ('chart','kpi','table') | sql_query_id FK (source query) | stored_sql text (normalised SQL snapshot) | spec jsonb | position jsonb {x,y,w,h} | last_refreshed_at | last_result_id FK query_results | last_error text |

### 3.5 Operations
**usage_counters** | owner_id | day date | runs int | llm_tokens int | PK(owner_id, day) |

**audit_log** | id | actor_id NULL | action ('login','login_failed','dataset.create','dataset.delete','guard.reject','account.delete',…) | target_type | target_id | ip inet | meta jsonb | created_at | INDEX(created_at), INDEX(actor_id) |

## 4. Dataset schemas (`ds_<hex>`)

- Table and column names come from `ingestion/identifiers.py`: lowercase snake_case, ASCII only, reserved words get a `_col` suffix, max 63 bytes, collisions de-duplicated with `_2`, `_3`.
- Each table gets a surrogate `_row_id bigint GENERATED ALWAYS AS IDENTITY` (useful for stable evidence row references). It's hidden from the agent's schema context.
- Created by the `sageboard_ingest` role, which owns the schema. After load:
  ```sql
  CREATE ROLE ds_<hex>_r NOLOGIN;
  GRANT USAGE ON SCHEMA ds_<hex> TO ds_<hex>_r;
  GRANT SELECT ON ALL TABLES IN SCHEMA ds_<hex> TO ds_<hex>_r;
  GRANT ds_<hex>_r TO sageboard_executor;   -- executor can SET ROLE into it
  ANALYZE ds_<hex>.<each table>;
  ```
- Indexes: ingestion creates btree indexes on inferred identifier/FK columns and date columns (cap 5 per table) to keep agent queries fast.
- Deletion: `DROP SCHEMA ds_<hex> CASCADE; DROP ROLE ds_<hex>_r;` inside a transaction, then delete the metadata.

## 5. Sample dataset (bundled, FR-D7)

`retail_demo`: `customers (≈2k)`, `regions (8)`, `products (≈150)`, `orders (≈25k, 2024-01..2025-12)`, `order_items (≈70k)`, `returns (≈2k)`. It is generated by a seeded, deterministic script (`packages/eval-datasets/generate_retail.py`) with planted, documented patterns (seasonality, one under-performing region, a pricing anomaly). The eval set (TESTING_STRATEGY §7) has known answers because of this.

Each user gets their own copy (an isolated `ds_` schema) when they first sign up. That keeps the isolation model uniform with uploads.

## 6. Migrations and lifecycle
- Alembic manages `app` only (`include_schemas`, with a filter excluding `ds_%` and `lg`). It runs as `sageboard_owner` over `MIGRATION_DATABASE_URL`, which must be Neon's **direct** endpoint. The version table is `app.alembic_version`. Baseline revision `0001` landed in Phase 1; application tables start in Phase 2.
- Migration 0001 creates the `app` schema, extensions (`citext`, `pgcrypto`) and base roles. In managed environments roles may need to be created out-of-band by the owner account (documented in the deploy runbook).
- Retention job (daily, in-process scheduler at startup or a platform cron): delete `query_results` past `expires_at` (default 30 days) that aren't referenced by reports or widgets, delete `run_events` older than 30 days for finished runs, and keep `analysis_runs`/`sql_queries` rows (small) for history.

## 7. Representative queries (shape check)
- History list: `SELECT ... FROM app.analysis_runs WHERE owner_id=$1 AND ($2::text IS NULL OR search_tsv @@ plainto_tsquery($2)) ORDER BY created_at DESC LIMIT 25` with keyset cursor on `(created_at, id)`.
- SSE replay: `SELECT seq, type, payload FROM app.run_events WHERE run_id=$1 AND seq > $2 ORDER BY seq`.
- Run detail: run + steps + sql_queries + insights in 4 indexed queries (no N+1 across attempts).
