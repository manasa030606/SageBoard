"""FastAPI dependencies shared by route modules.

Authentication and authorisation live here so route handlers never touch tokens,
cookies or ownership rules directly:

- ``CurrentUser``     the signed-in user (401 otherwise). Every service call receives it,
                      and every service query filters by ``owner_id`` (404 for others).
- ``csrf_protect``    double-submit check on POST/PUT/PATCH/DELETE (403 otherwise).
- ``rate_limit(...)`` per-key sliding-window limits (429 + Retry-After).
"""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.agent.runner import RunManager
from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER
from app.auth.ratelimit import RateLimiter
from app.auth.tokens import tokens_match
from app.core.config import Settings
from app.core.errors import CsrfError, RateLimitedError, ServiceUnavailableError
from app.db.engines import Databases
from app.db.models import User
from app.services.analysis import AnalysisService
from app.services.auth import AuthService
from app.services.connections import ConnectionService
from app.services.datasets import DatasetService
from app.services.health import HealthService
from app.services.history import HistoryService
from app.services.reports import ReportService

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


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


def client_ip(request: Request) -> str | None:
    """Client address as seen by uvicorn (run it with --proxy-headers behind a proxy).

    Only a parseable IP is returned; anything else (a test client, a bad proxy header)
    becomes None rather than breaking the audit log's INET column.
    """
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def get_auth_service(session: SessionDep, settings: SettingsDep) -> AuthService:
    return AuthService(session, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    request: Request, session: SessionDep, settings: SettingsDep, auth: AuthServiceDep
) -> User:
    if settings.auth_mode == "demo":
        # Local development only (refused when ENV=production): act as the seeded user.
        user = await session.scalar(
            select(User).where(User.email == settings.demo_user_email.lower(), User.is_active)
        )
        if user is None:
            raise ServiceUnavailableError(
                "The demo user doesn’t exist yet. Run `uv run python -m app.seed` in apps/api.",
                details={"hint": "seed"},
            )
    else:
        user = await auth.user_from_access_token(request.cookies.get(ACCESS_COOKIE))
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def csrf_protect(request: Request, settings: SettingsDep) -> None:
    """Double-submit CSRF check for cookie-authenticated, state-changing requests.

    A cross-site form or fetch can make the browser *send* our cookies, but it cannot
    *read* them or our responses, so it cannot copy the token into the header.
    """
    if settings.auth_mode == "demo" or request.method in SAFE_METHODS:
        return
    if not tokens_match(request.headers.get(CSRF_HEADER), request.cookies.get(CSRF_COOKIE)):
        raise CsrfError


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def enforce(limiter: RateLimiter, key: str, limit: int, window_s: float, message: str) -> None:
    retry_after = limiter.hit(key, limit, window_s)
    if retry_after is not None:
        raise RateLimitedError(retry_after, message)


def upload_rate_limit() -> Callable[..., Awaitable[None]]:
    async def dependency(user: CurrentUser, limiter: RateLimiterDep, settings: SettingsDep) -> None:
        enforce(
            limiter,
            f"upload:{user.id}",
            settings.uploads_per_hour,
            3600,
            "You’ve uploaded a lot of files in the last hour. Please wait before uploading more.",
        )

    return dependency


def get_run_manager(request: Request) -> RunManager:
    manager: RunManager = request.app.state.run_manager
    return manager


RunManagerDep = Annotated[RunManager, Depends(get_run_manager)]


async def analysis_rate_limit(
    user: CurrentUser, limiter: RateLimiterDep, settings: SettingsDep
) -> None:
    enforce(
        limiter,
        f"analysis:{user.id}",
        settings.analyses_per_hour,
        3600,
        "You’ve asked a lot of questions in the last hour. Please wait a little before asking more.",
    )


def get_dataset_service(
    session: SessionDep, databases: DatabasesDep, settings: SettingsDep
) -> DatasetService:
    return DatasetService(session, databases, settings)


DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]


def get_analysis_service(session: SessionDep) -> AnalysisService:
    return AnalysisService(session)


AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]


def get_history_service(session: SessionDep) -> HistoryService:
    return HistoryService(session)


HistoryServiceDep = Annotated[HistoryService, Depends(get_history_service)]


def get_report_service(session: SessionDep) -> ReportService:
    return ReportService(session)


ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]


def get_connection_service(session: SessionDep) -> ConnectionService:
    return ConnectionService(session)


ConnectionServiceDep = Annotated[ConnectionService, Depends(get_connection_service)]
