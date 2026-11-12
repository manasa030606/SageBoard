from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.errors import NotFoundError
from app.main import create_app
from tests.conftest import make_settings


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_wrong_method_uses_error_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/healthz")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_app_error_and_unhandled_error_are_mapped() -> None:
    app = create_app(make_settings())

    @app.get("/boom/app")
    async def app_error() -> None:
        raise NotFoundError("Dataset not found.", details={"dataset_id": "x"})

    @app.get("/boom/unhandled")
    async def unhandled() -> None:
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        r1 = client.get("/boom/app")
        assert r1.status_code == 404
        assert r1.json()["error"] == {
            "code": "NOT_FOUND",
            "message": "Dataset not found.",
            "details": {"dataset_id": "x"},
            "request_id": r1.headers["X-Request-ID"],
        }

        r2 = client.get("/boom/unhandled")
        assert r2.status_code == 500
        assert r2.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "secret internal detail" not in r2.text
