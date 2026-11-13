"""Connection management for the three database identities (ADR-0002).

| Pool        | Role                | Used for                                   | Driver          |
|-------------|---------------------|--------------------------------------------|-----------------|
| app         | sageboard_app       | application metadata (users, datasets, …)  | SQLAlchemy      |
| ingest      | sageboard_ingest    | create dataset schemas, COPY data, profile | asyncpg (COPY)  |
| executor    | sageboard_executor  | read-only queries via SET LOCAL ROLE       | asyncpg         |

The pools never share credentials, and the frontend never sees any of them.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.session import create_engine, create_session_factory


def asyncpg_dsn(sqlalchemy_url: str) -> str:
    """'postgresql+asyncpg://…' → 'postgresql://…' for the raw asyncpg driver."""
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@dataclass
class Databases:
    app_engine: AsyncEngine | None
    sessions: async_sessionmaker[AsyncSession] | None
    ingest: asyncpg.Pool | None
    executor: asyncpg.Pool | None

    async def close(self) -> None:
        for pool in (self.ingest, self.executor):
            if pool is not None:
                await pool.close()
        if self.app_engine is not None:
            await self.app_engine.dispose()


async def _pool(url: str, settings: Settings, name: str, max_size: int) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        asyncpg_dsn(url),
        min_size=0,  # lazy: the service still starts if a database is briefly unreachable
        max_size=max_size,
        timeout=settings.db_connect_timeout_s,
        statement_cache_size=0,  # compatible with transaction-mode poolers (Neon)
        server_settings={"application_name": f"{settings.app_name}:{name}"},
    )
    assert pool is not None  # noqa: S101 - create_pool only returns None when awaited inside a context
    return pool


async def open_databases(settings: Settings) -> Databases:
    engine = create_engine(settings)
    sessions = create_session_factory(engine) if engine is not None else None
    ingest = (
        await _pool(settings.ingest_database_url.get_secret_value(), settings, "ingest", 3)
        if settings.ingest_database_url
        else None
    )
    executor = (
        await _pool(settings.executor_database_url.get_secret_value(), settings, "executor", 5)
        if settings.executor_database_url
        else None
    )
    return Databases(app_engine=engine, sessions=sessions, ingest=ingest, executor=executor)
