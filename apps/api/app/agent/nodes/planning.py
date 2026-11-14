"""Planning agent: question → structured analytical tasks.

The model proposes the plan; code normalises it (step ids renumbered s1…sN, only
backward dependencies kept) so routing can rely on its shape.
"""

from __future__ import annotations

from typing import Any

from app.agent.nodes.common import schema_for_prompt, understanding_payload
from app.agent.prompts import load_prompt, render
from app.agent.runtime import NodeContext
from app.agent.state import AgentState, AnalysisPlan, PlanStep, StepResult


class MissingSchemaContextError(RuntimeError):
    pass


def normalize_plan(plan: AnalysisPlan) -> tuple[AnalysisPlan, list[str]]:
    notes: list[str] = []
    mapping = {step.step_id: f"s{i + 1}" for i, step in enumerate(plan.steps)}
    steps: list[PlanStep] = []
    for i, step in enumerate(plan.steps):
        new_id = f"s{i + 1}"
        earlier = {f"s{j + 1}" for j in range(i)}
        deps = []
        for dep in step.depends_on:
            mapped = mapping.get(dep)
            if mapped in earlier:
                deps.append(mapped)
            else:
                notes.append(f"{new_id}: dropped dependency on {dep} (not an earlier step)")
        steps.append(step.model_copy(update={"step_id": new_id, "depends_on": sorted(set(deps))}))
    return plan.model_copy(update={"steps": steps}), notes


async def plan_analysis(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    schema = state.get("schema_context")
    if schema is None or not schema.tables:
        raise MissingSchemaContextError("planning requires schema context (ADR-0007)")
    prompt = load_prompt("plan_analysis")
    parts: list[str | tuple[str, Any]] = [
        ("question", state["question"]),
        ("understanding", understanding_payload(state)),
        ("schema_context", schema_for_prompt(schema)),
    ]
    if state.get("prior_context"):
        parts.append(("prior_context", state["prior_context"]))
    plan = await ctx.llm(prompt, render(*parts), AnalysisPlan)
    plan, notes = normalize_plan(plan)
    ctx.summary = {
        "steps": [f"{s.step_id}: {s.purpose}" for s in plan.steps],
        "analysis_tasks": plan.analysis_tasks,
        **({"normalised": notes} if notes else {}),
    }
    return {
        "plan": plan,
        "current_step_idx": 0,
        "step_results": {s.step_id: StepResult(step_id=s.step_id) for s in plan.steps},
    }
