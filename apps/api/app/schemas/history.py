"""Query history (the SQL audit trail)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


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
