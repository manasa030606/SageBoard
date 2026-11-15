"""End-to-end runs of the real graph with a scripted model and fake tools."""

from __future__ import annotations

from typing import Any

from app.agent.graph import build_graph, initial_state, run_graph
from app.agent.state import AgentState
from tests.agent.fakes import Harness, budget, items
from tests.agent.scenarios import QUESTION, revenue_harness


async def run(h: Harness, question: str = QUESTION, **kwargs: Any) -> AgentState:
    state = initial_state(
        run_id="t",
        question=question,
        today="2025-10-15",
        budget=kwargs.pop("budget", budget()),
        **kwargs,
    )
    return await run_graph(build_graph(), state, h.deps)


def nodes(state: AgentState) -> list[str]:
    return [e.node for e in state["trace"]]


async def test_revenue_decline_full_workflow() -> None:
    h = revenue_harness()
    final = await run(h)

    assert h.provider.unexpected == [] and h.provider.leftover() == {}
    response = final["response"]
    assert response.status == "answered"
    assert final["termination_reason"] == "completed"

    # planning → three steps, all succeeded; s2 recovered from a Guard rejection
    assert [s.step_id for s in final["plan"].steps] == ["s1", "s2", "s3"]
    s2 = final["step_results"]["s2"]
    assert s2.status == "succeeded"
    assert [a.guard_status for a in s2.attempts] == ["rejected", "accepted"]
    assert s2.attempts[0].guard_violations[0].code == "UNKNOWN_COLUMN"
    assert s2.attempts[0].diagnosis and s2.attempts[0].diagnosis.category == "unknown_column"
    assert s2.attempts[1].origin == "recovery"
    # the recovery prompt carried the real error and where the column lives
    recovery_text = h.provider.calls_for("recover_error")[0].text
    assert "has no column “category”" in recovery_text and "products" in recovery_text

    # analysis: deterministic facts
    facts = {f.fact_id: f for f in final["facts"]}
    assert facts["f3"].kind == "pct_change" and facts["f3"].value == -15.0
    electronics = items(facts["f4"])[0]
    assert electronics["label"] == "Electronics" and electronics["contribution_pct"] == 80.0

    # visualization: valid grouped bar kept; invalid pie (7 slices) → table fallback
    kinds = [(c.chart_type, c.step_id) for c in final["charts"]]
    assert kinds == [("grouped_bar", "s2"), ("table", "s3")]
    assert "slices" in (final["charts"][1].fallback_reason or "")

    # reflection: round 1 rejected the ungrounded 23.4%, round 2 verified everything
    assert nodes(final).count("generate_insights") == 2
    assert nodes(final).count("verify_insights") == 2
    feedback_prompt = h.provider.calls_for("generate_insights")[1].text
    assert "UNGROUNDED_NUMBER 23.4%" in feedback_prompt
    assert [i.verification for i in response.key_findings] == ["verified"] * 3
    assert response.summary_source == "model"
    assert final["verification"].time_period_check == "passed"
    assert final["verification"].metrics_check == "passed"

    # observability: every node recorded with status and duration
    assert nodes(final)[0] == "load_context" and nodes(final)[-1] == "compose_response"
    assert all(e.status == "succeeded" for e in final["trace"]), [
        (e.node, e.status, e.error) for e in final["trace"] if e.status != "succeeded"
    ]
    assert all(e.duration_ms >= 0 for e in final["trace"])
    assert [e.seq for e in final["trace"]] == list(range(1, len(final["trace"]) + 1))
    assert final["budget"].sql_exec == 3
    assert final["budget"].llm_calls == len(h.provider.calls)


# ------------------------------------------------------------- other paths
import asyncio  # noqa: E402

from app.agent.llm.client import LLMError  # noqa: E402
from app.agent.state import NodeEvent  # noqa: E402
from tests.agent import scenarios as sc  # noqa: E402
from tests.agent.fakes import FakeExecutor, ScriptedProvider, db_error, ok  # noqa: E402

ONE_STEP_PLAN = {**sc.PLAN, "steps": [sc.PLAN["steps"][0]], "analysis_tasks": ["pct change"]}


async def test_out_of_scope_stops_after_understanding() -> None:
    provider = ScriptedProvider(
        {
            "understand_query": [
                {
                    **sc.UNDERSTANDING,
                    "status": "out_of_scope",
                    "out_of_scope_reason": "There is no cost or margin data.",
                }
            ]
        }
    )
    final = await run(Harness(provider, FakeExecutor([])), "What is our profit margin?")
    assert nodes(final) == ["load_context", "understand_query", "compose_response"]
    assert final["response"].status == "out_of_scope"
    assert "no cost or margin data" in final["response"].summary


async def test_clarification_question_is_returned_with_options() -> None:
    provider = ScriptedProvider(
        {
            "understand_query": [
                {
                    **sc.UNDERSTANDING,
                    "status": "needs_clarification",
                    "clarification_question": "Best by revenue or by number of orders?",
                    "clarification_options": ["Revenue", "Orders"],
                }
            ]
        }
    )
    final = await run(Harness(provider, FakeExecutor([])), "Who are our best customers?")
    response = final["response"]
    assert response.status == "clarification_needed" and response.clarification_options == [
        "Revenue",
        "Orders",
    ]
    assert final["termination_reason"] == "clarification_needed"


async def test_every_attempt_fails_then_the_run_explains_why() -> None:
    provider = sc.revenue_provider()
    provider.script["plan_analysis"] = [ONE_STEP_PLAN]
    provider.script["generate_sql"] = [{"sql": sc.SQL_S1}]
    provider.script["recover_error"] = [
        {"diagnosis": "d", "sql": sc.SQL_S1 + " AND o.channel = 'web'", "change_summary": "c"},
        {"diagnosis": "d", "sql": sc.SQL_S1 + " AND o.channel = 'mobile'", "change_summary": "c"},
    ]
    for key in (
        "analyze_results",
        "generate_visualization",
        "generate_insights",
        "verify_insights",
        "compose_response",
    ):
        provider.script[key] = []
    executor = FakeExecutor(
        [], default=db_error("42883", "function round(double precision, integer) does not exist")
    )
    h = Harness(provider, executor)
    final = await run(h)
    s1 = final["step_results"]["s1"]
    assert len(s1.attempts) == 3 and s1.status == "failed"
    assert [a.diagnosis.category for a in s1.attempts[:2]] == ["undefined_function"] * 2  # type: ignore[union-attr]
    assert nodes(final).count("recover_error") == 2 and nodes(final).count("execute_sql") == 3
    assert final["termination_reason"] == "all_steps_failed"
    assert final["response"].status == "failed"
    assert (
        "after 3 attempts" in final["response"].summary
        and "round(double precision" in final["response"].summary
    )
    assert "analyze_results" not in nodes(final) and provider.unexpected == []


async def test_one_failed_step_gives_a_partial_answer() -> None:
    provider = sc.revenue_provider()
    provider.script["recover_error"] = [
        {
            "diagnosis": "d",
            "sql": sc.SQL_S2.replace("ORDER BY p.category", "ORDER BY 2"),
            "change_summary": "c",
        },
        {
            "diagnosis": "d",
            "sql": sc.SQL_S2.replace("ORDER BY p.category", "ORDER BY 3"),
            "change_summary": "c",
        },
    ]
    region = {**sc.I3, "evidence": [{"kind": "fact", "fact_id": "f4"}]}
    provider.script["generate_insights"] = [{"insights": [sc.I1, region]}]
    provider.script["verify_insights"] = [sc.judge_all_supported]
    provider.script["generate_visualization"] = [{"charts": []}]
    provider.script["analyze_results"] = [
        {"calls": [sc.ANALYSIS["calls"][0], sc.ANALYSIS["calls"][2]]}
    ]
    provider.script["compose_response"] = [{"summary": "Revenue fell 15% to $85,000."}]
    executor = sc.revenue_executor()
    executor.rules.insert(
        0, ("p.category", db_error("57014", "canceling statement due to statement timeout"))
    )
    final = await run(Harness(provider, executor))
    assert final["step_results"]["s2"].status == "failed"
    s2 = final["step_results"]["s2"]
    assert s2.attempts[0].diagnosis.category == "unknown_column"  # type: ignore[union-attr]
    assert s2.attempts[1].diagnosis.category == "timeout"  # type: ignore[union-attr]
    response = final["response"]
    assert response.status == "partial"
    assert any("Part of the analysis failed" in c for c in response.caveats)
    assert provider.unexpected == []


async def test_insight_still_unsupported_after_two_rounds_is_removed() -> None:
    provider = sc.revenue_provider()
    provider.script["generate_insights"] = [
        {"insights": [sc.I1, sc.I2_BAD]},
        {"insights": [sc.I1, sc.I2_BAD]},
    ]
    provider.script["compose_response"] = [{"summary": "Revenue fell 15% to $85,000."}]
    final = await run(Harness(provider, sc.revenue_executor()))
    response = final["response"]
    assert [i.headline for i in response.key_findings] == [sc.I1["headline"]]
    assert final["verification"].removed[0]["reasons"] == ["UNGROUNDED_NUMBER 23.4%"]
    assert any("1 insight removed" in c for c in response.caveats)
    assert nodes(final).count("verify_insights") == 2


async def test_llm_budget_exhaustion_ends_with_a_coherent_response() -> None:
    h = sc.revenue_harness()
    final = await run(h, budget=budget(max_llm_calls=7))
    assert final["termination_reason"] == "budget_exhausted"
    assert (
        final["response"].status == "failed" and "time or call limit" in final["response"].summary
    )
    assert final["budget"].llm_calls <= 7
    assert nodes(final)[-1] == "compose_response"


async def test_empty_result_triggers_one_targeted_repair() -> None:
    provider = sc.revenue_provider()
    provider.script["plan_analysis"] = [ONE_STEP_PLAN]
    provider.script["generate_sql"] = [{"sql": sc.SQL_S1 + " AND o.status = 'Delivered'"}]
    provider.script["recover_error"] = [
        {
            "diagnosis": "status values are lowercase",
            "sql": sc.SQL_S1,
            "change_summary": "fixed filter",
        }
    ]
    provider.script["analyze_results"] = [{"calls": [sc.ANALYSIS["calls"][0]]}]
    provider.script["generate_visualization"] = [
        {
            "charts": [
                {
                    "chart_type": "kpi",
                    "step_id": "s1",
                    "y": ["revenue_after"],
                    "title": "Sep revenue",
                }
            ]
        }
    ]
    provider.script["generate_insights"] = [{"insights": [sc.I1]}]
    provider.script["verify_insights"] = [sc.judge_all_supported]
    provider.script["compose_response"] = [{"summary": "Revenue fell 15%."}]
    cols = [("revenue_before", "numeric"), ("revenue_after", "numeric")]
    executor = FakeExecutor(
        [("'Delivered'", ok(cols, [[None, None]])), ("revenue_before", ok(cols, sc.S1_ROWS))]
    )
    h = Harness(provider, executor)
    final = await run(h)
    s1 = final["step_results"]["s1"]
    assert [a.diagnosis.category if a.diagnosis else None for a in s1.attempts] == [
        "empty_result",
        None,
    ]
    assert "time_coverage" in provider.calls_for("recover_error")[0].text
    assert final["response"].status == "answered" and provider.unexpected == []


async def test_cancellation_mid_run_stops_cleanly() -> None:
    h = sc.revenue_harness()
    h.deps.cancel_event = asyncio.Event()

    async def cancel_after_plan(event: NodeEvent) -> None:
        if event.node == "plan_analysis":
            h.deps.cancel_event.set()  # type: ignore[union-attr]

    h.deps.on_event = cancel_after_plan
    final = await run(h)
    assert final["termination_reason"] == "cancelled" and final["response"].status == "failed"
    assert h.executor.executed == []
    assert nodes(final)[-1] == "compose_response"


async def test_chart_agent_failure_degrades_to_tables() -> None:
    provider = sc.revenue_provider()
    provider.script["generate_visualization"] = [LLMError("provider down", code="LLM_UNAVAILABLE")]
    final = await run(Harness(provider, sc.revenue_executor()))
    assert {c.chart_type for c in final["charts"]} == {"table"}
    viz = next(e for e in final["trace"] if e.node == "generate_visualization")
    assert viz.status == "degraded" and "LLMError" in (viz.error or "")
    assert final["response"].status == "answered"


async def test_dataset_text_is_always_inside_data_boundaries() -> None:
    h = sc.revenue_harness()
    await run(h)
    for call in h.provider.calls:
        assert "Content inside <data" in call.system
        first = call.messages[0]["content"]
        assert sc.QUESTION not in first.replace(
            f'<data name="question">\n{sc.QUESTION}\n</data>', ""
        )


async def test_quota_exhaustion_mid_run_stops_without_further_model_calls() -> None:
    provider = sc.revenue_provider()
    quota = LLMError(
        "google: the daily quota is used up. Resets at midnight Pacific time.",
        code="LLM_QUOTA_EXCEEDED",
    )
    provider.script["generate_visualization"] = [quota]
    h = Harness(provider, sc.revenue_executor())
    final = await run(h)
    assert final["termination_reason"] == "llm_unavailable"
    assert final["llm_error"] == {"code": "LLM_QUOTA_EXCEEDED", "message": str(quota)}
    viz = next(e for e in final["trace"] if e.node == "generate_visualization")
    assert viz.status == "failed"  # not degraded: a fallback can't fix a used-up quota
    after = nodes(final)[nodes(final).index("generate_visualization") + 1 :]
    assert after == ["compose_response"]
    assert not h.provider.calls_for("generate_insights") and not h.provider.calls_for(
        "compose_response"
    )
    response = final["response"]
    assert response.status == "failed" and "LLM_QUOTA_EXCEEDED" in response.summary
    assert "Nothing was guessed" in response.summary


async def test_quota_exhaustion_after_verification_keeps_verified_findings() -> None:
    provider = sc.revenue_provider()
    provider.script["generate_insights"] = [{"insights": [sc.I1, sc.I3]}]
    provider.script["verify_insights"] = [sc.judge_all_supported]
    provider.script["compose_response"] = []  # never called after a fatal error
    final_provider = provider
    h = Harness(final_provider, sc.revenue_executor())
    # simulate the model becoming unavailable right after verification
    original = h.deps.on_event

    async def quota_after_verify(event: NodeEvent) -> None:
        if event.node == "verify_insights":
            final_provider.script["compose_response"] = [
                LLMError("quota", code="LLM_QUOTA_EXCEEDED")
            ]
        if original:
            await original(event)

    h.deps.on_event = quota_after_verify
    final = await run(h)
    response = final["response"]
    assert response.status == "answered" and response.summary_source == "template"
    assert [i.verification for i in response.key_findings] == ["verified", "verified"]


async def test_insight_step_failure_is_reported_as_such() -> None:
    provider = sc.revenue_provider()
    provider.script["generate_insights"] = [
        LLMError("google: the reply was cut off", code="LLM_TRUNCATED")
    ]
    provider.script["verify_insights"] = []
    provider.script["compose_response"] = []
    final = await run(Harness(provider, sc.revenue_executor()))
    response = final["response"]
    assert response.status == "partial"
    assert "the insight step failed" in response.summary and "cut off" in response.summary
    assert "no insight passed verification" not in response.summary


async def test_column_labels_copied_with_their_type_still_work() -> None:
    """Regression (real Gemini run, 2026-11-15): the model wrote "revenue_before (numeric)"."""
    provider = sc.revenue_provider()
    suffixed = [
        {k: f"{v} (text)" if k.endswith("_column") else v for k, v in call_.items()}
        for call_ in sc.ANALYSIS["calls"]
    ]
    provider.script["analyze_results"] = [{"calls": suffixed}]
    provider.script["generate_visualization"] = [
        {
            "charts": [
                {
                    "chart_type": "grouped_bar",
                    "step_id": "s2",
                    "x": "category (text)",
                    "y": ["revenue_before (numeric)", "revenue_after (numeric)"],
                    "title": "Revenue by category",
                }
            ]
        }
    ]
    cell = {
        "headline": "Electronics had $50,000 in August",
        "detail": "Its largest month.",
        "category": "finding",
        "evidence": [
            {"kind": "cell", "step_id": "s2", "row_index": 0, "column": "revenue_before (numeric)"}
        ],
        "confidence": "high",
    }
    provider.script["generate_insights"] = [{"insights": [sc.I1, cell]}]
    provider.script["verify_insights"] = [sc.judge_all_supported]
    provider.script["compose_response"] = [{"summary": "Revenue fell 15%."}]
    final = await run(Harness(provider, sc.revenue_executor()))
    assert [f.kind for f in final["facts"]][2:] == ["pct_change", "group_change", "group_change"]
    assert final["charts"][0].chart_type == "grouped_bar" and final["charts"][0].y == [
        "revenue_before",
        "revenue_after",
    ]
    assert [i.verification for i in final["response"].key_findings] == ["verified", "verified"]
    # the model now sees names and types as separate fields
    analysis_prompt = provider.calls_for("analyze_results")[0].text
    assert '{"name": "revenue_before", "type": "numeric"}' in analysis_prompt


async def test_unsafe_sql_is_never_retried() -> None:
    """Phase 6 policy: recovery is for honest mistakes. A write attempt fails the step
    immediately — no model call, no second attempt, nothing sent to the database."""
    provider = sc.revenue_provider()
    provider.script["plan_analysis"] = [{**sc.PLAN, "steps": [sc.PLAN["steps"][0]]}]
    provider.script["generate_sql"] = [{"sql": "DELETE FROM orders WHERE status = 'cancelled'"}]
    for key in (
        "recover_error",
        "analyze_results",
        "generate_visualization",
        "generate_insights",
        "verify_insights",
        "compose_response",
    ):
        provider.script[key] = []
    h = Harness(provider, sc.revenue_executor())
    final = await run(h)
    s1 = final["step_results"]["s1"]
    assert len(s1.attempts) == 1  # exactly one attempt: no retry
    assert s1.attempts[0].guard_status == "rejected"
    assert s1.attempts[0].diagnosis and s1.attempts[0].diagnosis.category == "unsafe_query"
    assert not s1.attempts[0].diagnosis.recoverable
    assert "not attempted" in (s1.failure_explanation or "")
    assert h.executor.executed == []  # nothing reached the database
    assert h.provider.calls_for("recover_error") == []  # no model call spent on it
    assert final["termination_reason"] == "all_steps_failed"
    assert final["response"].status == "failed"


async def test_follow_up_questions_are_suggested_and_grounded() -> None:
    provider = sc.revenue_provider()
    provider.script["compose_response"] = [
        {
            "summary": "Revenue fell 15% in September, to $85,000.",
            "follow_up_questions": [
                "Which Electronics products drove the decline?",
                "How did revenue by region change over the last six months?",
                "Did the 42% discount campaign affect this?",  # 42% is ungrounded → dropped
            ],
        }
    ]
    final = await run(Harness(provider, sc.revenue_executor()))
    response = final["response"]
    assert response.status == "answered" and response.summary_source == "model"
    assert response.follow_up_questions == [
        "Which Electronics products drove the decline?",
        "How did revenue by region change over the last six months?",
    ]
