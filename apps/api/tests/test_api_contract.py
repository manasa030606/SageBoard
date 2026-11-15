"""API contract without a database: route inventory, documentation, failure handling."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.cookies import ACCESS_COOKIE
from app.auth.tokens import create_access_token
from app.main import create_app
from tests.conftest import TEST_JWT_SECRET, make_settings

API = "/api/v1"
EXPECTED_OPERATIONS = {
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
    ("GET", "/auth/me"),
    ("GET", "/datasets"),
    ("POST", "/datasets/uploads"),
    ("POST", "/datasets/demo"),
    ("POST", "/datasets/{dataset_id}/finalize"),
    ("GET", "/datasets/{dataset_id}"),
    ("PATCH", "/datasets/{dataset_id}"),
    ("DELETE", "/datasets/{dataset_id}"),
    ("GET", "/datasets/{dataset_id}/schema"),
    ("GET", "/datasets/{dataset_id}/jobs"),
    ("GET", "/datasets/{dataset_id}/tables/{table_name}/preview"),
    ("PATCH", "/datasets/{dataset_id}/tables/{table_id}"),
    ("PATCH", "/datasets/{dataset_id}/columns/{column_id}"),
    ("GET", "/connections"),
    ("GET", "/conversations"),
    ("POST", "/conversations"),
    ("GET", "/conversations/{conversation_id}"),
    ("PATCH", "/conversations/{conversation_id}"),
    ("DELETE", "/conversations/{conversation_id}"),
    ("POST", "/conversations/{conversation_id}/sessions"),
    ("GET", "/analysis-sessions/{session_id}"),
    ("POST", "/analysis-sessions/{session_id}/cancel"),
    ("GET", "/analysis-sessions/{session_id}/trace"),
    ("GET", "/history/sessions"),
    ("GET", "/history/queries"),
    ("GET", "/reports"),
    ("POST", "/reports"),
    ("GET", "/reports/{report_id}"),
    ("PATCH", "/reports/{report_id}"),
    ("DELETE", "/reports/{report_id}"),
    ("GET", "/reports/{report_id}/export.md"),
    ("GET", "/reports/{report_id}/export.pdf"),
}
PUBLIC = {
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
}
UNREACHABLE_DB = "postgresql+asyncpg://sageboard_app:SuperSecretPw@127.0.0.1:1/sageboard"


def openapi() -> dict[str, Any]:
    spec: dict[str, Any] = create_app(make_settings()).openapi()
    return spec


def operations(spec: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (method.upper(), path.removeprefix(API)): op
        for path, item in spec["paths"].items()
        for method, op in item.items()
    }


def test_every_endpoint_is_present_and_nothing_unexpected() -> None:
    assert set(operations(openapi())) == EXPECTED_OPERATIONS


def test_every_endpoint_is_documented() -> None:
    for key, op in operations(openapi()).items():
        assert op.get("summary"), f"{key} has no summary"
        assert op.get("tags"), f"{key} has no tag"
        assert any(code.startswith("2") for code in op["responses"]), (
            f"{key} has no success response"
        )


def test_protected_endpoints_document_401_and_use_the_error_envelope() -> None:
    spec = openapi()
    for key, op in operations(spec).items():
        if key in PUBLIC:
            continue
        assert "401" in op["responses"], f"{key} does not document 401"
        schema = op["responses"]["401"]["content"]["application/json"]["schema"]
        assert schema["$ref"].endswith("/ErrorResponse")


def test_docs_are_disabled_in_production() -> None:
    settings = make_settings(
        env="production",
        cors_origins=["https://app.example.com"],
        llm_provider="anthropic",
        anthropic_api_key="k",
        llm_model="m",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get(f"{API}/docs").status_code == 404


def test_unauthenticated_requests_get_401_before_touching_the_database() -> None:
    with TestClient(create_app(make_settings(database_url=UNREACHABLE_DB))) as client:
        for path in ("/datasets", "/conversations", "/history/queries", "/reports", "/auth/me"):
            response = client.get(f"{API}{path}")
            assert response.status_code == 401, path
            assert response.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.parametrize("auth_mode", ["session", "demo"])
def test_database_failure_is_a_clean_503(auth_mode: str) -> None:
    settings = make_settings(database_url=UNREACHABLE_DB, auth_mode=auth_mode)
    token, _ = create_access_token(uuid.uuid4(), TEST_JWT_SECRET, settings.access_token_minutes)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        client.cookies.set(ACCESS_COOKIE, token)
        response = client.get(f"{API}/datasets")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "DATABASE_UNAVAILABLE"
    for leak in ("SuperSecretPw", "127.0.0.1", "sageboard_app", "Traceback", "Errno", "asyncpg"):
        assert leak not in response.text


def test_missing_database_configuration_is_a_503() -> None:
    with TestClient(create_app(make_settings(auth_mode="demo"))) as client:
        response = client.get(f"{API}/datasets")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_cors_allows_the_csrf_header_and_exposes_retry_after() -> None:
    with TestClient(create_app(make_settings())) as client:
        response = client.options(
            f"{API}/datasets/demo",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-csrf-token,content-type",
            },
        )
    assert response.status_code == 200
    assert "x-csrf-token" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-allow-credentials"] == "true"
    evil = TestClient(create_app(make_settings())).options(
        f"{API}/datasets",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in evil.headers
