"""Visualization agent: model proposes chart specs; code validates them against the
actual result columns and falls back to a table when a spec doesn't fit."""

from __future__ import annotations

from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from app.agent.nodes.common import (
    plan_steps,
    sensitive_columns,
    step_payload,
    understanding_payload,
)
from app.agent.prompts import load_prompt, render
from app.agent.runtime import NodeContext
from app.agent.state import AgentState, ChartSpec
from app.agent.tools.charts import table_fallback, validate_chart

MAX_CHARTS = 3


class ChartSelection(BaseModel):
    charts: list[ChartSpec] = Field(default_factory=list, max_length=6)


def _succeeded(state: AgentState) -> list[str]:
    return [
        s.step_id
        for s in plan_steps(state)
        if state["step_results"][s.step_id].status == "succeeded"
    ]


async def generate_visualization(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    steps = _succeeded(state)
    results = state["step_results"]
    hidden = sensitive_columns(state)
    selection = await ctx.llm(
        load_prompt("generate_visualization"),
        render(
            ("question", state["question"]),
            ("understanding", understanding_payload(state)),
            ("results", [step_payload(results[s], rows=8, hidden=hidden) for s in steps]),
        ),
        ChartSelection,
    )
    charts: list[ChartSpec] = []
    rejected = []
    for spec in selection.charts[:MAX_CHARTS]:
        errors = await ctx.tool(
            "validate_chart_spec",
            spec.model_dump(exclude_defaults=True),
            partial(validate_chart, spec, results.get(spec.step_id)),
        )
        if not errors:
            charts.append(spec)
        elif spec.step_id in results and results[spec.step_id].status == "succeeded":
            rejected.append(f"{spec.chart_type} on {spec.step_id}: {'; '.join(errors)}")
            charts.append(table_fallback(results[spec.step_id], spec.title, "; ".join(errors)))
        else:
            rejected.append(f"{spec.chart_type} on {spec.step_id}: {'; '.join(errors)}")
    if not charts and steps:
        charts = [
            table_fallback(
                results[steps[0]], plan_steps(state)[0].purpose, "no valid chart proposed"
            )
        ]
    ctx.summary = {
        "charts": [f"{c.chart_type} {c.step_id}: {c.title}" for c in charts],
        **({"rejected_specs": rejected} if rejected else {}),
    }
    return {"charts": charts}


def generate_visualization_fallback(
    state: AgentState, exc: Exception, ctx: NodeContext
) -> dict[str, Any]:
    purposes = {s.step_id: s.purpose for s in plan_steps(state)}
    return {
        "charts": [
            table_fallback(
                state["step_results"][s],
                purposes[s],
                f"chart agent unavailable ({type(exc).__name__})",
            )
            for s in _succeeded(state)[:MAX_CHARTS]
        ]
    }
