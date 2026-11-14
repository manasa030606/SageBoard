"""Scripted model replies for the "Why did revenue decrease last month?" scenario."""

from __future__ import annotations

from typing import Any

from tests.agent.fakes import FakeExecutor, Harness, ScriptedProvider, db_error, ok

QUESTION = "Why did revenue decrease last month?"

UNDERSTANDING: dict[str, Any] = {
    "status": "answerable",
    "restated_question": "Why did revenue in September 2025 fall compared with August 2025?",
    "intent": "explanation",
    "metrics": ["revenue"],
    "dimensions": ["category", "region"],
    "filters": ["exclude cancelled orders"],
    "time_range": "2025-09-01 to 2025-09-30 vs 2025-08-01 to 2025-08-31",
    "assumptions": [
        "Last month = September 2025, the latest full month in the data.",
        "Revenue = quantity × unit_price × (1 − discount), excluding cancelled orders.",
    ],
}

SCHEMA_ACTIONS: list[dict[str, Any]] = [
    {"action": "get_table_schema", "tables": ["orders", "order_items", "products", "customers"]},
    {"action": "get_join_paths", "tables": ["orders", "order_items", "products", "customers"]},
    {
        "action": "finish",
        "selected_tables": ["orders", "order_items", "products", "customers"],
        "rationale": "Revenue comes from order_items joined to orders; category from products; region from customers.",
    },
]

PLAN: dict[str, Any] = {
    "steps": [
        {
            "step_id": "s1",
            "purpose": "Total revenue in August and September 2025",
            "expected_output": "one row with revenue_before (Aug) and revenue_after (Sep)",
        },
        {
            "step_id": "s2",
            "purpose": "Revenue by product category for both months",
            "expected_output": "one row per category with revenue_before and revenue_after",
        },
        {
            "step_id": "s3",
            "purpose": "Revenue by customer region for both months",
            "expected_output": "one row per region with revenue_before and revenue_after",
        },
    ],
    "analysis_tasks": [
        "percentage change of total revenue (s1)",
        "change by category and contribution to the total change (s2)",
        "change by region and contribution to the total change (s3)",
    ],
    "final_answer_shape": "The size of the decline and the categories and regions that drove it.",
}

LINE = "SUM(oi.quantity * oi.unit_price * (1 - oi.discount))"
PERIODS = (
    f"ROUND({LINE} FILTER (WHERE o.order_date >= DATE '2025-08-01' AND o.order_date < DATE '2025-09-01')::numeric, 2) AS revenue_before, "
    f"ROUND({LINE} FILTER (WHERE o.order_date >= DATE '2025-09-01' AND o.order_date < DATE '2025-10-01')::numeric, 2) AS revenue_after"
)
JOIN = "FROM order_items AS oi JOIN orders AS o ON o.order_id = oi.order_id"
WHERE = "WHERE o.status <> 'cancelled' AND o.order_date >= DATE '2025-08-01' AND o.order_date < DATE '2025-10-01'"

SQL_S1 = f"SELECT {PERIODS} {JOIN} {WHERE}"
SQL_S2_BAD = f"SELECT o.category, {PERIODS} {JOIN} {WHERE} GROUP BY o.category"
SQL_S2 = f"SELECT p.category, {PERIODS} {JOIN} JOIN products AS p ON p.product_id = oi.product_id {WHERE} GROUP BY p.category ORDER BY p.category"
SQL_S3 = f"SELECT c.region, {PERIODS} {JOIN} JOIN customers AS c ON c.customer_id = o.customer_id {WHERE} GROUP BY c.region ORDER BY c.region"

NUM = "numeric"
S1_ROWS = [[100000.0, 85000.0]]
S2_ROWS = [
    ["Electronics", 50000.0, 38000.0],
    ["Home", 30000.0, 29000.0],
    ["Toys", 20000.0, 18000.0],
]
S3_ROWS = [[f"Region {i}", 100000.0 / 7, 85000.0 / 7] for i in range(1, 8)]

ANALYSIS: dict[str, Any] = {
    "calls": [
        {
            "tool": "pct_change",
            "description": "Change in total revenue, Aug → Sep 2025",
            "before": {"fact_id": "f1"},
            "after": {"fact_id": "f2"},
            "unit": "%",
        },
        {
            "tool": "group_change",
            "step_id": "s2",
            "description": "Revenue change by category",
            "label_column": "category",
            "before_column": "revenue_before",
            "after_column": "revenue_after",
            "unit": "USD",
        },
        {
            "tool": "group_change",
            "step_id": "s3",
            "description": "Revenue change by region",
            "label_column": "region",
            "before_column": "revenue_before",
            "after_column": "revenue_after",
            "unit": "USD",
        },
    ]
}

CHARTS: dict[str, Any] = {
    "charts": [
        {
            "chart_type": "grouped_bar",
            "step_id": "s2",
            "x": "category",
            "y": ["revenue_before", "revenue_after"],
            "title": "Revenue by category, Aug vs Sep 2025",
            "value_format": "currency",
        },
        {
            "chart_type": "pie",
            "step_id": "s3",
            "x": "region",
            "y": ["revenue_after"],
            "title": "September revenue by region",
        },
    ]
}

I1: dict[str, Any] = {
    "headline": "Revenue fell 15% from $100,000 in August to $85,000 in September",
    "detail": "Total revenue dropped by $15,000 month over month.",
    "category": "finding",
    "evidence": [{"kind": "fact", "fact_id": "f3"}],
    "confidence": "high",
}
I2_BAD: dict[str, Any] = {
    "headline": "Electronics accounted for 23.4% of the decline",
    "detail": "Electronics revenue fell the most.",
    "category": "finding",
    "evidence": [{"kind": "fact", "fact_id": "f4"}],
    "confidence": "high",
}
I2_GOOD: dict[str, Any] = {
    "headline": "Electronics accounted for 80% of the decline",
    "detail": "Electronics revenue fell by $12,000, from $50,000 to $38,000.",
    "category": "finding",
    "evidence": [{"kind": "fact", "fact_id": "f4"}],
    "confidence": "high",
}
I3: dict[str, Any] = {
    "headline": "The decline was spread evenly across regions",
    "detail": "Every region fell by the same proportion, so region does not explain the drop.",
    "category": "comparison",
    "evidence": [{"kind": "fact", "fact_id": "f5"}],
    "confidence": "medium",
}


def judge_all_supported(messages: list[Any]) -> dict[str, Any]:
    text = messages[-1]["content"]
    ids = [f"i{n}" for n in range(1, 6) if f'"insight_id": "i{n}"' in text]
    return {
        "metrics_match": True,
        "time_period_match": True,
        "insights": [{"insight_id": i, "supported": True} for i in ids],
        "uncertainty_notes": ["Only two months were compared."],
    }


def revenue_provider() -> ScriptedProvider:
    return ScriptedProvider(
        {
            "understand_query": [UNDERSTANDING],
            "retrieve_schema": list(SCHEMA_ACTIONS),
            "plan_analysis": [PLAN],
            "generate_sql": [
                {"sql": SQL_S1, "explanation": "Totals for both months."},
                {"sql": SQL_S2_BAD, "explanation": "By category."},
                {"sql": SQL_S3, "explanation": "By region."},
            ],
            "recover_error": [
                {
                    "diagnosis": "category lives in products, not orders.",
                    "sql": SQL_S2,
                    "change_summary": "Joined products and grouped by p.category.",
                }
            ],
            "analyze_results": [ANALYSIS],
            "generate_visualization": [CHARTS],
            "generate_insights": [{"insights": [I1, I2_BAD, I3]}, {"insights": [I1, I2_GOOD, I3]}],
            "verify_insights": [judge_all_supported, judge_all_supported],
            "compose_response": [
                {
                    "summary": "Revenue fell 15% in September, to $85,000. Electronics accounted for 80% of the decline."
                }
            ],
        }
    )


def revenue_executor() -> FakeExecutor:
    cols = [("revenue_before", NUM), ("revenue_after", NUM)]
    return FakeExecutor(
        [
            ("p.category", ok([("category", "text"), *cols], S2_ROWS)),
            ("c.region", ok([("region", "text"), *cols], S3_ROWS)),
            ("revenue_before", ok(cols, S1_ROWS)),
        ],
        default=db_error("42601", "unexpected SQL in test"),
    )


def revenue_harness() -> Harness:
    return Harness(revenue_provider(), revenue_executor())
