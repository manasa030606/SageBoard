"""History: past analysis sessions and every SQL statement Sageboard validated or ran."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import decode_cursor, encode_cursor
from app.db.models import AnalysisSession, Conversation, Dataset, QueryExecution, Report, User

SNIPPET_CHARS = 280


def _snippet(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 1].rstrip() + "…"


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
        since: datetime | None = None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Past analyses, newest first. Only columns the list needs are read: the stored
        result (every step's rows) can be large and stays in the database."""
        findings = AnalysisSession.result["response"]["key_findings"]
        finding_count = func.coalesce(
            case(
                (func.jsonb_typeof(findings) == "array", func.jsonb_array_length(findings)), else_=0
            ),
            0,
        )
        query_count = (
            select(func.count())
            .where(
                QueryExecution.analysis_session_id == AnalysisSession.id,
                QueryExecution.owner_id == owner.id,
                QueryExecution.exec_status == "ok",
            )
            .scalar_subquery()
        )
        report_id = (
            select(Report.id)
            .where(Report.analysis_session_id == AnalysisSession.id, Report.owner_id == owner.id)
            .order_by(Report.created_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(
                AnalysisSession.id,
                AnalysisSession.conversation_id,
                Conversation.title.label("conversation_title"),
                AnalysisSession.dataset_id,
                Dataset.name.label("dataset_name"),
                AnalysisSession.question,
                AnalysisSession.status,
                AnalysisSession.final_summary,
                finding_count.label("finding_count"),
                query_count.label("query_count"),
                AnalysisSession.duration_ms,
                AnalysisSession.created_at,
                report_id.label("report_id"),
            )
            .join(Conversation, Conversation.id == AnalysisSession.conversation_id)
            .join(Dataset, Dataset.id == AnalysisSession.dataset_id)
            .where(
                AnalysisSession.owner_id == owner.id,
                Conversation.owner_id == owner.id,
                Dataset.owner_id == owner.id,
            )
        )
        if status:
            stmt = stmt.where(AnalysisSession.status == status)
        if dataset_id:
            stmt = stmt.where(AnalysisSession.dataset_id == dataset_id)
        if since:
            stmt = stmt.where(AnalysisSession.created_at >= since)
        if q and q.strip():
            pattern = f"%{_escape_like(q.strip())}%"
            stmt = stmt.where(
                or_(
                    AnalysisSession.question.ilike(pattern, escape="\\"),
                    AnalysisSession.final_summary.ilike(pattern, escape="\\"),
                    Dataset.name.ilike(pattern, escape="\\"),
                )
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
        rows = list((await self.session.execute(stmt.limit(limit + 1))).mappings().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = encode_cursor(rows[-1]["created_at"], rows[-1]["id"])
        items = [
            {
                **{k: v for k, v in row.items() if k != "final_summary"},
                "summary": _snippet(row["final_summary"]),
            }
            for row in rows
        ]
        return items, next_cursor

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
