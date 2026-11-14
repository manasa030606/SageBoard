"""Access tokens (JWT), refresh tokens (opaque, hashed at rest) and CSRF tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"
ISSUER = "sageboard"


class TokenInvalid(Exception):
    pass


class TokenExpired(TokenInvalid):
    pass


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    expires_at: datetime


def create_access_token(user_id: uuid.UUID, secret: str, minutes: int) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=minutes)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "iss": ISSUER,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM), expires


def decode_access_token(token: str, secret: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],  # never trust the token's own "alg"
            issuer=ISSUER,
            options={"require": ["sub", "exp", "iat", "iss", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired from exc
    except jwt.PyJWTError as exc:
        raise TokenInvalid from exc
    if payload.get("typ") != "access":
        raise TokenInvalid
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError as exc:
        raise TokenInvalid from exc
    return AccessClaims(user_id, datetime.fromtimestamp(payload["exp"], UTC))


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_match(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and secrets.compare_digest(str(a), str(b))
