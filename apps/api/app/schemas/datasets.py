"""Dataset API contracts (docs/architecture/ARCHITECTURE.md). No credentials or schema names leak out."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Dataset, DatasetColumn, DatasetTable

ColumnTypeName = Literal["integer", "bigint", "numeric", "boolean", "date", "timestamptz", "text"]


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    column_name: str
    display_name: str
    ordinal: int
    data_type: str
    inferred_type: str | None
    is_nullable: bool
    is_primary_key: bool
    semantic_role: str | None
    description: str | None
    is_sensitive: bool
    profile: dict[str, Any]

    @classmethod
    def build(cls, column: DatasetColumn) -> ColumnOut:
        out = cls.model_validate(column)
        if column.is_sensitive:  # never return stored samples for sensitive columns
            out.profile = {
                **out.profile,
                "min": None,
                "max": None,
                "top_values": [],
                "examples": [],
            }
        return out


class TableOut(BaseModel):
    id: uuid.UUID
    table_name: str
    display_name: str
    description: str | None
    row_count: int
    primary_key: list[str]
    columns: list[ColumnOut]

    @classmethod
    def build(cls, table: DatasetTable) -> TableOut:
        return cls(
            id=table.id,
            table_name=table.table_name,
            display_name=table.display_name,
            description=table.description,
            row_count=table.row_count,
            primary_key=list(table.primary_key),
            columns=[ColumnOut.build(c) for c in table.columns],
        )


class DatasetSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    source_type: str
    file_name: str | None
    status: str
    status_reason: str | None
    version: int
    total_rows: int | None
    size_bytes: int | None
    table_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, d: Dataset) -> DatasetSummary:
        return cls(
            id=d.id,
            name=d.name,
            description=d.description,
            source_type=d.source_type,
            file_name=d.file_name,
            status=d.status,
            status_reason=d.status_reason,
            version=d.version,
            total_rows=d.total_rows,
            size_bytes=d.size_bytes,
            table_count=len(d.tables),
            created_at=d.created_at,
            updated_at=d.updated_at,
        )


class DatasetDetail(DatasetSummary):
    tables: list[TableOut]

    @classmethod
    def build(cls, d: Dataset) -> DatasetDetail:
        base = DatasetSummary.build(d).model_dump()
        return cls(**base, tables=[TableOut.build(t) for t in d.tables])


class DatasetPage(BaseModel):
    items: list[DatasetSummary]


class InferredColumn(BaseModel):
    name: str
    display_name: str
    inferred_type: ColumnTypeName
    missing_count: int
    sample_values: list[str]


class UploadIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    column: str | None = None
    line: int | None = None


class UploadReview(BaseModel):
    dataset: DatasetSummary
    row_count: int
    rejected_count: int
    rejected_samples: list[dict[str, Any]]
    columns: list[InferredColumn]
    issues: list[UploadIssue]


class FinalizeRequest(BaseModel):
    column_types: dict[str, ColumnTypeName] = Field(
        default_factory=dict,
        description="Optional overrides: column name → type. Others keep the suggested type.",
    )


class ColumnPatch(BaseModel):
    description: str | None = Field(default=None, max_length=1000)
    is_sensitive: bool | None = None


class PreviewColumn(BaseModel):
    name: str
    data_type: str
    is_sensitive: bool


class PreviewResponse(BaseModel):
    table: str
    columns: list[PreviewColumn]
    rows: list[list[Any]]
    limit: int
    offset: int
    has_more: bool
    masked_columns: list[str]
    exec_ms: int


class ConnectionOut(BaseModel):
    """Connection metadata only. Secrets and hostnames of the internal warehouse are never returned."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    kind: str
    status: str
    created_at: datetime


class DatasetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class TablePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str | None = Field(default=None, max_length=1000)


class IngestionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: Literal["pending", "running", "succeeded", "failed"]
    file_name: str | None
    file_size: int | None
    rows_total: int | None
    rows_loaded: int | None
    rows_rejected: int | None
    issues: list[dict[str, Any]]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class DemoProvisioned(BaseModel):
    dataset: DatasetDetail
    created: bool
