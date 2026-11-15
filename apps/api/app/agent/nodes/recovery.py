"""Error Recovery agent.

When an attempt fails (Guard rejection, database error, timeout) or returns an unusable
result (empty, truncated), this node:

1. captures the failure from the attempt;
2. classifies it in code (``classify_attempt``), with a fixed hint per category;
3. gathers the schema relevant to *this* error (tables in the failing SQL, where each
   missing column actually lives, sampled filter values, time coverage);
4. asks the model for a corrected query (structured output);
5. appends it as a new attempt, which the graph sends back to ``validate_sql``;
6. never loops forever: routers allow at most ``max_attempts_per_step`` attempts;
7. when recovery is impossible, leaves an explanation that ``finish_step`` reports.
"""

from __future__ import annotations

from typing import Any

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.agent.nodes.common import (
    current_plan_step,
    current_result,
    put_step,
    schema_for_prompt,
    understanding_payload,
)
from app.agent.nodes.schema import build_context
from app.agent.prompts import load_prompt, render
from app.agent.runtime import NodeContext
from app.agent.state import AgentState, ErrorDiagnosis, SQLAttempt
from app.agent.tools.errors import classify_attempt


class RepairedSQL(BaseModel):
    diagnosis: str = Field(max_length=600)
    sql: str = Field(min_length=1, max_length=20_000)
    change_summary: str = Field(default="", max_length=400)


def diagnose(attempt: SQLAttempt, needs_repair: ErrorDiagnosis | None) -> ErrorDiagnosis:
    if attempt.exec_status == "ok" and needs_repair is not None:
        return needs_repair
    repeated = any(v.code == "REPEATED_QUERY" for v in attempt.guard_violations)
    return classify_attempt(attempt, repeated=repeated)


def tables_in(sql: str) -> list[str]:
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except SqlglotError:
        return []
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    return sorted({t.name for t in tree.find_all(exp.Table) if t.name and t.name not in ctes})


async def recover_error(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    step = current_plan_step(state)
    result = current_result(state)
    failed = result.latest()
    if failed is None:
        raise RuntimeError("recover_error ran without a failed attempt")

    # 1–2. capture and classify
    diagnosis = diagnose(failed, result.needs_repair)
    failed.diagnosis = diagnosis
    result.needs_repair = None
    ctx.summary = {
        "step_id": result.step_id,
        "failed_attempt": failed.attempt,
        "category": diagnosis.category,
        "recoverable": diagnosis.recoverable,
    }
    if not diagnosis.recoverable:
        result.failure_explanation = (
            f"{diagnosis.summary} Automatic correction is not attempted for this kind of error."
        )
        return put_step(state, result)

    # 3. relevant schema and error context
    tools = ctx.deps.schema
    referenced = [t for t in tables_in(failed.sql) if t in tools.table_names]
    relevant = build_context(
        tools, [*state["schema_context"].tables, *referenced], "error context", 0
    )
    error_context: dict[str, Any] = {
        "category": diagnosis.category,
        "summary": diagnosis.summary,
        "hint": diagnosis.hint,
    }
    if diagnosis.category in {"unknown_column", "unknown_table", "ambiguous_column"}:
        error_context["all_tables"] = {
            t: [c.name for c in tools.table(t).columns] for t in tools.table_names
        }
    if diagnosis.category == "empty_result":
        error_context["time_coverage"] = [
            {"table": t["table"], "coverage": t["time_coverage"]}
            for t in state["table_catalog"]
            if t["time_coverage"]
        ]
    history = [
        {
            "attempt": a.attempt,
            "sql": a.sql,
            "problem": (a.diagnosis.summary if a.diagnosis else None)
            or "; ".join(v.message for v in a.guard_violations)
            or a.exec_error,
        }
        for a in result.attempts
    ]

    # 4. regenerate
    repaired = await ctx.llm(
        load_prompt("recover_error"),
        render(
            ("question", state["question"]),
            ("understanding", understanding_payload(state)),
            ("current_step", step.model_dump()),
            ("failed_attempts", history),
            ("error", error_context),
            ("schema_context", schema_for_prompt(relevant)),
        ),
        RepairedSQL,
    )
    # 5. new attempt → validate_sql (revalidation)
    result.attempts.append(
        SQLAttempt(
            attempt=len(result.attempts) + 1,
            sql=repaired.sql,
            explanation=f"{repaired.diagnosis} Change: {repaired.change_summary}".strip(),
            origin="recovery",
        )
    )
    ctx.summary.update(new_attempt=len(result.attempts), diagnosis=repaired.diagnosis[:200])
    return put_step(state, result)


def recover_error_fallback(state: AgentState, exc: Exception, ctx: NodeContext) -> dict[str, Any]:
    result = current_result(state)
    failed = result.latest()
    if failed is not None and failed.diagnosis is None:
        failed.diagnosis = diagnose(failed, result.needs_repair)
    result.needs_repair = None
    result.failure_explanation = (
        f"{failed.diagnosis.summary if failed and failed.diagnosis else 'The query failed.'} "
        f"Automatic recovery was unavailable ({type(exc).__name__})."
    )
    return put_step(state, result)
