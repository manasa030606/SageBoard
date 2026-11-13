"""datasets.connection_id: RESTRICT → NO ACTION, DEFERRABLE INITIALLY DEFERRED.

Deleting a user cascades to both ``database_connections`` and ``datasets``. PostgreSQL
runs each cascade as a nested statement, so an immediate check on the connection FK
fails before the datasets are gone. Deferring the check to commit lets one user delete
cascade cleanly, while deleting a connection that still has datasets is still refused.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "fk_datasets_connection_id_database_connections"


def _recreate(ondelete: str, *, deferred: bool) -> None:
    op.drop_constraint(FK, "datasets", schema="app", type_="foreignkey")
    op.create_foreign_key(
        FK,
        "datasets",
        "database_connections",
        ["connection_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
        ondelete=ondelete,
        deferrable=deferred or None,
        initially="DEFERRED" if deferred else None,
    )


def upgrade() -> None:
    _recreate("NO ACTION", deferred=True)


def downgrade() -> None:
    _recreate("RESTRICT", deferred=False)
