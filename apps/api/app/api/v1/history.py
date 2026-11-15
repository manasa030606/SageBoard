"""History: past analysis sessions and the SQL audit trail."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, HistoryServiceDep
from app.api.pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery
from app.schemas.analysis import SessionStatus
from app.schemas.common import Page
from app.schemas.errors import ErrorResponse
from app.schemas.history import HistoryItem, QueryHistoryItem

router = APIRouter(prefix="/history", tags=["history"])
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (401, 422, 503)
}


@router.get(
    "/sessions",
    response_model=Page[HistoryItem],
    responses=ERRORS,
    summary="Past analyses (newest first): search question, answer and dataset; filter by status, dataset, date",
)
async def list_sessions(  # noqa: PLR0917 - FastAPI query parameters
    user: CurrentUser,
    service: HistoryServiceDep,
    status: SessionStatus | None = None,
    dataset_id: uuid.UUID | None = None,
    q: Annotated[
        str | None, Query(max_length=200, description="Search questions, answers and dataset names")
    ] = None,
    since: Annotated[
        datetime | None, Query(description="Only analyses created at or after this")
    ] = None,
    limit: LimitQuery = DEFAULT_LIMIT,
    cursor: CursorQuery = None,
) -> Page[HistoryItem]:
    items, next_cursor = await service.list_sessions(
        user, status=status, dataset_id=dataset_id, q=q, since=since, limit=limit, cursor=cursor
    )
    return Page(items=[HistoryItem.model_validate(i) for i in items], next_cursor=next_cursor)


@router.get(
    "/queries",
    response_model=Page[QueryHistoryItem],
    responses=ERRORS,
    summary="Every SQL statement validated or run for you (previews now; agent SQL later)",
)
async def list_queries(  # noqa: PLR0917 - FastAPI query parameters
    user: CurrentUser,
    service: HistoryServiceDep,
    dataset_id: uuid.UUID | None = None,
    analysis_session_id: uuid.UUID | None = None,
    origin: Literal["agent", "preview", "widget_refresh", "rerun"] | None = None,
    exec_status: Literal["not_run", "ok", "error", "timeout", "cancelled"] | None = None,
    limit: LimitQuery = DEFAULT_LIMIT,
    cursor: CursorQuery = None,
) -> Page[QueryHistoryItem]:
    items, next_cursor = await service.list_queries(
        user,
        dataset_id=dataset_id,
        analysis_session_id=analysis_session_id,
        origin=origin,
        exec_status=exec_status,
        limit=limit,
        cursor=cursor,
    )
    return Page(items=[QueryHistoryItem.model_validate(i) for i in items], next_cursor=next_cursor)
