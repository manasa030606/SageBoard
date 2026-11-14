"""Schema tools: what the agent may know about a dataset (ADR-0007).

All answers come from the stored catalog, which is built by introspecting the live
warehouse at load time, so tables and columns here are the real ones. Sensitive
columns (detected at ingestion) never expose sample values or min/max.

Tools exposed to the Schema Retrieval agent's tool loop:

- ``get_table_schema(table)`` — columns, types, descriptions, profiles
- ``get_join_paths(tables)``  — join conditions from declared/inferred relationships
- ``get_column_values(table, column)`` — the most common stored values (text columns)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.state import ColumnContext
from app.agent.tools.sql_guard import GuardPolicy
from app.db.models import Dataset

TIME_TYPES = frozenset({"date", "timestamptz", "timestamp"})
NUMERIC_TYPES = frozenset({"integer", "bigint", "numeric", "smallint", "real", "double"})
MAX_VALUES = 20


class SchemaToolError(ValueError):
    """A tool was called with a table or column that isn't in the dataset."""


@dataclass(frozen=True)
class CatalogColumn:
    name: str
    data_type: str
    description: str | None = None
    is_primary_key: bool = False
    is_sensitive: bool = False
    null_pct: float | None = None
    distinct_count: int | None = None
    samples: tuple[str, ...] = ()
    min_value: str | None = None
    max_value: str | None = None


@dataclass(frozen=True)
class CatalogTable:
    name: str
    description: str | None
    row_count: int
    columns: tuple[CatalogColumn, ...]

    def column(self, name: str) -> CatalogColumn | None:
        return next((c for c in self.columns if c.name == name), None)


@dataclass(frozen=True)
class CatalogRelationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str

    def condition(self) -> str:
        return f"{self.from_table}.{self.from_column} = {self.to_table}.{self.to_column}"


@dataclass(frozen=True)
class DatasetCatalog:
    dataset_id: str
    name: str
    schema_name: str
    reader_role: str
    tables: tuple[CatalogTable, ...]
    relationships: tuple[CatalogRelationship, ...] = field(default_factory=tuple)

    @staticmethod
    def from_dataset(dataset: Dataset) -> DatasetCatalog:
        """Build from a Dataset loaded with tables, columns and relationships."""
        names = {t.id: t.table_name for t in dataset.tables}
        tables = []
        for t in sorted(dataset.tables, key=lambda t: t.table_name):
            columns = []
            for c in sorted(t.columns, key=lambda c: c.ordinal):
                profile: dict[str, Any] = c.profile or {}
                samples: list[str] = []
                if not c.is_sensitive:
                    samples = [str(v["value"]) for v in profile.get("top_values", [])] or [
                        str(v) for v in profile.get("examples", [])
                    ]
                columns.append(
                    CatalogColumn(
                        name=c.column_name,
                        data_type=c.data_type,
                        description=c.description,
                        is_primary_key=c.is_primary_key,
                        is_sensitive=c.is_sensitive,
                        null_pct=profile.get("null_pct"),
                        distinct_count=profile.get("distinct_count"),
                        samples=tuple(samples[:MAX_VALUES]),
                        min_value=None if c.is_sensitive else _str(profile.get("min")),
                        max_value=None if c.is_sensitive else _str(profile.get("max")),
                    )
                )
            tables.append(CatalogTable(t.table_name, t.description, t.row_count, tuple(columns)))
        relationships = tuple(
            CatalogRelationship(
                names[r.from_table_id], r.from_column, names[r.to_table_id], r.to_column
            )
            for r in dataset.relationships
        )
        return DatasetCatalog(
            dataset_id=str(dataset.id),
            name=dataset.name,
            schema_name=dataset.schema_name,
            reader_role=dataset.reader_role,
            tables=tuple(tables),
            relationships=relationships,
        )


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


class SchemaTools:
    def __init__(self, catalog: DatasetCatalog) -> None:
        self.catalog = catalog
        self._tables = {t.name: t for t in catalog.tables}

    # ------------------------------------------------------------- read side
    @property
    def table_names(self) -> list[str]:
        return sorted(self._tables)

    def table(self, name: str) -> CatalogTable:
        table = self._tables.get(name)
        if table is None:
            raise SchemaToolError(f"Unknown table “{name}”. Tables: {', '.join(self.table_names)}.")
        return table

    def table_catalog(self) -> list[dict[str, Any]]:
        """The light catalog for Query Understanding: names, sizes, time coverage."""
        out = []
        for t in self.catalog.tables:
            out.append(
                {
                    "table": t.name,
                    "description": t.description,
                    "row_count": t.row_count,
                    "columns": [c.name for c in t.columns],
                    "time_coverage": [
                        {"column": c.name, "min": c.min_value, "max": c.max_value}
                        for c in t.columns
                        if c.data_type in TIME_TYPES and c.min_value
                    ],
                }
            )
        return out

    # -------------------------------------------------------------- the tools
    def get_table_schema(self, table: str) -> dict[str, Any]:
        t = self.table(table)
        return {
            "table": t.name,
            "description": t.description,
            "row_count": t.row_count,
            "columns": [self.column_context(t.name, c.name).model_dump() for c in t.columns],
            "foreign_keys": [
                r.condition() for r in self.catalog.relationships if t.name == r.from_table
            ],
        }

    def get_join_paths(self, tables: list[str]) -> list[str]:
        """Join conditions connecting ``tables``: direct links, then one-hop bridges."""
        wanted = {self.table(name).name for name in tables}
        rels = self.catalog.relationships
        direct = [r for r in rels if r.from_table in wanted and r.to_table in wanted]
        paths = [r.condition() for r in direct]
        linked = {r.from_table for r in direct} | {r.to_table for r in direct}
        for name in sorted(wanted - linked if len(wanted) > 1 else set()):
            for r1 in rels:
                if name not in (r1.from_table, r1.to_table):
                    continue
                bridge = r1.to_table if r1.from_table == name else r1.from_table
                for r2 in rels:
                    if r2 is r1 or bridge not in (r2.from_table, r2.to_table):
                        continue
                    other = r2.to_table if r2.from_table == bridge else r2.from_table
                    if other in wanted and other != name:
                        for cond in (r1.condition(), r2.condition()):
                            if cond not in paths:
                                paths.append(cond)
        return paths

    def get_column_values(self, table: str, column: str) -> dict[str, Any]:
        t = self.table(table)
        c = t.column(column)
        if c is None:
            raise SchemaToolError(f"Table “{table}” has no column “{column}”.")
        if c.is_sensitive:
            return {"table": table, "column": column, "values": [], "note": "sensitive: hidden"}
        return {
            "table": table,
            "column": column,
            "values": list(c.samples),
            "distinct_count": c.distinct_count,
        }

    def column_context(self, table: str, column: str) -> ColumnContext:
        t = self.table(table)
        c = t.column(column)
        if c is None:
            raise SchemaToolError(f"Table “{table}” has no column “{column}”.")
        return ColumnContext(
            table=t.name,
            column=c.name,
            data_type=c.data_type,
            description=c.description,
            is_primary_key=c.is_primary_key,
            null_pct=c.null_pct,
            distinct_count=c.distinct_count,
            sample_values=list(c.samples[:10]),
            min_value=c.min_value,
            max_value=c.max_value,
        )

    def guard_policy(self, max_rows: int) -> GuardPolicy:
        return GuardPolicy(
            dataset_schema=self.catalog.schema_name,
            tables={t.name: {c.name: c.data_type for c in t.columns} for t in self.catalog.tables},
            max_rows=max_rows,
        )
