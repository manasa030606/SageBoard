"""Conversations and the analysis sessions (questions) inside them.

Asking a question stores it as ``queued`` and, when a language model is configured,
starts the LangGraph agent in the background (202 Accepted). Poll
``GET /analysis-sessions/{id}`` for the result and ``…/trace`` for node-by-node progress.
Without a configured model the session stays queued and the response says so.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.agent.usage import seconds_until_reset
from app.api.deps import (
    AnalysisServiceDep,
    CurrentUser,
    DatabasesDep,
    RunManagerDep,
    SettingsDep,
    analysis_rate_limit,
    csrf_protect,
)
from app.api.pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery
from app.core.errors import DailyModelLimitError, RateLimitedError
from app.core.logging import get_logger
from app.schemas.analysis import (
    ConversationCreate,
    ConversationDetail,
    ConversationPatch,
    ConversationSummary,
    MessageOut,
    NodeRunOut,
    SessionAccepted,
    SessionCreate,
    SessionDetail,
    SessionSummary,
)
from app.schemas.common import Page
from app.schemas.errors import ErrorResponse
from app.services.analysis import AGENT_PENDING_MESSAGE, AGENT_STARTED_MESSAGE

log = get_logger(__name__)
router = APIRouter(tags=["conversations"], dependencies=[Depends(csrf_protect)])
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)
}


def _detail(convo: Any) -> ConversationDetail:
    return ConversationDetail(
        **ConversationSummary.model_validate(convo).model_dump(),
        messages=[MessageOut.model_validate(m) for m in convo.messages],
        sessions=[SessionSummary.model_validate(s) for s in convo.sessions],
    )


@router.get(
    "/conversations",
    response_model=Page[ConversationSummary],
    responses=ERRORS,
    summary="Your conversations, most recently active first",
)
async def list_conversations(
    user: CurrentUser,
    service: AnalysisServiceDep,
    dataset_id: uuid.UUID | None = None,
    limit: LimitQuery = DEFAULT_LIMIT,
    cursor: CursorQuery = None,
) -> Page[ConversationSummary]:
    rows, next_cursor = await service.list_conversations(
        user, dataset_id=dataset_id, limit=limit, cursor=cursor
    )
    return Page(
        items=[ConversationSummary.model_validate(c) for c in rows], next_cursor=next_cursor
    )


@router.post(
    "/conversations",
    response_model=ConversationDetail,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
    summary="Start a conversation about one of your datasets",
)
async def create_conversation(
    body: ConversationCreate, user: CurrentUser, service: AnalysisServiceDep
) -> ConversationDetail:
    return _detail(
        await service.create_conversation(user, dataset_id=body.dataset_id, title=body.title)
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    responses=ERRORS,
    summary="A conversation with its messages and analysis sessions",
)
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, service: AnalysisServiceDep
) -> ConversationDetail:
    return _detail(await service.get_conversation(user, conversation_id))


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    responses=ERRORS,
    summary="Rename",
)
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationPatch,
    user: CurrentUser,
    service: AnalysisServiceDep,
) -> ConversationDetail:
    return _detail(await service.rename_conversation(user, conversation_id, body.title))


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERRORS,
    summary="Delete a conversation, its messages and sessions",
)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, service: AnalysisServiceDep
) -> Response:
    await service.delete_conversation(user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/conversations/{conversation_id}/sessions",
    response_model=SessionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={**ERRORS, 429: {"model": ErrorResponse}},
    dependencies=[Depends(analysis_rate_limit)],
    summary="Ask a question (starts the analysis agent when a model is configured)",
)
async def create_session(
    conversation_id: uuid.UUID,
    body: SessionCreate,
    *,
    user: CurrentUser,
    service: AnalysisServiceDep,
    manager: RunManagerDep,
    databases: DatabasesDep,
    settings: SettingsDep,
) -> SessionAccepted:
    limit = settings.llm_daily_request_limit
    if manager.available and limit and await service.model_calls_today() >= limit:
        raise DailyModelLimitError(seconds_until_reset())
    if manager.available and manager.active_for(user.id) >= settings.analyses_concurrent_per_user:
        log.warning("rate_limited", limit="concurrent_analyses", user_id=str(user.id))
        raise RateLimitedError(
            5, "You already have analyses running. Wait for one to finish, then ask again."
        )
    run = await service.create_session(user, conversation_id, body.question)
    started = manager.available and databases.executor is not None
    if started:
        manager.start(run.id, databases, user.id)
    return SessionAccepted(
        session=SessionSummary.model_validate(run),
        agent_available=started,
        message=AGENT_STARTED_MESSAGE if started else AGENT_PENDING_MESSAGE,
    )


@router.get(
    "/analysis-sessions/{session_id}",
    response_model=SessionDetail,
    responses=ERRORS,
    summary="One analysis session",
)
async def get_session(
    session_id: uuid.UUID, user: CurrentUser, service: AnalysisServiceDep
) -> SessionDetail:
    return SessionDetail.model_validate(await service.get_session(user, session_id))


@router.post(
    "/analysis-sessions/{session_id}/cancel",
    response_model=SessionDetail,
    responses=ERRORS,
    summary="Cancel a queued or running session (idempotent)",
)
async def cancel_session(
    session_id: uuid.UUID, user: CurrentUser, service: AnalysisServiceDep, manager: RunManagerDep
) -> SessionDetail:
    run = await service.cancel_session(user, session_id)
    manager.cancel(run.id)  # stops a running agent at its next node boundary
    return SessionDetail.model_validate(run)


@router.get(
    "/analysis-sessions/{session_id}/trace",
    response_model=list[NodeRunOut],
    responses=ERRORS,
    summary="The agent's node-by-node trace: status, duration, tool and model calls",
)
async def get_trace(
    session_id: uuid.UUID, user: CurrentUser, service: AnalysisServiceDep
) -> list[NodeRunOut]:
    return [NodeRunOut.model_validate(r) for r in await service.list_node_runs(user, session_id)]
