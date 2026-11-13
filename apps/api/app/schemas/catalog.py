"""Schema catalog contract — the structured context the agent will use to write SQL."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class ForeignKeyOut(BaseModel):
    column: str
    references_table: str
    references_column: str


class ColumnSchema(BaseModel):
    name: str
    display_name: str
    data_type: str
    nullable: bool
    is_primary_key: bool
    semantic_role: str | None
    description: str | None
    is_sensitive: bool
    null_pct: float | None = None
    distinct_count: int | None = None
    min: str | None = None
    max: str | None = None
    sample_values: list[str] = Field(default_factory=list)
    samples_redacted: bool = False


class TableSchema(BaseModel):
    name: str
    description: str | None
    row_count: int
    primary_key: list[str]
    columns: list[ColumnSchema]
    foreign_keys: list[ForeignKeyOut]


class TableSummary(BaseModel):
    name: str
    description: str | None
    row_count: int
    column_count: int


class RelationshipOut(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    origin: Literal["declared", "inferred"]


class SchemaCatalog(BaseModel):
    dataset_id: uuid.UUID
    dataset_name: str
    dataset_version: int
    level: Literal["summary", "full"]
    tables: list[TableSchema] | list[TableSummary]
    relationships: list[RelationshipOut]

    def stats(self) -> dict[str, Any]:
        return {"tables": len(self.tables), "relationships": len(self.relationships)}
