"""Verification agent (reflection).

Pass 1 — deterministic and authoritative (``Grounder``): every number must match the
cited evidence, evidence ids must exist, no unsupported causal claims, recommendations
must be conditional.

Run-level checks — the time period: when the question names a period, at least one
executed query must reference a date column; metrics and periods are also judged by
the model.

Pass 2 — model judge, advisory and **reject-only**: it can mark an insight as
unsupported (wrong direction, overstated, wrong metric), never rescue one that failed
pass 1.

Rejected insights go back to ``generate_insights`` with reasons (bounded rounds). Those
still rejected after the last round are removed and listed, so the user can see what
verification took out. Uncertainty notes are collected for the final response.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.agent.llm.client import LLMError
from app.agent.nodes.common import plan_steps, step_payload, understanding_payload
from app.agent.prompts import load_prompt, render
from app.agent.runtime import BudgetExhaustedError, NodeContext
from app.agent.state import AgentState, Insight, VerificationReport
from app.agent.tools.grounding import Grounder
from app.agent.tools.schema import TIME_TYPES


class InsightJudgement(BaseModel):
    insight_id: str
    supported: bool
    issue: str | None = None


class JudgeVerdict(BaseModel):
    metrics_match: bool
    metrics_issue: str | None = None
    time_period_match: bool
    time_issue: str | None = None
    insights: list[InsightJudgement] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list, max_length=5)


def context_text(state: AgentState) -> str:
    u = state.get("understanding")
    parts = [state["question"], state.get("clarification_answer") or ""]
    if u:
        parts += [u.restated_question, u.time_range or "", *u.assumptions, *u.filters]
    return "\n".join(parts)


def time_period_check(state: AgentState, ctx: NodeContext) -> str:
    u = state.get("understanding")
    if not u or not u.time_range:
        return "not_applicable"
    tools = ctx.deps.schema
    time_columns = {
        c.name.lower() for t in tools.catalog.tables for c in t.columns if c.data_type in TIME_TYPES
    }
    for query in executed_queries(state):
        try:
            tree = sqlglot.parse_one(query["sql"] or "", read="postgres")
        except SqlglotError:
            continue
        if any(col.name.lower() in time_columns for col in tree.find_all(exp.Column)):
            return "passed"
    return (
        f"issue: no executed query uses a date column, but the question asks about {u.time_range}"
    )


def executed_queries(state: AgentState) -> list[dict[str, Any]]:
    out = []
    for step in plan_steps(state):
        r = state["step_results"][step.step_id]
        attempt = next((a for a in reversed(r.attempts) if a.exec_status == "ok"), None)
        if r.status == "succeeded" and attempt is not None:
            out.append(
                {"step_id": step.step_id, "purpose": step.purpose, "sql": attempt.normalized_sql}
            )
    return out


def uncertainty_notes(state: AgentState) -> list[str]:
    notes = []
    for step in plan_steps(state):
        r = state["step_results"][step.step_id]
        if r.status == "failed":
            notes.append(f"Part of the analysis failed: {r.failure_explanation}")
        elif r.status == "skipped":
            notes.append(f"“{step.purpose}” was skipped because a step it depends on failed.")
        if r.truncated:
            notes.append(
                f"“{step.purpose}” returned more rows than the cap; figures use the first rows only."
            )
        if r.status == "succeeded" and r.row_count == 0:
            notes.append(f"“{step.purpose}” returned no data.")
    u = state.get("understanding")
    if u and u.assumptions:
        notes.append("Assumptions: " + "; ".join(u.assumptions))
    return notes


async def verify_insights(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    grounder = Grounder(state.get("facts", []), state["step_results"], context_text(state))
    insights = [i.model_copy(deep=True) for i in state.get("insights", [])]
    ctx.budget.verify_rounds += 1
    final_round = ctx.budget.verify_rounds >= ctx.budget.max_verify_rounds

    # pass 1: deterministic grounding
    for insight in insights:
        reasons = await ctx.tool(
            "grounding.check",
            {"insight_id": insight.insight_id},
            partial(grounder.check_insight, insight),
        )
        insight.rejection_reasons = reasons
        insight.verification = "rejected" if reasons else "unverified"

    report = VerificationReport(round=ctx.budget.verify_rounds)
    report.time_period_check = time_period_check(state, ctx)

    # pass 2: model judge (reject-only)
    candidates = [i for i in insights if i.verification == "unverified"]
    judge_notes: list[str] = []
    if candidates:
        try:
            verdict = await ctx.llm(
                load_prompt("verify_insights"),
                render(
                    ("question", state["question"]),
                    ("understanding", understanding_payload(state)),
                    ("executed_queries", executed_queries(state)),
                    (
                        "results",
                        [
                            step_payload(state["step_results"][q["step_id"]], rows=10)
                            for q in executed_queries(state)
                        ],
                    ),
                    ("facts", [f.model_dump() for f in state.get("facts", [])]),
                    (
                        "insights",
                        [
                            i.model_dump(
                                include={"insight_id", "headline", "detail", "category", "evidence"}
                            )
                            for i in candidates
                        ],
                    ),
                ),
                JudgeVerdict,
            )
        except (LLMError, BudgetExhaustedError) as exc:
            ctx.degraded_reason = f"consistency judge unavailable ({type(exc).__name__})"
            judge_notes.append(
                "The meaning check was unavailable; numbers were verified by code only."
            )
        else:
            report.metrics_check = (
                "passed"
                if verdict.metrics_match
                else f"issue: {verdict.metrics_issue or 'metric mismatch'}"
            )
            if not verdict.time_period_match and report.time_period_check != "not_applicable":
                report.time_period_check = f"issue: {verdict.time_issue or 'period mismatch'}"
            judged = {j.insight_id: j for j in verdict.insights}
            for insight in candidates:
                j = judged.get(insight.insight_id)
                if j is not None and not j.supported:
                    insight.verification = "rejected"
                    insight.rejection_reasons = [f"UNSUPPORTED_BY_EVIDENCE {j.issue or ''}".strip()]
            judge_notes += verdict.uncertainty_notes
    for insight in insights:
        if insight.verification == "unverified":
            insight.verification = "verified"

    rejected = [i for i in insights if i.verification == "rejected"]
    feedback = [
        f"{i.insight_id} “{i.headline}”: {'; '.join(i.rejection_reasons)}" for i in rejected
    ]
    kept: list[Insight] = insights
    if rejected and final_round:
        report.removed = [
            {"headline": i.headline, "reasons": i.rejection_reasons} for i in rejected
        ]
        kept = [i for i in insights if i.verification == "verified"]
    report.verified_insights = sum(i.verification == "verified" for i in insights)
    report.rejected_insights = len(rejected)
    report.uncertainty = [
        *uncertainty_notes(state),
        *judge_notes,
        *(
            [f"Metric check: {report.metrics_check.removeprefix('issue: ')}"]
            if report.metrics_check.startswith("issue")
            else []
        ),
        *(
            [f"Time period check: {report.time_period_check.removeprefix('issue: ')}"]
            if report.time_period_check.startswith("issue")
            else []
        ),
    ]
    ctx.summary = {
        "round": report.round,
        "verified": report.verified_insights,
        "rejected": [f"{i.insight_id}: {'; '.join(i.rejection_reasons)}" for i in rejected],
        "metrics_check": report.metrics_check,
        "time_period_check": report.time_period_check,
        **({"removed": len(report.removed)} if report.removed else {}),
    }
    return {"insights": kept, "verification": report, "verification_feedback": feedback}
