"""Unit tests for individual nodes (each run through the real ``traced_node`` wrapper)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.agent.graph import NODES
from app.agent.nodes.planning import normalize_plan
from app.agent.nodes.schema import build_context
from app.agent.runtime import AgentDeps, traced_node
from app.agent.state import (
    AgentState,
    AnalysisPlan,
    Budget,
    ComputedFact,
    EvidenceRef,
    Insight,
    QueryUnderstanding,
    SQLAttempt,
    StepResult,
)
from app.agent.tools.analysis import ResultTable
from tests.agent import scenarios as sc
from tests.agent.fakes import FakeExecutor, Harness, ScriptedProvider, budget, db_error, ok


async def run_node(name: str, state: dict[str, Any], deps: AgentDeps) -> dict[str, Any]:
    fn, fallback, always = NODES[name]
    node = traced_node(name, fn, fallback=fallback, always_run=always)
    return await node(state, {"configurable": {"deps": deps}})  # type: ignore[arg-type]


def harness(script: dict[str, list[Any]] | None = None, rules: list[Any] | None = None) -> Harness:
    return Harness(ScriptedProvider(script), FakeExecutor(rules or []))


def planned_state(h: Harness, **overrides: Any) -> dict[str, Any]:
    """State as it is just before SQL generation for step s1 of the revenue plan."""
    plan = AnalysisPlan.model_validate(sc.PLAN)
    state: dict[str, Any] = {
        "run_id": "t",
        "question": sc.QUESTION,
        "today": "2025-10-15",
        "prior_context": [],
        "table_catalog": h.deps.schema.table_catalog(),
        "understanding": QueryUnderstanding.model_validate(sc.UNDERSTANDING),
        "schema_context": build_context(
            h.deps.schema, ["orders", "order_items", "products", "customers"], "r", 0
        ),
        "plan": plan,
        "current_step_idx": 0,
        "step_results": {s.step_id: StepResult(step_id=s.step_id) for s in plan.steps},
        "facts": [],
        "charts": [],
        "insights": [],
        "verification_feedback": [],
        "budget": budget(),
        "trace": [],
        "errors": [],
    }
    state.update(overrides)
    return state


def with_attempt(state: dict[str, Any], step_id: str, **attempt: Any) -> dict[str, Any]:
    results = dict(state["step_results"])
    r = results[step_id].model_copy(deep=True)
    r.attempts.append(
        SQLAttempt(
            attempt=len(r.attempts) + 1,
            sql=attempt.pop("sql", "SELECT 1"),
            explanation="",
            **attempt,
        )
    )
    results[step_id] = r
    return {**state, "step_results": results}


# ------------------------------------------------------------------ wrapper


async def test_wrapper_records_event_and_budget() -> None:
    h = harness()
    out = await run_node("load_context", {"question": "q", "budget": Budget(), "trace": []}, h.deps)
    (event,) = out["trace"]
    assert event.node == "load_context" and event.status == "succeeded" and event.seq == 1
    assert event.tool_calls[0]["tool"] == "get_table_catalog" and event.tool_calls[0]["ok"]
    assert out["budget"].deadline_ts > 0 and len(out["table_catalog"]) == 4


async def test_critical_node_failure_terminates_with_error() -> None:
    h = harness({"understand_query": [{"nonsense": 1}, {"still": "bad"}]})
    out = await run_node("understand_query", planned_state(h), h.deps)
    assert out["termination_reason"] == "error"
    assert out["trace"][0].status == "failed" and "LLMOutputError" in out["trace"][0].error
    assert out["budget"].llm_calls == 2  # failed calls still count


async def test_node_with_fallback_degrades() -> None:
    h = harness({"generate_visualization": []})  # model unavailable
    state = planned_state(h)
    results = dict(state["step_results"])
    results["s1"] = StepResult(
        step_id="s1",
        status="succeeded",
        columns=[("x", "numeric")],
        row_count=1,
        preview_rows=[[1]],
    )
    out = await run_node("generate_visualization", {**state, "step_results": results}, h.deps)
    assert out["trace"][0].status == "degraded"
    assert [c.chart_type for c in out["charts"]] == ["table"]
    assert "chart agent unavailable" in (out["charts"][0].fallback_reason or "")


async def test_cancelled_run_skips_nodes() -> None:
    h = harness()
    h.deps.cancel_event = asyncio.Event()
    h.deps.cancel_event.set()
    out = await run_node("generate_sql", planned_state(h), h.deps)
    assert out["termination_reason"] == "cancelled" and out["cancel_requested"]
    assert out["trace"][0].summary == {"skipped": "cancelled"}
    assert h.provider.calls == []


async def test_deadline_skips_nodes() -> None:
    h = harness()
    out = await run_node("generate_sql", planned_state(h, budget=Budget(deadline_ts=1.0)), h.deps)
    assert out["termination_reason"] == "budget_exhausted"


async def test_llm_call_cap_is_enforced_before_calling() -> None:
    h = harness({"generate_sql": [{"sql": "SELECT 1"}]})
    state = planned_state(h, budget=budget(max_llm_calls=3, llm_calls=3))
    out = await run_node("generate_sql", state, h.deps)
    assert h.provider.calls == []
    assert out["termination_reason"] == "budget_exhausted"


# -------------------------------------------------------- understanding


async def test_understanding_out_of_scope() -> None:
    h = harness(
        {
            "understand_query": [
                {
                    **sc.UNDERSTANDING,
                    "status": "out_of_scope",
                    "out_of_scope_reason": "No cost data.",
                }
            ]
        }
    )
    out = await run_node("understand_query", planned_state(h), h.deps)
    assert out["termination_reason"] == "out_of_scope"


async def test_understanding_may_ask_once_but_not_after_an_answer() -> None:
    reply = {
        **sc.UNDERSTANDING,
        "status": "needs_clarification",
        "clarification_question": "Which metric?",
        "clarification_options": ["Revenue", "Orders"],
    }
    h = harness({"understand_query": [reply, reply]})
    first = await run_node("understand_query", planned_state(h), h.deps)
    assert first["termination_reason"] == "clarification_needed"
    second = await run_node(
        "understand_query", planned_state(h, clarification_answer="Revenue"), h.deps
    )
    assert second["understanding"].status == "answerable" and "termination_reason" not in second
    assert "clarification_answer" in h.provider.calls[1].text


async def test_understanding_receives_conversation_context() -> None:
    h = harness({"understand_query": [sc.UNDERSTANDING]})
    prior = [{"question": "Revenue by month?", "answer": "Revenue peaked in July."}]
    await run_node("understand_query", planned_state(h, prior_context=prior), h.deps)
    assert "Revenue peaked in July." in h.provider.calls[0].text


# ---------------------------------------------------------------- schema


async def test_schema_loop_feeds_tool_errors_back_and_respects_the_cap() -> None:
    h = harness(
        {
            "retrieve_schema": [
                {"action": "get_table_schema", "tables": ["payments"]},  # error → observation
                {"action": "get_column_values", "table": "orders", "column": "status"},
                {"action": "get_table_schema", "tables": ["orders"]},
            ]
        }
    )
    state = planned_state(h, budget=budget(max_schema_tool_calls=2))
    state.pop("schema_context")
    out = await run_node("retrieve_schema", state, h.deps)
    second_turn = h.provider.calls[1].text
    assert "Unknown table “payments”" in second_turn
    assert out["schema_context"].tool_calls == 2
    # cap reached without finish → whole small dataset (nothing was inspected successfully)
    assert out["trace"][0].status == "degraded"


async def test_schema_finish_filters_invented_tables() -> None:
    h = harness(
        {
            "retrieve_schema": [
                {
                    "action": "finish",
                    "selected_tables": ["orders", "revenue_facts"],
                    "rationale": "r",
                }
            ]
        }
    )
    out = await run_node("retrieve_schema", planned_state(h), h.deps)
    ctx = out["schema_context"]
    assert ctx.tables == ["orders"] and all(c.table == "orders" for c in ctx.columns)
    assert out["trace"][0].summary["ignored_unknown_tables"] == ["revenue_facts"]


# --------------------------------------------------------------- planning


def test_plan_normalisation_renumbers_and_drops_forward_dependencies() -> None:
    plan = AnalysisPlan.model_validate(
        {
            "final_answer_shape": "x",
            "steps": [
                {"step_id": "s3", "purpose": "a", "expected_output": "a", "depends_on": ["s5"]},
                {"step_id": "s5", "purpose": "b", "expected_output": "b", "depends_on": ["s3"]},
            ],
        }
    )
    normalized, notes = normalize_plan(plan)
    assert [(s.step_id, s.depends_on) for s in normalized.steps] == [("s1", []), ("s2", ["s1"])]
    assert notes == ["s1: dropped dependency on s5 (not an earlier step)"]


async def test_planning_refuses_to_run_without_schema_context() -> None:
    h = harness({"plan_analysis": [sc.PLAN]})
    state = planned_state(h)
    state.pop("schema_context")
    out = await run_node("plan_analysis", state, h.deps)
    assert (
        out["termination_reason"] == "error"
        and "MissingSchemaContextError" in out["trace"][0].error
    )
    assert h.provider.calls == []


async def test_planning_prompt_contains_real_schema() -> None:
    h = harness({"plan_analysis": [sc.PLAN]})
    out = await run_node("plan_analysis", planned_state(h), h.deps)
    assert len(out["plan"].steps) == 3
    assert "unit_price numeric" in h.provider.calls[0].text


# -------------------------------------------------------------------- SQL


async def test_generate_sql_uses_schema_and_earlier_steps() -> None:
    h = harness({"generate_sql": [{"sql": sc.SQL_S2, "explanation": "e"}]})
    state = planned_state(h, current_step_idx=1)
    done = with_attempt(
        state,
        "s1",
        sql=sc.SQL_S1,
        guard_status="accepted",
        normalized_sql="SELECT s1",
        exec_status="ok",
    )
    done["step_results"]["s1"].status = "succeeded"
    out = await run_node("generate_sql", done, h.deps)
    assert out["step_results"]["s2"].attempts[0].sql == sc.SQL_S2
    prompt = h.provider.calls[0].text
    assert '"step_id": "s2"' in prompt and "SELECT s1" in prompt and "category text" in prompt


async def test_validate_sql_rejects_unsafe_and_repeated_queries() -> None:
    h = harness()
    state = with_attempt(planned_state(h), "s1", sql="DELETE FROM orders")
    out = await run_node("validate_sql", state, h.deps)
    attempt = out["step_results"]["s1"].attempts[0]
    assert attempt.guard_status == "rejected" and attempt.guard_violations[0].code == "NOT_A_SELECT"

    first = with_attempt(planned_state(h), "s1", sql=sc.SQL_S1)
    validated = await run_node("validate_sql", first, h.deps)
    again = with_attempt({**first, **validated}, "s1", sql=sc.SQL_S1 + "  ")
    out = await run_node("validate_sql", again, h.deps)
    assert out["step_results"]["s1"].attempts[1].guard_violations[0].code == "REPEATED_QUERY"


async def test_execute_sql_records_errors_without_crashing() -> None:
    h = harness(
        rules=[
            (
                "revenue_before",
                db_error("42803", 'column "o.status" must appear in the GROUP BY clause'),
            )
        ]
    )
    state = with_attempt(
        planned_state(h), "s1", sql=sc.SQL_S1, guard_status="accepted", normalized_sql=sc.SQL_S1
    )
    out = await run_node("execute_sql", state, h.deps)
    attempt = out["step_results"]["s1"].attempts[0]
    assert (attempt.exec_status, attempt.error_code) == ("error", "42803")
    assert out["budget"].sql_exec == 1 and out["trace"][0].status == "succeeded"


async def test_execute_sql_refuses_unvalidated_sql() -> None:
    h = harness(rules=[("", ok([("x", "int4")], [[1]]))])
    out = await run_node(
        "execute_sql", with_attempt(planned_state(h), "s1", sql="SELECT 1"), h.deps
    )
    assert out["termination_reason"] == "error" and h.executor.executed == []


async def test_execute_sql_respects_the_execution_cap() -> None:
    h = harness(rules=[("", ok([("x", "int4")], [[1]]))])
    state = with_attempt(
        planned_state(h, budget=budget(max_sql_exec=1, sql_exec=1)),
        "s1",
        sql="SELECT 1",
        guard_status="accepted",
        normalized_sql="SELECT 1",
    )
    out = await run_node("execute_sql", state, h.deps)
    assert out["termination_reason"] == "budget_exhausted" and h.executor.executed == []


async def test_check_result_flags_empty_once() -> None:
    h = harness()
    state = with_attempt(
        planned_state(h), "s1", guard_status="accepted", exec_status="ok", row_count=0
    )
    out = await run_node("check_result", state, h.deps)
    assert out["step_results"]["s1"].needs_repair.category == "empty_result"
    # after one repair for emptiness, an empty result is accepted with a note
    s = out["step_results"]["s1"]
    s.attempts[0].diagnosis = s.needs_repair
    s.needs_repair = None
    state2 = with_attempt(
        {**state, "step_results": {**state["step_results"], "s1": s}},
        "s1",
        guard_status="accepted",
        exec_status="ok",
        row_count=0,
    )
    out2 = await run_node("check_result", state2, h.deps)
    assert out2["step_results"]["s1"].needs_repair is None
    assert "No matching data" in out2["step_results"]["s1"].notes[0]


async def test_finish_step_explains_failure_and_skips_dependents() -> None:
    h = harness()
    plan = AnalysisPlan.model_validate(
        {
            **sc.PLAN,
            "steps": [
                sc.PLAN["steps"][0],
                {**sc.PLAN["steps"][1], "depends_on": ["s1"]},
                sc.PLAN["steps"][2],
            ],
        }
    )
    state = planned_state(h, plan=plan)
    for _ in range(3):
        state = with_attempt(
            state,
            "s1",
            guard_status="accepted",
            exec_status="error",
            error_code="42703",
            exec_error='column "revenue" does not exist',
        )
    out = await run_node("finish_step", state, h.deps)
    assert out["step_results"]["s1"].status == "failed"
    assert "after 3 attempts" in out["step_results"]["s1"].failure_explanation
    assert 'column "revenue" does not exist' in out["step_results"]["s1"].failure_explanation
    assert out["step_results"]["s2"].status == "skipped"
    assert out["current_step_idx"] == 2 and "termination_reason" not in out


# --------------------------------------------------------------- recovery


async def test_recovery_classifies_and_gives_relevant_context() -> None:
    h = harness({"recover_error": [{"diagnosis": "d", "sql": sc.SQL_S2, "change_summary": "c"}]})
    state = with_attempt(
        planned_state(h, current_step_idx=1),
        "s2",
        sql="SELECT o.category FROM orders o",
        guard_status="accepted",
        exec_status="error",
        error_code="42703",
        exec_error="column o.category does not exist",
    )
    out = await run_node("recover_error", state, h.deps)
    s2 = out["step_results"]["s2"]
    assert s2.attempts[0].diagnosis.category == "unknown_column"
    assert s2.attempts[1].origin == "recovery" and s2.attempts[1].guard_status == "pending"
    prompt = h.provider.calls[0].text
    assert '"all_tables"' in prompt and "column o.category does not exist" in prompt


async def test_recovery_stops_on_unrecoverable_errors() -> None:
    h = harness()
    state = with_attempt(
        planned_state(h),
        "s1",
        guard_status="accepted",
        exec_status="error",
        error_code="42501",
        exec_error="permission denied for table x",
    )
    out = await run_node("recover_error", state, h.deps)
    s1 = out["step_results"]["s1"]
    assert len(s1.attempts) == 1 and "not attempted" in s1.failure_explanation
    assert h.provider.calls == []


async def test_recovery_fallback_explains_when_the_model_fails() -> None:
    h = harness({"recover_error": []})
    state = with_attempt(
        planned_state(h),
        "s1",
        guard_status="accepted",
        exec_status="timeout",
        error_code="57014",
        exec_error="canceling statement due to statement timeout",
    )
    out = await run_node("recover_error", state, h.deps)
    assert "Automatic recovery was unavailable" in out["step_results"]["s1"].failure_explanation
    assert out["trace"][0].status == "degraded"


# ------------------------------------------------------- analysis, insights


def analysed_state(h: Harness) -> dict[str, Any]:
    state = planned_state(h, current_step_idx=3)
    results = {}
    specs: list[tuple[str, list[tuple[str, str]], list[list[Any]]]] = [
        ("s1", [("revenue_before", "numeric"), ("revenue_after", "numeric")], sc.S1_ROWS),
        (
            "s2",
            [("category", "text"), ("revenue_before", "numeric"), ("revenue_after", "numeric")],
            sc.S2_ROWS,
        ),
        (
            "s3",
            [("region", "text"), ("revenue_before", "numeric"), ("revenue_after", "numeric")],
            sc.S3_ROWS,
        ),
    ]
    for sid, cols, rows in specs:
        results[sid] = StepResult(
            step_id=sid,
            status="succeeded",
            columns=cols,
            row_count=len(rows),
            preview_rows=rows,
            attempts=[
                SQLAttempt(
                    attempt=1,
                    sql="x",
                    explanation="",
                    guard_status="accepted",
                    normalized_sql=sc.SQL_S1,
                    exec_status="ok",
                )
            ],
        )
        h.deps.results[sid] = ResultTable(sid, [c for c, _ in cols], rows)
    return {**state, "step_results": results}


async def test_analysis_runs_auto_facts_then_selected_tools() -> None:
    h = harness(
        {
            "analyze_results": [
                {
                    "calls": [
                        *sc.ANALYSIS["calls"],
                        {
                            "tool": "total",
                            "step_id": "s2",
                            "column": "nope",
                            "description": "bad column",
                        },
                    ]
                }
            ]
        }
    )
    out = await run_node("analyze_results", analysed_state(h), h.deps)
    assert [f.kind for f in out["facts"]] == [
        "lookup",
        "lookup",
        "pct_change",
        "group_change",
        "group_change",
    ]
    assert out["trace"][0].summary["skipped_calls"][0].startswith("total:")
    assert out["trace"][0].status == "succeeded"


async def test_analysis_fallback_keeps_deterministic_facts() -> None:
    h = harness({"analyze_results": []})
    out = await run_node("analyze_results", analysed_state(h), h.deps)
    assert out["trace"][0].status == "degraded" and [f.kind for f in out["facts"]] == [
        "lookup",
        "lookup",
    ]


def _insight(headline: str, fact: str = "f1", category: str = "finding") -> Insight:
    return Insight(
        insight_id="i1",
        headline=headline,
        detail="",
        category=category,
        evidence=[EvidenceRef(kind="fact", fact_id=fact)],
        confidence="high",
    )


async def test_verification_judge_can_reject_but_never_rescue() -> None:
    h = harness(
        {
            "verify_insights": [
                {
                    "metrics_match": True,
                    "time_period_match": True,
                    "insights": [
                        {"insight_id": "i1", "supported": True},
                        {"insight_id": "i2", "supported": False, "issue": "says rose, data fell"},
                    ],
                }
            ]
        }
    )
    state = analysed_state(h)
    fact = ComputedFact(
        fact_id="f1",
        step_id="s1",
        kind="pct_change",
        description="d",
        value=-15.0,
        inputs={"supporting": {"before": 100000.0, "after": 85000.0, "change": -15000.0}},
    )
    insights = [
        _insight("Revenue fell 15%"),
        _insight("Revenue rose 15%").model_copy(update={"insight_id": "i2"}),
        _insight("Revenue fell 99%").model_copy(update={"insight_id": "i3"}),
    ]
    out = await run_node(
        "verify_insights", {**state, "facts": [fact], "insights": insights}, h.deps
    )
    by_id = {i.insight_id: i for i in out["insights"]}
    assert by_id["i1"].verification == "verified"
    assert (
        by_id["i2"].verification == "rejected" and "says rose" in by_id["i2"].rejection_reasons[0]
    )
    assert by_id["i3"].rejection_reasons == ["UNGROUNDED_NUMBER 99%"]
    judged = h.provider.calls[0].text
    assert '"insight_id": "i3"' not in judged  # failed pass 1: never sent to the judge
    assert len(out["verification_feedback"]) == 2


async def test_verification_removes_rejected_insights_after_the_last_round() -> None:
    h = harness({"verify_insights": []})  # judge unavailable → degraded, code-only
    state = analysed_state(h)
    fact = ComputedFact(fact_id="f1", step_id="s1", kind="lookup", description="d", value=85000.0)
    st = {
        **state,
        "facts": [fact],
        "insights": [
            _insight("Revenue was $85,000"),
            _insight("Revenue was $90,000").model_copy(update={"insight_id": "i2"}),
        ],
        "budget": budget(verify_rounds=1),
    }
    out = await run_node("verify_insights", st, h.deps)
    assert [i.insight_id for i in out["insights"]] == ["i1"]
    assert out["verification"].removed[0]["reasons"] == ["UNGROUNDED_NUMBER $90,000"]
    assert out["trace"][0].status == "degraded"
    assert any("verified by code only" in n for n in out["verification"].uncertainty)


async def test_time_period_check_flags_queries_without_dates() -> None:
    h = harness(
        {"verify_insights": [{"metrics_match": True, "time_period_match": True, "insights": []}]}
    )
    state = analysed_state(h)
    for r in state["step_results"].values():
        r.attempts[0].normalized_sql = "SELECT SUM(quantity) FROM order_items"
    fact = ComputedFact(fact_id="f1", step_id="s1", kind="lookup", description="d", value=1.0)
    out = await run_node(
        "verify_insights", {**state, "facts": [fact], "insights": [_insight("One")]}, h.deps
    )
    assert out["verification"].time_period_check.startswith(
        "issue: no executed query uses a date column"
    )


# --------------------------------------------------------------- response


async def test_response_rejects_a_summary_with_new_numbers() -> None:
    h = harness({"compose_response": [{"summary": "Revenue fell 42%."}]})
    state = analysed_state(h)
    fact = ComputedFact(fact_id="f1", step_id="s1", kind="pct_change", description="d", value=-15.0)
    verified = _insight("Revenue fell 15%").model_copy(update={"verification": "verified"})
    out = await run_node(
        "compose_response", {**state, "facts": [fact], "insights": [verified]}, h.deps
    )
    response = out["response"]
    assert response.summary == "Revenue fell 15%." and response.summary_source == "template"
    assert out["trace"][0].status == "degraded"


@pytest.mark.parametrize(
    ("reason", "status", "text"),
    [
        ("out_of_scope", "out_of_scope", "can’t answer"),
        ("all_steps_failed", "failed", "None of the queries"),
        ("error", "failed", "Nothing was guessed"),
        ("cancelled", "failed", "cancelled"),
    ],
)
async def test_response_explains_every_termination(reason: str, status: str, text: str) -> None:
    h = harness()
    out = await run_node("compose_response", planned_state(h, termination_reason=reason), h.deps)
    assert out["response"].status == status and text in out["response"].summary
    assert out["termination_reason"] == reason and h.provider.calls == []


async def test_response_runs_even_after_the_deadline() -> None:
    h = harness()
    state: AgentState = planned_state(h, budget=Budget(deadline_ts=1.0))  # type: ignore[assignment]
    out = await run_node("compose_response", state, h.deps)  # type: ignore[arg-type]
    assert out["response"].status == "failed" and out["termination_reason"] == "budget_exhausted"
