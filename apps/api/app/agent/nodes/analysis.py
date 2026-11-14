"""Result Analysis agent: the model selects calculations; tools compute them."""

from __future__ import annotations

from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from app.agent.nodes.common import plan_steps, step_payload, understanding_payload
from app.agent.prompts import load_prompt, render
from app.agent.runtime import NodeContext
from app.agent.state import AgentState, ComputedFact
from app.agent.tools.analysis import AnalysisCall, AnalysisEngine, AnalysisToolError
from app.agent.tools.charts import NUMERIC_PG_TYPES

MAX_CALLS = 12
BRIEF_ITEMS = 8


class AnalysisSelection(BaseModel):
    calls: list[AnalysisCall] = Field(default_factory=list, max_length=MAX_CALLS)


def _engine(state: AgentState, ctx: NodeContext) -> AnalysisEngine:
    succeeded = {k for k, r in state["step_results"].items() if r.status == "succeeded"}
    return AnalysisEngine({k: v for k, v in ctx.deps.results.items() if k in succeeded})


async def _auto_facts(state: AgentState, ctx: NodeContext, engine: AnalysisEngine) -> None:
    """Single-row results become lookup facts for each numeric column (deterministic)."""
    purposes = {s.step_id: s.purpose for s in plan_steps(state)}
    for step_id in sorted(engine.tables):
        result = state["step_results"][step_id]
        if result.row_count != 1:
            continue
        for column, pg_type in result.columns:
            if (
                pg_type not in NUMERIC_PG_TYPES
                or result.preview_rows[0][[c for c, _ in result.columns].index(column)] is None
            ):
                continue
            call = AnalysisCall(
                tool="lookup",
                step_id=step_id,
                column=column,
                description=f"{purposes.get(step_id, step_id)} — {column}"[:200],
            )
            await ctx.tool(
                "analysis.lookup",
                call.model_dump(exclude_defaults=True),
                partial(engine.run, call),
            )


def _fact_brief(fact: ComputedFact) -> dict[str, Any]:
    value = fact.value
    if isinstance(value, list) and len(value) > BRIEF_ITEMS:
        value = [*value[:BRIEF_ITEMS], {"more": len(value) - BRIEF_ITEMS}]
    return {
        "fact_id": fact.fact_id,
        "kind": fact.kind,
        "description": fact.description,
        "value": value,
    }


async def analyze_results(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    engine = _engine(state, ctx)
    await _auto_facts(state, ctx, engine)
    payloads = [step_payload(state["step_results"][k]) for k in sorted(engine.tables)]
    selection = await ctx.llm(
        load_prompt("analyze_results"),
        render(
            ("question", state["question"]),
            ("understanding", understanding_payload(state)),
            ("analysis_tasks", state["plan"].analysis_tasks),
            ("results", payloads),
            ("existing_facts", [_fact_brief(f) for f in engine.facts]),
        ),
        AnalysisSelection,
    )
    skipped = []
    for call in selection.calls:
        try:
            await ctx.tool(
                f"analysis.{call.tool}",
                call.model_dump(exclude_defaults=True),
                partial(engine.run, call),
            )
        except AnalysisToolError as exc:
            skipped.append(f"{call.tool}: {exc}")
    ctx.summary = {
        "facts": [f"{f.fact_id} {f.kind}: {f.description}" for f in engine.facts],
        **({"skipped_calls": skipped} if skipped else {}),
    }
    if skipped and len(skipped) == len(selection.calls) and selection.calls:
        ctx.degraded_reason = "every selected calculation failed"
    return {"facts": engine.facts}


def analyze_results_fallback(state: AgentState, exc: Exception, ctx: NodeContext) -> dict[str, Any]:
    """Without the model, keep the deterministic single-row facts."""
    engine = _engine(state, ctx)
    purposes = {s.step_id: s.purpose for s in plan_steps(state)}
    for step_id in sorted(engine.tables):
        result = state["step_results"][step_id]
        if result.row_count != 1:
            continue
        for column, pg_type in result.columns:
            if pg_type in NUMERIC_PG_TYPES:
                try:
                    engine.run(
                        AnalysisCall(
                            tool="lookup",
                            step_id=step_id,
                            column=column,
                            description=f"{purposes.get(step_id, step_id)} — {column}"[:200],
                        )
                    )
                except AnalysisToolError:
                    continue
    return {"facts": engine.facts}
