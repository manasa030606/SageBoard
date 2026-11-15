"""SQL nodes: generation (agent), validation and execution (tools), result checks and
step control (deterministic)."""

from __future__ import annotations

from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from app.agent.nodes.common import (
    current_plan_step,
    current_result,
    plan_steps,
    put_step,
    schema_for_prompt,
    sensitive_columns,
    step_payload,
    understanding_payload,
)
from app.agent.prompts import load_prompt, render
from app.agent.runtime import BudgetExhaustedError, NodeContext
from app.agent.state import AgentState, GuardViolation, SQLAttempt, StepResult
from app.agent.tools.analysis import ResultTable
from app.agent.tools.errors import result_problem
from app.agent.tools.sql_guard import validate_sql as guard_validate


class SQLDraft(BaseModel):
    sql: str = Field(min_length=1, max_length=20_000)
    explanation: str = Field(default="", max_length=600)


class NoAttemptError(RuntimeError):
    pass


def earlier_steps(state: AgentState, before: str) -> list[dict[str, Any]]:
    out = []
    for step in plan_steps(state):
        if step.step_id == before:
            break
        result = state["step_results"].get(step.step_id)
        attempt = result.latest() if result else None
        if result and result.status == "succeeded" and attempt:
            out.append(
                {"step_id": step.step_id, "purpose": step.purpose, "sql": attempt.normalized_sql}
            )
    return out


# ------------------------------------------------------------------ generation


async def generate_sql(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    step = current_plan_step(state)
    result = current_result(state)
    parts: list[str | tuple[str, Any]] = [
        ("question", state["question"]),
        ("understanding", understanding_payload(state)),
        ("plan", state["plan"].model_dump()),
        ("current_step", step.model_dump()),
        ("schema_context", schema_for_prompt(state["schema_context"])),
    ]
    if earlier := earlier_steps(state, step.step_id):
        parts.append(("earlier_steps", earlier))
    deps = [state["step_results"][d] for d in step.depends_on if d in state["step_results"]]
    if deps:
        parts.append(
            ("dependency_results", [step_payload(d, hidden=sensitive_columns(state)) for d in deps])
        )
    parts.append(f"Write the SQL for step {step.step_id}.")
    draft = await ctx.llm(load_prompt("generate_sql"), render(*parts), SQLDraft)
    result.attempts.append(
        SQLAttempt(attempt=len(result.attempts) + 1, sql=draft.sql, explanation=draft.explanation)
    )
    ctx.summary = {"step_id": step.step_id, "attempt": len(result.attempts)}
    return put_step(state, result)


def generate_sql_fallback(state: AgentState, exc: Exception, ctx: NodeContext) -> dict[str, Any]:
    result = current_result(state)
    result.failure_explanation = f"The SQL could not be generated ({type(exc).__name__})."
    return put_step(state, result)


# ------------------------------------------------------------------ validation


async def validate_sql(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    result = current_result(state)
    attempt = result.latest()
    if attempt is None:
        raise NoAttemptError("validate_sql ran without an SQL attempt")
    policy = ctx.deps.schema.guard_policy(ctx.deps.max_rows)
    verdict = await ctx.tool(
        "sql_guard.validate",
        {"step_id": result.step_id, "attempt": attempt.attempt},
        partial(guard_validate, attempt.sql, policy),
    )
    previous = {a.normalized_sql for a in result.attempts[:-1] if a.normalized_sql}
    if verdict.ok and verdict.normalized_sql in previous:
        attempt.guard_status = "rejected"
        attempt.normalized_sql = verdict.normalized_sql
        attempt.guard_violations = [
            GuardViolation(
                code="REPEATED_QUERY", message="This query is identical to an earlier attempt."
            )
        ]
    elif verdict.ok:
        attempt.guard_status = "accepted"
        attempt.normalized_sql = verdict.normalized_sql
        attempt.guard_violations = []
    else:
        attempt.guard_status = "rejected"
        attempt.guard_violations = verdict.violations
    ctx.summary = {
        "step_id": result.step_id,
        "attempt": attempt.attempt,
        "status": attempt.guard_status,
        "violations": [v.code for v in attempt.guard_violations],
    }
    return put_step(state, result)


# ------------------------------------------------------------------- execution


async def execute_sql(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    result = current_result(state)
    attempt = result.latest()
    if attempt is None or attempt.guard_status != "accepted" or not attempt.normalized_sql:
        raise NoAttemptError("execute_sql only runs Guard-approved SQL")
    if ctx.budget.sql_exec >= ctx.budget.max_sql_exec:
        raise BudgetExhaustedError(f"SQL execution limit ({ctx.budget.max_sql_exec}) reached")
    sql = attempt.normalized_sql
    outcome = await ctx.atool(
        "execute_sql",
        {"step_id": result.step_id, "attempt": attempt.attempt},
        partial(ctx.deps.executor.run, sql),
    )
    ctx.budget.sql_exec += 1
    attempt.exec_ms = outcome.exec_ms
    if outcome.status == "ok":
        attempt.exec_status = "ok"
        attempt.row_count = len(outcome.rows)
        names = [name for name, _ in outcome.columns]
        ctx.deps.results[result.step_id] = ResultTable(result.step_id, names, outcome.rows)
        result.columns = outcome.columns
        result.row_count = len(outcome.rows)
        result.truncated = outcome.truncated
        result.preview_rows = outcome.rows[: ctx.deps.preview_rows]
    else:
        attempt.exec_status = outcome.status
        attempt.error_code = outcome.error_code
        attempt.exec_error = outcome.error_message
        # An earlier successful (but flagged) result of this step is kept as a fallback.
    ctx.summary = {
        "step_id": result.step_id,
        "attempt": attempt.attempt,
        "status": attempt.exec_status,
        "rows": attempt.row_count,
        "ms": outcome.exec_ms,
        **({"error_code": outcome.error_code} if outcome.error_code else {}),
    }
    return put_step(state, result)


# ---------------------------------------------------------------- result check


def _repairs(result: StepResult, category: str) -> int:
    return sum(1 for a in result.attempts if a.diagnosis and a.diagnosis.category == category)


async def check_result(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    """Deterministic sanity checks on a successful query (error detection)."""
    result = current_result(state)
    result.needs_repair = None
    rows = result.preview_rows
    empty = result.row_count == 0 or (result.row_count == 1 and all(v is None for v in rows[0]))
    if empty:
        if _repairs(result, "empty_result") == 0:
            result.needs_repair = result_problem(
                "empty_result", "The query returned no data (or only NULLs)."
            )
        else:
            result.notes.append("No matching data, confirmed after a corrective retry.")
    elif result.truncated:
        if _repairs(result, "fan_out") == 0:
            result.needs_repair = result_problem(
                "fan_out",
                f"The query returned more than {ctx.deps.max_rows} rows; "
                "aggregate to the grain in the expected output.",
            )
        else:
            result.notes.append(
                f"Result truncated at {ctx.deps.max_rows} rows; figures use only those rows."
            )
    ctx.summary = {
        "step_id": result.step_id,
        "rows": result.row_count,
        "verdict": result.needs_repair.category if result.needs_repair else "accepted",
    }
    return put_step(state, result)


# ---------------------------------------------------------------- step control


def explain_failure(result: StepResult, purpose: str) -> str:
    attempt = result.latest()
    tries = len(result.attempts)
    reason = result.failure_explanation
    if reason is None and attempt is not None:
        diagnosis = attempt.diagnosis
        if attempt.guard_status == "rejected":
            reason = "; ".join(v.message for v in attempt.guard_violations)
        elif attempt.exec_error:
            reason = attempt.exec_error
        elif diagnosis:
            reason = diagnosis.summary
    reason = reason or "unknown error"
    return (
        f"Couldn’t complete “{purpose}” after {tries} attempt{'s' if tries != 1 else ''}. "
        f"Last problem: {reason}"
    )[:600]


async def finish_step(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    """Close the current step (succeeded/failed), then move to the next runnable step."""
    steps = plan_steps(state)
    idx = state.get("current_step_idx", 0)
    step = steps[idx]
    result = current_result(state)
    attempt = result.latest()
    last_ok = next((a for a in reversed(result.attempts) if a.exec_status == "ok"), None)
    if attempt is not None and attempt.exec_status == "ok":
        result.status = "succeeded"
        if result.needs_repair is not None:
            result.notes.append(f"Accepted with an unresolved check: {result.needs_repair.summary}")
            result.needs_repair = None
    elif last_ok is not None and step.step_id in ctx.deps.results:
        result.status = "succeeded"
        problem = last_ok.diagnosis.summary if last_ok.diagnosis else "a flagged result"
        result.notes.append(
            f"Used the result of attempt {last_ok.attempt} ({problem}); later corrections failed."
        )
    else:
        result.status = "failed"
        result.failure_explanation = explain_failure(result, step.purpose)
        ctx.deps.results.pop(step.step_id, None)
    results = dict(state["step_results"])
    results[step.step_id] = result

    skipped = []
    idx += 1
    while idx < len(steps):
        blocked = [d for d in steps[idx].depends_on if results[d].status != "succeeded"]
        if not blocked:
            break
        skipped_result = results[steps[idx].step_id].model_copy(deep=True)
        skipped_result.status = "skipped"
        skipped_result.notes.append(
            f"Skipped: depends on {', '.join(blocked)}, which did not succeed."
        )
        results[steps[idx].step_id] = skipped_result
        skipped.append(steps[idx].step_id)
        idx += 1

    update: dict[str, Any] = {"step_results": results, "current_step_idx": idx}
    if idx >= len(steps) and not any(r.status == "succeeded" for r in results.values()):
        update["termination_reason"] = "all_steps_failed"
    ctx.summary = {
        "step_id": step.step_id,
        "status": result.status,
        "attempts": len(result.attempts),
        **({"skipped": skipped} if skipped else {}),
    }
    return update
