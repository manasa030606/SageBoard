"""Baseline: ensure the application schema exists.

The ``app`` schema and its grants are normally created by the role bootstrap script
(infra/postgres/init/001_roles.sh). This migration makes the schema's presence part of
the migration history so a fresh environment can be verified with ``alembic current``.
Application tables (users, sessions, ...) start in Phase 2.

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app")


def downgrade() -> None:
    # Never drop the schema automatically: it will hold user data.
    pass
