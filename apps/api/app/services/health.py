"""Health and readiness logic (kept out of the route handlers)."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import asyncpg
from sqlalchemy import text

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.engines import Databases
from app.schemas.health import DependencyCheck, HealthResponse, ReadinessResponse

log = get_logger(__name__)

DB_CHECK_TIMEOUT_S = 3.0


class HealthService:
    def __init__(self, settings: Settings, databases: Databases) -> None:
        self._settings = settings
        self._databases = databases

    def liveness(self) -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=self._settings.app_name,
            version=self._settings.app_version,
            environment=self._settings.env.value,
            timestamp=datetime.now(UTC),
        )

    async def readiness(self) -> ReadinessResponse:
        checks = {
            "database": await self._check_database(),
            "ingest_database": await self._check_pool(
                self._databases.ingest, "INGEST_DATABASE_URL", "ingest"
            ),
            "executor_database": await self._check_pool(
                self._databases.executor, "EXECUTOR_DATABASE_URL", "executor"
            ),
            "llm_config": self._check_llm_config(),
        }
        ready = all(check.status == "ok" for check in checks.values())
        return ReadinessResponse(
            status="ready" if ready else "not_ready",
            service=self._settings.app_name,
            version=self._settings.app_version,
            timestamp=datetime.now(UTC),
            checks=checks,
        )

    async def _check_database(self) -> DependencyCheck:
        engine = self._databases.app_engine
        if engine is None:
            return DependencyCheck(status="not_configured", detail="DATABASE_URL is not set.")
        start = time.perf_counter()
        try:
            async with asyncio.timeout(DB_CHECK_TIMEOUT_S), engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # any failure means "not ready"; details go to logs only
            log.warning("readiness_db_failed", error_type=type(exc).__name__)
            return DependencyCheck(status="unavailable", detail="Database is unreachable.")
        return DependencyCheck(
            status="ok", latency_ms=round((time.perf_counter() - start) * 1000, 1)
        )

    async def _check_pool(
        self, pool: asyncpg.Pool | None, env_name: str, label: str
    ) -> DependencyCheck:
        if pool is None:
            return DependencyCheck(status="not_configured", detail=f"{env_name} is not set.")
        start = time.perf_counter()
        try:
            async with asyncio.timeout(DB_CHECK_TIMEOUT_S), pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as exc:
            log.warning("readiness_pool_failed", pool=label, error_type=type(exc).__name__)
            return DependencyCheck(
                status="unavailable", detail=f"The {label} connection is unreachable."
            )
        return DependencyCheck(
            status="ok", latency_ms=round((time.perf_counter() - start) * 1000, 1)
        )

    def _check_llm_config(self) -> DependencyCheck:
        # Configuration is validated at startup (Settings). No network call is made here:
        # provider connectivity is checked by the adapter introduced in Phase 5.
        return DependencyCheck(status="ok", detail=f"provider={self._settings.llm_provider.value}")
