"""Small helpers shared by nodes. Nodes never mutate state objects in place: they copy,
change the copy and return it in their partial update."""

from __future__ import annotations

from typing import Any

from app.agent.state import AgentState, PlanStep, SchemaContext, StepResult

PROMPT_PREVIEW_ROWS = 20


def plan_steps(state: AgentState) -> list[PlanStep]:
    return state["plan"].steps if state.get("plan") else []


def current_plan_step(state: AgentState) -> PlanStep:
    return plan_steps(state)[state.get("current_step_idx", 0)]


def current_result(state: AgentState) -> StepResult:
    """A deep copy of the current step's result, safe to modify."""
    step = current_plan_step(state)
    existing = state.get("step_results", {}).get(step.step_id)
    return existing.model_copy(deep=True) if existing else StepResult(step_id=step.step_id)


def put_step(state: AgentState, result: StepResult) -> dict[str, Any]:
    results = dict(state.get("step_results", {}))
    results[result.step_id] = result
    return {"step_results": results}


def schema_for_prompt(context: SchemaContext) -> dict[str, Any]:
    tables: dict[str, list[str]] = {}
    for c in context.columns:
        line = f"{c.column} {c.data_type}"
        if c.is_primary_key:
            line += " PK"
        if c.description:
            line += f" — {c.description}"
        if c.sample_values:
            line += f" (values: {', '.join(c.sample_values[:8])})"
        if c.min_value and c.max_value:
            line += f" [range {c.min_value} → {c.max_value}]"
        tables.setdefault(c.table, []).append(line)
    return {"tables": tables, "join_paths": context.join_paths}


def step_payload(result: StepResult, rows: int = PROMPT_PREVIEW_ROWS) -> dict[str, Any]:
    return {
        "step_id": result.step_id,
        "status": result.status,
        # names and types as separate fields: a combined "name (type)" label gets copied
        # back as if it were the column name
        "columns": [{"name": name, "type": pg} for name, pg in result.columns],
        "row_count": result.row_count,
        "truncated": result.truncated,
        "rows": [{"row_index": i, "values": r} for i, r in enumerate(result.preview_rows[:rows])],
        "notes": result.notes,
    }


def understanding_payload(state: AgentState) -> dict[str, Any]:
    u = state.get("understanding")
    return u.model_dump(exclude={"clarification_options", "clarification_question"}) if u else {}
