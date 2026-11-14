"""Routers (pure functions) and the compiled graph's exact shape."""

from __future__ import annotations

import inspect
from typing import Any, cast

import pytest

from app.agent import routing
from app.agent.graph import CONDITIONAL_EDGES, NODES, build_graph
from app.agent.state import AgentState, AnalysisPlan, Budget, ErrorDiagnosis, SQLAttempt, StepResult
from tests.agent import scenarios as sc
from tests.agent.fakes import budget


def state(attempts: list[SQLAttempt] | None = None, **kw: Any) -> AgentState:
    plan = AnalysisPlan.model_validate(sc.PLAN)
    results = {s.step_id: StepResult(step_id=s.step_id) for s in plan.steps}
    results["s1"].attempts = attempts or []
    if "needs_repair" in kw:
        results["s1"].needs_repair = kw.pop("needs_repair")
    return cast(
        AgentState,
        {"plan": plan, "current_step_idx": 0, "step_results": results, "budget": budget(), **kw},
    )


def attempt(n: int = 1, **kw: Any) -> SQLAttempt:
    return SQLAttempt(attempt=n, sql="SELECT 1", explanation="", **kw)


def test_every_router_short_circuits_to_compose_when_stopping() -> None:
    for stopped in (
        state(termination_reason="error"),
        state(cancel_requested=True),
        state(budget=Budget(deadline_ts=1.0)),
    ):
        for source, (router, _) in CONDITIONAL_EDGES.items():
            assert router(stopped) == routing.COMPOSE, source


@pytest.mark.parametrize(
    ("router", "attempts", "expected"),
    [
        (routing.route_after_generation, [attempt(guard_status="pending")], "validate_sql"),
        (routing.route_after_generation, [], "finish_step"),
        (routing.route_after_validation, [attempt(guard_status="accepted")], "execute_sql"),
        (routing.route_after_validation, [attempt(guard_status="rejected")], "recover_error"),
        (
            routing.route_after_validation,
            [attempt(i, guard_status="rejected") for i in (1, 2, 3)],
            "finish_step",
        ),
        (
            routing.route_after_execution,
            [attempt(guard_status="accepted", exec_status="ok")],
            "check_result",
        ),
        (
            routing.route_after_execution,
            [attempt(guard_status="accepted", exec_status="error")],
            "recover_error",
        ),
        (
            routing.route_after_execution,
            [attempt(guard_status="accepted", exec_status="timeout")],
            "recover_error",
        ),
        (
            routing.route_after_execution,
            [attempt(i, guard_status="accepted", exec_status="error") for i in (1, 2, 3)],
            "finish_step",
        ),
        (
            routing.route_after_recovery,
            [
                attempt(guard_status="accepted", exec_status="error"),
                attempt(2, guard_status="pending"),
            ],
            "validate_sql",
        ),
        (
            routing.route_after_recovery,
            [attempt(guard_status="accepted", exec_status="error")],
            "finish_step",
        ),
    ],
)
def test_sql_routing(router: Any, attempts: list[SQLAttempt], expected: str) -> None:
    assert router(state(attempts)) == expected


def test_check_routing_and_retry_bound() -> None:
    empty = ErrorDiagnosis(category="empty_result", recoverable=True, summary="empty")
    assert (
        routing.route_after_check(state([attempt(exec_status="ok")], needs_repair=empty))
        == "recover_error"
    )
    full = [attempt(i, exec_status="ok") for i in (1, 2, 3)]
    assert routing.route_after_check(state(full, needs_repair=empty)) == "finish_step"
    assert routing.route_after_check(state([attempt(exec_status="ok")])) == "finish_step"


def test_step_and_verification_routing() -> None:
    assert routing.route_after_step(state(current_step_idx=1)) == "generate_sql"
    assert routing.route_after_step(state(current_step_idx=3)) == "analyze_results"
    assert (
        routing.route_after_verification(state(verification_feedback=["i1: bad"]))
        == "generate_insights"
    )
    done = state(verification_feedback=["i1: bad"], budget=budget(verify_rounds=2))
    assert routing.route_after_verification(done) == routing.COMPOSE
    assert routing.route_after_verification(state(verification_feedback=[])) == routing.COMPOSE


def test_compiled_graph_has_exactly_the_designed_nodes_and_edges() -> None:
    graph = build_graph().get_graph()
    assert set(graph.nodes) == {*NODES, "__start__", "__end__"}
    edges = {(e.source, e.target, e.conditional) for e in graph.edges}
    assert edges == {
        ("__start__", "load_context", False),
        ("load_context", "understand_query", False),
        ("compose_response", "__end__", False),
        ("understand_query", "retrieve_schema", True),
        ("understand_query", "compose_response", True),
        ("retrieve_schema", "plan_analysis", True),
        ("retrieve_schema", "compose_response", True),
        ("plan_analysis", "generate_sql", True),
        ("plan_analysis", "compose_response", True),
        ("generate_sql", "validate_sql", True),
        ("generate_sql", "finish_step", True),
        ("generate_sql", "compose_response", True),
        ("validate_sql", "execute_sql", True),
        ("validate_sql", "recover_error", True),
        ("validate_sql", "finish_step", True),
        ("validate_sql", "compose_response", True),
        ("execute_sql", "check_result", True),
        ("execute_sql", "recover_error", True),
        ("execute_sql", "finish_step", True),
        ("execute_sql", "compose_response", True),
        ("check_result", "recover_error", True),
        ("check_result", "finish_step", True),
        ("check_result", "compose_response", True),
        ("recover_error", "validate_sql", True),
        ("recover_error", "finish_step", True),
        ("recover_error", "compose_response", True),
        ("finish_step", "generate_sql", True),
        ("finish_step", "analyze_results", True),
        ("finish_step", "compose_response", True),
        ("analyze_results", "generate_visualization", True),
        ("analyze_results", "compose_response", True),
        ("generate_visualization", "generate_insights", True),
        ("generate_visualization", "compose_response", True),
        ("generate_insights", "verify_insights", True),
        ("generate_insights", "compose_response", True),
        ("verify_insights", "generate_insights", True),
        ("verify_insights", "compose_response", True),
    }


def test_the_twelve_requested_responsibilities_are_separate_nodes() -> None:
    requested = {
        "understand_query",
        "plan_analysis",
        "retrieve_schema",
        "generate_sql",
        "validate_sql",
        "execute_sql",
        "recover_error",
        "analyze_results",
        "generate_visualization",
        "generate_insights",
        "verify_insights",
        "compose_response",
    }
    assert requested <= set(NODES)
    # validation and execution are tools, never model calls
    for name in ("validate_sql", "execute_sql", "check_result", "finish_step"):
        assert "ctx.llm" not in inspect.getsource(NODES[name][0]), name
