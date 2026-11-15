"""Phase 7: the complete question-to-insight pipeline on more than one dataset.

The demo dataset is exercised end-to-end in test_agent_pg.py. Here an *uploaded CSV*
with a different schema goes through the same API: upload → finalize → conversation →
two questions → charts, verified insights and grounded follow-up suggestions. Only the
model is scripted; catalog, Guard, executor and analysis tools are the real ones.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.llm.client import LLMMessage, StructuredLLM
from app.core.config import Settings
from app.main import create_app
from tests.agent.fakes import ScriptedProvider, data_from
from tests.integration.conftest import sign_up

pytestmark = pytest.mark.integration

API = "/api/v1"

SALES_CSV = (
    "Order ID,Order Date,Amount,Region\n"
    "1,2026-01-03,100.00,West\n"
    "2,2026-01-04,200.50,West\n"
    "3,2026-01-05,50.25,East\n"
    "4,2026-01-06,149.75,East\n"
    "5,2026-01-07,400.00,North\n"
    "6,2026-02-01,99.50,West\n"
    "7,2026-02-02,60.00,East\n"
    "8,2026-02-03,40.00,North\n"
)
# Independent truth, computed by hand from the CSV above.
TOTALS = {"North": 440.00, "West": 400.00, "East": 260.00}
ORDER_COUNTS = {"West": 3, "East": 3, "North": 2}


def understanding(restated: str, metric: str) -> dict[str, Any]:
    return {
        "status": "answerable",
        "restated_question": restated,
        "intent": "ranking",
        "metrics": [metric],
        "dimensions": ["region"],
        "filters": [],
        "time_range": "all data",
        "assumptions": [],
    }


def plan(purpose: str, expected: str) -> dict[str, Any]:
    return {
        "steps": [
            {"step_id": "s1", "purpose": purpose, "expected_output": expected, "depends_on": []}
        ],
        "analysis_tasks": [purpose.lower()],
        "final_answer_shape": "A ranking of the regions.",
    }


def insight_from_top_n(messages: list[LLMMessage]) -> dict[str, Any]:
    fact = next(f for f in data_from(messages, "facts") if f["kind"] == "top_n")
    top = fact["value"][0]
    return {
        "insights": [
            {
                "headline": f"{top['label']} leads with {top['value']:,.2f} in sales",
                "detail": "Computed from the grouped totals in step s1.",
                "category": "finding",
                "evidence": [{"kind": "fact", "fact_id": fact["fact_id"]}],
                "confidence": "high",
            }
        ]
    }


def insight_from_total(messages: list[LLMMessage]) -> dict[str, Any]:
    fact = next(f for f in data_from(messages, "facts") if f["kind"] == "total")
    return {
        "insights": [
            {
                "headline": f"{fact['value']:,.0f} orders in total across the regions",
                "detail": "Sum of the per-region order counts from step s1.",
                "category": "finding",
                "evidence": [{"kind": "fact", "fact_id": fact["fact_id"]}],
                "confidence": "high",
            }
        ]
    }


def judge(messages: list[LLMMessage]) -> dict[str, Any]:
    insights = data_from(messages, "insights")
    return {
        "metrics_match": True,
        "time_period_match": True,
        "insights": [{"insight_id": i["insight_id"], "supported": True} for i in insights],
    }


def summary_with_follow_ups(messages: list[LLMMessage]) -> dict[str, Any]:
    verified = data_from(messages, "verified_insights")
    return {
        "summary": verified[0]["headline"] + ".",
        "follow_up_questions": [
            "Which region had the most orders?",
            "Did North reach 47% of total sales?",  # 47 is in no fact or row → must be dropped
        ],
    }


def summary_plain(messages: list[LLMMessage]) -> dict[str, Any]:
    verified = data_from(messages, "verified_insights")
    return {"summary": verified[0]["headline"] + "."}


def fill_script(provider: ScriptedProvider, table: str) -> None:
    """Both questions' scripted responses, in the order the two runs consume them."""
    revenue_sql = (
        f"SELECT region, SUM(amount) AS total_amount FROM {table} "
        "GROUP BY region ORDER BY total_amount DESC"
    )
    count_sql = (
        f"SELECT region, COUNT(*) AS order_count FROM {table} "
        "GROUP BY region ORDER BY order_count DESC"
    )
    provider.script.update(
        {
            "understand_query": [
                understanding("Which region has the highest total sales?", "total sales"),
                understanding("How many orders did each region place?", "order count"),
            ],
            "retrieve_schema": [
                {"action": "finish", "selected_tables": [table], "rationale": "r"},
                {"action": "finish", "selected_tables": [table], "rationale": "r"},
            ],
            "plan_analysis": [
                plan("Total sales by region", "one row per region"),
                plan("Order count by region", "one row per region"),
            ],
            "generate_sql": [
                {"sql": revenue_sql, "explanation": "sum amount per region"},
                {"sql": count_sql, "explanation": "count orders per region"},
            ],
            "analyze_results": [
                {
                    "calls": [
                        {
                            "tool": "top_n",
                            "step_id": "s1",
                            "label_column": "region",
                            "value_column": "total_amount",
                            "n": 3,
                            "description": "Regions ranked by total sales",
                            "unit": "USD",
                        }
                    ]
                },
                {
                    "calls": [
                        {
                            "tool": "total",
                            "step_id": "s1",
                            "column": "order_count",
                            "description": "Total number of orders",
                        }
                    ]
                },
            ],
            "generate_visualization": [
                {
                    "charts": [
                        {
                            "chart_type": "pie",
                            "step_id": "s1",
                            "x": "region",
                            "y": ["total_amount"],
                            "title": "Share of sales by region",
                        }
                    ]
                },
                {
                    "charts": [
                        {
                            "chart_type": "horizontal_bar",
                            "step_id": "s1",
                            "x": "region",
                            "y": ["order_count"],
                            "title": "Orders by region",
                        }
                    ]
                },
            ],
            "generate_insights": [insight_from_top_n, insight_from_total],
            "verify_insights": [judge, judge],
            "compose_response": [summary_with_follow_ups, summary_plain],
        }
    )


def _wait(client: TestClient, session_id: str, timeout_s: float = 30) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        body: dict[str, Any] = client.get(f"{API}/analysis-sessions/{session_id}").json()
        if body["status"] not in ("queued", "running"):
            return body
        time.sleep(0.1)
    raise AssertionError("agent run did not finish")


def _ask(client: TestClient, conversation_id: str, question: str) -> dict[str, Any]:
    accepted = client.post(
        f"{API}/conversations/{conversation_id}/sessions", json={"question": question}
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["agent_available"] is True
    return _wait(client, accepted.json()["session"]["id"])


def test_pipeline_answers_two_questions_on_an_uploaded_csv_dataset(
    pg_settings: Callable[..., Settings],
) -> None:
    provider = ScriptedProvider({})
    with TestClient(create_app(pg_settings(), agent_llm=StructuredLLM(provider))) as client:
        sign_up(client)

        # A dataset with a schema unlike the demo's: one flat sales table from a CSV.
        name = f"Regional sales {uuid.uuid4().hex[:6]}"
        uploaded = client.post(
            f"{API}/datasets/uploads",
            files={"file": ("sales.csv", SALES_CSV, "text/csv")},
            data={"name": name},
        )
        assert uploaded.status_code == 201, uploaded.text
        dataset_id = uploaded.json()["dataset"]["id"]
        ready = client.post(f"{API}/datasets/{dataset_id}/finalize", json={"column_types": {}})
        assert ready.status_code == 200, ready.text
        table = ready.json()["tables"][0]["table_name"]
        fill_script(provider, table)

        convo = client.post(f"{API}/conversations", json={"dataset_id": dataset_id}).json()

        # ---- question 1: totals by region → pie chart, top_n fact, grounded follow-ups
        detail = _ask(client, convo["id"], "Which region brought in the most revenue?")
        assert detail["status"] == "succeeded", detail
        result = detail["result"]
        assert result["response"]["status"] == "answered"

        step = result["steps"][0]
        totals = {row[0]: float(row[1]) for row in step["rows"]}
        assert totals == pytest.approx(TOTALS)  # the executor really ran the SQL

        chart = result["charts"][0]
        assert chart["chart_type"] == "pie" and chart["fallback_reason"] is None
        assert chart["columns"] == ["region", "total_amount"]
        assert len(chart["data"]) == 3 and chart["data"][0][0] == "North"

        insight = result["response"]["key_findings"][0]
        assert "North leads with 440.00" in insight["headline"]
        assert insight["evidence"][0]["kind"] == "fact"
        fact = next(f for f in result["facts"] if f["kind"] == "top_n")
        assert fact["value"][0] == {"rank": 1, "label": "North", "value": 440.0}

        # The ungrounded "47%" suggestion is dropped; the clean one survives.
        assert result["response"]["follow_up_questions"] == ["Which region had the most orders?"]

        # ---- question 2, same conversation: counts by region → horizontal bar, total fact
        detail2 = _ask(client, convo["id"], "Which region had the most orders?")
        assert detail2["status"] == "succeeded", detail2
        result2 = detail2["result"]

        counts = {row[0]: int(row[1]) for row in result2["steps"][0]["rows"]}
        assert counts == ORDER_COUNTS

        chart2 = result2["charts"][0]
        assert chart2["chart_type"] == "horizontal_bar" and chart2["fallback_reason"] is None
        assert "8 orders in total" in result2["response"]["key_findings"][0]["headline"]
        assert result2["response"]["follow_up_questions"] == []

        # The conversation thread now holds both exchanges, in order.
        thread = client.get(f"{API}/conversations/{convo['id']}").json()
        assert [m["role"] for m in thread["messages"]] == ["user", "assistant"] * 2
        assert [s["status"] for s in thread["sessions"]] == ["succeeded", "succeeded"]
