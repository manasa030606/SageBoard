"""Fixtures for tests that run against a real PostgreSQL.

Skipped unless all four role-specific URLs point at a **dedicated test database**
(prepared with ``bash infra/postgres/setup-local.sh --db sageboard_test``):

    SAGEBOARD_TEST_DATABASE_URL            sageboard_app
    SAGEBOARD_TEST_INGEST_DATABASE_URL     sageboard_ingest
    SAGEBOARD_TEST_EXECUTOR_DATABASE_URL   sageboard_executor
    SAGEBOARD_TEST_MIGRATION_DATABASE_URL  sageboard_owner (migrations)

The migration test downgrades to an empty schema, so never point these at real data.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.engines import open_databases
from app.main import create_app
from app.seed.demo import seed_demo
from tests.conftest import make_settings

ENV = {
    "app": "SAGEBOARD_TEST_DATABASE_URL",
    "ingest": "SAGEBOARD_TEST_INGEST_DATABASE_URL",
    "executor": "SAGEBOARD_TEST_EXECUTOR_DATABASE_URL",
    "owner": "SAGEBOARD_TEST_MIGRATION_DATABASE_URL",
}


@dataclass(frozen=True)
class PgUrls:
    app: str
    ingest: str
    executor: str
    owner: str

    @staticmethod
    def dsn(url: str) -> str:
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on a fresh loop (sync tests talk to asyncpg this way)."""
    return asyncio.run(coro)


async def fetch(url: str, sql: str, *args: Any) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(PgUrls.dsn(url))
    try:
        rows: list[asyncpg.Record] = await conn.fetch(sql, *args)
        return rows
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def pg() -> PgUrls:
    missing = [v for v in ENV.values() if not os.environ.get(v)]
    if missing:
        pytest.skip(f"integration test: set {', '.join(missing)}")
    return PgUrls(**{k: os.environ[v] for k, v in ENV.items()})


@pytest.fixture
def pg_settings(pg: PgUrls, tmp_path: Path) -> Callable[..., Settings]:
    def factory(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "database_url": pg.app,
            "ingest_database_url": pg.ingest,
            "executor_database_url": pg.executor,
            "upload_dir": tmp_path / "uploads",
            "demo_dataset_scale": "small",
        }
        values.update(overrides)
        return make_settings(**values)

    return factory


async def _seed(settings: Settings, **kwargs: Any) -> Any:
    databases = await open_databases(settings)
    try:
        return await seed_demo(databases, settings, **kwargs)
    finally:
        await databases.close()


@pytest.fixture
def seed(pg_settings: Callable[..., Settings]) -> Callable[..., Any]:
    """Seed the demo dataset (small scale) into the test database."""

    def do(**kwargs: Any) -> Any:
        kwargs.setdefault("scale", "small")
        return run(_seed(pg_settings(), **kwargs))

    return do


PASSWORD = "correct horse battery staple"


def sign_up(
    client: TestClient, email: str | None = None, name: str = "Test Analyst"
) -> dict[str, Any]:
    """Register a fresh account; the client keeps its cookies and sends the CSRF header."""
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.test"
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD, "full_name": name}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    client.headers["X-CSRF-Token"] = body["csrf_token"]
    return body


@contextmanager
def signed_in(settings: Settings, *, with_demo: bool = True) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        sign_up(client)
        if with_demo:
            response = client.post("/api/v1/datasets/demo")
            assert response.status_code in {200, 201}, response.text
        yield client


@pytest.fixture
def api(pg_settings: Callable[..., Settings]) -> Iterator[TestClient]:
    """A signed-in user with their own copy of the (small) demo dataset."""
    with signed_in(pg_settings()) as client:
        yield client
