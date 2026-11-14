"""Conditional routing. Pure functions of the state (and the clock).

Every router first checks ``must_stop``: once the run is terminated, cancelled or past
its deadline it goes straight to ``compose_response``, so a run always ends with a
coherent answer and never hangs. Retries are bounded here, in code.
"""

from __future__ import annotations

import time

from app.agent.nodes.common import current_result, plan_steps
from app.agent.state import AgentState

COMPOSE = "compose_response"


def must_stop(state: AgentState, now: float | None = None) -> bool:
    if state.get("termination_reason") or state.get("cancel_requested"):
        return True
    budget = state.get("budget")
    clock = time.time() if now is None else now
    return bool(budget and budget.deadline_ts and clock > budget.deadline_ts)


def _attempts_left(state: AgentState) -> bool:
    return len(current_result(state).attempts) < state["budget"].max_attempts_per_step


def route_after_understanding(state: AgentState) -> str:
    return COMPOSE if must_stop(state) else "retrieve_schema"


def route_after_schema(state: AgentState) -> str:
    return COMPOSE if must_stop(state) else "plan_analysis"


def route_after_plan(state: AgentState) -> str:
    return COMPOSE if must_stop(state) or not plan_steps(state) else "generate_sql"


def route_after_generation(state: AgentState) -> str:
    if must_stop(state):
        return COMPOSE
    result = current_result(state)
    latest = result.latest()
    if latest is None or latest.guard_status != "pending":
        return "finish_step"  # generation failed: nothing to validate
    return "validate_sql"


def route_after_validation(state: AgentState) -> str:
    if must_stop(state):
        return COMPOSE
    latest = current_result(state).latest()
    if latest is not None and latest.guard_status == "accepted":
        return "execute_sql"
    return "recover_error" if _attempts_left(state) else "finish_step"


def route_after_execution(state: AgentState) -> str:
    if must_stop(state):
        return COMPOSE
    latest = current_result(state).latest()
    if latest is not None and latest.exec_status == "ok":
        return "check_result"
    return "recover_error" if _attempts_left(state) else "finish_step"


def route_after_check(state: AgentState) -> str:
    if must_stop(state):
        return COMPOSE
    needs = current_result(state).needs_repair
    return "recover_error" if needs is not None and _attempts_left(state) else "finish_step"


def route_after_recovery(state: AgentState) -> str:
    if must_stop(state):
        return COMPOSE
    latest = current_result(state).latest()
    # a new pending attempt means recovery produced SQL → revalidate it
    return (
        "validate_sql" if latest is not None and latest.guard_status == "pending" else "finish_step"
    )


def route_after_step(state: AgentState) -> str:
    if must_stop(state):
        return COMPOSE
    if state.get("current_step_idx", 0) < len(plan_steps(state)):
        return "generate_sql"
    return "analyze_results"


def route_continue(next_node: str):  # type: ignore[no-untyped-def]
    def route(state: AgentState) -> str:
        return COMPOSE if must_stop(state) else next_node

    route.__name__ = f"route_to_{next_node}"
    return route


def route_after_verification(state: AgentState) -> str:
    if must_stop(state):
        return COMPOSE
    budget = state["budget"]
    if state.get("verification_feedback") and budget.verify_rounds < budget.max_verify_rounds:
        return "generate_insights"
    return COMPOSE
