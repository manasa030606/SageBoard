"""Health and readiness logic (kept out of the route handlers)."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.logging import get_logger
from app.schemas.health import DependencyCheck, HealthResponse, ReadinessResponse

log = get_logger(__name__)

DB_CHECK_TIMEOUT_S = 3.0


class HealthService:
    def __init__(self, settings: Settings, engine: AsyncEngine | None) -> None:
        self._settings = settings
        self._engine = engine

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
        if self._engine is None:
            return DependencyCheck(status="not_configured", detail="DATABASE_URL is not set.")
        start = time.perf_counter()
        try:
            async with asyncio.timeout(DB_CHECK_TIMEOUT_S), self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # any failure means "not ready"; details go to logs only
            log.warning("readiness_db_failed", error_type=type(exc).__name__)
            return DependencyCheck(status="unavailable", detail="Database is unreachable.")
        return DependencyCheck(
            status="ok", latency_ms=round((time.perf_counter() - start) * 1000, 1)
        )

    def _check_llm_config(self) -> DependencyCheck:
        # Configuration is validated at startup (Settings). No network call is made here:
        # provider connectivity is checked by the adapter introduced in Phase 5.
        return DependencyCheck(status="ok", detail=f"provider={self._settings.llm_provider.value}")
