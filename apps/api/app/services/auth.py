"""Accounts and sessions: register, sign in, refresh rotation, sign out."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import passwords, tokens
from app.core.config import Settings
from app.core.errors import (
    AuthRequiredError,
    ConflictError,
    InvalidCredentialsError,
    TokenExpiredError,
    ValidationFailedError,
)
from app.db.models import RefreshToken, User
from app.services import audit

# Deliberately simple: one "@", a dot in the domain, no spaces. Real verification is
# an email round-trip, which is out of scope for the MVP.
MAX_EMAIL_LENGTH = 320
ROTATION_GRACE = timedelta(seconds=30)
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


@dataclass(frozen=True)
class IssuedSession:
    user: User
    access_token: str
    access_expires: datetime
    refresh_token: str
    refresh_expires: datetime
    csrf_token: str
    refresh_id: uuid.UUID


def normalise_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    @property
    def _secret(self) -> str:
        assert self.settings.jwt_secret is not None  # noqa: S101 - enforced by settings validation
        return self.settings.jwt_secret.get_secret_value()

    # ------------------------------------------------------------------ accounts
    async def register(
        self, *, email: str, password: str, full_name: str, ip: str | None, user_agent: str | None
    ) -> IssuedSession:
        email = normalise_email(email)
        if not EMAIL_RE.match(email) or len(email) > MAX_EMAIL_LENGTH:
            raise ValidationFailedError("Enter a valid email address.", code="INVALID_EMAIL")
        problem = passwords.password_problem(password, email)
        if problem:
            raise ValidationFailedError(problem, code="WEAK_PASSWORD")
        name = " ".join(full_name.split())
        if not name:
            raise ValidationFailedError("Enter your name.", code="INVALID_NAME")
        if await self._by_email(email) is not None:
            raise ConflictError(
                "An account with this email already exists. Sign in instead.", code="EMAIL_TAKEN"
            )

        user = User(email=email, full_name=name, password_hash=passwords.hash_password(password))
        self.session.add(user)
        await self.session.flush()
        audit.record(self.session, "auth.register", actor_id=user.id, ip=ip)
        return await self._issue(user, family_id=uuid.uuid4(), user_agent=user_agent)

    async def login(
        self, *, email: str, password: str, ip: str | None, user_agent: str | None
    ) -> IssuedSession:
        email = normalise_email(email)
        user = await self._by_email(email)
        ok = passwords.verify_password(user.password_hash if user else None, password)
        if user is None or not ok or not user.is_active:
            audit.record(
                self.session, "auth.login_failed", actor_id=user.id if user else None, ip=ip
            )
            await self.session.commit()
            raise InvalidCredentialsError
        if user.password_hash and passwords.needs_rehash(user.password_hash):
            user.password_hash = passwords.hash_password(password)
        user.last_login_at = datetime.now(UTC)
        audit.record(self.session, "auth.login", actor_id=user.id, ip=ip)
        return await self._issue(user, family_id=uuid.uuid4(), user_agent=user_agent)

    async def user_from_access_token(self, token: str | None) -> User:
        if not token:
            raise AuthRequiredError
        try:
            claims = tokens.decode_access_token(token, self._secret)
        except tokens.TokenExpired as exc:
            raise TokenExpiredError from exc
        except tokens.TokenInvalid as exc:
            raise AuthRequiredError from exc
        user = await self.session.get(User, claims.user_id)
        if user is None or not user.is_active:
            raise AuthRequiredError
        return user

    # ------------------------------------------------------------------ sessions
    async def refresh(
        self, raw_token: str | None, *, ip: str | None, user_agent: str | None
    ) -> IssuedSession:
        """Rotate a refresh token. Presenting an already-rotated token revokes its family."""
        if not raw_token:
            raise AuthRequiredError
        now = datetime.now(UTC)
        record = await self.session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == tokens.hash_refresh_token(raw_token))
            .with_for_update()
        )
        if record is None:
            raise AuthRequiredError
        if record.revoked_at is not None:
            # Two tabs refreshing at the same instant both send the old token; the loser
            # arrives just after rotation. Inside the grace window that is a race, not theft.
            in_grace = now - record.revoked_at < ROTATION_GRACE
            if (
                record.replaced_by_id is not None and not in_grace
            ):  # reuse of a rotated token → assume theft
                await self._revoke_family(record.family_id, now)
                audit.record(self.session, "auth.refresh_reuse", actor_id=record.user_id, ip=ip)
                await self.session.commit()
            raise AuthRequiredError
        if record.expires_at <= now:
            raise TokenExpiredError
        user = await self.session.get(User, record.user_id)
        if user is None or not user.is_active:
            raise AuthRequiredError
        issued = await self._issue(user, family_id=record.family_id, user_agent=user_agent)
        record.revoked_at = now
        record.replaced_by_id = issued.refresh_id
        return issued

    async def logout(self, raw_token: str | None, *, ip: str | None) -> None:
        """Revoke this login's token family. Works even if the access token expired."""
        if not raw_token:
            return
        record = await self.session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == tokens.hash_refresh_token(raw_token)
            )
        )
        if record is not None:
            await self._revoke_family(record.family_id, datetime.now(UTC))
            audit.record(self.session, "auth.logout", actor_id=record.user_id, ip=ip)

    # ------------------------------------------------------------------ helpers
    async def _by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def _revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def _issue(
        self, user: User, *, family_id: uuid.UUID, user_agent: str | None
    ) -> IssuedSession:
        access, access_expires = tokens.create_access_token(
            user.id, self._secret, self.settings.access_token_minutes
        )
        refresh = tokens.new_refresh_token()
        refresh_expires = datetime.now(UTC) + timedelta(days=self.settings.refresh_token_days)
        record = RefreshToken(
            user_id=user.id,
            family_id=family_id,
            token_hash=tokens.hash_refresh_token(refresh),
            expires_at=refresh_expires,
            user_agent=(user_agent or "")[:300] or None,
        )
        self.session.add(record)
        await self.session.flush()
        return IssuedSession(
            user,
            access,
            access_expires,
            refresh,
            refresh_expires,
            tokens.new_csrf_token(),
            record.id,
        )
