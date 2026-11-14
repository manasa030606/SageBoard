"""Reports: immutable snapshots of a finished analysis session."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_session_id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)


class ReportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=20_000)


class ReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    analysis_session_id: uuid.UUID | None
    dataset_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ReportDetail(ReportSummary):
    summary: str
    summary_edited_by_user: bool
    content: dict[str, Any]
