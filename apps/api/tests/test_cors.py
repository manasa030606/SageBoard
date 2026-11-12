from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ALLOWED_ORIGIN


def test_preflight_from_allowed_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/healthz",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type, X-Request-ID",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_preflight_from_disallowed_origin_is_refused(client: TestClient) -> None:
    response = client.options(
        "/api/v1/healthz",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_simple_request_from_disallowed_origin_gets_no_cors_headers(client: TestClient) -> None:
    response = client.get("/api/v1/healthz", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_request_id_header_is_exposed_to_browsers(client: TestClient) -> None:
    response = client.get("/api/v1/healthz", headers={"Origin": ALLOWED_ORIGIN})
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]


def test_error_responses_also_carry_cors_headers(client: TestClient) -> None:
    response = client.get("/api/v1/missing", headers={"Origin": ALLOWED_ORIGIN})
    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
