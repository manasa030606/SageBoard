"""Users and analytical database connections."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid7


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
