"""Warehouse operations on the ingest connection (role ``sageboard_ingest``).

- provision / drop a dataset schema and its SELECT-only reader role
- create typed tables and bulk-load rows with COPY (no SQL string building for values)
- introspect the real catalog: tables, columns, types, primary keys, foreign keys
- profile columns: missing %, distinct count, range, top values / examples

All identifiers pass through ``quote_ident``; all values are bind parameters or COPY data.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from app.db.identifiers import assert_dataset_schema, assert_reader_role, qualified, quote_ident
from app.ingestion.types import PG_TYPE, ColumnType

EXECUTOR_ROLE = "sageboard_executor"
ROW_ID = "_row_id"
COPY_BATCH = 5_000
TOP_VALUES_MAX_DISTINCT = 50


# ------------------------------------------------------------------ provisioning
async def provision_schema(conn: asyncpg.Connection, schema: str, reader_role: str) -> None:
    schema, role = assert_dataset_schema(schema), assert_reader_role(reader_role)
    await conn.execute(f"CREATE SCHEMA {quote_ident(schema)}")
    await conn.execute(f"REVOKE ALL ON SCHEMA {quote_ident(schema)} FROM PUBLIC")
    await conn.execute(f"CREATE ROLE {quote_ident(role)} NOLOGIN NOINHERIT")


async def grant_reader(conn: asyncpg.Connection, schema: str, reader_role: str) -> None:
    """Called after all tables exist: the reader role may only SELECT in this schema."""
    schema, role = assert_dataset_schema(schema), assert_reader_role(reader_role)
    await conn.execute(f"GRANT USAGE ON SCHEMA {quote_ident(schema)} TO {quote_ident(role)}")
    await conn.execute(
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {quote_ident(schema)} TO {quote_ident(role)}"
    )
    await conn.execute(f"GRANT {quote_ident(role)} TO {quote_ident(EXECUTOR_ROLE)}")


async def drop_schema(conn: asyncpg.Connection, schema: str, reader_role: str) -> None:
    schema, role = assert_dataset_schema(schema), assert_reader_role(reader_role)
    await conn.execute(f"DROP SCHEMA IF EXISTS {quote_ident(schema)} CASCADE")
    exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role)
    if exists:
        await conn.execute(f"DROP ROLE {quote_ident(role)}")


# ------------------------------------------------------------------ tables & data
@dataclass(frozen=True)
class ColumnDef:
    name: str
    type: ColumnType
    not_null: bool = False


async def create_table(
    conn: asyncpg.Connection,
    schema: str,
    table: str,
    columns: Sequence[ColumnDef],
    *,
    primary_key: Sequence[str] | None = None,
    with_row_id: bool = True,
) -> None:
    parts = []
    if with_row_id:
        parts.append(f"{quote_ident(ROW_ID)} bigint GENERATED ALWAYS AS IDENTITY")
    for c in columns:
        parts.append(f"{quote_ident(c.name)} {PG_TYPE[c.type]}{' NOT NULL' if c.not_null else ''}")
    if primary_key:
        parts.append(f"PRIMARY KEY ({', '.join(quote_ident(k) for k in primary_key)})")
    elif with_row_id:
        parts.append(f"PRIMARY KEY ({quote_ident(ROW_ID)})")
    await conn.execute(
        f"CREATE TABLE {qualified(schema, table)} (\n  " + ",\n  ".join(parts) + "\n)"
    )


async def copy_rows(
    conn: asyncpg.Connection,
    schema: str,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> int:
    """Bulk-load rows with the COPY protocol, in batches. Returns rows written."""
    for name in (schema, table, *columns):
        quote_ident(name)  # validate
    written = 0
    batch: list[Sequence[Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= COPY_BATCH:
            await conn.copy_records_to_table(
                table, records=batch, columns=list(columns), schema_name=schema
            )
            written += len(batch)
            batch = []
    if batch:
        await conn.copy_records_to_table(
            table, records=batch, columns=list(columns), schema_name=schema
        )
        written += len(batch)
    return written


# ------------------------------------------------------------------ introspection
@dataclass
class InspectedColumn:
    name: str
    type: ColumnType
    pg_type: str
    nullable: bool
    ordinal: int


@dataclass
class InspectedForeignKey:
    constraint_name: str
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


@dataclass
class InspectedTable:
    name: str
    columns: list[InspectedColumn]
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[InspectedForeignKey] = field(default_factory=list)


_PG_TO_COLUMN_TYPE: dict[str, ColumnType] = {
    "integer": "integer",
    "smallint": "integer",
    "bigint": "bigint",
    "numeric": "numeric",
    "real": "numeric",
    "double precision": "numeric",
    "boolean": "boolean",
    "date": "date",
    "timestamp with time zone": "timestamptz",
    "timestamp without time zone": "timestamptz",
    "text": "text",
    "character varying": "text",
    "character": "text",
}

_COLUMNS_SQL = """
SELECT table_name, column_name, ordinal_position, data_type, is_nullable = 'YES' AS nullable
FROM information_schema.columns
WHERE table_schema = $1
ORDER BY table_name, ordinal_position
"""

_CONSTRAINTS_SQL = """
SELECT con.conname::text AS name, con.contype::text AS kind, cl.relname::text AS table_name,
       ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum ORDER BY k.ord)::text[] AS columns,
       fcl.relname::text AS ref_table,
       ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY AS k(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum ORDER BY k.ord)::text[] AS ref_columns
FROM pg_constraint con
JOIN pg_class cl ON cl.oid = con.conrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace
LEFT JOIN pg_class fcl ON fcl.oid = con.confrelid
WHERE n.nspname = $1 AND con.contype IN ('p', 'f')
ORDER BY cl.relname, con.conname
"""


async def inspect_schema(conn: asyncpg.Connection, schema: str) -> list[InspectedTable]:
    """Read the live structure of a dataset schema from the PostgreSQL catalog."""
    schema = assert_dataset_schema(schema)
    tables: dict[str, InspectedTable] = {}
    for r in await conn.fetch(_COLUMNS_SQL, schema):
        table = tables.setdefault(r["table_name"], InspectedTable(r["table_name"], []))
        if r["column_name"] == ROW_ID:
            continue  # internal surrogate key, hidden from users and the agent
        table.columns.append(
            InspectedColumn(
                name=r["column_name"],
                type=_PG_TO_COLUMN_TYPE.get(r["data_type"], "text"),
                pg_type=r["data_type"],
                nullable=r["nullable"],
                ordinal=r["ordinal_position"],
            )
        )
    for r in await conn.fetch(_CONSTRAINTS_SQL, schema):
        owner = tables.get(r["table_name"])
        if owner is None:
            continue
        if r["kind"] == "p":
            owner.primary_key = [c for c in r["columns"] if c != ROW_ID]
        else:
            owner.foreign_keys.append(
                InspectedForeignKey(
                    r["name"], list(r["columns"]), r["ref_table"], list(r["ref_columns"])
                )
            )
    return sorted(tables.values(), key=lambda t: t.name)


# ------------------------------------------------------------------ profiling
@dataclass
class ColumnProfile:
    null_pct: float
    distinct_count: int
    min: str | None
    max: str | None
    top_values: list[dict[str, Any]]
    examples: list[str]

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


async def profile_table(
    conn: asyncpg.Connection,
    schema: str,
    table: str,
    columns: Sequence[InspectedColumn],
    sensitive: set[str],
) -> tuple[int, dict[str, ColumnProfile]]:
    """Exact row count plus per-column statistics. Sensitive columns get counts only."""
    target = qualified(schema, table)
    aggregates = ["count(*) AS n"]
    for i, c in enumerate(columns):
        col = quote_ident(c.name)
        aggregates.append(f"count({col}) AS nn{i}")
        aggregates.append(f"count(DISTINCT {col}) AS d{i}")
        ranged = c.type not in ("boolean", "text") and c.name not in sensitive
        aggregates.append(f"min({col})::text AS lo{i}" if ranged else f"NULL::text AS lo{i}")
        aggregates.append(f"max({col})::text AS hi{i}" if ranged else f"NULL::text AS hi{i}")
    stats = await conn.fetchrow(f"SELECT {', '.join(aggregates)} FROM {target}")  # noqa: S608 - identifiers validated + quoted
    assert stats is not None  # noqa: S101 - aggregate query always returns a row
    total = int(stats["n"])

    profiles: dict[str, ColumnProfile] = {}
    for i, c in enumerate(columns):
        distinct = int(stats[f"d{i}"])
        top: list[dict[str, Any]] = []
        examples: list[str] = []
        if c.name not in sensitive and c.type in ("text", "boolean"):
            col = quote_ident(c.name)
            if distinct <= TOP_VALUES_MAX_DISTINCT:
                rows = await conn.fetch(
                    f"SELECT {col}::text AS v, count(*) AS n FROM {target} WHERE {col} IS NOT NULL "  # noqa: S608 - identifiers validated + quoted
                    f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10"
                )
                top = [{"value": r["v"], "count": int(r["n"])} for r in rows]
            else:
                rows = await conn.fetch(
                    f"SELECT DISTINCT {col}::text AS v FROM {target} WHERE {col} IS NOT NULL ORDER BY 1 LIMIT 5"  # noqa: S608 - identifiers validated + quoted
                )
                examples = [str(r["v"])[:80] for r in rows]
        profiles[c.name] = ColumnProfile(
            null_pct=round(1 - int(stats[f"nn{i}"]) / total, 4) if total else 0.0,
            distinct_count=distinct,
            min=stats[f"lo{i}"],
            max=stats[f"hi{i}"],
            top_values=top,
            examples=examples,
        )
    return total, profiles
