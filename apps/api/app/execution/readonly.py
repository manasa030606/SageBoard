"""Read-only query execution against one dataset.

Every call runs in its own transaction on the executor pool:

    BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
    SET LOCAL ROLE ds_<id>_r;            -- the dataset's SELECT-only role
    SET LOCAL search_path = ds_<id>;
    SET LOCAL statement_timeout = …;
    <query>                              -- bind parameters only
    COMMIT;                              -- nothing to commit; SET LOCAL ends here

Phase 3 uses this only for server-built statements (dataset preview). LLM-generated
SQL will additionally pass the SQL Guard first (next phases); this module is the
last line of defence, not the only one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
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
        columns = [a.name for a in stmt.get_attributes()]
    truncated = len(records) > max_rows
    rows = [[to_json_value(v) for v in r.values()] for r in records[:max_rows]]
    return ReadOnlyResult(columns, rows, truncated, int((time.perf_counter() - start) * 1000))
