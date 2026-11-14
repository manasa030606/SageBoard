"""Password hashing (argon2id) and the password policy."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# argon2-cffi's defaults are the RFC 9106 "low memory" profile (argon2id, 64 MiB, t=3).
_HASHER = PasswordHasher()
# Verified against when the account doesn't exist, so a login for an unknown email
# takes about as long as a wrong password (no account enumeration by timing).
_DUMMY_HASH = _HASHER.hash("sageboard-timing-equaliser")

MIN_LENGTH = 10
MAX_LENGTH = 128
MIN_DISTINCT_CHARS = 4
_COMMON = frozenset(
    {
        "password", "password1", "password12", "password123", "1234567890", "123456789",
        "qwertyuiop", "qwerty1234", "iloveyou12", "letmein123", "welcome123", "admin12345",
        "sageboard1", "sageboard123", "abcdefghij", "0987654321", "1111111111", "passw0rd12",
    }
)  # fmt: skip


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _HASHER.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _HASHER.check_needs_rehash(password_hash)


def password_problem(password: str, email: str) -> str | None:
    """A user-facing reason the password is unacceptable, or None."""
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters."
    lowered = password.lower()
    if lowered in _COMMON or len(set(password)) < MIN_DISTINCT_CHARS:
        return "This password is too easy to guess. Try a longer phrase."
    if lowered == email.lower() or lowered == email.split("@", maxsplit=1)[0].lower():
        return "Don’t use your email address as your password."
    return None
