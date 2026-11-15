"""The agent against real PostgreSQL: real catalog, SQL Guard, read-only executor and
database errors. Only the model is scripted (tests/agent/fakes.py)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agent.graph import build_graph, initial_state, run_graph
from app.agent.llm.client import LLMMessage, StructuredLLM
from app.agent.runtime import AgentDeps
from app.agent.state import AgentState
from app.agent.tools.executor import ExecutionOutcome, PostgresExecutor
from app.agent.tools.schema import DatasetCatalog, SchemaTools
from app.core.config import Settings
from app.db.engines import open_databases
from app.db.models import Dataset, DatasetTable
from app.main import create_app
from tests.agent.fakes import ScriptedProvider, budget, data_from, items
from tests.integration.conftest import PgUrls, run, sign_up

pytestmark = pytest.mark.integration

LINE = "oi.quantity * oi.unit_price * (1 - oi.discount)"
BOUNDS = "WITH bounds AS (SELECT DATE_TRUNC('month', MAX(order_date)) AS cur FROM orders) "
FROM = (
    "FROM order_items oi JOIN orders o ON o.order_id = oi.order_id "
    "JOIN products p ON p.product_id = oi.product_id CROSS JOIN bounds b "
    "WHERE o.status <> 'cancelled' GROUP BY p.category ORDER BY p.category"
)
GOOD_SQL = (
    f"{BOUNDS}SELECT p.category, "
    f"ROUND(SUM({LINE}) FILTER (WHERE o.order_date >= b.cur - INTERVAL '1 month' AND o.order_date < b.cur)::numeric, 2) AS revenue_before, "
    f"ROUND(SUM({LINE}) FILTER (WHERE o.order_date >= b.cur)::numeric, 2) AS revenue_after {FROM}"
)
# Passes the Guard (every column exists) but PostgreSQL rejects it: SUM over a text column.
BAD_SQL = f"{BOUNDS}SELECT p.category, SUM(o.status) AS revenue_before, SUM({LINE}) AS revenue_after {FROM}"

UNDERSTANDING = {
    "status": "answerable",
    "restated_question": "How did revenue by category change in the latest month vs the month before?",
    "intent": "comparison",
    "metrics": ["revenue"],
    "dimensions": ["category"],
    "filters": ["exclude cancelled"],
    "time_range": "latest month in the data vs the previous month",
    "assumptions": [
        "Revenue = quantity × unit_price × (1 − discount), excluding cancelled orders."
    ],
}
PLAN = {
    "steps": [
        {
            "step_id": "s1",
            "purpose": "Revenue by category, previous vs latest month",
            "expected_output": "one row per category with revenue_before and revenue_after",
        }
    ],
    "analysis_tasks": ["change by category and contribution"],
    "final_answer_shape": "Which categories moved most.",
}


def insight_from_facts(messages: list[LLMMessage]) -> dict[str, Any]:
    """A scripted 'model' that copies the real computed numbers from the facts it was given."""
    fact = next(f for f in data_from(messages, "facts") if f["kind"] == "group_change")
    top = fact["value"][0]
    return {
        "insights": [
            {
                "headline": f"{top['label']} revenue went from {top['before']:,.2f} to {top['after']:,.2f}",
                "detail": f"That is the largest change of any category ({top['change']:,.2f}).",
                "category": "finding",
                "evidence": [{"kind": "fact", "fact_id": fact["fact_id"]}],
                "confidence": "high",
            }
        ]
    }


def summary_from_insights(messages: list[LLMMessage]) -> dict[str, Any]:
    return {"summary": data_from(messages, "verified_insights")[0]["headline"] + "."}


def judge(messages: list[LLMMessage]) -> dict[str, Any]:
    return {
        "metrics_match": True,
        "time_period_match": True,
        "insights": [{"insight_id": "i1", "supported": True}],
    }


def script(first_sql: str = BAD_SQL) -> ScriptedProvider:
    return ScriptedProvider(
        {
            "understand_query": [UNDERSTANDING],
            "retrieve_schema": [
                {"action": "get_table_schema", "tables": ["orders", "order_items", "products"]},
                {
                    "action": "finish",
                    "selected_tables": ["orders", "order_items", "products"],
                    "rationale": "r",
                },
            ],
            "plan_analysis": [PLAN],
            "generate_sql": [{"sql": first_sql, "explanation": "first try"}],
            "recover_error": [
                {
                    "diagnosis": "status is text; revenue comes from order_items.",
                    "sql": GOOD_SQL,
                    "change_summary": "fixed",
                }
            ],
            "analyze_results": [
                {
                    "calls": [
                        {
                            "tool": "group_change",
                            "step_id": "s1",
                            "label_column": "category",
                            "before_column": "revenue_before",
                            "after_column": "revenue_after",
                            "description": "Revenue change by category",
                            "unit": "USD",
                        }
                    ]
                }
            ],
            "generate_visualization": [
                {
                    "charts": [
                        {
                            "chart_type": "grouped_bar",
                            "step_id": "s1",
                            "x": "category",
                            "y": ["revenue_before", "revenue_after"],
                            "title": "Revenue by category",
                        }
                    ]
                }
            ],
            "generate_insights": [insight_from_facts],
            "verify_insights": [judge],
            "compose_response": [summary_from_insights],
        }
    )


def provision(settings: Settings) -> tuple[TestClient, uuid.UUID]:
    client = TestClient(create_app(settings))
    client.__enter__()
    sign_up(client)
    response = client.post("/api/v1/datasets/demo")
    assert response.status_code in {200, 201}, response.text
    return client, uuid.UUID(response.json()["dataset"]["id"])


class RecordingExecutor(PostgresExecutor):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.sql: list[str] = []

    async def run(self, sql: str) -> ExecutionOutcome:
        self.sql.append(sql)
        return await super().run(sql)


async def _run_agent(
    settings: Settings, dataset_id: uuid.UUID, provider: ScriptedProvider
) -> tuple[AgentState, RecordingExecutor]:
    databases = await open_databases(settings)
    try:
        assert databases.sessions is not None and databases.executor is not None
        async with databases.sessions() as db:
            dataset = await db.scalar(
                select(Dataset)
                .where(Dataset.id == dataset_id)
                .options(
                    selectinload(Dataset.tables).selectinload(DatasetTable.columns),
                    selectinload(Dataset.relationships),
                )
            )
            assert dataset is not None
            catalog = DatasetCatalog.from_dataset(dataset)
        executor = RecordingExecutor(
            databases.executor,
            schema=catalog.schema_name,
            reader_role=catalog.reader_role,
            max_rows=1000,
            timeout_ms=5000,
        )
        deps = AgentDeps(
            llm=StructuredLLM(provider),
            schema=SchemaTools(catalog),
            executor=executor,
            max_rows=1000,
        )
        state = initial_state(
            run_id="pg",
            question="How did revenue by category change last month?",
            today="2026-11-14",
            budget=budget(),
        )
        return await run_graph(build_graph(), state, deps), executor
    finally:
        await databases.close()


async def _truth(pg: PgUrls, schema: str) -> dict[str, tuple[float, float]]:
    """Independent computation of the expected numbers (ingest role, plain SQL)."""
    conn = await asyncpg.connect(PgUrls.dsn(pg.ingest))
    try:
        await conn.execute(f'SET search_path = "{schema}"')
        # the executor runs in UTC (D59); the expectation must not depend on the server's zone
        await conn.execute("SET TIME ZONE 'UTC'")
        rows = await conn.fetch(GOOD_SQL)
        return {
            r["category"]: (float(r["revenue_before"] or 0), float(r["revenue_after"] or 0))
            for r in rows
        }
    finally:
        await conn.close()


def test_agent_recovers_from_a_real_database_error_and_numbers_match(
    pg: PgUrls, pg_settings: Callable[..., Settings]
) -> None:
    settings = pg_settings()
    client, dataset_id = provision(settings)
    try:
        provider = script()
        final, executor = run(_run_agent(settings, dataset_id, provider))
    finally:
        client.__exit__(None, None, None)
    assert provider.unexpected == [], provider.unexpected
    s1 = final["step_results"]["s1"]
    first, second = s1.attempts
    assert (first.guard_status, first.exec_status, first.error_code) == (
        "accepted",
        "error",
        "42883",
    )
    assert "function sum(text) does not exist" in (first.exec_error or "")
    assert first.diagnosis and first.diagnosis.category == "undefined_function"
    assert "function sum(text) does not exist" in provider.calls_for("recover_error")[0].text
    assert second.exec_status == "ok" and s1.status == "succeeded"

    schema = run(_schema_of(settings, dataset_id))
    truth = run(_truth(pg, schema))
    fact = next(f for f in final["facts"] if f.kind == "group_change")
    computed = {g["label"]: (g["before"], g["after"]) for g in items(fact)}
    assert computed.keys() == truth.keys() and len(truth) >= 3
    for category, (before, after) in truth.items():
        assert computed[category] == pytest.approx((before, after), abs=0.01)

    response = final["response"]
    assert response.status == "answered" and response.key_findings[0].verification == "verified"
    assert final["verification"].time_period_check == "passed"
    assert len(executor.sql) == 2


async def _schema_of(settings: Settings, dataset_id: uuid.UUID) -> str:
    databases = await open_databases(settings)
    try:
        assert databases.sessions is not None
        async with databases.sessions() as db:
            dataset = await db.get(Dataset, dataset_id)
            assert dataset is not None
            return dataset.schema_name
    finally:
        await databases.close()


def test_destructive_sql_never_reaches_the_database(
    pg: PgUrls, pg_settings: Callable[..., Settings]
) -> None:
    settings = pg_settings()
    client, dataset_id = provision(settings)
    try:
        provider = script(first_sql="DROP TABLE orders; SELECT 1")
        final, executor = run(_run_agent(settings, dataset_id, provider))
    finally:
        client.__exit__(None, None, None)
    first = final["step_results"]["s1"].attempts[0]
    assert (
        first.guard_status == "rejected" and first.guard_violations[0].code == "MULTIPLE_STATEMENTS"
    )
    assert all("drop" not in sql.lower() for sql in executor.sql)
    schema = run(_schema_of(settings, dataset_id))
    count = run(_count_orders(pg, schema))
    assert count > 0  # the table is still there


async def _count_orders(pg: PgUrls, schema: str) -> int:
    conn = await asyncpg.connect(PgUrls.dsn(pg.ingest))
    try:
        return int(await conn.fetchval(f'SELECT COUNT(*) FROM "{schema}".orders'))
    finally:
        await conn.close()


# ------------------------------------------------------------------ the API


def _wait(client: TestClient, session_id: str, timeout_s: float = 30) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        body: dict[str, Any] = client.get(f"/api/v1/analysis-sessions/{session_id}").json()
        if body["status"] not in ("queued", "running"):
            return body
        time.sleep(0.1)
    raise AssertionError("agent run did not finish")


def _api_client(settings: Settings, provider: ScriptedProvider) -> TestClient:
    return TestClient(create_app(settings, agent_llm=StructuredLLM(provider)))


def test_api_runs_the_agent_and_exposes_result_trace_and_history(
    pg_settings: Callable[..., Settings],
) -> None:
    provider = script()
    with _api_client(pg_settings(), provider) as client:
        sign_up(client)
        dataset = client.post("/api/v1/datasets/demo").json()["dataset"]
        convo = client.post("/api/v1/conversations", json={"dataset_id": dataset["id"]}).json()
        accepted = client.post(
            f"/api/v1/conversations/{convo['id']}/sessions",
            json={"question": "How did revenue by category change last month?"},
        )
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["agent_available"] is True
        session_id = accepted.json()["session"]["id"]

        detail = _wait(client, session_id)
        assert detail["status"] == "succeeded", detail
        assert detail["llm_provider"] == "scripted" and detail["llm_calls"] == len(provider.calls)
        assert detail["sql_executions"] == 2 and detail["duration_ms"] > 0
        result = detail["result"]
        assert result["response"]["status"] == "answered"
        assert result["charts"][0]["chart_type"] == "grouped_bar" and result["charts"][0]["data"]
        assert result["steps"][0]["sql"].startswith("WITH bounds")
        assert (
            detail["understanding"]["intent"] == "comparison"
            and detail["plan"]["steps"][0]["step_id"] == "s1"
        )

        trace = client.get(f"/api/v1/analysis-sessions/{session_id}/trace").json()
        names = [t["node"] for t in trace]
        assert names[0] == "load_context" and names[-1] == "compose_response"
        assert "recover_error" in names and [t["seq"] for t in trace] == list(
            range(1, len(trace) + 1)
        )
        assert all(
            t["duration_ms"] >= 0 and t["status"] in ("succeeded", "degraded") for t in trace
        )
        execute = next(t for t in trace if t["node"] == "execute_sql")
        assert execute["tool_calls"][0]["tool"] == "execute_sql"

        conversation = client.get(f"/api/v1/conversations/{convo['id']}").json()
        assert [m["role"] for m in conversation["messages"]] == ["user", "assistant"]
        assert conversation["messages"][1]["content"] == result["response"]["summary"]

        history = client.get("/api/v1/history/queries").json()["items"]
        agent_rows = [q for q in history if q.get("origin") == "agent"]
        assert len(agent_rows) == 2
        assert {q["exec_status"] for q in agent_rows} == {"ok", "error"}

        # another account can't see this trace
        with TestClient(client.app) as other:
            sign_up(other)
            assert other.get(f"/api/v1/analysis-sessions/{session_id}/trace").status_code == 404


def test_api_clarification_then_answer_resumes_the_original_question(
    pg_settings: Callable[..., Settings],
) -> None:
    ask = {
        **UNDERSTANDING,
        "status": "needs_clarification",
        "clarification_question": "Revenue or order count?",
        "clarification_options": ["Revenue", "Orders"],
    }
    provider = script()
    provider.script["understand_query"] = [ask, UNDERSTANDING]
    with _api_client(pg_settings(), provider) as client:
        sign_up(client)
        dataset = client.post("/api/v1/datasets/demo").json()["dataset"]
        convo = client.post("/api/v1/conversations", json={"dataset_id": dataset["id"]}).json()
        first = client.post(
            f"/api/v1/conversations/{convo['id']}/sessions",
            json={"question": "Which categories did best?"},
        ).json()
        asked = _wait(client, first["session"]["id"])
        assert asked["status"] == "awaiting_input"
        assert asked["result"]["response"]["clarification_options"] == ["Revenue", "Orders"]

        second = client.post(
            f"/api/v1/conversations/{convo['id']}/sessions", json={"question": "Revenue"}
        ).json()
        answered = _wait(client, second["session"]["id"])
        assert answered["status"] == "succeeded"
        resumed = provider.calls_for("understand_query")[1].text
        assert (
            "Which categories did best?" in resumed
            and '<data name="clarification_answer">\nRevenue' in resumed
        )
        earlier = client.get(f"/api/v1/analysis-sessions/{first['session']['id']}").json()
        assert (
            earlier["status"] == "succeeded"
            and earlier["termination_reason"] == "clarification_answered"
        )


def test_without_a_model_sessions_stay_queued(pg_settings: Callable[..., Settings]) -> None:
    with TestClient(create_app(pg_settings())) as client:  # LLM_PROVIDER=mock
        sign_up(client)
        dataset = client.post("/api/v1/datasets/demo").json()["dataset"]
        convo = client.post("/api/v1/conversations", json={"dataset_id": dataset["id"]}).json()
        accepted = client.post(
            f"/api/v1/conversations/{convo['id']}/sessions", json={"question": "Revenue?"}
        ).json()
        assert accepted["agent_available"] is False and "no language model" in accepted["message"]
        time.sleep(0.3)
        detail = client.get(f"/api/v1/analysis-sessions/{accepted['session']['id']}").json()
        assert detail["status"] == "queued" and detail["result"] is None
        assert (
            client.get(f"/api/v1/analysis-sessions/{accepted['session']['id']}/trace").json() == []
        )


def test_runs_interrupted_by_a_restart_are_marked_failed(
    pg: PgUrls, pg_settings: Callable[..., Settings]
) -> None:
    settings = pg_settings()
    with TestClient(create_app(settings)) as client:
        sign_up(client)
        dataset = client.post("/api/v1/datasets/demo").json()["dataset"]
        convo = client.post("/api/v1/conversations", json={"dataset_id": dataset["id"]}).json()
        session_id = client.post(
            f"/api/v1/conversations/{convo['id']}/sessions", json={"question": "q"}
        ).json()["session"]["id"]
        run(_set_status(pg, session_id, "running"))  # simulate a crash mid-run
    with TestClient(create_app(settings)) as client:  # restart
        pass
    rows = run(_status(pg, session_id))
    assert rows == ("failed", "INTERRUPTED")


async def _set_status(pg: PgUrls, session_id: str, status: str) -> None:
    conn = await asyncpg.connect(PgUrls.dsn(pg.app))
    try:
        await conn.execute(
            "UPDATE app.analysis_sessions SET status = $1 WHERE id = $2",
            status,
            uuid.UUID(session_id),
        )
    finally:
        await conn.close()


async def _status(pg: PgUrls, session_id: str) -> tuple[str, str | None]:
    conn = await asyncpg.connect(PgUrls.dsn(pg.app))
    try:
        row = await conn.fetchrow(
            "SELECT status, error_code FROM app.analysis_sessions WHERE id = $1",
            uuid.UUID(session_id),
        )
        assert row is not None
        return row["status"], row["error_code"]
    finally:
        await conn.close()


def test_daily_model_limit_stops_new_analyses(pg_settings: Callable[..., Settings]) -> None:
    provider = script()
    with _api_client(pg_settings(), provider) as client:
        sign_up(client)
        dataset = client.post("/api/v1/datasets/demo").json()["dataset"]
        convo = client.post("/api/v1/conversations", json={"dataset_id": dataset["id"]}).json()
        first = client.post(
            f"/api/v1/conversations/{convo['id']}/sessions",
            json={"question": "Revenue by category?"},
        )
        used = _wait(client, first.json()["session"]["id"])["llm_calls"]
        assert used > 0

    limited = pg_settings(llm_daily_request_limit=used)  # today's usage already reaches it
    with _api_client(limited, script()) as client:
        sign_up(client)
        dataset = client.post("/api/v1/datasets/demo").json()["dataset"]
        convo = client.post("/api/v1/conversations", json={"dataset_id": dataset["id"]}).json()
        refused = client.post(
            f"/api/v1/conversations/{convo['id']}/sessions", json={"question": "Again?"}
        )
        assert refused.status_code == 429, refused.text
        assert refused.json()["error"]["code"] == "DAILY_BUDGET_EXCEEDED"
        assert int(refused.headers["Retry-After"]) > 0
        assert client.get(f"/api/v1/conversations/{convo['id']}").json()["sessions"] == []
