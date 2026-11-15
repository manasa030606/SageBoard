"""Demo seeding into the warehouse, the schema catalog it produces, and who can read it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import asyncpg
import pytest

from app.execution.readonly import run_readonly
from tests.integration.conftest import PgUrls, fetch, run

pytestmark = pytest.mark.integration

EXPECTED_ROWS = {"customers": 300, "products": 40}
EXPECTED_FKS = {
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("orders", "customer_id", "customers", "customer_id"),
    ("payments", "order_id", "orders", "order_id"),
}


@pytest.fixture
def demo(seed: Callable[..., Any]) -> Any:
    return seed(replace=True)


def catalog(pg: PgUrls, dataset_id: Any) -> dict[str, Any]:
    tables = run(
        fetch(
            pg.app,
            "SELECT table_name, row_count, primary_key FROM app.dataset_tables WHERE dataset_id = $1",
            dataset_id,
        )
    )
    rels = run(
        fetch(
            pg.app,
            "SELECT f.table_name AS ft, r.from_column, t.table_name AS tt, r.to_column "
            "FROM app.dataset_relationships r "
            "JOIN app.dataset_tables f ON f.id = r.from_table_id "
            "JOIN app.dataset_tables t ON t.id = r.to_table_id WHERE r.dataset_id = $1",
            dataset_id,
        )
    )
    return {
        "tables": {r["table_name"]: r for r in tables},
        "fks": {(r["ft"], r["from_column"], r["tt"], r["to_column"]) for r in rels},
    }


def test_seed_loads_tables_and_records_the_catalog(pg: PgUrls, demo: Any) -> None:
    assert demo.created
    assert demo.dataset.status == "ready"
    cat = catalog(pg, demo.dataset.id)
    assert set(cat["tables"]) == {"customers", "products", "orders", "order_items", "payments"}
    for table, rows in EXPECTED_ROWS.items():
        assert cat["tables"][table]["row_count"] == rows
    for table, row in cat["tables"].items():
        assert row["row_count"] == demo.row_counts[table]
    assert cat["tables"]["orders"]["primary_key"] == '["order_id"]'
    assert cat["fks"] == EXPECTED_FKS


def test_seed_is_idempotent_and_replace_rebuilds(
    pg: PgUrls, demo: Any, seed: Callable[..., Any]
) -> None:
    again = seed()
    assert not again.created
    assert again.dataset.id == demo.dataset.id

    rebuilt = seed(replace=True)
    assert rebuilt.created
    assert rebuilt.dataset.schema_name != demo.dataset.schema_name
    assert rebuilt.checksum == demo.checksum  # same seed → same data
    old = run(
        fetch(pg.owner, "SELECT 1 FROM pg_namespace WHERE nspname = $1", demo.dataset.schema_name)
    )
    old_role = run(
        fetch(pg.owner, "SELECT 1 FROM pg_roles WHERE rolname = $1", demo.dataset.reader_role)
    )
    assert old == []
    assert old_role == []


def test_sensitive_columns_are_flagged_and_profiled_without_values(pg: PgUrls, demo: Any) -> None:
    rows = run(
        fetch(
            pg.app,
            "SELECT c.column_name, c.is_sensitive, c.profile FROM app.dataset_columns c "
            "JOIN app.dataset_tables t ON t.id = c.table_id "
            "WHERE t.dataset_id = $1 AND t.table_name = 'customers'",
            demo.dataset.id,
        )
    )
    by_name = {r["column_name"]: r for r in rows}
    for name in ("email", "first_name", "last_name"):
        assert by_name[name]["is_sensitive"], name
        assert "@" not in by_name[name]["profile"]
    assert not by_name["segment"]["is_sensitive"]
    assert "Consumer" in by_name["segment"]["profile"]


# ------------------------------------------------------------------ permissions
async def _try(url: str, sql: str) -> str:
    conn = await asyncpg.connect(PgUrls.dsn(url))
    try:
        await conn.fetch(sql)
    except asyncpg.PostgresError as exc:
        return type(exc).__name__
    finally:
        await conn.close()
    return "ok"


def test_app_role_cannot_read_or_write_dataset_data(pg: PgUrls, demo: Any) -> None:
    schema = demo.dataset.schema_name
    assert (
        run(_try(pg.app, f'SELECT * FROM "{schema}".orders LIMIT 1'))
        == "InsufficientPrivilegeError"
    )
    assert run(_try(pg.app, f'DELETE FROM "{schema}".orders')) == "InsufficientPrivilegeError"


def test_executor_reads_only_through_the_dataset_reader_role(pg: PgUrls, demo: Any) -> None:
    schema, role = demo.dataset.schema_name, demo.dataset.reader_role
    assert (
        run(_try(pg.executor, f'SELECT * FROM "{schema}".orders LIMIT 1'))
        == "InsufficientPrivilegeError"
    )

    async def read() -> Any:
        pool = await asyncpg.create_pool(PgUrls.dsn(pg.executor), min_size=0, max_size=1)
        try:
            return await run_readonly(
                pool,
                schema=schema,
                reader_role=role,
                sql="SELECT count(*) AS n FROM orders",
                params=[],
                max_rows=10,
                timeout_ms=5000,
            )
        finally:
            await pool.close()

    result = run(read())
    assert result.rows[0][0] == demo.row_counts["orders"]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("DELETE FROM payments", "ReadOnlySQLTransactionError"),
        ("UPDATE orders SET status = 'x'", "ReadOnlySQLTransactionError"),
        ("CREATE TABLE evil (id int)", "ReadOnlySQLTransactionError"),
        ("SELECT * FROM app.users", "InsufficientPrivilegeError"),
        ("SELECT pg_sleep(2)", "QueryCanceledError"),
    ],
)
def test_executor_refuses_writes_foreign_schemas_and_long_queries(
    pg: PgUrls, demo: Any, sql: str, expected: str
) -> None:
    async def attempt() -> str:
        pool = await asyncpg.create_pool(PgUrls.dsn(pg.executor), min_size=0, max_size=1)
        try:
            await run_readonly(
                pool,
                schema=demo.dataset.schema_name,
                reader_role=demo.dataset.reader_role,
                sql=sql,
                params=[],
                max_rows=10,
                timeout_ms=500,
            )
        except asyncpg.PostgresError as exc:
            return type(exc).__name__
        finally:
            await pool.close()
        return "ok"

    assert run(attempt()) == expected


def test_reader_role_cannot_log_in_and_is_scoped(pg: PgUrls, demo: Any) -> None:
    rows = run(
        fetch(
            pg.owner,
            "SELECT rolcanlogin, rolinherit FROM pg_roles WHERE rolname = $1",
            demo.dataset.reader_role,
        )
    )
    assert rows[0]["rolcanlogin"] is False
    assert rows[0]["rolinherit"] is False


def test_executor_pins_session_timezone_to_utc(pg: PgUrls, demo: Any) -> None:
    """A non-UTC server/role default must not shift which month or day a timestamp falls in."""

    async def read() -> list[Any]:
        pool = await asyncpg.create_pool(
            PgUrls.dsn(pg.executor),
            min_size=0,
            max_size=1,
            server_settings={"timezone": "Asia/Kolkata"},
        )
        try:
            result = await run_readonly(
                pool,
                schema=demo.dataset.schema_name,
                reader_role=demo.dataset.reader_role,
                sql=(
                    "SELECT current_setting('TimeZone') AS tz, "
                    "to_char(TIMESTAMPTZ '2026-10-31 20:00:00+00', 'YYYY-MM-DD') AS day"
                ),
                params=[],
                max_rows=10,
                timeout_ms=5000,
            )
            return list(result.rows[0])
        finally:
            await pool.close()

    # Kolkata (UTC+5:30) would say 2026-11-01 for this instant.
    assert run(read()) == ["UTC", "2026-10-31"]
