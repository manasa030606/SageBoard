"""Migrations: full downgrade → upgrade round trip, and models match the migrations.

Runs first (file name) because it empties the test database's ``app`` schema.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest

from app.ingestion.warehouse import drop_schema
from tests.integration.conftest import PgUrls, fetch, run

pytestmark = pytest.mark.integration
API_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "alembic_version",
    "agent_node_runs",
    "users",
    "database_connections",
    "datasets",
    "dataset_tables",
    "dataset_columns",
    "dataset_relationships",
    "ingestion_jobs",
    "conversations",
    "messages",
    "analysis_sessions",
    "query_executions",
    "reports",
    "refresh_tokens",
    "audit_log",
}


def alembic(pg: PgUrls, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "MIGRATION_DATABASE_URL": pg.owner}
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def app_tables(pg: PgUrls) -> set[str]:
    rows = run(
        fetch(
            pg.owner, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'app'"
        )
    )
    return {r["table_name"] for r in rows}


async def _dataset_schemas(pg: PgUrls) -> list[tuple[str, str]]:
    rows = await fetch(pg.app, "SELECT schema_name, reader_role FROM app.datasets")
    return [(r["schema_name"], r["reader_role"]) for r in rows]


async def _drop_dataset_schemas(pg: PgUrls, pairs: list[tuple[str, str]]) -> None:
    conn = await asyncpg.connect(PgUrls.dsn(pg.ingest))
    try:
        for schema, role in pairs:
            async with conn.transaction():
                await drop_schema(conn, schema, role)
    finally:
        await conn.close()


def test_downgrade_to_base_and_upgrade_to_head(pg: PgUrls) -> None:
    # Datasets own warehouse schemas outside Alembic's reach: drop them first so the
    # downgrade doesn't orphan them.
    if "datasets" in app_tables(pg):
        run(_drop_dataset_schemas(pg, run(_dataset_schemas(pg))))

    down = alembic(pg, "downgrade", "base")
    assert down.returncode == 0, down.stderr
    assert app_tables(pg) <= {"alembic_version"}

    up = alembic(pg, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    assert app_tables(pg) == EXPECTED_TABLES
    version = run(fetch(pg.owner, "SELECT version_num FROM app.alembic_version"))
    assert version[0]["version_num"] == "0006"


def test_models_match_migrations(pg: PgUrls) -> None:
    result = alembic(pg, "check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_expected_indexes_and_constraints_exist(pg: PgUrls) -> None:
    rows = run(fetch(pg.owner, "SELECT indexname FROM pg_indexes WHERE schemaname = 'app'"))
    indexes = {r["indexname"] for r in rows}
    for name in (
        "uq_users_email_lower",
        "ix_datasets_owner_id_created_at",
        "ix_conversations_owner_id_updated_at",
    ):
        assert name in indexes, f"missing index {name}"
    fks = run(
        fetch(
            pg.owner,
            "SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname = 'app' AND c.contype = 'f'",
        )
    )
    assert len(fks) >= 15


def test_app_role_has_dml_but_no_ddl_on_app_tables(pg: PgUrls) -> None:
    rows = run(
        fetch(
            pg.owner,
            "SELECT DISTINCT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'sageboard_app' AND table_schema = 'app'",
        )
    )
    assert {r["privilege_type"] for r in rows} == {"SELECT", "INSERT", "UPDATE", "DELETE"}
