"""Declarative base for application-metadata models (schema ``app``).

Concepts (mentor note):
- *Declarative base*: SQLAlchemy maps Python classes to tables. Every model in
  ``app.db.models`` inherits from ``Base`` and therefore lives in the ``app`` schema.
- *Naming convention*: constraint names are generated deterministically, so Alembic
  migrations are stable and readable (``fk_datasets_owner_id_users``).
- *UUIDv7*: primary keys are random-looking but time-ordered, which keeps B-tree
  indexes compact (newer rows append at the end) and avoids exposing row counts.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

APP_SCHEMA = "app"

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def uuid7() -> uuid.UUID:
    """RFC 9562 UUID version 7: 48-bit Unix-ms timestamp | ver | 12 rand | var | 62 rand."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits; 74 are used
    rand_a = rand & 0xFFF
    rand_b = (rand >> 12) & ((1 << 62) - 1)
    value = ((ms & ((1 << 48) - 1)) << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


class Base(DeclarativeBase):
    metadata = MetaData(schema=APP_SCHEMA, naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
