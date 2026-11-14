"""Integration tests for the base role model (docs/adr/0002).

They connect as the real runtime roles and assert that PostgreSQL itself refuses
what each role must not do. Skipped unless the role-specific URLs are provided:

    SAGEBOARD_TEST_DATABASE_URL           (sageboard_app)
    SAGEBOARD_TEST_EXECUTOR_DATABASE_URL  (sageboard_executor)

Run ``alembic upgrade head`` first so ``app.alembic_version`` exists.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import asyncpg
import pytest

pytestmark = pytest.mark.integration


def _dsn(env_var: str) -> str:
    url = os.environ.get(env_var)
    if not url:
        pytest.skip(f"{env_var} not set (integration test)")
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture
async def app_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(_dsn("SAGEBOARD_TEST_DATABASE_URL"))
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def executor_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(_dsn("SAGEBOARD_TEST_EXECUTOR_DATABASE_URL"))
    try:
        yield conn
    finally:
        await conn.close()


# --------------------------------------------------------------------- app role
async def test_app_role_can_read_app_metadata(app_conn: asyncpg.Connection) -> None:
    assert await app_conn.fetchval("SELECT current_user") == "sageboard_app"
    # Granted through default privileges on tables created by sageboard_owner.
    assert await app_conn.fetchval("SELECT version_num FROM app.alembic_version") == "0004"


async def test_app_role_cannot_create_schema_objects(app_conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("CREATE TABLE app.should_fail (id int)")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("CREATE TABLE public.should_fail (id int)")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("CREATE SCHEMA should_fail")


async def test_app_role_cannot_alter_migration_history(app_conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_conn.execute("DROP TABLE app.alembic_version")


# ---------------------------------------------------------------- executor role
async def test_executor_sessions_are_read_only(executor_conn: asyncpg.Connection) -> None:
    assert await executor_conn.fetchval("SHOW default_transaction_read_only") == "on"
    assert await executor_conn.fetchval("SHOW statement_timeout") == "10s"
    with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
        await executor_conn.execute("CREATE TEMP TABLE should_fail (id int)")


async def test_executor_cannot_read_app_metadata(executor_conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await executor_conn.fetch("SELECT * FROM app.alembic_version")


async def test_executor_cannot_switch_to_privileged_roles(
    executor_conn: asyncpg.Connection,
) -> None:
    # Superusers differ by install (`postgres` in Docker/Linux, your macOS user name with
    # Homebrew, `neondb_owner` on Neon), so test whichever ones actually exist.
    superusers = [
        r["rolname"]
        for r in await executor_conn.fetch("SELECT rolname FROM pg_roles WHERE rolsuper")
    ]
    assert superusers, "expected at least one superuser role"
    for role in ("sageboard_app", "sageboard_owner", "sageboard_ingest", *superusers):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await executor_conn.execute(f'SET ROLE "{role}"')
