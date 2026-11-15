"""SQL execution tool.

``PostgresExecutor`` runs Guard-approved SQL through the Phase 3 read-only executor
(dataset reader role, ``READ ONLY`` transaction, statement timeout). Database errors are
returned as data (SQLSTATE + a sanitised message) so the Error Recovery agent can use
them; they never crash the workflow. Infrastructure failures (pool closed, network)
are raised and handled by the node wrapper.

Phase 6 adds two protections:

- **Cost gate.** Before executing, ``EXPLAIN (FORMAT JSON)`` estimates the plan's cost
  (in PostgreSQL's arbitrary cost units, not milliseconds). Above the ceiling, the
  query is refused with ``error_code="COST_LIMIT"`` — classified as recoverable, so the
  Error Recovery agent gets one chance to aggregate earlier. The estimate is rough;
  the ceiling is generous, and the statement timeout remains the hard stop.
- **Cancellation.** When the run's cancel event fires mid-query, the asyncio task
  running the query is cancelled; asyncpg then sends PostgreSQL a cancel request for
  the in-flight statement (the ``pg_cancel_backend`` mechanism, keyed to our own
  backend), so the database stops working on it instead of running to the timeout.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import asyncpg

from app.execution.readonly import ReadOnlyResult, run_readonly

TIMEOUT_SQLSTATE = "57014"
MAX_ERROR_CHARS = 300
COST_LIMIT_CODE = "COST_LIMIT"


@dataclass(frozen=True)
class ExecutionOutcome:
    status: Literal["ok", "error", "timeout", "cancelled"]
    columns: list[tuple[str, str]] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    exec_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
    plan_cost: float | None = None


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
        max_plan_cost: float = 0,  # 0 disables the cost gate
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self._pool = pool
        self._schema = schema
        self._role = reader_role
        self._max_rows = max_rows
        self._timeout_ms = timeout_ms
        self._max_plan_cost = max_plan_cost
        self._cancel = cancel_event

    async def run(self, sql: str) -> ExecutionOutcome:
        start = time.perf_counter()

        def elapsed() -> int:
            return int((time.perf_counter() - start) * 1000)

        if self._cancelled():
            return self._cancelled_outcome(elapsed())
        try:
            if self._max_plan_cost > 0:
                cost = await self._plan_cost(sql)
                if cost is not None and cost > self._max_plan_cost:
                    return ExecutionOutcome(
                        status="error",
                        exec_ms=elapsed(),
                        error_code=COST_LIMIT_CODE,
                        error_message=(
                            f"estimated plan cost {cost:,.0f} exceeds the ceiling "
                            f"{self._max_plan_cost:,.0f}; the query was not executed"
                        ),
                        plan_cost=cost,
                    )
            result = await self._query(sql)
        except asyncio.CancelledError:
            if self._cancelled():  # our cancel, not the caller's teardown
                return self._cancelled_outcome(elapsed())
            raise
        except asyncpg.PostgresError as exc:
            code = getattr(exc, "sqlstate", None)
            return ExecutionOutcome(
                status="timeout" if code == TIMEOUT_SQLSTATE else "error",
                exec_ms=elapsed(),
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

    # ------------------------------------------------------------------ internals
    def _cancelled(self) -> bool:
        return self._cancel is not None and self._cancel.is_set()

    @staticmethod
    def _cancelled_outcome(exec_ms: int) -> ExecutionOutcome:
        return ExecutionOutcome(
            status="cancelled",
            exec_ms=exec_ms,
            error_message="The analysis was cancelled; the database query was cancelled too.",
        )

    async def _query(self, sql: str) -> ReadOnlyResult:
        """Run ``sql``, aborting the in-flight statement if the run is cancelled."""
        query = asyncio.ensure_future(self._run_readonly(sql))
        if self._cancel is None:
            return await query
        waiter = asyncio.ensure_future(self._cancel.wait())
        try:
            await asyncio.wait({query, waiter}, return_when=asyncio.FIRST_COMPLETED)
            if not query.done():
                # Cancelling the task makes asyncpg send the server a cancel request
                # for the running statement before releasing the connection.
                query.cancel()
                with suppress(asyncio.CancelledError, asyncpg.PostgresError):
                    await query
                raise asyncio.CancelledError
            return query.result()
        finally:
            waiter.cancel()
            with suppress(asyncio.CancelledError):
                await waiter

    async def _run_readonly(self, sql: str) -> ReadOnlyResult:
        return await run_readonly(
            self._pool,
            schema=self._schema,
            reader_role=self._role,
            sql=sql,
            params=[],
            max_rows=self._max_rows,
            timeout_ms=self._timeout_ms,
        )

    async def _plan_cost(self, sql: str) -> float | None:
        """Total cost of the query plan, estimated by PostgreSQL (never executes)."""
        result = await self._run_readonly(f"EXPLAIN (FORMAT JSON) {sql}")
        try:
            cell = result.rows[0][0]
            plans = json.loads(cell) if isinstance(cell, str) else cell
            return float(plans[0]["Plan"]["Total Cost"])
        except (IndexError, KeyError, TypeError, ValueError):
            return None  # unparseable plan: fail open, the timeout still protects
