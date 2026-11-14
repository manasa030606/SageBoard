"""Conversations, messages and analysis sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SessionStatus = Literal[
    "queued", "running", "awaiting_input", "succeeded", "partial", "failed", "cancelled"
]


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)


class ConversationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: Literal["user", "assistant", "system"]
    content: str
    analysis_session_id: uuid.UUID | None
    created_at: datetime


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    conversation_id: uuid.UUID
    dataset_id: uuid.UUID
    question: str
    status: SessionStatus
    duration_ms: int | None
    created_at: datetime


class SessionDetail(SessionSummary):
    dataset_version: int
    termination_reason: str | None
    understanding: dict[str, Any] | None
    plan: dict[str, Any] | None
    final_summary: str | None
    error_code: str | None
    error_message: str | None
    llm_calls: int
    sql_executions: int
    tokens_in: int
    tokens_out: int
    started_at: datetime | None
    finished_at: datetime | None


class SessionAccepted(BaseModel):
    """Response to creating a session. ``agent_available`` is false until the agent phase."""

    session: SessionSummary
    agent_available: bool
    message: str


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    dataset_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]
    sessions: list[SessionSummary]
