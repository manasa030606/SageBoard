from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

ALLOWED_ORIGIN = "http://localhost:3000"


TEST_JWT_SECRET = "test-only-secret-" + "x" * 40


def make_settings(**overrides: Any) -> Settings:
    """Settings built only from explicit values: never reads the developer's .env."""
    base: dict[str, Any] = {
        "env": "test",
        "log_json": False,
        "log_level": "WARNING",
        "cors_origins": [ALLOWED_ORIGIN],
        "database_url": None,
        "llm_provider": "mock",
        "jwt_secret": TEST_JWT_SECRET,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings_factory() -> Callable[..., Settings]:
    return make_settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(make_settings())) as test_client:
        yield test_client


@pytest.fixture
def db_url() -> str:
    url = os.environ.get("SAGEBOARD_TEST_DATABASE_URL")
    if not url:
        pytest.skip("SAGEBOARD_TEST_DATABASE_URL not set (integration test)")
    return url
