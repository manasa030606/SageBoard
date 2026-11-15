"""Conversation memory: what a turn stores and which earlier turns a new question gets back."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agent.memory import (
    CONTEXT_CHARS,
    MAX_RELEVANT,
    SCAN_TURNS,
    build_turn_memory,
    content_tokens,
    followup_reason,
    select_relevant,
)
from app.agent.prompts import load_prompt
from tests.agent import scenarios as sc
from tests.agent.test_nodes import harness, planned_state, run_node


def turn(
    question: str,
    *,
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
    time_range: str | None = None,
    answer: str = "An answer.",
    version: int = 1,
    tables: list[str] | None = None,
) -> dict[str, Any]:
    """A memory record built the same way the runner builds it."""
    return build_turn_memory(
        question=question,
        understanding={
            "restated_question": question,
            "intent": "aggregate",
            "metrics": metrics or [],
            "dimensions": dimensions or [],
            "filters": [],
            "time_range": time_range,
        },
        result={
            "schema_tables": tables or ["orders"],
            "steps": [
                {"step_id": "s1", "purpose": "p", "status": "succeeded", "sql": "SELECT 1"},
                {"step_id": "s2", "purpose": "p", "status": "failed", "sql": "SELECT broken"},
            ],
            "response": {
                "key_findings": [
                    {"headline": "Electronics leads", "category": "finding"},
                    {"headline": "Data is partial", "category": "caveat"},
                ]
            },
        },
        final_summary=answer,
        dataset_version=version,
    )


# ----------------------------------------------------------------------- storing


def test_memory_records_what_the_turn_established_and_nothing_else() -> None:
    m = turn(
        "Total revenue by category in September?",
        metrics=["total revenue"],
        dimensions=["category"],
        time_range="2026-09-01 to 2026-09-30",
        answer="Electronics brought $1,200 in September.",
    )
    assert m["metrics"] == ["total revenue"] and m["dimensions"] == ["category"]
    assert m["time_range"] == "2026-09-01 to 2026-09-30"
    assert m["findings"] == ["Electronics leads"]  # caveats are not findings
    assert [s["step"] for s in m["sql"]] == ["s1"]  # only SQL that actually ran
    assert m["answer"] == "Electronics brought $1,200 in September."
    assert {"revenue", "category", "september"} <= set(m["keywords"])


def test_memory_of_a_session_without_a_result_is_still_valid() -> None:
    m = build_turn_memory(
        question="Hello?", understanding=None, result=None, final_summary=None, dataset_version=3
    )
    assert m["answer"] is None and m["sql"] == [] and m["dataset_version"] == 3


def test_long_text_is_clipped() -> None:
    m = turn("q " * 400, answer="word " * 400)
    assert len(m["question"]) <= 300 and len(m["answer"]) <= 600


def test_content_tokens_fold_plurals_and_drop_stop_words() -> None:
    assert content_tokens("What were the total Regions by month?") == {
        "total",
        "region",
        "month",
    }


# ------------------------------------------------------------ follow-up detection


@pytest.mark.parametrize(
    "question",
    [
        "Compare it with last month",
        "And by region?",
        "What about Canada?",
        "Break that down by category",
        "now the same for 2025 please",
        "by month",  # too short to stand alone
        "Is that higher than the previous period?",
    ],
)
def test_questions_that_point_back_are_detected(question: str) -> None:
    assert followup_reason(question)


@pytest.mark.parametrize(
    "question",
    [
        "What was total revenue by category in September 2026?",
        "Why did revenue decrease last month?",
        "How many customers signed up in each country during 2025?",
    ],
)
def test_standalone_questions_are_not_treated_as_follow_ups(question: str) -> None:
    assert followup_reason(question) is None


# ---------------------------------------------------------------------- retrieval


REVENUE = turn(
    "Total revenue by category in September?", metrics=["revenue"], dimensions=["category"]
)
CUSTOMERS = turn(
    "How many customers signed up per country?", metrics=["customers"], dimensions=["country"]
)
SHIPPING = turn(
    "Average shipping time by carrier?", metrics=["shipping time"], dimensions=["carrier"]
)


def test_a_reference_brings_back_the_previous_turn_only() -> None:
    chosen = select_relevant(
        "Compare it with last month", [REVENUE, CUSTOMERS, SHIPPING], dataset_version=1
    )
    assert [c["question"] for c in chosen] == [SHIPPING["question"]]
    assert "previous turn" in chosen[0]["relevance"]
    assert "keywords" not in chosen[0]  # internal ranking data is not sent to the model


def test_an_unrelated_question_gets_no_prior_context() -> None:
    chosen = select_relevant(
        "What is the refund rate for orders paid by gift card?",
        [REVENUE, CUSTOMERS],
        dataset_version=1,
    )
    assert chosen == []


def test_a_standalone_question_that_revisits_an_old_topic_finds_that_turn() -> None:
    chosen = select_relevant(
        "What was the revenue by category last quarter?",
        [REVENUE, CUSTOMERS, SHIPPING],
        dataset_version=1,
    )
    assert [c["question"] for c in chosen] == [REVENUE["question"]]  # not the latest turn
    assert chosen[0]["relevance"].startswith("shares topic words")
    assert "revenue" in chosen[0]["relevance"]


def test_at_most_three_turns_are_returned_oldest_first() -> None:
    turns = [
        turn(f"Revenue by category question {i}", metrics=["revenue"], dimensions=["category"])
        for i in range(8)
    ]
    chosen = select_relevant(
        "Show the revenue by category and compare it with the previous period",
        turns,
        dataset_version=1,
    )
    assert len(chosen) == MAX_RELEVANT
    assert [c["question"] for c in chosen] == sorted(c["question"] for c in chosen)
    assert chosen[-1]["question"].endswith("7")  # the previous turn is always among them


def test_only_a_bounded_window_of_history_is_considered() -> None:
    old_revenue = turn("Total revenue by category?", metrics=["revenue"], dimensions=["category"])
    filler = [
        turn(f"Shipping time by carrier {i}?", metrics=["shipping"]) for i in range(SCAN_TURNS)
    ]
    chosen = select_relevant(
        "What was the revenue by category last quarter?", [old_revenue, *filler], dataset_version=1
    )
    assert chosen == []  # the matching turn fell outside the window


def test_numbers_of_a_turn_from_another_dataset_version_are_not_carried_over() -> None:
    old = turn(
        "Total revenue by category?", metrics=["revenue"], answer="Revenue was $999.", version=1
    )
    chosen = select_relevant("And by region?", [old], dataset_version=2)
    assert "answer" not in chosen[0] and "findings" not in chosen[0] and "sql" not in chosen[0]
    assert "not carried over" in chosen[0]["stale"]
    assert chosen[0]["metrics"] == ["revenue"]  # the shape survives, so the reference resolves


def test_the_context_block_is_kept_within_budget() -> None:
    big = [
        turn(f"Revenue by category {i}", metrics=["revenue"], answer="x" * 580, tables=["orders"])
        for i in range(3)
    ]
    for t in big:
        t["sql"] = [{"step": "s1", "purpose": "p", "sql": "SELECT " + "y" * 690}] * 2
    chosen = select_relevant(
        "Compare it with revenue by category", big, dataset_version=1, budget=2500
    )
    assert len(json.dumps(chosen)) <= 2500
    assert CONTEXT_CHARS >= 2500


def test_no_history_means_no_context() -> None:
    assert select_relevant("Compare it with last month", [], dataset_version=1) == []


# ------------------------------------------------- what the agent's nodes receive


async def test_understanding_gets_the_structured_referent_and_traces_why() -> None:
    previous = turn(
        "Total revenue by category in September?",
        metrics=["total revenue"],
        dimensions=["category"],
        time_range="2026-09-01 to 2026-09-30",
        answer="Electronics brought $1,200.",
    )
    prior = select_relevant("Compare it with last month", [REVENUE, previous], dataset_version=1)
    h = harness({"understand_query": [sc.UNDERSTANDING]})
    state = planned_state(h, prior_context=prior, question="Compare it with last month")
    update = await run_node("understand_query", state, h.deps)

    sent = h.provider.calls[0].text
    assert '"total revenue"' in sent and "2026-09-01 to 2026-09-30" in sent  # the referent
    assert "Compare it with last month" in sent
    assert "Average shipping" not in sent  # nothing unrelated leaks in
    event = update["trace"][0]
    assert event.summary["prior_turns"] == 1
    assert "previous turn" in event.summary["prior_relevance"][0]


def test_the_understanding_prompt_teaches_reference_resolution() -> None:
    prompt = load_prompt("understand_query")
    assert prompt.version >= "understand_query.v2"
    for rule in ("Compare it with last month", "stand alone", "stale", "needs_clarification"):
        assert rule in prompt.system
