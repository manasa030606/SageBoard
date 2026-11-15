"""Final Response generator.

Always runs, whatever happened before, so the user gets a coherent answer: the direct
answer from **verified** insights only, plus caveats and assumptions; or an honest
explanation (clarification question, out-of-scope reason, failed steps, budget limit).
The model may word the summary, but its numbers are checked against the verified
insights' evidence; if that check fails (or no model is available) a deterministic
summary built from the verified headlines is used instead.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent.llm.client import LLMError
from app.agent.nodes.common import plan_steps
from app.agent.nodes.verification import context_text
from app.agent.prompts import load_prompt, render
from app.agent.runtime import BudgetExhaustedError, NodeContext, stop_reason
from app.agent.state import AgentState, FinalResponse, Insight
from app.agent.tools.grounding import Grounder

MAX_TEMPLATE_HEADLINES = 3


class SummaryDraft(BaseModel):
    summary: str = Field(min_length=1, max_length=1200)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)


def _failures(state: AgentState) -> list[str]:
    out = []
    for step in plan_steps(state):
        r = state.get("step_results", {}).get(step.step_id)
        if r and r.status == "failed" and r.failure_explanation:
            out.append(r.failure_explanation)
    return out


def template_summary(insights: list[Insight]) -> str:
    findings = [i for i in insights if i.category != "caveat"] or insights
    return " ".join(i.headline.rstrip(".") + "." for i in findings[:MAX_TEMPLATE_HEADLINES])


async def compose_response(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    reason = stop_reason(state, ctx.deps) or "completed"
    u = state.get("understanding")
    assumptions = list(u.assumptions) if u else []
    verification = state.get("verification")
    caveats = list(verification.uncertainty) if verification else []
    if verification and verification.removed:
        n = len(verification.removed)
        caveats.append(
            f"{n} insight{'s' if n != 1 else ''} removed because verification could not confirm {'them' if n != 1 else 'it'}."
        )
    failures = _failures(state)
    verified = [i for i in state.get("insights", []) if i.verification == "verified"]
    llm_note = None
    if reason == "llm_unavailable":
        llm_error = state.get("llm_error") or {}
        llm_note = (
            f"The language model became unavailable ({llm_error.get('code', 'LLM_ERROR')}): "
            f"{llm_error.get('message', 'no details')} Nothing was guessed."
        )
        caveats.append(llm_note)

    if reason == "clarification_needed" and u:
        response = FinalResponse(
            status="clarification_needed",
            summary=u.clarification_question or "Could you clarify the question?",
            clarification_question=u.clarification_question,
            clarification_options=u.clarification_options,
            assumptions=assumptions,
        )
    elif reason == "out_of_scope":
        why = (u.out_of_scope_reason if u else None) or "No tables in this dataset can answer it."
        response = FinalResponse(
            status="out_of_scope",
            summary=f"This dataset can’t answer that question. {why}",
            assumptions=assumptions,
        )
    elif reason in {"error", "all_steps_failed", "cancelled"} or (
        reason in {"budget_exhausted", "llm_unavailable"} and not verified
    ):
        lead = {
            "error": "The analysis stopped because a required step failed. Nothing was guessed.",
            "all_steps_failed": "None of the queries for this question could be completed.",
            "cancelled": "The analysis was cancelled.",
            "budget_exhausted": "The analysis hit its time or call limit before producing verified results.",
            "llm_unavailable": llm_note or "The language model became unavailable.",
        }[reason]
        response = FinalResponse(
            status="failed",
            summary=" ".join([lead, *failures[:2]])[:1200],
            caveats=[
                *(c for c in caveats if c != llm_note),
                *[e for e in state.get("errors", []) if reason == "error"],
            ],
            assumptions=assumptions,
        )
    else:
        partial = reason in {"budget_exhausted", "llm_unavailable"} or any(
            r.status != "succeeded" for r in state.get("step_results", {}).values()
        )
        if not verified:
            insight_failure = next(
                (e for e in state.get("errors", []) if e.startswith("generate_insights:")), None
            )
            summary = (
                "The queries ran, but the insight step failed, so the results are shown "
                f"without conclusions. ({insight_failure.split(': ', 1)[1]})"
                if insight_failure and not state.get("insights")
                else "The queries ran, but no insight passed verification. "
                "The results are shown without conclusions."
            )
            response = FinalResponse(
                status="partial",
                summary=summary[:1200],
                caveats=caveats,
                assumptions=assumptions,
            )
        else:
            follow_ups: list[str] = []
            if reason == "llm_unavailable":  # don't call a model that just failed
                summary, source = template_summary(verified), "template"
            else:
                summary, source, follow_ups = await _summarise(state, ctx, verified, caveats)
            response = FinalResponse(
                status="partial" if partial else "answered",
                summary=summary,
                key_findings=verified,
                caveats=caveats,
                assumptions=assumptions,
                follow_up_questions=follow_ups,
                summary_source=source,
            )
    ctx.summary = {
        "status": response.status,
        "reason": reason,
        "summary_source": response.summary_source,
    }
    return {"response": response, "termination_reason": reason}


async def _summarise(
    state: AgentState, ctx: NodeContext, verified: list[Insight], caveats: list[str]
) -> tuple[str, str, list[str]]:
    fallback = template_summary(verified)
    try:
        draft = await ctx.llm(
            load_prompt("compose_response"),
            render(
                ("question", state["question"]),
                (
                    "verified_insights",
                    [i.model_dump(include={"headline", "detail", "category"}) for i in verified],
                ),
                ("caveats", caveats[:4]),
            ),
            SummaryDraft,
            temperature=0.2,
        )
    except (LLMError, BudgetExhaustedError) as exc:
        ctx.degraded_reason = f"summary written from template ({type(exc).__name__})"
        return fallback, "template", []
    grounder = Grounder(state.get("facts", []), state["step_results"], context_text(state))
    allowed = [v for i in verified for v in grounder.allowed_values(i.evidence)]
    # Follow-up suggestions are questions, not claims — but any number they quote must
    # still be grounded; offending suggestions are dropped, not rewritten.
    follow_ups = [
        q.strip()[:140]
        for q in draft.follow_up_questions
        if q.strip() and not grounder.ungrounded_numbers(q, allowed)
    ][:3]
    bad = grounder.ungrounded_numbers(draft.summary, allowed)
    if bad:
        ctx.degraded_reason = f"model summary had ungrounded numbers {bad}; template used"
        return fallback, "template", follow_ups
    return draft.summary, "model", follow_ups
