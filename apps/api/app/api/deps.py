"""FastAPI dependencies shared by route modules."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.services.health import HealthService


def get_app_settings(request: Request) -> Settings:
    """The settings the running app was created with (not a fresh global read)."""
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_engine(request: Request) -> AsyncEngine | None:
    engine: AsyncEngine | None = request.app.state.db_engine
    return engine


def get_health_service(
    settings: SettingsDep, engine: Annotated[AsyncEngine | None, Depends(get_engine)]
) -> HealthService:
    return HealthService(settings, engine)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
