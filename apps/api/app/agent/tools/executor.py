"""SQL execution tool.

``PostgresExecutor`` runs Guard-approved SQL through the Phase 3 read-only executor
(dataset reader role, ``READ ONLY`` transaction, statement timeout). Database errors are
returned as data (SQLSTATE + a sanitised message) so the Error Recovery agent can use
them; they never crash the workflow. Infrastructure failures (pool closed, network)
are raised and handled by the node wrapper.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import asyncpg

from app.execution.readonly import run_readonly

TIMEOUT_SQLSTATE = "57014"
MAX_ERROR_CHARS = 300


@dataclass(frozen=True)
class ExecutionOutcome:
    status: Literal["ok", "error", "timeout"]
    columns: list[tuple[str, str]] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    exec_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None


class SqlExecutor(Protocol):
    async def run(self, sql: str) -> ExecutionOutcome: ...


def sanitize_db_error(exc: asyncpg.PostgresError) -> str:
    """Message + hint only. ``detail`` can contain row values, so it is dropped."""
    message = str(getattr(exc, "message", None) or exc)
    hint = getattr(exc, "hint", None)
    text = f"{message} (hint: {hint})" if hint else message
    return " ".join(text.split())[:MAX_ERROR_CHARS]


class PostgresExecutor:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        schema: str,
        reader_role: str,
        max_rows: int,
        timeout_ms: int,
    ) -> None:
        self._pool = pool
        self._schema = schema
        self._role = reader_role
        self._max_rows = max_rows
        self._timeout_ms = timeout_ms

    async def run(self, sql: str) -> ExecutionOutcome:
        start = time.perf_counter()
        try:
            result = await run_readonly(
                self._pool,
                schema=self._schema,
                reader_role=self._role,
                sql=sql,
                params=[],
                max_rows=self._max_rows,
                timeout_ms=self._timeout_ms,
            )
        except asyncpg.PostgresError as exc:
            code = getattr(exc, "sqlstate", None)
            return ExecutionOutcome(
                status="timeout" if code == TIMEOUT_SQLSTATE else "error",
                exec_ms=int((time.perf_counter() - start) * 1000),
                error_code=code,
                error_message=sanitize_db_error(exc),
            )
        return ExecutionOutcome(
            status="ok",
            columns=list(zip(result.columns, result.column_types, strict=True)),
            rows=result.rows,
            truncated=result.truncated,
            exec_ms=result.exec_ms,
        )
