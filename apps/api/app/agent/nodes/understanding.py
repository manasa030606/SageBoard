"""Entry nodes: ``load_context`` and the Query Understanding agent."""

from __future__ import annotations

from typing import Any

from app.agent.prompts import load_prompt, render
from app.agent.runtime import NodeContext
from app.agent.state import AgentState, Budget, QueryUnderstanding


async def load_context(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    """Load the light table catalog and start the budget clock (no LLM)."""
    catalog = await ctx.tool("get_table_catalog", {}, ctx.deps.schema.table_catalog)
    existing = state.get("budget") or Budget()
    budget = existing.model_copy(
        update={"deadline_ts": existing.deadline_ts or ctx.deps.clock() + 180}
    )
    ctx.budget = budget
    ctx.summary = {"tables": len(catalog), "prior_turns": len(state.get("prior_context", []))}
    return {
        "table_catalog": catalog,
        "step_results": {},
        "facts": [],
        "charts": [],
        "insights": [],
        "verification_feedback": [],
        "current_step_idx": 0,
        "termination_reason": None,
    }


async def understand_query(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    prompt = load_prompt("understand_query")
    parts: list[str | tuple[str, Any]] = [
        f"Today's date: {state.get('today', 'unknown')}.",
        ("table_catalog", state["table_catalog"]),
    ]
    if state.get("prior_context"):
        parts.append(("prior_context", state["prior_context"]))
    parts.append(("question", state["question"]))
    if state.get("clarification_answer"):
        parts.append(("clarification_answer", state["clarification_answer"]))
    understanding = await ctx.llm(prompt, render(*parts), QueryUnderstanding)

    # Code, not the model, decides whether asking again is allowed.
    if understanding.status == "needs_clarification" and (
        state.get("clarification_answer") or not understanding.clarification_question
    ):
        understanding = understanding.model_copy(
            update={
                "status": "answerable",
                "assumptions": [
                    *understanding.assumptions,
                    "The question was ambiguous; Sageboard used the most likely reading.",
                ],
            }
        )

    update: dict[str, Any] = {"understanding": understanding}
    if understanding.status == "needs_clarification":
        update["termination_reason"] = "clarification_needed"
    elif understanding.status == "out_of_scope":
        update["termination_reason"] = "out_of_scope"
    prior = state.get("prior_context") or []
    ctx.summary = {
        "status": understanding.status,
        "intent": understanding.intent,
        "metrics": understanding.metrics,
        "time_range": understanding.time_range,
        # Which earlier turns the agent was given, and why (empty for a standalone question).
        "prior_turns": len(prior),
        "prior_relevance": [str(p.get("relevance", ""))[:120] for p in prior],
    }
    return update
