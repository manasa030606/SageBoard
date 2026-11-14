"""Insight Generation agent: evidence-cited insights from facts and result previews."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.nodes.common import plan_steps, step_payload, understanding_payload
from app.agent.prompts import load_prompt, render
from app.agent.runtime import NodeContext
from app.agent.state import AgentState, EvidenceRef, Insight


class InsightIn(BaseModel):
    headline: str = Field(max_length=160)
    detail: str = Field(max_length=800)
    category: Literal["finding", "comparison", "anomaly", "recommendation", "caveat"]
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=8)
    confidence: Literal["high", "medium", "low"]


class InsightDraft(BaseModel):
    insights: list[InsightIn] = Field(min_length=1, max_length=6)


def step_status_notes(state: AgentState) -> list[str]:
    notes = []
    for step in plan_steps(state):
        r = state["step_results"][step.step_id]
        if r.status != "succeeded":
            notes.append(
                f"{step.step_id} ({step.purpose}) {r.status}: {r.failure_explanation or '; '.join(r.notes)}"
            )
        else:
            notes += [f"{step.step_id}: {n}" for n in r.notes]
    return notes


async def generate_insights(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    results = state["step_results"]
    succeeded = [s.step_id for s in plan_steps(state) if results[s.step_id].status == "succeeded"]
    parts: list[str | tuple[str, Any]] = [
        ("question", state["question"]),
        ("understanding", understanding_payload(state)),
        ("plan", state["plan"].model_dump()),
        ("facts", [f.model_dump() for f in state.get("facts", [])]),
        ("results", [step_payload(results[s]) for s in succeeded]),
    ]
    if notes := step_status_notes(state):
        parts.append(("step_notes", notes))
    feedback = state.get("verification_feedback", [])
    if feedback:
        parts.append(("verification_feedback", feedback))
        kept = [
            i.model_dump(include={"headline", "detail", "category", "evidence", "confidence"})
            for i in state.get("insights", [])
            if i.verification == "verified"
        ]
        if kept:
            parts.append(("insights_that_passed", kept))
    draft = await ctx.llm(
        load_prompt("generate_insights"), render(*parts), InsightDraft, temperature=0.2
    )
    insights = [
        Insight(insight_id=f"i{n + 1}", **item.model_dump())
        for n, item in enumerate(draft.insights)
    ]
    ctx.summary = {
        "round": ctx.budget.verify_rounds + 1,
        "insights": [f"{i.insight_id} [{i.category}] {i.headline}" for i in insights],
    }
    return {"insights": insights}


def generate_insights_fallback(
    state: AgentState, exc: Exception, ctx: NodeContext
) -> dict[str, Any]:
    # Keep what already passed verification; never invent text without the model.
    return {"insights": [i for i in state.get("insights", []) if i.verification == "verified"]}
