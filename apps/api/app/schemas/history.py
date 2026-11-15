"""Query history (the SQL audit trail)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class HistoryItem(BaseModel):
    """One past analysis as History lists it: enough to find it, judge it, and reopen it."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    conversation_id: uuid.UUID
    conversation_title: str
    dataset_id: uuid.UUID
    dataset_name: str
    question: str
    status: Literal[
        "queued", "running", "awaiting_input", "succeeded", "partial", "failed", "cancelled"
    ]
    summary: str | None  # the answer, shortened for the list
    finding_count: int
    query_count: int  # SQL statements that ran for this analysis
    duration_ms: int | None
    created_at: datetime
    report_id: uuid.UUID | None  # newest saved report for this analysis, if any


class QueryHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_name: str
    analysis_session_id: uuid.UUID | None
    origin: Literal["agent", "preview", "widget_refresh", "rerun"]
    attempt: int
    executed_sql: str | None
    guard_status: Literal["accepted", "rejected", "not_applicable"]
    guard_violations: list[dict[str, Any]]
    exec_status: Literal["not_run", "ok", "error", "timeout", "cancelled"]
    error_code: str | None
    error_message: str | None
    row_count: int | None
    truncated: bool
    exec_ms: int | None
    created_at: datetime
