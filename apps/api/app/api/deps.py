"""FastAPI dependencies shared by route modules."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.db.engines import Databases
from app.db.models import User
from app.services.datasets import DatasetService
from app.services.health import HealthService


def get_app_settings(request: Request) -> Settings:
    """The settings the running app was created with (not a fresh global read)."""
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_databases(request: Request) -> Databases:
    databases: Databases = request.app.state.databases
    return databases


DatabasesDep = Annotated[Databases, Depends(get_databases)]


def get_engine(databases: DatabasesDep) -> AsyncEngine | None:
    return databases.app_engine


def get_health_service(settings: SettingsDep, databases: DatabasesDep) -> HealthService:
    return HealthService(settings, databases)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


async def get_session(databases: DatabasesDep) -> AsyncIterator[AsyncSession]:
    if databases.sessions is None:
        raise ServiceUnavailableError("The application database is not configured.")
    async with databases.sessions() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(session: SessionDep, settings: SettingsDep) -> User:
    """Identity until authentication lands: every request acts as the seeded demo user.

    Settings validation refuses AUTH_MODE=demo in production, so this cannot ship as-is.
    All services take the user explicitly, so real auth replaces only this function.
    """
    user = await session.scalar(
        select(User).where(User.email == settings.demo_user_email.lower(), User.is_active)
    )
    if user is None:
        raise ServiceUnavailableError(
            "The demo user doesn’t exist yet. Run `uv run python -m app.seed` in apps/api.",
            details={"hint": "seed"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_dataset_service(
    session: SessionDep, databases: DatabasesDep, settings: SettingsDep
) -> DatasetService:
    return DatasetService(session, databases, settings)


DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]
