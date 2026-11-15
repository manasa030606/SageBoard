"""Reports: immutable snapshots of a finished analysis session."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _no_nul(value: str | None) -> str | None:
    """PostgreSQL text can't hold NUL; drop it rather than fail with a 500."""
    return value.replace("\x00", "") if isinstance(value, str) else value


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_session_id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)

    _clean = field_validator("title")(_no_nul)


class ReportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=20_000)

    _clean = field_validator("title", "summary")(_no_nul)


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
    fidelity: Fidelity | None = None


class FidelityIssue(BaseModel):
    where: str
    numbers: list[str]


class Fidelity(BaseModel):
    """Did every number in the narrative appear in the stored query results?"""

    status: Literal["verified", "flagged", "not_checkable"]
    checked: int
    issues: list[FidelityIssue] = Field(default_factory=list)
