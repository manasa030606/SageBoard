"""Integration tests against a real PostgreSQL (skipped unless SAGEBOARD_TEST_DATABASE_URL)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings

pytestmark = pytest.mark.integration


def test_readyz_is_ready_with_a_reachable_database(db_url: str) -> None:
    with TestClient(create_app(make_settings(database_url=db_url))) as client:
        response = client.get("/api/v1/readyz")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["database"]["latency_ms"] is not None


def test_readyz_reports_unreachable_database_without_leaking_details() -> None:
    # Port 1 on localhost: nothing listens there, so the connection is refused quickly.
    url = "postgresql+asyncpg://nobody:topsecret@127.0.0.1:1/none"
    with TestClient(create_app(make_settings(database_url=url, db_connect_timeout_s=2))) as client:
        response = client.get("/api/v1/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["database"]["status"] == "unavailable"
    assert "topsecret" not in response.text
