#!/usr/bin/env bash
# Sageboard — base database roles and hardening (idempotent).
#
# Runs automatically on first start of the Docker Compose Postgres container
# (docker-entrypoint-initdb.d). It can also be run by hand against any PostgreSQL 16
# (including Neon, connected as the project owner role) — see infra/README.md.
#
# Required environment variables (never hardcode passwords here):
#   POSTGRES_DB, SAGEBOARD_OWNER_PASSWORD, SAGEBOARD_APP_PASSWORD,
#   SAGEBOARD_INGEST_PASSWORD, SAGEBOARD_EXECUTOR_PASSWORD
#
# Role model (docs/adr/0002-database-topology-and-permissions.md):
#   sageboard_owner     owns the `app` and `lg` schemas, runs migrations
#   sageboard_app       API runtime: read/write on `app` only
#   sageboard_ingest    creates per-dataset schemas + reader roles (Phase 3)
#   sageboard_executor  runs analytical SQL; no privileges of its own (NOINHERIT),
#                       may only SET ROLE into a per-dataset reader role (Phase 3/4)
set -euo pipefail

: "${POSTGRES_DB:?}" "${SAGEBOARD_OWNER_PASSWORD:?}" "${SAGEBOARD_APP_PASSWORD:?}"
: "${SAGEBOARD_INGEST_PASSWORD:?}" "${SAGEBOARD_EXECUTOR_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER:-postgres}" \
  --dbname "$POSTGRES_DB" \
  -v db="$POSTGRES_DB" \
  -v owner_pw="$SAGEBOARD_OWNER_PASSWORD" \
  -v app_pw="$SAGEBOARD_APP_PASSWORD" \
  -v ingest_pw="$SAGEBOARD_INGEST_PASSWORD" \
  -v executor_pw="$SAGEBOARD_EXECUTOR_PASSWORD" <<'SQL'
-- psql variables are interpolated client-side; :'x' quotes a literal, :"x" an identifier.
SELECT format('CREATE ROLE sageboard_owner LOGIN PASSWORD %L', :'owner_pw')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sageboard_owner') \gexec
SELECT format('CREATE ROLE sageboard_app LOGIN PASSWORD %L', :'app_pw')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sageboard_app') \gexec
SELECT format('CREATE ROLE sageboard_ingest LOGIN CREATEROLE PASSWORD %L', :'ingest_pw')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sageboard_ingest') \gexec
SELECT format('CREATE ROLE sageboard_executor LOGIN NOINHERIT PASSWORD %L', :'executor_pw')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sageboard_executor') \gexec

-- Keep passwords in sync with the environment on every run (roles may pre-exist).
SELECT format('ALTER ROLE sageboard_owner PASSWORD %L', :'owner_pw') \gexec
SELECT format('ALTER ROLE sageboard_app PASSWORD %L', :'app_pw') \gexec
SELECT format('ALTER ROLE sageboard_ingest PASSWORD %L', :'ingest_pw') \gexec
SELECT format('ALTER ROLE sageboard_executor PASSWORD %L', :'executor_pw') \gexec

-- No role gets superuser, replication or RLS bypass.
ALTER ROLE sageboard_owner    NOSUPERUSER NOCREATEDB NOREPLICATION NOBYPASSRLS;
ALTER ROLE sageboard_app      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE sageboard_ingest   NOSUPERUSER NOCREATEDB NOREPLICATION NOBYPASSRLS;
ALTER ROLE sageboard_executor NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

-- Database-level hardening: nobody connects, creates schemas or temp tables by default.
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO sageboard_owner, sageboard_app, sageboard_ingest, sageboard_executor;
GRANT CREATE ON DATABASE :"db" TO sageboard_owner, sageboard_ingest;   -- schema creation only
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- Safety defaults applied to every session of the runtime roles.
ALTER ROLE sageboard_app      SET statement_timeout = '30s';
ALTER ROLE sageboard_executor SET statement_timeout = '10s';
ALTER ROLE sageboard_executor SET default_transaction_read_only = on;
ALTER ROLE sageboard_executor SET idle_in_transaction_session_timeout = '15s';

-- Application metadata schema. Tables arrive via Alembic migrations (Phase 2+),
-- created by sageboard_owner; default privileges give the app role DML on them.
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION sageboard_owner;
REVOKE ALL ON SCHEMA app FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO sageboard_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sageboard_owner IN SCHEMA app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sageboard_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sageboard_owner IN SCHEMA app
  GRANT USAGE, SELECT ON SEQUENCES TO sageboard_app;
SQL

echo "sageboard: base roles and schemas are in place"
