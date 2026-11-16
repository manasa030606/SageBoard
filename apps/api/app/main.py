"""FastAPI application factory.

``create_app`` wires configuration, logging, middleware, error handlers, the database
engine lifecycle and the versioned routers. Run locally with::

    uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.llm.client import StructuredLLM
from app.agent.llm.factory import build_llm
from app.agent.runner import RunManager, fail_interrupted_runs
from app.api.v1.router import api_router
from app.auth.ratelimit import RateLimiter
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    REQUEST_ID_HEADER,
    BodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.db.engines import Databases, open_databases
from app.ingestion.uploads import sweep_stale

log = get_logger(__name__)

# CPU-heavy work (CSV analysis and loading) runs in worker threads. With Python's default 5 ms
# switch interval such a thread can keep the GIL long enough to stall every other request for
# seconds (measured: a 20 MB CSV delayed /healthz by 2.3 s). A shorter interval hands the GIL
# back to the event loop promptly at no measurable cost to the worker.
GIL_SWITCH_INTERVAL_S = 0.0002


_FROM_SETTINGS = object()


def create_app(
    settings: Settings | None = None, *, agent_llm: StructuredLLM | object | None = _FROM_SETTINGS
) -> FastAPI:
    """``agent_llm`` overrides the model built from settings (tests inject a scripted one)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    llm = build_llm(settings) if agent_llm is _FROM_SETTINGS else agent_llm
    run_manager = RunManager(settings=settings, llm=llm)  # type: ignore[arg-type]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        sys.setswitchinterval(GIL_SWITCH_INTERVAL_S)
        databases = await open_databases(settings)
        app.state.databases = databases
        removed = sweep_stale(settings.upload_dir, settings.upload_ttl_minutes * 60)
        interrupted = 0
        if databases.sessions is not None:
            try:
                interrupted = await fail_interrupted_runs(databases.sessions)
            except Exception as exc:  # the API still starts; /readyz reports the database
                log.warning("startup.interrupted_runs_check_failed", error=type(exc).__name__)
        log.info(
            "startup",
            env=settings.env.value,
            version=settings.app_version,
            database_configured=databases.app_engine is not None,
            ingest_configured=databases.ingest is not None,
            executor_configured=databases.executor is not None,
            stale_uploads_removed=removed,
            llm_provider=settings.llm_provider.value,
            agent_available=run_manager.available,
            interrupted_runs_failed=interrupted,
            cors_origins=settings.cors_origins,
        )
        try:
            yield
        finally:
            await run_manager.shutdown()
            await databases.close()
            log.info("shutdown")

    app = FastAPI(
        title="Sageboard API",
        version=settings.app_version,
        lifespan=lifespan,
        # The API description and interactive docs are not published in production.
        openapi_url=None if settings.is_production else f"{settings.api_prefix}/openapi.json",
        docs_url=None if settings.is_production else f"{settings.api_prefix}/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    # Default so dependencies work even before lifespan runs (e.g. some test clients).
    app.state.databases = Databases(app_engine=None, sessions=None, ingest=None, executor=None)
    app.state.rate_limiter = RateLimiter()
    app.state.run_manager = run_manager

    # Middleware order: the last added runs first. CORS must wrap everything so that
    # error responses also carry CORS headers.
    app.add_middleware(
        BodyLimitMiddleware,
        upload_path=f"{settings.api_prefix}/datasets/uploads",
        upload_max_bytes=settings.upload_max_bytes,
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # explicit allowlist, never "*"
        allow_credentials=True,  # cookie auth arrives in Phase 2
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token", "Idempotency-Key"],
        expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
        max_age=600,
    )

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """``uvicorn app.main:app`` builds the app on first access, not at import time.

    Importing ``create_app`` (tests, scripts) therefore never reads the developer's
    ``.env`` or fails on its missing secrets.
    """
    global _app  # noqa: PLW0603 - one cached application per process
    if name != "app":
        raise AttributeError(name)
    if _app is None:
        _app = create_app()
    return _app
