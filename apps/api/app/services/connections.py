"""Database connections: where a dataset's data lives."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DatabaseConnection, User

INTERNAL_CONNECTION_NAME = "Sageboard warehouse"


async def get_or_create_internal_connection(
    session: AsyncSession, owner: User
) -> DatabaseConnection:
    found = await session.scalar(
        select(DatabaseConnection).where(
            DatabaseConnection.owner_id == owner.id, DatabaseConnection.kind == "internal_warehouse"
        )
    )
    if found:
        return found
    connection = DatabaseConnection(
        owner_id=owner.id, name=INTERNAL_CONNECTION_NAME, kind="internal_warehouse"
    )
    session.add(connection)
    await session.flush()
    return connection


class ConnectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, owner: User) -> list[DatabaseConnection]:
        rows = await self.session.scalars(
            select(DatabaseConnection)
            .where(DatabaseConnection.owner_id == owner.id)
            .order_by(DatabaseConnection.created_at)
        )
        return list(rows.all())
