"""The Sageboard analysis workflow as a LangGraph ``StateGraph``.

    START → load_context → understand_query ─┬─▶ compose_response (clarify / out of scope)
                                             └─▶ retrieve_schema → plan_analysis
      ┌──────────────────────────────────────────────────────────┘
      ▼
    generate_sql → validate_sql ─ accepted ─▶ execute_sql ─ ok ─▶ check_result
                     │ rejected                  │ error              │ empty / truncated
                     ▼                           ▼                    ▼
                  recover_error ◀────────────────┴────────────────────┘   (≤ 3 attempts)
                     │ new SQL → validate_sql      │ out of attempts / unrecoverable
                     ▼                             ▼
                 finish_step ◀─────────────────────┘ ─ more steps ─▶ generate_sql
                     │ all steps done
                     ▼
    analyze_results → generate_visualization → generate_insights → verify_insights
                                                     ▲                  │ rejected (≤ 2 rounds)
                                                     └──────────────────┘
                                                                        ▼
                                                               compose_response → END

Every router can short-circuit to ``compose_response`` (terminated, cancelled, out of
budget). See docs/AGENT_WORKFLOW.md for the full state-transition table.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent import routing
from app.agent.nodes.analysis import analyze_results, analyze_results_fallback
from app.agent.nodes.insights import generate_insights, generate_insights_fallback
from app.agent.nodes.planning import plan_analysis
from app.agent.nodes.recovery import recover_error, recover_error_fallback
from app.agent.nodes.response import compose_response
from app.agent.nodes.schema import retrieve_schema, retrieve_schema_fallback
from app.agent.nodes.sql import (
    check_result,
    execute_sql,
    finish_step,
    generate_sql,
    generate_sql_fallback,
    validate_sql,
)
from app.agent.nodes.understanding import load_context, understand_query
from app.agent.nodes.verification import verify_insights
from app.agent.nodes.visualization import (
    generate_visualization,
    generate_visualization_fallback,
)
from app.agent.runtime import AgentDeps, Fallback, NodeFn, traced_node
from app.agent.state import AgentState, Budget

# name → (implementation, fallback, always_run). No fallback = critical node: a failure
# ends the run with termination_reason="error" (explained by compose_response).
NODES: dict[str, tuple[NodeFn, Fallback | None, bool]] = {
    "load_context": (load_context, None, False),
    "understand_query": (understand_query, None, False),  # 1 Query Understanding
    "retrieve_schema": (retrieve_schema, retrieve_schema_fallback, False),  # 3 Schema Retrieval
    "plan_analysis": (plan_analysis, None, False),  # 2 Planning
    "generate_sql": (generate_sql, generate_sql_fallback, False),  # 4 SQL Generation
    "validate_sql": (validate_sql, None, False),  # 5 SQL Validation
    "execute_sql": (execute_sql, None, False),  # 6 SQL Execution
    "check_result": (check_result, None, False),  # 7 error detection
    "recover_error": (recover_error, recover_error_fallback, False),  # 7 Error Recovery
    "finish_step": (finish_step, None, False),  # step control
    "analyze_results": (analyze_results, analyze_results_fallback, False),  # 8 Result Analysis
    "generate_visualization": (generate_visualization, generate_visualization_fallback, False),  # 9
    "generate_insights": (generate_insights, generate_insights_fallback, False),  # 10 Insights
    "verify_insights": (verify_insights, None, False),  # 11 Verification
    "compose_response": (compose_response, None, True),  # 12 Final Response
}

C = routing.COMPOSE
CONDITIONAL_EDGES: dict[str, tuple[Callable[[AgentState], str], list[str]]] = {
    "understand_query": (routing.route_after_understanding, ["retrieve_schema", C]),
    "retrieve_schema": (routing.route_after_schema, ["plan_analysis", C]),
    "plan_analysis": (routing.route_after_plan, ["generate_sql", C]),
    "generate_sql": (routing.route_after_generation, ["validate_sql", "finish_step", C]),
    "validate_sql": (
        routing.route_after_validation,
        ["execute_sql", "recover_error", "finish_step", C],
    ),
    "execute_sql": (
        routing.route_after_execution,
        ["check_result", "recover_error", "finish_step", C],
    ),
    "check_result": (routing.route_after_check, ["recover_error", "finish_step", C]),
    "recover_error": (routing.route_after_recovery, ["validate_sql", "finish_step", C]),
    "finish_step": (routing.route_after_step, ["generate_sql", "analyze_results", C]),
    "analyze_results": (
        routing.route_continue("generate_visualization"),
        ["generate_visualization", C],
    ),
    "generate_visualization": (
        routing.route_continue("generate_insights"),
        ["generate_insights", C],
    ),
    "generate_insights": (routing.route_continue("verify_insights"), ["verify_insights", C]),
    "verify_insights": (routing.route_after_verification, ["generate_insights", C]),
}
FIXED_EDGES = [(START, "load_context"), ("load_context", "understand_query"), (C, END)]

# Upper bound on node executions per run (LangGraph's default of 25 is too low for a
# six-step plan with retries). Budgets stop real runs long before this.
RECURSION_LIMIT = 200


def build_graph() -> CompiledStateGraph[Any, Any, Any, Any]:
    graph = StateGraph(AgentState)
    for name, (fn, fallback, always_run) in NODES.items():
        node = traced_node(name, fn, fallback=fallback, always_run=always_run)
        # LangGraph's overloads describe nodes as protocols with named parameters.
        graph.add_node(name, node)  # type: ignore[call-overload]
    for source, target in FIXED_EDGES:
        graph.add_edge(source, target)
    for source, (router, targets) in CONDITIONAL_EDGES.items():
        graph.add_conditional_edges(source, router, targets)
    return graph.compile()


def initial_state(
    *,
    run_id: str,
    question: str,
    today: str,
    budget: Budget,
    prior_context: list[dict[str, Any]] | None = None,
    clarification_answer: str | None = None,
) -> AgentState:
    return AgentState(
        run_id=run_id,
        question=question,
        today=today,
        budget=budget,
        prior_context=prior_context or [],
        clarification_answer=clarification_answer,
        trace=[],
        errors=[],
    )


async def run_graph(
    graph: CompiledStateGraph[Any, Any, Any, Any], state: AgentState, deps: AgentDeps
) -> AgentState:
    final = await graph.ainvoke(
        state, config={"configurable": {"deps": deps}, "recursion_limit": RECURSION_LIMIT}
    )
    return cast(AgentState, final)
