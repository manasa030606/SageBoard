"""Response models for the health endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

CheckStatus = Literal["ok", "unavailable", "not_configured"]


class HealthResponse(BaseModel):
    """Liveness: the process is up and serving requests."""

    status: Literal["ok"]
    service: str
    version: str
    environment: str
    timestamp: datetime


class DependencyCheck(BaseModel):
    status: CheckStatus
    latency_ms: float | None = None
    detail: str | None = None


class ReadinessResponse(BaseModel):
    """Readiness: every required dependency is usable."""

    status: Literal["ready", "not_ready"]
    service: str
    version: str
    timestamp: datetime
    checks: dict[str, DependencyCheck]
