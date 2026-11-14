"""Auth building blocks, settings rules and pagination cursors (no database)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.api.pagination import decode_cursor, encode_cursor
from app.auth import passwords, tokens
from app.auth.ratelimit import RateLimiter
from app.core.config import Settings
from app.core.errors import ValidationFailedError
from tests.conftest import TEST_JWT_SECRET

SECRET = TEST_JWT_SECRET


# ------------------------------------------------------------------ passwords
def test_password_hash_is_argon2id_and_verifies() -> None:
    hashed = passwords.hash_password("a long passphrase here")
    assert hashed.startswith("$argon2id$")
    assert "a long passphrase here" not in hashed
    assert passwords.verify_password(hashed, "a long passphrase here")
    assert not passwords.verify_password(hashed, "a long passphrase herE")


def test_verify_handles_missing_and_corrupt_hashes() -> None:
    assert not passwords.verify_password(None, "anything at all")
    assert not passwords.verify_password("not-a-hash", "anything at all")


@pytest.mark.parametrize(
    ("password", "email", "fragment"),
    [
        ("short", "a@b.co", "at least"),
        ("x" * 129, "a@b.co", "at most"),
        ("password123", "a@b.co", "easy to guess"),
        ("aaaaaaaaaaaa", "a@b.co", "easy to guess"),
        ("alice@example.com", "alice@example.com", "email"),
        ("alice.wonder", "alice.wonder@example.com", "email"),
    ],
)
def test_password_policy(password: str, email: str, fragment: str) -> None:
    problem = passwords.password_problem(password, email)
    assert problem is not None
    assert fragment in problem


def test_good_password_passes() -> None:
    assert passwords.password_problem("correct horse battery staple", "a@b.co") is None


# --------------------------------------------------------------------- tokens
def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token, expires = tokens.create_access_token(user_id, SECRET, 15)
    claims = tokens.decode_access_token(token, SECRET)
    assert claims.user_id == user_id
    assert abs((claims.expires_at - expires).total_seconds()) < 1


def _forge(payload: dict[str, object], secret: str = SECRET, alg: str = "HS256") -> str:
    return jwt.encode(payload, secret, algorithm=alg)


def _claims(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "iss": "sageboard",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    base.update(overrides)
    return base


def test_expired_token_is_reported_as_expired() -> None:
    past = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
    with pytest.raises(tokens.TokenExpired):
        tokens.decode_access_token(_forge(_claims(exp=past)), SECRET)


@pytest.mark.parametrize(
    "token",
    [
        _forge(_claims(), secret="another-secret-that-is-long-enough-123456"),  # wrong key
        _forge(_claims(typ="refresh")),  # wrong token type
        _forge(_claims(iss="someone-else")),  # wrong issuer
        _forge(_claims(sub="not-a-uuid")),
        _forge({k: v for k, v in _claims().items() if k != "exp"}),  # no expiry
        jwt.encode(_claims(), None, algorithm="none"),  # unsigned: "alg": "none"
        "not.a.jwt",
        "",
    ],
)
def test_invalid_tokens_are_rejected(token: str) -> None:
    with pytest.raises(tokens.TokenInvalid):
        tokens.decode_access_token(token, SECRET)


def test_tampered_payload_is_rejected() -> None:
    token, _ = tokens.create_access_token(uuid.uuid4(), SECRET, 15)
    header, _payload, signature = token.split(".")
    other, _ = tokens.create_access_token(uuid.uuid4(), SECRET, 15)
    forged = ".".join([header, other.split(".")[1], signature])
    with pytest.raises(tokens.TokenInvalid):
        tokens.decode_access_token(forged, SECRET)


def test_refresh_tokens_are_random_and_only_hashes_are_stored() -> None:
    a, b = tokens.new_refresh_token(), tokens.new_refresh_token()
    assert a != b
    assert len(a) >= 40
    assert tokens.hash_refresh_token(a) == tokens.hash_refresh_token(a)
    assert a not in tokens.hash_refresh_token(a)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("x" * 10, "x" * 10, True),
        ("x", "y", False),
        ("", "", False),
        (None, None, False),
        ("x", None, False),
    ],
)
def test_csrf_token_comparison(a: str | None, b: str | None, expected: bool) -> None:
    assert tokens.tokens_match(a, b) is expected


# --------------------------------------------------------------- rate limiter
def test_rate_limiter_blocks_then_recovers() -> None:
    now = [1000.0]
    limiter = RateLimiter(clock=lambda: now[0])
    assert [limiter.hit("k", 3, 60) for _ in range(3)] == [None, None, None]
    retry = limiter.hit("k", 3, 60)
    assert retry is not None
    assert 1 <= retry <= 60
    assert limiter.hit("other", 3, 60) is None  # keys are independent
    now[0] += 61
    assert limiter.hit("k", 3, 60) is None


# ------------------------------------------------------------------- settings
def test_session_mode_requires_a_strong_jwt_secret(
    settings_factory: Callable[..., Settings],
) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        settings_factory(auth_mode="session", jwt_secret="too-short")
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        settings_factory(auth_mode="session", jwt_secret=None)
    assert settings_factory(auth_mode="demo", jwt_secret=None).auth_mode == "demo"


def test_samesite_none_requires_secure_cookies(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="COOKIE_SAMESITE=none"):
        settings_factory(cookie_samesite="none")
    assert settings_factory(cookie_samesite="none", cookie_secure=True).secure_cookies


def test_production_forbids_insecure_cookies(settings_factory: Callable[..., Settings]) -> None:
    prod = {
        "env": "production",
        "cors_origins": ["https://app.example.com"],
        "llm_provider": "anthropic",
        "anthropic_api_key": "k",
        "llm_model": "m",
    }
    assert settings_factory(**prod).secure_cookies is True
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        settings_factory(**prod, cookie_secure=False)
    with pytest.raises(ValidationError, match="AUTH_MODE=demo"):
        settings_factory(**prod, auth_mode="demo")


# ----------------------------------------------------------------- pagination
def test_cursor_round_trip() -> None:
    at, item = datetime(2026, 11, 14, 10, 0, tzinfo=UTC), uuid.uuid4()
    assert decode_cursor(encode_cursor(at, item)) == (at, item)
    assert decode_cursor(None) is None


@pytest.mark.parametrize("cursor", ["garbage", "e30", "WyJ4IiwgInkiXQ", "%%%"])
def test_bad_cursor_is_a_validation_error(cursor: str) -> None:
    with pytest.raises(ValidationFailedError, match="page link"):
        decode_cursor(cursor)
