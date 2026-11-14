"""Accounts and sessions end-to-end: cookies, CSRF, rotation, reuse detection, limits."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
from app.core.config import Settings
from app.main import create_app
from app.schemas.auth import SessionOut
from tests.conftest import TEST_JWT_SECRET
from tests.integration.conftest import PASSWORD, PgUrls, fetch, run, sign_up

pytestmark = pytest.mark.integration
API = "/api/v1"


@pytest.fixture
def client(pg_settings: Callable[..., Settings]) -> Iterator[TestClient]:
    with TestClient(create_app(pg_settings())) as c:
        yield c


def email() -> str:
    return f"auth-{uuid.uuid4().hex[:10]}@example.test"


def replace_cookie(client: TestClient, name: str, value: str | None) -> None:
    """Overwrite a cookie the server set, keeping its domain and path (no duplicates)."""
    jar = client.cookies.jar
    existing = next(c for c in jar if c.name == name)
    jar.clear(existing.domain, existing.path, name)
    client.cookies.set(name, value or "", domain=existing.domain, path=existing.path)


def refresh(client: TestClient) -> object:
    response = client.post(f"{API}/auth/refresh")
    if response.status_code == 200:
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]  # CSRF rotates too
    return response


def set_cookie_headers(response: object) -> list[str]:
    return response.headers.get_list("set-cookie")  # type: ignore[attr-defined, no-any-return]


# --------------------------------------------------------------------- register
def test_register_signs_in_with_safe_cookies(client: TestClient) -> None:
    address = email()
    response = client.post(
        f"{API}/auth/register",
        json={"email": address.upper(), "password": PASSWORD, "full_name": " Ada  Lovelace "},
    )
    assert response.status_code == 201
    body = SessionOut.model_validate(response.json())
    assert body.user.email == address  # stored lower-case
    assert body.user.full_name == "Ada Lovelace"
    assert body.auth_mode == "session"
    assert "password" not in response.text
    cookies = {c.split("=", 1)[0]: c for c in set_cookie_headers(response)}
    assert "HttpOnly" in cookies[ACCESS_COOKIE]
    assert "HttpOnly" in cookies[REFRESH_COOKIE]
    assert "Path=/api/v1/auth" in cookies[REFRESH_COOKIE]
    assert "HttpOnly" not in cookies[CSRF_COOKIE]
    assert all("SameSite=lax" in c for c in cookies.values())
    assert client.get(f"{API}/auth/me").json()["user"]["email"] == address


def test_password_is_stored_as_argon2id(pg: PgUrls, client: TestClient) -> None:
    address = email()
    client.post(
        f"{API}/auth/register", json={"email": address, "password": PASSWORD, "full_name": "A"}
    )
    row = run(fetch(pg.app, "SELECT password_hash FROM app.users WHERE email = $1", address))[0]
    assert row["password_hash"].startswith("$argon2id$")
    assert PASSWORD not in row["password_hash"]


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        ({"email": "not-an-email", "password": PASSWORD, "full_name": "A"}, 422, "INVALID_EMAIL"),
        ({"email": "x@example.test", "password": "short", "full_name": "A"}, 422, "WEAK_PASSWORD"),
        (
            {"email": "x@example.test", "password": "password123", "full_name": "A"},
            422,
            "WEAK_PASSWORD",
        ),
        (
            {"email": "x@example.test", "password": PASSWORD, "full_name": "   "},
            422,
            "INVALID_NAME",
        ),
        ({"email": "x@example.test", "password": PASSWORD}, 422, "VALIDATION_ERROR"),
        (
            {"email": "x@example.test", "password": PASSWORD, "full_name": "A", "is_admin": True},
            422,
            "VALIDATION_ERROR",
        ),
    ],
)
def test_register_validation(
    client: TestClient, payload: dict[str, object], status: int, code: str
) -> None:
    response = client.post(f"{API}/auth/register", json=payload)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_duplicate_email_is_a_conflict_case_insensitively(client: TestClient) -> None:
    address = email()
    sign_up(client, address)
    response = client.post(
        f"{API}/auth/register",
        json={"email": address.upper(), "password": PASSWORD, "full_name": "B"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


# ------------------------------------------------------------------------ login
def test_login_and_wrong_password(pg: PgUrls, pg_settings: Callable[..., Settings]) -> None:
    address = email()
    with TestClient(create_app(pg_settings())) as setup:
        sign_up(setup, address)
    with TestClient(create_app(pg_settings())) as client:
        ok = client.post(
            f"{API}/auth/login", json={"email": f"  {address.upper()} ", "password": PASSWORD}
        )
        assert ok.status_code == 200
        assert client.get(f"{API}/auth/me").status_code == 200
        wrong = client.post(
            f"{API}/auth/login", json={"email": address, "password": PASSWORD + "!"}
        )
        unknown = client.post(f"{API}/auth/login", json={"email": email(), "password": PASSWORD})
    for response in (wrong, unknown):  # same answer either way: no account enumeration
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    actions = run(
        fetch(
            pg.app,
            "SELECT action FROM app.audit_log a JOIN app.users u ON u.id = a.actor_id WHERE u.email = $1",
            address,
        )
    )
    assert {r["action"] for r in actions} >= {"auth.register", "auth.login", "auth.login_failed"}


def test_login_is_rate_limited(pg_settings: Callable[..., Settings]) -> None:
    with TestClient(create_app(pg_settings(login_attempts_per_minute=3))) as client:
        statuses = [
            client.post(
                f"{API}/auth/login",
                json={"email": "who@example.test", "password": "nope-nope-nope"},
            ).status_code
            for _ in range(4)
        ]
        limited = client.post(
            f"{API}/auth/login", json={"email": "who@example.test", "password": "x"}
        )
    assert statuses == [401, 401, 401, 429]
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1


def test_registration_is_rate_limited(pg_settings: Callable[..., Settings]) -> None:
    with TestClient(create_app(pg_settings(registrations_per_hour=2))) as client:
        codes = [
            client.post(
                f"{API}/auth/register",
                json={"email": email(), "password": PASSWORD, "full_name": "A"},
            ).status_code
            for _ in range(3)
        ]
    assert codes == [201, 201, 429]


# ------------------------------------------------------------ tokens & sessions
def test_missing_tampered_and_expired_access_tokens(client: TestClient) -> None:
    assert client.get(f"{API}/datasets").json()["error"]["code"] == "AUTH_REQUIRED"
    body = sign_up(client)
    user_id = body["user"]["id"]
    past = datetime.now(UTC) - timedelta(minutes=1)
    expired = jwt.encode(
        {
            "sub": user_id,
            "typ": "access",
            "iss": "sageboard",
            "iat": int(past.timestamp()) - 60,
            "exp": int(past.timestamp()),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    replace_cookie(client, ACCESS_COOKIE, expired)
    response = client.get(f"{API}/datasets")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"
    forged = jwt.encode(
        {"sub": user_id, "typ": "access", "iss": "sageboard", "iat": 1, "exp": 4102444800},
        "x" * 40,
        algorithm="HS256",
    )
    replace_cookie(client, ACCESS_COOKIE, forged)
    assert client.get(f"{API}/datasets").json()["error"]["code"] == "AUTH_REQUIRED"


def test_refresh_rotates_and_reuse_revokes_the_family(client: TestClient) -> None:
    sign_up(client)
    first = client.cookies.get(REFRESH_COOKIE)
    assert refresh(client).status_code == 200  # type: ignore[attr-defined]
    second = client.cookies.get(REFRESH_COOKIE)
    assert second and second != first

    # Present the rotated (old) token after the grace window: treated as theft.
    from app.services import auth as auth_module  # noqa: PLC0415

    grace = auth_module.ROTATION_GRACE
    auth_module.ROTATION_GRACE = timedelta(0)
    try:
        replace_cookie(client, REFRESH_COOKIE, first)
        stolen = client.post(f"{API}/auth/refresh")
    finally:
        auth_module.ROTATION_GRACE = grace
    assert stolen.status_code == 401
    replace_cookie(client, REFRESH_COOKIE, second)
    assert client.post(f"{API}/auth/refresh").status_code == 401  # whole family revoked


def test_concurrent_refresh_inside_grace_window_does_not_revoke(client: TestClient) -> None:
    sign_up(client)
    first = client.cookies.get(REFRESH_COOKIE)
    assert refresh(client).status_code == 200  # type: ignore[attr-defined]
    second = client.cookies.get(REFRESH_COOKIE)
    replace_cookie(client, REFRESH_COOKIE, first)
    assert client.post(f"{API}/auth/refresh").status_code == 401  # the losing tab
    replace_cookie(client, REFRESH_COOKIE, second)
    assert refresh(client).status_code == 200  # type: ignore[attr-defined]  # winner still works


def test_logout_revokes_and_clears(pg: PgUrls, client: TestClient) -> None:
    body = sign_up(client)
    response = client.post(f"{API}/auth/logout")
    assert response.status_code == 204
    cleared = " ".join(set_cookie_headers(response))
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        assert f'{name}=""' in cleared or f"{name}=;" in cleared
    live = run(
        fetch(
            pg.app,
            "SELECT count(*) AS n FROM app.refresh_tokens WHERE user_id = $1 AND revoked_at IS NULL",
            uuid.UUID(body["user"]["id"]),
        )
    )
    assert live[0]["n"] == 0
    assert client.get(f"{API}/auth/me").status_code == 401


def test_inactive_user_is_signed_out(pg: PgUrls, client: TestClient) -> None:
    body = sign_up(client)
    run(
        fetch(
            pg.app,
            "UPDATE app.users SET is_active = false WHERE id = $1",
            uuid.UUID(body["user"]["id"]),
        )
    )
    assert client.get(f"{API}/auth/me").status_code == 401


# ------------------------------------------------------------------------ CSRF
@pytest.mark.parametrize("header", [None, "wrong-token"])
def test_state_changes_require_the_csrf_header(client: TestClient, header: str | None) -> None:
    sign_up(client)
    del client.headers["X-CSRF-Token"]
    if header:
        client.headers["X-CSRF-Token"] = header
    for method, path in (
        ("POST", "/datasets/demo"),
        ("POST", "/conversations"),
        ("POST", "/auth/logout"),
        ("PATCH", f"/datasets/{uuid.uuid4()}"),
        ("DELETE", f"/reports/{uuid.uuid4()}"),
    ):
        response = client.request(method, f"{API}{path}", json={})
        assert response.status_code == 403, (method, path)
        assert response.json()["error"]["code"] == "CSRF_FAILED"
    assert client.get(f"{API}/datasets").status_code == 200  # reads don't need it


def test_refresh_works_after_a_page_reload_without_csrf(client: TestClient) -> None:
    """A reloaded page has no CSRF token in memory; refresh is how it gets a new one."""
    body = sign_up(client)
    del client.headers["X-CSRF-Token"]
    past = datetime.now(UTC) - timedelta(minutes=1)
    expired = jwt.encode(
        {
            "sub": body["user"]["id"],
            "typ": "access",
            "iss": "sageboard",
            "iat": int(past.timestamp()) - 60,
            "exp": int(past.timestamp()),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    replace_cookie(client, ACCESS_COOKIE, expired)
    assert client.get(f"{API}/datasets").status_code == 401
    refreshed = client.post(f"{API}/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["csrf_token"]
    assert client.get(f"{API}/datasets").status_code == 200


def test_me_reissues_a_lost_csrf_cookie(client: TestClient) -> None:
    sign_up(client)
    client.cookies.delete(CSRF_COOKIE)
    body = client.get(f"{API}/auth/me").json()
    assert body["csrf_token"]
    assert client.cookies.get(CSRF_COOKIE) == body["csrf_token"]
