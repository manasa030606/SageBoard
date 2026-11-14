"""Conversations, messages, analysis sessions, agent node runs, query executions, reports.

The LangGraph agent (Phase 5) fills ``analysis_sessions`` (status, understanding, plan,
result), ``agent_node_runs`` (one row per node execution: the run trace) and
``query_executions`` (every SQL attempt, origin = 'agent').
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, uuid7

SESSION_STATUSES = (
    "queued",
    "running",
    "awaiting_input",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
)


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_owner_id_updated_at", "owner_id", text("updated_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    sessions: Mapped[list[AnalysisSession]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class AnalysisSession(CreatedAtMixin, Base):
    """One agent run for one question (called a 'run' in the API)."""

    __tablename__ = "analysis_sessions"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in SESSION_STATUSES)})", name="status"
        ),
        CheckConstraint("char_length(question) BETWEEN 1 AND 2000", name="question_length"),
        Index("ix_analysis_sessions_owner_id_created_at", "owner_id", text("created_at DESC")),
        Index(
            "ix_analysis_sessions_active",
            "status",
            postgresql_where=text("status IN ('queued', 'running', 'awaiting_input')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    termination_reason: Mapped[str | None] = mapped_column(String(32))
    understanding: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    final_summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sql_executions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Phase 5: the final response, steps, facts, charts and verification report.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    llm_provider: Mapped[str | None] = mapped_column(String(32))
    llm_model: Mapped[str | None] = mapped_column(String(120))

    conversation: Mapped[Conversation] = relationship(back_populates="sessions")
    query_executions: Mapped[list[QueryExecution]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


NODE_RUN_STATUSES = ("succeeded", "failed", "degraded")


class AgentNodeRun(Base):
    """One execution of one graph node: status, duration, tool calls, LLM calls."""

    __tablename__ = "agent_node_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in NODE_RUN_STATUSES)})", name="status"
        ),
        Index("uq_agent_node_runs_session_seq", "analysis_session_id", "seq", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    analysis_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_sessions.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    node: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    llm_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text)


class Message(CreatedAtMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="role"),
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    analysis_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_sessions.id", ondelete="SET NULL"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class QueryExecution(CreatedAtMixin, Base):
    """Every analytical SQL statement Sageboard validated or ran (audit trail)."""

    __tablename__ = "query_executions"
    __table_args__ = (
        CheckConstraint("origin IN ('agent', 'preview', 'widget_refresh', 'rerun')", name="origin"),
        CheckConstraint(
            "guard_status IN ('accepted', 'rejected', 'not_applicable')", name="guard_status"
        ),
        CheckConstraint(
            "exec_status IN ('not_run', 'ok', 'error', 'timeout', 'cancelled')", name="exec_status"
        ),
        Index("ix_query_executions_owner_id_created_at", "owner_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    analysis_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_sessions.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    plan_step_id: Mapped[str | None] = mapped_column(String(16))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    executed_sql: Mapped[str | None] = mapped_column(Text)
    sql_fingerprint: Mapped[str | None] = mapped_column(String(64))
    guard_status: Mapped[str] = mapped_column(String(16), nullable=False)
    guard_violations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    exec_status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exec_ms: Mapped[int | None] = mapped_column(Integer)

    session: Mapped[AnalysisSession | None] = relationship(back_populates="query_executions")


class Report(TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_owner_id_created_at", "owner_id", text("created_at DESC")),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    analysis_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_sessions.id", ondelete="SET NULL"), index=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Immutable snapshot of sections, charts, insights and SQL (see API_SPECIFICATION §7).
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
