"""Performance benchmark: Guard validation, query execution and the EXPLAIN cost gate."""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any

from app.agent.tools.executor import PostgresExecutor
from app.agent.tools.schema import SchemaTools
from app.agent.tools.sql_guard import validate_sql
from app.core.config import Settings
from app.db.engines import open_databases
from evals.cases import CASES
from evals.harness import open_env
from evals.safety import _catalog

CARTESIAN = [
    ("comma join, 2 tables", "SELECT COUNT(*) AS n FROM customers c, orders o"),
    ("CROSS JOIN, 2 tables", "SELECT COUNT(*) AS n FROM customers c CROSS JOIN orders o"),
    (
        "comma join, 3 tables",
        "SELECT COUNT(*) AS n FROM customers c, orders o, order_items oi",
    ),
    (
        "join with ON (true)",
        "SELECT COUNT(*) AS n FROM orders o JOIN order_items oi ON TRUE",
    ),
]


def _stats(xs: list[float]) -> dict[str, float]:
    s = sorted(xs)
    return {
        "p50": s[len(s) // 2],
        "p95": s[min(len(s) - 1, round(0.95 * (len(s) - 1)))],
        "mean": statistics.fmean(s),
        "count": len(s),
    }


async def _measure(settings: Settings, schema: str, role: str, policy: Any, repeats: int) -> Any:
    databases = await open_databases(settings)
    try:
        assert databases.executor is not None
        ex = PostgresExecutor(
            databases.executor,
            schema=schema,
            reader_role=role,
            max_rows=settings.agent_max_result_rows,
            timeout_ms=settings.executor_statement_timeout_ms,
            max_plan_cost=settings.executor_max_plan_cost,
        )
        per_step: dict[str, list[float]] = {}
        wall: list[float] = []
        for case in CASES:
            if case.kind != "answer":
                continue
            for i, step in enumerate(case.steps, 1):
                for _ in range(repeats):
                    t0 = time.perf_counter()
                    out = await ex.run(step.sql)
                    wall.append((time.perf_counter() - t0) * 1000)
                    if out.status == "ok":
                        per_step.setdefault(f"{case.id}.s{i}", []).append(float(out.exec_ms))
        probes = []
        for name, sql in CARTESIAN:
            res = validate_sql(sql, policy)
            t0 = time.perf_counter()
            out = await ex.run(sql)
            probes.append(
                {
                    "name": name,
                    "guard_ok": res.ok,
                    "status": out.status,
                    "sqlstate": out.error_code,
                    "plan_cost": out.plan_cost,
                    "ms": (time.perf_counter() - t0) * 1000,
                }
            )
        return per_step, wall, probes
    finally:
        await databases.close()


def cartesian_summary(probes: list[dict[str, Any]], gate: float) -> str:
    stopped = [p for p in probes if p["status"] != "ok"]
    ran = [p for p in probes if p["status"] == "ok"]
    rejected = sum(not p["guard_ok"] for p in probes)
    text = (
        f"The Guard rejected {rejected}/{len(probes)} Cartesian-product statements. "
        f"With the Guard bypassed, the EXPLAIN cost gate ({gate:,.0f}) alone stopped "
        f"{len(stopped)}/{len(probes)} before they returned rows"
    )
    if ran:
        text += "; these ran to completion: " + ", ".join(p["name"] for p in ran)
    return text + "."


def run_bench(settings: Settings, scale: str, repeats: int = 5) -> dict[str, Any]:
    with open_env(settings, "oracle", scale) as env:
        catalog, schema, role = _catalog(settings, env.dataset_id)
        policy = SchemaTools(catalog).guard_policy(max_rows=5000)
        sqls = [s.sql for c in CASES if c.kind == "answer" for s in c.steps]
        g: list[float] = []
        for _ in range(repeats):
            for sql in sqls:
                t0 = time.perf_counter()
                validate_sql(sql, policy)
                g.append((time.perf_counter() - t0) * 1000)
        per_step, wall, probes = asyncio.run(_measure(settings, schema, role, policy, repeats))
        medians = [statistics.median(v) for v in per_step.values()]
        slow = sorted(per_step.items(), key=lambda kv: -statistics.median(kv[1]))[:3]
        rows = {
            t["table_name"]: t["row_count"]
            for t in env.client.get(f"/api/v1/datasets/{env.dataset_id}").json()["tables"]
        }
        return {
            "scale": scale,
            "rows": ", ".join(f"{k} {v:,}" for k, v in rows.items()),
            "repeats": repeats,
            "measurements": {
                "Guard validation (ms per statement)": _stats(g),
                "Query execution, per reference query (ms, median of repeats)": _stats(medians),
                "Query round trip incl. EXPLAIN cost gate (ms)": _stats(wall),
            },
            "cartesian": probes,
            "notes": [
                "Slowest reference queries by median execution time: "
                + ", ".join(f"{k} ({statistics.median(v):.0f} ms)" for k, v in slow),
                "Cost-gate probe: " + cartesian_summary(probes, settings.executor_max_plan_cost),
            ],
        }
