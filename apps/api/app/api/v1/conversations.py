"""Conversations and the analysis sessions (questions) inside them.

No agent runs yet: creating a session records the question as ``queued`` and the
response says ``agent_available: false``. Nothing here fabricates an answer.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import AnalysisServiceDep, CurrentUser, csrf_protect
from app.api.pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery
from app.schemas.analysis import (
    ConversationCreate,
    ConversationDetail,
    ConversationPatch,
    ConversationSummary,
    MessageOut,
    SessionAccepted,
    SessionCreate,
    SessionDetail,
    SessionSummary,
)
from app.schemas.common import Page
from app.schemas.errors import ErrorResponse
from app.services.analysis import AGENT_PENDING_MESSAGE

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
    responses=ERRORS,
    summary="Ask a question (recorded as a queued analysis session)",
)
async def create_session(
    conversation_id: uuid.UUID, body: SessionCreate, user: CurrentUser, service: AnalysisServiceDep
) -> SessionAccepted:
    run = await service.create_session(user, conversation_id, body.question)
    return SessionAccepted(
        session=SessionSummary.model_validate(run),
        agent_available=False,
        message=AGENT_PENDING_MESSAGE,
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
    session_id: uuid.UUID, user: CurrentUser, service: AnalysisServiceDep
) -> SessionDetail:
    return SessionDetail.model_validate(await service.cancel_session(user, session_id))
