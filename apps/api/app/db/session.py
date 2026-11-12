"""Async SQLAlchemy engine for the *application metadata* connection.

This engine connects as the application role (``sageboard_app``). Dataset queries
will use a separate, restricted executor pool introduced in Phase 4 — the two are
never shared (docs/adr/0002-database-topology-and-permissions.md).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine | None:
    """Create the app engine, or ``None`` when no DATABASE_URL is configured."""
    if settings.database_url is None:
        return None
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.db_connect_timeout_s,
            "server_settings": {"application_name": settings.app_name},
            # Required when connecting through a transaction-mode pooler such as
            # Neon's PgBouncer endpoint; harmless on a direct connection.
            "statement_cache_size": 0,
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
