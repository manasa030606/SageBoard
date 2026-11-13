"""Schema metadata service (read side).

Answers "what does this dataset look like?" from the stored catalog — table names,
column names and types, primary keys, foreign keys, relationships and sample values —
with privacy controls applied:

- sensitive columns never return samples or min/max (``samples_redacted = True``)
- ``include_samples=False`` strips samples everywhere (e.g. strict privacy mode)
- ``level="summary"`` returns only table names, descriptions and sizes: the light
  catalog the agent's understanding step receives (ADR-0007)

The catalog is produced by introspecting the live warehouse at load time, so it
reflects real constraints, not what an upload claimed.
"""

from __future__ import annotations

from typing import Literal

from app.db.models import Dataset, DatasetColumn
from app.schemas.catalog import (
    ColumnSchema,
    ForeignKeyOut,
    RelationshipOut,
    SchemaCatalog,
    TableSchema,
    TableSummary,
)

MAX_SAMPLES = 10


def _column(column: DatasetColumn, include_samples: bool) -> ColumnSchema:
    profile = column.profile or {}
    redact = column.is_sensitive
    samples: list[str] = []
    if include_samples and not redact:
        samples = [str(v["value"]) for v in profile.get("top_values", [])] or [
            str(v) for v in profile.get("examples", [])
        ]
    return ColumnSchema(
        name=column.column_name,
        display_name=column.display_name,
        data_type=column.data_type,
        nullable=column.is_nullable,
        is_primary_key=column.is_primary_key,
        semantic_role=column.semantic_role,
        description=column.description,
        is_sensitive=column.is_sensitive,
        null_pct=profile.get("null_pct"),
        distinct_count=profile.get("distinct_count"),
        min=None if redact else profile.get("min"),
        max=None if redact else profile.get("max"),
        sample_values=samples[:MAX_SAMPLES],
        samples_redacted=redact,
    )


def build_catalog(
    dataset: Dataset, *, level: Literal["summary", "full"] = "full", include_samples: bool = True
) -> SchemaCatalog:
    """Build the catalog from a dataset loaded with tables, columns and relationships."""
    names = {t.id: t.table_name for t in dataset.tables}
    relationships = [
        RelationshipOut(
            from_table=names[r.from_table_id],
            from_column=r.from_column,
            to_table=names[r.to_table_id],
            to_column=r.to_column,
            origin=r.origin,
        )
        for r in sorted(
            dataset.relationships, key=lambda r: (names[r.from_table_id], r.from_column)
        )
    ]
    if level == "summary":
        summaries = [
            TableSummary(
                name=t.table_name,
                description=t.description,
                row_count=t.row_count,
                column_count=len(t.columns),
            )
            for t in dataset.tables
        ]
        return SchemaCatalog(
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            level="summary",
            tables=summaries,
            relationships=relationships,
        )

    tables = []
    for t in dataset.tables:
        fks = [
            ForeignKeyOut(
                column=r.from_column, references_table=r.to_table, references_column=r.to_column
            )
            for r in relationships
            if r.from_table == t.table_name
        ]
        tables.append(
            TableSchema(
                name=t.table_name,
                description=t.description,
                row_count=t.row_count,
                primary_key=list(t.primary_key),
                columns=[_column(c, include_samples) for c in t.columns],
                foreign_keys=fks,
            )
        )
    return SchemaCatalog(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        level="full",
        tables=tables,
        relationships=relationships,
    )
