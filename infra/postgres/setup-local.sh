#!/usr/bin/env bash
# Sageboard — prepare a NATIVE local PostgreSQL (no Docker needed).
#
# Works with PostgreSQL installed via Homebrew (`brew install postgresql@16`)
# or Postgres.app on macOS, and with distro packages on Linux.
#
# What it does (safe to run repeatedly):
#   1. loads passwords from infra/.env
#   2. finds psql and checks the server is reachable
#   3. creates the `sageboard` database if it does not exist
#   4. runs infra/postgres/init/001_roles.sh (roles, hardening, `app` schema)
#
# Usage (from the repository root):
#   bash infra/postgres/setup-local.sh
#
# Optional overrides:
#   PG_SUPERUSER  admin role to connect as (default: your macOS username,
#                 which is what Homebrew and Postgres.app create)
#   PGHOST / PGPORT / PGPASSWORD  standard libpq variables
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/infra/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "✗ $ENV_FILE not found. Run: cp infra/.env.example infra/.env" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# --- locate psql -------------------------------------------------------------
if ! command -v psql >/dev/null 2>&1; then
  for dir in /opt/homebrew/opt/postgresql@16/bin /usr/local/opt/postgresql@16/bin \
             /Applications/Postgres.app/Contents/Versions/latest/bin; do
    if [[ -x "$dir/psql" ]]; then export PATH="$dir:$PATH"; break; fi
  done
fi
if ! command -v psql >/dev/null 2>&1; then
  cat >&2 <<'MSG'
✗ psql was not found. Install PostgreSQL 16, for example:
    brew install postgresql@16 && brew services start postgresql@16
  then add it to your PATH:
    echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
MSG
  exit 1
fi

export PGHOST="${PGHOST:-localhost}"
export PGPORT="${PGPORT:-${POSTGRES_PORT:-5432}}"
SUPERUSER="${PG_SUPERUSER:-$(whoami)}"
DB="${POSTGRES_DB:-sageboard}"

# --- check the server ----------------------------------------------------------
if ! psql -U "$SUPERUSER" -d postgres -tAc "SELECT 1" >/dev/null 2>&1; then
  cat >&2 <<MSG
✗ Could not connect to PostgreSQL at $PGHOST:$PGPORT as "$SUPERUSER".
  - Is the server running?  brew services list   (start: brew services start postgresql@16)
  - Different admin user?   PG_SUPERUSER=postgres bash infra/postgres/setup-local.sh
MSG
  exit 1
fi

VERSION_NUM="$(psql -U "$SUPERUSER" -d postgres -tAc "SHOW server_version_num")"
echo "• Connected to PostgreSQL $(psql -U "$SUPERUSER" -d postgres -tAc "SHOW server_version") at $PGHOST:$PGPORT as $SUPERUSER"
if (( VERSION_NUM < 160000 )); then
  echo "! Sageboard targets PostgreSQL 16 (Neon in production). Your server is older;"
  echo "  it will probably work for Phase 1, but please upgrade: brew install postgresql@16"
fi

# --- database ------------------------------------------------------------------
if [[ "$(psql -U "$SUPERUSER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB'")" != "1" ]]; then
  createdb -U "$SUPERUSER" "$DB"
  echo "• Created database $DB"
else
  echo "• Database $DB already exists"
fi

# --- roles, hardening, app schema -----------------------------------------------
POSTGRES_USER="$SUPERUSER" POSTGRES_DB="$DB" bash "$ROOT/infra/postgres/init/001_roles.sh" >/dev/null
echo "• Roles and schemas are in place (sageboard_owner, sageboard_app, sageboard_ingest, sageboard_executor)"
echo
echo "✓ Done. Next: make migrate   (or: cd apps/api && uv run alembic upgrade head)"
