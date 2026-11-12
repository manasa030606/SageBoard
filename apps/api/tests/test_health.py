from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "sageboard-api"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "test"
    datetime.fromisoformat(body["timestamp"])  # valid ISO-8601


def test_readyz_without_database_is_not_ready(client: TestClient) -> None:
    response = client.get("/api/v1/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"]["status"] == "not_configured"
    assert body["checks"]["llm_config"]["status"] == "ok"


def test_responses_carry_a_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/healthz")
    assert response.headers["X-Request-ID"].startswith("req_")


def test_well_formed_incoming_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/api/v1/healthz", headers={"X-Request-ID": "trace-abc12345"})
    assert response.headers["X-Request-ID"] == "trace-abc12345"


def test_malformed_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/healthz", headers={"X-Request-ID": "<script>"})
    assert response.headers["X-Request-ID"].startswith("req_")


def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/healthz" in paths
    assert "/api/v1/readyz" in paths
