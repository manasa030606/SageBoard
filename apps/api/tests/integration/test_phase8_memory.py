"""Phase 8: conversation memory through the real pipeline and database.

Only the model is scripted. The point of these tests is what the *understanding prompt
contains*: it is where earlier turns are (or are not) shown to the model, so isolation
between users, conversations and datasets is asserted on the text actually sent.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.llm.client import StructuredLLM
from app.core.config import Settings
from app.main import create_app
from tests.agent.fakes import Call, ScriptedProvider
from tests.integration.conftest import sign_up
from tests.integration.test_pipeline_multi_dataset import SALES_CSV, _ask, fill_script

pytestmark = pytest.mark.integration

API = "/api/v1"
FIRST = "Which region brought in the most revenue?"
FOLLOW_UP = "And what about the number of orders?"


def prior_turns(call: Call) -> list[dict[str, Any]]:
    marker = '<data name="prior_context">\n'
    text = call.text
    if marker not in text:
        return []
    body = text.split(marker, 1)[1].split("\n</data>", 1)[0]
    parsed: list[dict[str, Any]] = json.loads(body)
    return parsed


def set_up(client: TestClient, provider: ScriptedProvider, csv: str) -> tuple[str, str]:
    uploaded = client.post(
        f"{API}/datasets/uploads",
        files={"file": ("sales.csv", csv, "text/csv")},
        data={"name": f"Sales {uuid.uuid4().hex[:6]}"},
    )
    assert uploaded.status_code == 201, uploaded.text
    dataset_id = uploaded.json()["dataset"]["id"]
    ready = client.post(f"{API}/datasets/{dataset_id}/finalize", json={"column_types": {}})
    assert ready.status_code == 200, ready.text
    table = ready.json()["tables"][0]["table_name"]
    fill_script(provider, table)
    return dataset_id, table


def test_a_follow_up_sees_the_previous_turn_and_nothing_else(
    pg_settings: Callable[..., Settings],
) -> None:
    provider = ScriptedProvider({})
    with TestClient(create_app(pg_settings(), agent_llm=StructuredLLM(provider))) as client:
        sign_up(client)
        dataset_id, _ = set_up(client, provider, SALES_CSV)
        convo = client.post(f"{API}/conversations", json={"dataset_id": dataset_id}).json()

        first = _ask(client, convo["id"], FIRST)
        second = _ask(client, convo["id"], FOLLOW_UP)
        assert first["status"] == second["status"] == "succeeded"

        calls = provider.calls_for("understand_query")
        assert prior_turns(calls[0]) == []  # nothing to remember on the first question
        carried = prior_turns(calls[1])
        assert [t["question"] for t in carried] == [FIRST]
        assert "North" in json.dumps(carried[0])  # what that turn found, so "it" can be resolved

        # The trace the UI shows records how many earlier turns the model was given.
        trace = client.get(f"{API}/analysis-sessions/{second['id']}/trace").json()
        understand = next(n for n in trace if n["node"] == "understand_query")
        assert understand["summary"]["prior_turns"] == 1
        first_trace = client.get(f"{API}/analysis-sessions/{first['id']}/trace").json()
        assert (
            next(n for n in first_trace if n["node"] == "understand_query")["summary"][
                "prior_turns"
            ]
            == 0
        )


def test_memory_never_crosses_users_conversations_or_datasets(
    pg_settings: Callable[..., Settings],
) -> None:
    other_csv = SALES_CSV.replace("North", "Zulu").replace("West", "Yankee").replace("East", "Xray")
    settings = pg_settings()

    # User A answers a question about regions North/West/East.
    provider_a = ScriptedProvider({})
    with TestClient(create_app(settings, agent_llm=StructuredLLM(provider_a))) as a:
        sign_up(a)
        dataset_a, table_a = set_up(a, provider_a, SALES_CSV)
        convo_a = a.post(f"{API}/conversations", json={"dataset_id": dataset_a}).json()
        assert _ask(a, convo_a["id"], FIRST)["status"] == "succeeded"

        # Same user, *new conversation*, same dataset: a follow-up-looking question has no
        # earlier turn to lean on, so the model is shown none.
        fill_script(provider_a, table_a)
        convo_a2 = a.post(f"{API}/conversations", json={"dataset_id": dataset_a}).json()
        assert _ask(a, convo_a2["id"], FOLLOW_UP)["status"] == "succeeded"
        assert prior_turns(provider_a.calls_for("understand_query")[-1]) == []

    # User B has their own data and the very same question wording.
    provider_b = ScriptedProvider({})
    with TestClient(create_app(settings, agent_llm=StructuredLLM(provider_b))) as b:
        sign_up(b)
        dataset_b, _ = set_up(b, provider_b, other_csv)
        convo_b = b.post(f"{API}/conversations", json={"dataset_id": dataset_b}).json()
        assert _ask(b, convo_b["id"], FIRST)["status"] == "succeeded"
        assert _ask(b, convo_b["id"], FOLLOW_UP)["status"] == "succeeded"

        carried = prior_turns(provider_b.calls_for("understand_query")[1])
        assert [t["question"] for t in carried] == [FIRST]
        everything_b_sent = "\n".join(c.text for c in provider_b.calls)
        assert "Zulu" in everything_b_sent  # B's own results are used
        for leaked in ("North", "West", "East"):  # A's regions never are
            assert leaked not in everything_b_sent, leaked
