"""Conversations and analysis sessions.

Phase 4 stores questions and session state; nothing executes them yet. The agent that
moves a session from ``queued`` to a result arrives in a later phase, so creating a
session says so explicitly (``agent_available=False``) instead of pretending to answer.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.pagination import decode_cursor, encode_cursor
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.db.models import AnalysisSession, Conversation, Dataset, Message, User

DEFAULT_TITLE = "New conversation"
TITLE_FROM_QUESTION_CHARS = 80
ACTIVE_STATUSES = ("queued", "running", "awaiting_input")
AGENT_PENDING_MESSAGE = (
    "Your question is saved. The analysis agent isn’t connected yet, so it will stay "
    "queued until that feature is released."
)


class AnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------ conversations
    async def list_conversations(
        self, owner: User, *, dataset_id: uuid.UUID | None, limit: int, cursor: str | None
    ) -> tuple[Sequence[Conversation], str | None]:
        stmt = select(Conversation).where(Conversation.owner_id == owner.id)
        if dataset_id is not None:
            stmt = stmt.where(Conversation.dataset_id == dataset_id)
        after = decode_cursor(cursor)
        if after:
            at, last_id = after
            stmt = stmt.where(
                or_(
                    Conversation.updated_at < at,
                    and_(Conversation.updated_at == at, Conversation.id < last_id),
                )
            )
        stmt = stmt.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(
            limit + 1
        )
        rows = list((await self.session.scalars(stmt)).all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = encode_cursor(rows[-1].updated_at, rows[-1].id)
        return rows, next_cursor

    async def create_conversation(
        self, owner: User, *, dataset_id: uuid.UUID, title: str | None
    ) -> Conversation:
        await self._ready_dataset(owner, dataset_id)
        convo = Conversation(
            owner_id=owner.id,
            dataset_id=dataset_id,
            title=_clean_title(title) or DEFAULT_TITLE,
        )
        self.session.add(convo)
        await self.session.commit()
        return await self.get_conversation(owner, convo.id)

    async def get_conversation(self, owner: User, conversation_id: uuid.UUID) -> Conversation:
        convo = await self.session.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.owner_id == owner.id)
            .options(selectinload(Conversation.messages), selectinload(Conversation.sessions))
            .execution_options(populate_existing=True)
        )
        if convo is None:
            raise NotFoundError("That conversation doesn’t exist.")
        convo.sessions.sort(key=lambda s: s.created_at)
        return convo

    async def rename_conversation(
        self, owner: User, conversation_id: uuid.UUID, title: str
    ) -> Conversation:
        convo = await self.get_conversation(owner, conversation_id)
        cleaned = _clean_title(title)
        if not cleaned:
            raise ValidationFailedError("Enter a title.", code="INVALID_TITLE")
        convo.title = cleaned
        convo.updated_at = datetime.now(UTC)
        await self.session.commit()
        return await self.get_conversation(owner, conversation_id)

    async def delete_conversation(self, owner: User, conversation_id: uuid.UUID) -> None:
        convo = await self.get_conversation(owner, conversation_id)
        await self.session.delete(convo)
        await self.session.commit()

    # ---------------------------------------------------------------- sessions
    async def create_session(
        self, owner: User, conversation_id: uuid.UUID, question: str
    ) -> AnalysisSession:
        text = question.strip()
        if not text:
            raise ValidationFailedError("Type a question first.", code="EMPTY_QUESTION")
        convo = await self.get_conversation(owner, conversation_id)
        dataset = await self._ready_dataset(owner, convo.dataset_id)

        run = AnalysisSession(
            conversation_id=convo.id,
            owner_id=owner.id,
            dataset_id=dataset.id,
            dataset_version=dataset.version,
            question=text,
            status="queued",
        )
        self.session.add(run)
        await self.session.flush()
        self.session.add(
            Message(conversation_id=convo.id, analysis_session_id=run.id, role="user", content=text)
        )
        if convo.title == DEFAULT_TITLE:
            convo.title = _clean_title(text[:TITLE_FROM_QUESTION_CHARS]) or DEFAULT_TITLE
        convo.updated_at = datetime.now(UTC)
        await self.session.commit()
        return run

    async def get_session(self, owner: User, session_id: uuid.UUID) -> AnalysisSession:
        run = await self.session.scalar(
            select(AnalysisSession).where(
                AnalysisSession.id == session_id, AnalysisSession.owner_id == owner.id
            )
        )
        if run is None:
            raise NotFoundError("That analysis doesn’t exist.")
        return run

    async def cancel_session(self, owner: User, session_id: uuid.UUID) -> AnalysisSession:
        run = await self.get_session(owner, session_id)
        if run.status == "cancelled":
            return run  # idempotent
        if run.status not in ACTIVE_STATUSES:
            raise ConflictError(
                f"This analysis already finished ({run.status}), so it can’t be cancelled.",
                code="SESSION_NOT_CANCELLABLE",
            )
        run.status = "cancelled"
        run.termination_reason = "cancelled_by_user"
        run.finished_at = datetime.now(UTC)
        await self.session.commit()
        return run

    # ----------------------------------------------------------------- helpers
    async def _ready_dataset(self, owner: User, dataset_id: uuid.UUID) -> Dataset:
        dataset = await self.session.scalar(
            select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_id == owner.id)
        )
        if dataset is None:
            raise NotFoundError("That dataset doesn’t exist.")
        if dataset.status != "ready":
            raise ConflictError(
                "This dataset isn’t ready yet. Finish loading it first.", code="DATASET_NOT_READY"
            )
        return dataset


def _clean_title(title: str | None) -> str:
    return " ".join((title or "").split())[:200]
