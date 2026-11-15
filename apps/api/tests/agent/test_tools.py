"""Deterministic tools: schema, error classification, analysis engine, charts, grounding."""

from __future__ import annotations

import pytest

from app.agent.state import (
    ChartSpec,
    ComputedFact,
    EvidenceRef,
    GuardViolation,
    Insight,
    SQLAttempt,
    StepResult,
)
from app.agent.tools.analysis import AnalysisCall, AnalysisEngine, AnalysisToolError, ResultTable
from app.agent.tools.charts import validate_chart
from app.agent.tools.errors import classify_attempt
from app.agent.tools.grounding import Grounder, extract_numbers
from app.agent.tools.schema import SchemaToolError, SchemaTools
from tests.agent.fakes import items, shop_catalog

TOOLS = SchemaTools(shop_catalog())

# ---------------------------------------------------------------- schema tools


def test_table_catalog_is_light_and_has_time_coverage() -> None:
    orders = next(t for t in TOOLS.table_catalog() if t["table"] == "orders")
    assert orders["row_count"] == 2500
    assert orders["time_coverage"] == [
        {
            "column": "order_date",
            "min": "2024-01-01T00:00:00+00:00",
            "max": "2025-09-30T23:00:00+00:00",
        }
    ]


def test_table_schema_and_unknown_table() -> None:
    schema = TOOLS.get_table_schema("order_items")
    assert [c["column"] for c in schema["columns"]][:2] == ["order_item_id", "order_id"]
    assert "order_items.order_id = orders.order_id" in schema["foreign_keys"]
    with pytest.raises(SchemaToolError, match="Unknown table"):
        TOOLS.get_table_schema("payments")


def test_join_paths_direct_and_via_bridge() -> None:
    assert TOOLS.get_join_paths(["orders", "customers"]) == [
        "orders.customer_id = customers.customer_id"
    ]
    bridged = TOOLS.get_join_paths(["products", "orders"])
    assert set(bridged) == {
        "order_items.order_id = orders.order_id",
        "order_items.product_id = products.product_id",
    }


def test_column_values_hide_sensitive_columns() -> None:
    assert TOOLS.get_column_values("orders", "status")["values"][0] == "delivered"
    assert TOOLS.get_column_values("customers", "email")["values"] == []
    with pytest.raises(SchemaToolError):
        TOOLS.get_column_values("orders", "nope")


# --------------------------------------------------------- error classification


def _attempt(**kw: object) -> SQLAttempt:
    return SQLAttempt(attempt=1, sql="select 1", explanation="", **kw)


@pytest.mark.parametrize(
    ("kwargs", "category", "recoverable"),
    [
        (
            {
                "guard_status": "rejected",
                "guard_violations": [GuardViolation(code="UNKNOWN_COLUMN", message="m")],
            },
            "unknown_column",
            True,
        ),
        (
            {
                "guard_status": "rejected",
                "guard_violations": [GuardViolation(code="FORBIDDEN_FUNCTION", message="m")],
            },
            "unsafe_query",
            False,
        ),
        (
            {
                "guard_status": "rejected",
                "guard_violations": [GuardViolation(code="MULTIPLE_STATEMENTS", message="m")],
            },
            "unsafe_query",
            False,
        ),
        (
            {
                "guard_status": "rejected",
                "guard_violations": [GuardViolation(code="EMPTY_SQL", message="m")],
            },
            "guard_rejected",
            True,
        ),
        (
            {"guard_status": "accepted", "exec_status": "error", "error_code": "25006"},
            "unsafe_query",
            False,
        ),
        (
            {"guard_status": "accepted", "exec_status": "error", "error_code": "COST_LIMIT"},
            "too_expensive",
            True,
        ),
        (
            {"guard_status": "accepted", "exec_status": "error", "error_code": "42803"},
            "grouping_error",
            True,
        ),
        (
            {"guard_status": "accepted", "exec_status": "error", "error_code": "22012"},
            "division_by_zero",
            True,
        ),
        (
            {"guard_status": "accepted", "exec_status": "timeout", "error_code": "57014"},
            "timeout",
            True,
        ),
        (
            {"guard_status": "accepted", "exec_status": "error", "error_code": "42501"},
            "permission_denied",
            False,
        ),
        (
            {"guard_status": "accepted", "exec_status": "error", "error_code": "XX000"},
            "other",
            True,
        ),
    ],
)
def test_classify_attempt(kwargs: dict[str, object], category: str, recoverable: bool) -> None:
    diagnosis = classify_attempt(_attempt(**kwargs))
    assert diagnosis.category == category and diagnosis.recoverable is recoverable
    assert diagnosis.hint


def test_repeated_query_classification() -> None:
    assert classify_attempt(_attempt(), repeated=True).category == "repeated_query"


# ------------------------------------------------------------- analysis engine

ENGINE_TABLES = {
    "s1": ResultTable("s1", ["revenue_before", "revenue_after"], [[200.0, 150.0]]),
    "s2": ResultTable(
        "s2",
        ["category", "revenue_before", "revenue_after"],
        [["A", 100.0, 60.0], ["B", 60.0, 55.0], ["C", 40.0, 35.0]],
    ),
    "s3": ResultTable(
        "s3",
        ["month", "region", "revenue"],
        [
            ["2025-08-01", "N", 10.0],
            ["2025-09-01", "N", 4.0],
            ["2025-08-01", "S", 5.0],
            ["2025-09-01", "S", 6.0],
        ],
    ),
    "s4": ResultTable("s4", ["x", "y"], [[1, 2], [2, 4], [3, 6.5], [4, 8], [5, 100]]),
}


def call(**kw: object) -> AnalysisCall:
    return AnalysisCall(description="t", **kw)


def test_lookup_and_pct_change_from_facts_and_cells() -> None:
    e = AnalysisEngine(ENGINE_TABLES)
    f1 = e.run(call(tool="lookup", step_id="s1", column="revenue_before"))
    e.run(call(tool="lookup", step_id="s1", column="revenue_after"))
    f3 = e.run(call(tool="pct_change", before={"fact_id": "f1"}, after={"fact_id": "f2"}))
    assert (f1.fact_id, f1.value) == ("f1", 200.0)
    assert f3.value == -25.0 and f3.inputs["supporting"] == {
        "before": 200.0,
        "after": 150.0,
        "change": -50.0,
    }
    by_cell = e.run(
        call(
            tool="pct_change",
            before={"step_id": "s2", "column": "revenue_before", "where": {"category": "A"}},
            after={"step_id": "s2", "column": "revenue_after", "where": {"category": "A"}},
        )
    )
    assert by_cell.value == -40.0


def test_group_change_wide_and_long() -> None:
    e = AnalysisEngine(ENGINE_TABLES)
    wide = e.run(
        call(
            tool="group_change",
            step_id="s2",
            label_column="category",
            before_column="revenue_before",
            after_column="revenue_after",
        )
    )
    assert items(wide)[0] == {
        "label": "A",
        "before": 100.0,
        "after": 60.0,
        "change": -40.0,
        "pct_change": -40.0,
        "contribution_pct": 80.0,
    }
    assert wide.inputs["supporting"]["total_change"] == -50.0
    long = e.run(
        call(
            tool="group_change",
            step_id="s3",
            label_column="region",
            period_column="month",
            value_column="revenue",
            before_period="2025-08",
            after_period="2025-09",
        )
    )
    assert [g["label"] for g in items(long)] == ["N", "S"]
    assert long.inputs["supporting"]["total_change"] == -5.0


def test_share_top_trend_correlation_outliers() -> None:
    e = AnalysisEngine(ENGINE_TABLES)
    share = e.run(
        call(tool="share", step_id="s2", label_column="category", value_column="revenue_before")
    )
    assert share.value[0] == {"label": "A", "value": 100.0, "share_pct": 50.0}  # type: ignore[index]
    top = e.run(
        call(tool="top_n", step_id="s2", label_column="category", value_column="revenue_after", n=2)
    )
    assert [t["label"] for t in items(top)] == ["A", "B"]
    trend = e.run(call(tool="trend", step_id="s4", x_column="x", y_column="y"))
    assert trend.value[0]["max"] == 100.0 and trend.inputs["supporting"]["change"] == 98.0  # type: ignore[index]
    corr = e.run(call(tool="correlation", step_id="s4", x_column="x", y_column="y"))
    assert 0 < corr.value < 1  # type: ignore[operator]
    outliers = e.run(call(tool="outliers_iqr", step_id="s4", label_column="x", value_column="y"))
    assert outliers.value == [{"label": "5", "value": 100.0, "side": "high"}]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"tool": "total", "step_id": "s9", "column": "x"}, "unknown or failed step"),
        ({"tool": "total", "step_id": "s2", "column": "nope"}, "has no column"),
        ({"tool": "total", "step_id": "s2", "column": "category"}, "no numeric values"),
        ({"tool": "total", "step_id": "s2"}, "needs column"),
        ({"tool": "lookup", "step_id": "s2", "column": "revenue_after"}, "exactly one row"),
        (
            {"tool": "pct_change", "before": {"fact_id": "f9"}, "after": {"fact_id": "f9"}},
            "earlier numeric fact",
        ),
    ],
)
def test_analysis_errors_are_explicit(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(AnalysisToolError, match=message):
        AnalysisEngine(ENGINE_TABLES).run(call(**kwargs))


# ------------------------------------------------------------------- charts


def _step(columns: list[tuple[str, str]], rows: list[list[object]]) -> StepResult:
    return StepResult(
        step_id="s1", status="succeeded", columns=columns, row_count=len(rows), preview_rows=rows
    )


@pytest.mark.parametrize(
    ("spec", "step", "ok"),
    [
        (
            {"chart_type": "bar", "x": "cat", "y": ["rev"]},
            _step([("cat", "text"), ("rev", "numeric")], [["a", 1]]),
            True,
        ),
        (
            {"chart_type": "bar", "x": "cat", "y": ["cat"]},
            _step([("cat", "text"), ("rev", "numeric")], [["a", 1]]),
            False,
        ),
        (
            {"chart_type": "line", "x": "month", "y": ["rev"]},
            _step([("month", "text"), ("rev", "numeric")], [["2025-08", 1], ["2025-09", 2]]),
            True,
        ),
        (
            {"chart_type": "line", "x": "cat", "y": ["rev"]},
            _step([("cat", "text"), ("rev", "numeric")], [["a", 1]]),
            False,
        ),
        (
            {"chart_type": "pie", "x": "cat", "y": ["rev"]},
            _step([("cat", "text"), ("rev", "numeric")], [["a", -1]]),
            False,
        ),
        ({"chart_type": "kpi", "y": ["rev"]}, _step([("rev", "numeric")], [[5]]), True),
        ({"chart_type": "kpi", "y": ["rev"]}, _step([("rev", "numeric")], [[5], [6]]), False),
        (
            {"chart_type": "bar", "x": "missing", "y": ["rev"]},
            _step([("rev", "numeric")], [[5]]),
            False,
        ),
    ],
)
def test_chart_validation(spec: dict[str, object], step: StepResult, ok: bool) -> None:
    errors = validate_chart(ChartSpec(step_id="s1", title="t", **spec), step)
    assert (errors == []) is ok, errors


# --------------------------------------------------------------- grounding


def test_extract_numbers_handles_currency_suffixes_and_dates() -> None:
    tokens = {
        t.raw: t.value
        for t in extract_numbers("Revenue was $1.2M (−15.5%) on 2025-09-30, up 3x; 1,234 orders")
    }
    assert tokens == {"$1.2M": 1_200_000.0, "−15.5%": -15.5, "3x": 3.0, "1,234": 1234.0}


def _grounder() -> Grounder:
    facts = [
        ComputedFact(
            fact_id="f1",
            step_id="s1",
            kind="pct_change",
            description="d",
            value=-12.47,
            inputs={
                "supporting": {"before": 1_234_567.0, "after": 1_080_600.0, "change": -153_967.0}
            },
        ),
        ComputedFact(
            fact_id="f2",
            step_id="s2",
            kind="share",
            description="d",
            value=[{"label": "A", "value": 10.0, "share_pct": 0.25}],
        ),
    ]
    steps = {"s2": _step([("cat", "text"), ("rev", "numeric")], [["A", 42.0], ["B", 7.0]])}
    return Grounder(facts, steps, "Revenue in 2025 top 5")


def _insight(text: str, evidence: list[dict[str, object]], category: str = "finding") -> Insight:
    return Insight(
        insight_id="i1",
        headline=text,
        detail="",
        category=category,
        evidence=[EvidenceRef(**e) for e in evidence],
        confidence="high",
    )


@pytest.mark.parametrize(
    ("text", "evidence", "category", "expected"),
    [
        (
            "Revenue fell 12.5% to $1.08M from $1.23M",
            [{"kind": "fact", "fact_id": "f1"}],
            "finding",
            [],
        ),
        ("Revenue fell 12% in 2025", [{"kind": "fact", "fact_id": "f1"}], "finding", []),
        (
            "Revenue fell 23.4%",
            [{"kind": "fact", "fact_id": "f1"}],
            "finding",
            ["UNGROUNDED_NUMBER 23.4%"],
        ),
        ("A holds 25% of sales", [{"kind": "fact", "fact_id": "f2"}], "finding", []),
        (
            "Category A sold 42 units",
            [{"kind": "cell", "step_id": "s2", "row_index": 0, "column": "rev"}],
            "finding",
            [],
        ),
        (
            "Category A sold 7 units",
            [{"kind": "cell", "step_id": "s2", "row_index": 0, "column": "rev"}],
            "finding",
            ["UNGROUNDED_NUMBER 7"],
        ),
        ("Top 5 look stable", [{"kind": "fact", "fact_id": "f2"}], "finding", []),
        (
            "Revenue fell because of pricing",
            [{"kind": "fact", "fact_id": "f1"}],
            "finding",
            ["UNSUPPORTED_CAUSAL_CLAIM “because”"],
        ),
        (
            "Revenue may have fallen because of pricing",
            [{"kind": "fact", "fact_id": "f1"}],
            "caveat",
            [],
        ),
        (
            "Cut prices now",
            [{"kind": "fact", "fact_id": "f1"}],
            "recommendation",
            ["NON_CONDITIONAL_RECOMMENDATION"],
        ),
        ("Consider reviewing prices", [{"kind": "fact", "fact_id": "f1"}], "recommendation", []),
        ("Revenue moved", [{"kind": "fact", "fact_id": "f9"}], "finding", ["UNKNOWN_EVIDENCE f9"]),
        (
            "Revenue moved",
            [{"kind": "cell", "step_id": "s2", "row_index": 9}],
            "finding",
            ["UNKNOWN_EVIDENCE row s2[9]"],
        ),
    ],
)
def test_grounding(
    text: str, evidence: list[dict[str, object]], category: str, expected: list[str]
) -> None:
    assert _grounder().check_insight(_insight(text, evidence, category)) == expected


def test_numbers_must_come_from_cited_evidence_only() -> None:
    # 42 exists in s2, but this insight cites only f1, so 42 is not grounded.
    reasons = _grounder().check_insight(_insight("42 units", [{"kind": "fact", "fact_id": "f1"}]))
    assert reasons == ["UNGROUNDED_NUMBER 42"]
