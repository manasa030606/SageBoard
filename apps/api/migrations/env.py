"""Alembic environment (async).

Scope: Alembic manages ONLY the ``app`` schema. Per-dataset ``ds_*`` schemas are
created at runtime by the ingestion service and the ``lg`` schema by the LangGraph
checkpointer, so both are excluded from autogenerate.
"""

from __future__ import annotations

import asyncio
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

APP_SCHEMA = "app"
config = context.config
target_metadata = None  # set to Base.metadata when ORM models arrive (Phase 2)


def _url() -> str:
    url = get_settings().migration_database_url
    if url is None:
        raise RuntimeError("MIGRATION_DATABASE_URL is not set (owner role, direct connection).")
    return url.get_secret_value()


def _include_object(obj: Any, name: str | None, type_: str, *_: Any) -> bool:
    schema = getattr(obj, "schema", None)
    return not (type_ == "table" and schema not in (None, APP_SCHEMA))


def _configure(connection: Connection | None = None, **kwargs: Any) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=APP_SCHEMA,
        include_schemas=True,
        include_object=_include_object,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


def _friendly_connection_error(exc: Exception) -> None:
    message = str(getattr(exc, "orig", exc)).strip().splitlines()[0]
    raise SystemExit(
        "\n✗ Could not connect to PostgreSQL for migrations:\n"
        f"  {message}\n\n"
        "  Fixes:\n"
        "  - Database roles not created yet?  bash infra/postgres/setup-local.sh\n"
        "  - Passwords out of sync?           make sure infra/.env and apps/api/.env\n"
        "                                     use the same SAGEBOARD_*_PASSWORD values,\n"
        "                                     then re-run setup-local.sh\n"
        "  - Server not running?              brew services start postgresql@16\n"
    ) from None


if context.is_offline_mode():
    run_migrations_offline()
else:
    try:
        asyncio.run(run_migrations_online())
    except (OSError, DBAPIError) as exc:
        _friendly_connection_error(exc)
