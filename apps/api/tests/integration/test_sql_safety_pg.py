"""Defence-in-depth on real PostgreSQL: destructive SQL fed *directly* to the executor
(bypassing the SQL Guard on purpose) must be refused by the database itself, classified
as non-retryable, and leave the data untouched. Also covers the EXPLAIN cost gate and
cancelling an in-flight query."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import asyncpg
import pytest

from app.agent.state import SQLAttempt
from app.agent.tools.errors import classify_attempt
from app.agent.tools.executor import ExecutionOutcome, PostgresExecutor
from app.agent.tools.schema import SchemaTools
from app.agent.tools.sql_guard import GuardPolicy, validate_sql
from app.core.config import Settings
from app.db.engines import open_databases
from app.db.models import Dataset
from tests.agent.fakes import shop_catalog
from tests.integration.conftest import PgUrls, run
from tests.integration.test_agent_pg import provision

pytestmark = pytest.mark.integration

DESTRUCTIVE = [
    "INSERT INTO orders (order_id) VALUES (999999999)",
    "UPDATE orders SET status = 'hacked'",
    "DELETE FROM order_items",
    "DROP TABLE orders",
    "TRUNCATE customers",
    "CREATE TABLE exfil AS SELECT * FROM customers",
    "ALTER TABLE orders ADD COLUMN pwned int",
]


def _policy() -> GuardPolicy:
    return SchemaTools(shop_catalog()).guard_policy(500)


@asynccontextmanager
async def executor_for(
    settings: Settings, dataset_id: uuid.UUID, **overrides: object
) -> AsyncIterator[tuple[PostgresExecutor, str]]:
    databases = await open_databases(settings)
    try:
        assert databases.sessions is not None and databases.executor is not None
        async with databases.sessions() as db:
            dataset = await db.get(Dataset, dataset_id)
            assert dataset is not None
            schema, role = dataset.schema_name, dataset.reader_role
        kwargs: dict[str, object] = {
            "schema": schema,
            "reader_role": role,
            "max_rows": 1000,
            "timeout_ms": 10_000,
            **overrides,
        }
        yield PostgresExecutor(databases.executor, **kwargs), schema  # type: ignore[arg-type]
    finally:
        await databases.close()


async def _counts(pg: PgUrls, schema: str) -> dict[str, int]:
    conn = await asyncpg.connect(PgUrls.dsn(pg.ingest))
    try:
        out = {}
        for table in ("orders", "order_items", "customers"):
            out[table] = int(await conn.fetchval(f'SELECT COUNT(*) FROM "{schema}"."{table}"'))
        return out
    finally:
        await conn.close()


def _diagnosis(outcome: ExecutionOutcome) -> SQLAttempt:
    return SQLAttempt(
        attempt=1,
        sql="x",
        explanation="",
        guard_status="accepted",
        exec_status=outcome.status if outcome.status in ("error", "timeout") else "error",
        error_code=outcome.error_code,
        exec_error=outcome.error_message,
    )


def test_destructive_sql_bypassing_the_guard_is_refused_by_postgres(
    pg: PgUrls, pg_settings: Callable[..., Settings]
) -> None:
    settings = pg_settings()
    client, dataset_id = provision(settings)
    client.__exit__(None, None, None)

    async def attack() -> list[tuple[str, ExecutionOutcome]]:
        async with executor_for(settings, dataset_id) as (executor, schema):
            before = await _counts(pg, schema)
            outcomes = [(sql, await executor.run(sql)) for sql in DESTRUCTIVE]
            after = await _counts(pg, schema)
            assert after == before, "row counts changed!"
            return outcomes

    for sql, outcome in run(attack()):
        # Layer 1 would have rejected it anyway (belt):
        assert not validate_sql(sql, _policy()).ok, sql
        # Layer 2, the database, refused it too (braces):
        assert outcome.status == "error", (sql, outcome)
        assert outcome.error_code in {"25006", "42501"}, (sql, outcome.error_code)
        diagnosis = classify_attempt(_diagnosis(outcome))
        assert diagnosis.category in {"unsafe_query", "permission_denied"}
        assert not diagnosis.recoverable, sql  # never retried


def test_other_schemas_stay_unreachable_even_without_the_guard(
    pg: PgUrls, pg_settings: Callable[..., Settings]
) -> None:
    settings = pg_settings()
    client, dataset_id = provision(settings)
    client.__exit__(None, None, None)

    async def attack() -> list[ExecutionOutcome]:
        async with executor_for(settings, dataset_id) as (executor, _):
            return [
                await executor.run("SELECT email FROM app.users"),
                await executor.run("SELECT passwd FROM pg_catalog.pg_shadow"),
            ]

    for outcome in run(attack()):
        assert outcome.status == "error" and outcome.error_code == "42501", outcome
        assert not classify_attempt(_diagnosis(outcome)).recoverable


def test_cost_gate_refuses_expensive_plans_without_executing(
    pg: PgUrls, pg_settings: Callable[..., Settings]
) -> None:
    settings = pg_settings()
    client, dataset_id = provision(settings)
    client.__exit__(None, None, None)
    sql = "SELECT COUNT(*) FROM orders o JOIN order_items oi ON oi.order_id = o.order_id"

    async def check() -> tuple[ExecutionOutcome, ExecutionOutcome]:
        async with executor_for(settings, dataset_id, max_plan_cost=0.5) as (tight, _):
            refused = await tight.run(sql)
        async with executor_for(settings, dataset_id, max_plan_cost=5_000_000) as (normal, _):
            allowed = await normal.run(sql)
        return refused, allowed

    refused, allowed = run(check())
    assert refused.status == "error" and refused.error_code == "COST_LIMIT"
    assert refused.plan_cost and refused.plan_cost > 0.5
    assert "was not executed" in (refused.error_message or "")
    diagnosis = classify_attempt(_diagnosis(refused))
    assert diagnosis.category == "too_expensive" and diagnosis.recoverable  # one repair allowed
    assert allowed.status == "ok" and allowed.rows[0][0] > 0


def test_cancellation_aborts_an_in_flight_query(
    pg: PgUrls, pg_settings: Callable[..., Settings]
) -> None:
    settings = pg_settings()
    client, dataset_id = provision(settings)
    client.__exit__(None, None, None)

    async def check() -> tuple[ExecutionOutcome, float]:
        cancel = asyncio.Event()
        async with executor_for(settings, dataset_id, cancel_event=cancel, max_plan_cost=0) as (
            executor,
            _,
        ):
            start = time.perf_counter()
            query = asyncio.ensure_future(executor.run("SELECT COUNT(*), pg_sleep(8) FROM orders"))
            await asyncio.sleep(0.4)
            cancel.set()
            outcome = await query
            return outcome, time.perf_counter() - start

    outcome, wall = run(check())
    assert outcome.status == "cancelled"
    assert wall < 4, f"cancel took {wall:.1f}s — the query ran on"
    # a cancelled executor refuses further work immediately
    assert outcome.error_message and "cancelled" in outcome.error_message
