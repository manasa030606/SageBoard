"""History: past analysis sessions and every SQL statement Sageboard validated or ran."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import decode_cursor, encode_cursor
from app.db.models import AnalysisSession, Dataset, QueryExecution, User


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class HistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_sessions(
        self,
        owner: User,
        *,
        status: str | None,
        dataset_id: uuid.UUID | None,
        q: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[Sequence[AnalysisSession], str | None]:
        stmt = select(AnalysisSession).where(AnalysisSession.owner_id == owner.id)
        if status:
            stmt = stmt.where(AnalysisSession.status == status)
        if dataset_id:
            stmt = stmt.where(AnalysisSession.dataset_id == dataset_id)
        if q and q.strip():
            stmt = stmt.where(
                AnalysisSession.question.ilike(f"%{_escape_like(q.strip())}%", escape="\\")
            )
        after = decode_cursor(cursor)
        if after:
            at, last_id = after
            stmt = stmt.where(
                or_(
                    AnalysisSession.created_at < at,
                    and_(AnalysisSession.created_at == at, AnalysisSession.id < last_id),
                )
            )
        stmt = stmt.order_by(AnalysisSession.created_at.desc(), AnalysisSession.id.desc())
        rows = list((await self.session.scalars(stmt.limit(limit + 1))).all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id)
        return rows, next_cursor

    async def list_queries(
        self,
        owner: User,
        *,
        dataset_id: uuid.UUID | None,
        analysis_session_id: uuid.UUID | None,
        origin: str | None,
        exec_status: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        stmt = (
            select(QueryExecution, Dataset.name)
            .join(Dataset, Dataset.id == QueryExecution.dataset_id)
            .where(QueryExecution.owner_id == owner.id, Dataset.owner_id == owner.id)
        )
        if dataset_id:
            stmt = stmt.where(QueryExecution.dataset_id == dataset_id)
        if analysis_session_id:
            stmt = stmt.where(QueryExecution.analysis_session_id == analysis_session_id)
        if origin:
            stmt = stmt.where(QueryExecution.origin == origin)
        if exec_status:
            stmt = stmt.where(QueryExecution.exec_status == exec_status)
        after = decode_cursor(cursor)
        if after:
            at, last_id = after
            stmt = stmt.where(
                or_(
                    QueryExecution.created_at < at,
                    and_(QueryExecution.created_at == at, QueryExecution.id < last_id),
                )
            )
        stmt = stmt.order_by(QueryExecution.created_at.desc(), QueryExecution.id.desc())
        rows = list((await self.session.execute(stmt.limit(limit + 1))).all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1][0]
            next_cursor = encode_cursor(last.created_at, last.id)
        items = [
            {
                **{c.key: getattr(q, c.key) for c in QueryExecution.__table__.columns},
                "dataset_name": name,
            }
            for q, name in rows
        ]
        return items, next_cursor
