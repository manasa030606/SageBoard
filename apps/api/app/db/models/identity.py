"""Users and analytical database connections."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, uuid7


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Case-insensitive uniqueness without the citext extension.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Nullable until authentication is implemented; argon2id hashes only (never plaintext).
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    connections: Mapped[list[DatabaseConnection]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class DatabaseConnection(TimestampMixin, Base):
    """Where a dataset's data lives and how the executor reaches it.

    ``internal_warehouse`` connections use the server's own executor credentials from
    the environment; they store NO secret. ``postgres_external`` (post-MVP) will store
    only a reference to an encrypted secret, never the password itself.
    """

    __tablename__ = "database_connections"
    __table_args__ = (
        UniqueConstraint("owner_id", "name"),
        CheckConstraint("kind IN ('internal_warehouse', 'postgres_external')", name="kind"),
        CheckConstraint("status IN ('active', 'disabled', 'error')", name="status"),
        CheckConstraint("port IS NULL OR (port > 0 AND port < 65536)", name="port"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    host: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)
    database_name: Mapped[str | None] = mapped_column(String(128))
    secret_ref: Mapped[str | None] = mapped_column(String(255))

    owner: Mapped[User] = relationship(back_populates="connections")


class RefreshToken(CreatedAtMixin, Base):
    """One issued refresh token. Only its SHA-256 hash is stored.

    Tokens rotate on every use. All tokens from one login share a ``family_id``; if a
    token that was already rotated is presented again (a sign it was stolen), the whole
    family is revoked.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_family_id", "family_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column()
    user_agent: Mapped[str | None] = mapped_column(String(300))


class AuditLog(CreatedAtMixin, Base):
    """Security-relevant events: sign-ins, failures, token reuse, dataset create/delete."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(INET)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
