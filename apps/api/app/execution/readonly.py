"""Read-only query execution against one dataset.

Every call runs in its own transaction on the executor pool:

    BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
    SET LOCAL ROLE ds_<id>_r;            -- the dataset's SELECT-only role
    SET LOCAL search_path = ds_<id>;
    SET LOCAL statement_timeout = …;
    <query>                              -- bind parameters only
    COMMIT;                              -- nothing to commit; SET LOCAL ends here

Server-built statements (dataset preview) and Guard-approved agent SQL both run here.
Agent SQL passes the SQL Guard first (app.agent.tools.sql_guard); this module is the
last line of defence, not the only one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import asyncpg

from app.db.identifiers import assert_dataset_schema, assert_reader_role, quote_ident


@dataclass(frozen=True)
class ReadOnlyResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    exec_ms: int
    column_types: list[str] = field(default_factory=list)  # PostgreSQL type names


def to_json_value(value: Any) -> Any:
    """Convert database values to JSON-safe values without losing meaning."""
    if isinstance(value, Decimal):
        # Exact decimals that fit in a float's integer precision become numbers.
        return float(value) if abs(value) < Decimal(10) ** 15 else str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


async def run_readonly(
    pool: asyncpg.Pool,
    *,
    schema: str,
    reader_role: str,
    sql: str,
    params: list[Any],
    max_rows: int,
    timeout_ms: int,
) -> ReadOnlyResult:
    schema = assert_dataset_schema(schema)
    role = assert_reader_role(reader_role)
    start = time.perf_counter()
    async with pool.acquire() as conn, conn.transaction(isolation="repeatable_read", readonly=True):
        await conn.execute(f"SET LOCAL ROLE {quote_ident(role)}")
        await conn.execute(f"SET LOCAL search_path = {quote_ident(schema)}")
        await conn.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
        stmt = await conn.prepare(sql)
        records = await stmt.fetch(*params)
        attributes = stmt.get_attributes()
        columns = [a.name for a in attributes]
        types = [a.type.name for a in attributes]
    truncated = len(records) > max_rows
    rows = [[to_json_value(v) for v in r.values()] for r in records[:max_rows]]
    elapsed = int((time.perf_counter() - start) * 1000)
    return ReadOnlyResult(columns, rows, truncated, elapsed, types)
