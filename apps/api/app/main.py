"""FastAPI application factory.

``create_app`` wires configuration, logging, middleware, error handlers, the database
engine lifecycle and the versioned routers. Run locally with::

    uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.db.engines import Databases, open_databases
from app.ingestion.uploads import sweep_stale

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        databases = await open_databases(settings)
        app.state.databases = databases
        removed = sweep_stale(settings.upload_dir, settings.upload_ttl_minutes * 60)
        log.info(
            "startup",
            env=settings.env.value,
            version=settings.app_version,
            database_configured=databases.app_engine is not None,
            ingest_configured=databases.ingest is not None,
            executor_configured=databases.executor is not None,
            stale_uploads_removed=removed,
            llm_provider=settings.llm_provider.value,
            cors_origins=settings.cors_origins,
        )
        try:
            yield
        finally:
            await databases.close()
            log.info("shutdown")

    app = FastAPI(
        title="Sageboard API",
        version=settings.app_version,
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        # Interactive docs only outside production.
        docs_url=None if settings.is_production else f"{settings.api_prefix}/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    # Default so dependencies work even before lifespan runs (e.g. some test clients).
    app.state.databases = Databases(app_engine=None, sessions=None, ingest=None, executor=None)

    # Middleware order: the last added runs first. CORS must wrap everything so that
    # error responses also carry CORS headers.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # explicit allowlist, never "*"
        allow_credentials=True,  # cookie auth arrives in Phase 2
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token", "Idempotency-Key"],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
