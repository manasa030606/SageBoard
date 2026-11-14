"""Conversations, analysis sessions, history, reports and dataset metadata endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.schemas.analysis import ConversationDetail, SessionAccepted, SessionDetail
from app.schemas.common import Page
from app.schemas.history import QueryHistoryItem
from app.schemas.reports import ReportDetail
from tests.integration.conftest import PgUrls, fetch, run, signed_in

pytestmark = pytest.mark.integration
API = "/api/v1"


def demo_dataset(api: TestClient) -> dict[str, Any]:
    items = api.get(f"{API}/datasets").json()["items"]
    found: dict[str, Any] = next(d for d in items if d["name"] == "E-commerce demo")
    return found


def new_conversation(api: TestClient, title: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"dataset_id": demo_dataset(api)["id"]}
    if title:
        body["title"] = title
    response = api.post(f"{API}/conversations", json=body)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


def ask(api: TestClient, conversation_id: str, question: str) -> dict[str, Any]:
    response = api.post(
        f"{API}/conversations/{conversation_id}/sessions", json={"question": question}
    )
    assert response.status_code == 202, response.text
    data: dict[str, Any] = response.json()
    return data


def finish_session(
    pg: PgUrls, session_id: str, *, status: str = "succeeded", sql: str | None = None
) -> None:
    """Test setup only: simulate what the future agent will write for a finished run."""
    sid = uuid.UUID(session_id)
    run(
        fetch(
            pg.app,
            "UPDATE app.analysis_sessions SET status = $2, final_summary = 'Revenue grew 12%.', "
            "finished_at = now() WHERE id = $1",
            sid,
            status,
        )
    )
    if sql:
        run(
            fetch(
                pg.app,
                "INSERT INTO app.query_executions (id, analysis_session_id, owner_id, dataset_id, origin, attempt, "
                "executed_sql, guard_status, guard_violations, exec_status, row_count, truncated, created_at) "
                "SELECT gen_random_uuid(), s.id, s.owner_id, s.dataset_id, 'agent', 1, $2, 'accepted', '[]', "
                "'ok', 4, false, now() FROM app.analysis_sessions s WHERE s.id = $1",
                sid,
                sql,
            )
        )


# --------------------------------------------------------------- conversations
def test_conversation_lifecycle(api: TestClient) -> None:
    convo = ConversationDetail.model_validate(new_conversation(api))
    assert convo.title == "New conversation"
    assert convo.messages == []

    accepted = SessionAccepted.model_validate(
        ask(api, str(convo.id), "  What was revenue by region in 2026?  ")
    )
    assert accepted.agent_available is False
    assert accepted.session.status == "queued"
    assert accepted.session.question == "What was revenue by region in 2026?"
    assert "isn’t connected yet" in accepted.message

    detail = ConversationDetail.model_validate(api.get(f"{API}/conversations/{convo.id}").json())
    assert detail.title == "What was revenue by region in 2026?"  # first question names it
    assert [m.role for m in detail.messages] == ["user"]
    assert detail.messages[0].analysis_session_id == accepted.session.id
    assert [s.id for s in detail.sessions] == [accepted.session.id]

    renamed = api.patch(f"{API}/conversations/{convo.id}", json={"title": "  Regional  revenue "})
    assert renamed.json()["title"] == "Regional revenue"
    assert api.delete(f"{API}/conversations/{convo.id}").status_code == 204
    assert api.get(f"{API}/conversations/{convo.id}").status_code == 404
    assert api.get(f"{API}/analysis-sessions/{accepted.session.id}").status_code == 404  # cascaded


@pytest.mark.parametrize(
    ("question", "code"),
    [("", "VALIDATION_ERROR"), ("   ", "EMPTY_QUESTION"), ("x" * 2001, "VALIDATION_ERROR")],
)
def test_question_validation(api: TestClient, question: str, code: str) -> None:
    convo = new_conversation(api)
    response = api.post(f"{API}/conversations/{convo['id']}/sessions", json={"question": question})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_conversation_needs_an_owned_ready_dataset(pg: PgUrls, api: TestClient) -> None:
    assert (
        api.post(f"{API}/conversations", json={"dataset_id": str(uuid.uuid4())}).status_code == 404
    )
    pending = api.post(
        f"{API}/datasets/uploads",
        files={"file": ("p.csv", b"a,b\n1,2\n", "text/csv")},
        data={"name": "Pending"},
    ).json()["dataset"]
    response = api.post(f"{API}/conversations", json={"dataset_id": pending["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DATASET_NOT_READY"
    assert api.post(f"{API}/conversations", json={"dataset_id": "not-a-uuid"}).status_code == 422
    api.delete(f"{API}/datasets/{pending['id']}")


def test_conversation_list_paginates_by_cursor(api: TestClient) -> None:
    ids = [new_conversation(api, f"C{i}")["id"] for i in range(5)]
    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = Page[dict[str, Any]].model_validate(
            api.get(f"{API}/conversations", params=params).json()
        )
        seen += [c["id"] for c in page.items]
        assert len(page.items) <= 2
        cursor = page.next_cursor
        if not cursor:
            break
    assert seen == list(reversed(ids))  # most recently created first, no duplicates or gaps
    bad = api.get(f"{API}/conversations", params={"cursor": "garbage"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "INVALID_CURSOR"
    assert api.get(f"{API}/conversations", params={"limit": 0}).status_code == 422
    assert api.get(f"{API}/conversations", params={"limit": 101}).status_code == 422


def test_cancel_session(pg: PgUrls, api: TestClient) -> None:
    convo = new_conversation(api)
    session_id = ask(api, convo["id"], "Top products?")["session"]["id"]
    cancelled = SessionDetail.model_validate(
        api.post(f"{API}/analysis-sessions/{session_id}/cancel").json()
    )
    assert cancelled.status == "cancelled"
    assert cancelled.termination_reason == "cancelled_by_user"
    assert cancelled.finished_at is not None
    assert api.post(f"{API}/analysis-sessions/{session_id}/cancel").status_code == 200  # idempotent

    done = ask(api, convo["id"], "Second question")["session"]["id"]
    finish_session(pg, done)
    response = api.post(f"{API}/analysis-sessions/{done}/cancel")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SESSION_NOT_CANCELLABLE"


# --------------------------------------------------------------------- history
def test_query_history_records_previews(api: TestClient) -> None:
    dataset = demo_dataset(api)
    for table in ("orders", "customers", "products"):
        api.get(f"{API}/datasets/{dataset['id']}/tables/{table}/preview", params={"limit": 3})
    page = Page[QueryHistoryItem].model_validate(
        api.get(f"{API}/history/queries", params={"limit": 2}).json()
    )
    assert len(page.items) == 2
    assert page.next_cursor
    first = page.items[0]
    assert first.origin == "preview"
    assert first.dataset_name == "E-commerce demo"
    assert first.executed_sql is not None
    assert '"products"' in first.executed_sql  # newest first
    rest = api.get(f"{API}/history/queries", params={"cursor": page.next_cursor}).json()["items"]
    assert len(rest) == 1
    assert api.get(f"{API}/history/queries", params={"origin": "agent"}).json()["items"] == []
    assert api.get(f"{API}/history/queries", params={"origin": "bogus"}).status_code == 422


def test_session_history_filters_and_search(pg: PgUrls, api: TestClient) -> None:
    convo = new_conversation(api)
    a = ask(api, convo["id"], "Revenue by month")["session"]["id"]
    ask(api, convo["id"], "Refund rate by channel_100%")
    finish_session(pg, a)
    items = api.get(f"{API}/history/sessions").json()["items"]
    assert len(items) == 2
    assert [
        i["id"]
        for i in api.get(f"{API}/history/sessions", params={"status": "succeeded"}).json()["items"]
    ] == [a]
    assert len(api.get(f"{API}/history/sessions", params={"q": "REVENUE"}).json()["items"]) == 1
    # LIKE wildcards in the search are literal, not patterns
    assert len(api.get(f"{API}/history/sessions", params={"q": "_100%"}).json()["items"]) == 1
    assert (
        api.get(f"{API}/history/sessions", params={"q": "month%"}).json()["items"] == []
    )  # % isn't a wildcard
    assert (
        api.get(f"{API}/history/sessions", params={"q": "by_month"}).json()["items"] == []
    )  # nor is _


# --------------------------------------------------------------------- reports
def test_report_lifecycle(pg: PgUrls, api: TestClient) -> None:
    convo = new_conversation(api)
    session_id = ask(api, convo["id"], "How did revenue change in Q3 2026?")["session"]["id"]

    early = api.post(f"{API}/reports", json={"analysis_session_id": session_id})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "SESSION_NOT_FINISHED"

    finish_session(pg, session_id, sql="SELECT region, sum(amount) FROM payments GROUP BY 1")
    created = api.post(f"{API}/reports", json={"analysis_session_id": session_id})
    assert created.status_code == 201
    report = ReportDetail.model_validate(created.json())
    assert report.title == "How did revenue change in Q3 2026?"
    assert report.summary == "Revenue grew 12%."
    assert report.content["dataset"]["name"] == "E-commerce demo"
    assert report.content["queries"][0]["row_count"] == 4

    edited = api.patch(
        f"{API}/reports/{report.id}", json={"title": "Q3 revenue", "summary": "Edited."}
    ).json()
    assert edited["summary_edited_by_user"] is True
    assert api.patch(f"{API}/reports/{report.id}", json={"title": "   "}).status_code == 422

    listed = api.get(f"{API}/reports").json()["items"]
    assert [r["id"] for r in listed] == [str(report.id)]

    export = api.get(f"{API}/reports/{report.id}/export.md")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/markdown")
    assert 'filename="q3-revenue.md"' in export.headers["content-disposition"]
    assert export.text.startswith("# Q3 revenue\n")
    assert "```sql\nSELECT region, sum(amount) FROM payments GROUP BY 1\n```" in export.text

    assert api.delete(f"{API}/reports/{report.id}").status_code == 204
    assert api.get(f"{API}/reports/{report.id}").status_code == 404
    assert (
        api.post(f"{API}/reports", json={"analysis_session_id": str(uuid.uuid4())}).status_code
        == 404
    )


# ------------------------------------------------------------ dataset metadata
def test_dataset_metadata_endpoints(api: TestClient) -> None:
    dataset = demo_dataset(api)
    renamed = api.patch(
        f"{API}/datasets/{dataset['id']}", json={"name": "  Shop  data ", "description": "Mine"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Shop data"
    assert renamed.json()["description"] == "Mine"
    assert (
        api.patch(
            f"{API}/datasets/{dataset['id']}", json={"name": "x", "owner_id": "y"}
        ).status_code
        == 422
    )

    other = api.post(
        f"{API}/datasets/uploads",
        files={"file": ("o.csv", b"a\n1\n", "text/csv")},
        data={"name": "Other"},
    )
    clash = api.patch(f"{API}/datasets/{dataset['id']}", json={"name": "Other"})
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "NAME_TAKEN"
    api.delete(f"{API}/datasets/{other.json()['dataset']['id']}")

    detail = api.get(f"{API}/datasets/{dataset['id']}").json()
    table = next(t for t in detail["tables"] if t["table_name"] == "orders")
    patched = api.patch(
        f"{API}/datasets/{dataset['id']}/tables/{table['id']}",
        json={"description": "One row per order"},
    )
    assert patched.json()["description"] == "One row per order"
    assert (
        api.patch(f"{API}/datasets/{dataset['id']}/tables/{uuid.uuid4()}", json={}).status_code
        == 404
    )

    jobs = api.get(f"{API}/datasets/{dataset['id']}/jobs")
    assert jobs.status_code == 200
    assert jobs.json() == []  # the demo is generated, not uploaded


def test_demo_provisioning_is_idempotent_and_per_user(pg: PgUrls, api: TestClient) -> None:
    again = api.post(f"{API}/datasets/demo")
    assert again.status_code == 200
    assert again.json()["created"] is False
    replaced = api.post(f"{API}/datasets/demo", params={"replace": "true"})
    assert replaced.status_code == 201
    assert replaced.json()["dataset"]["status"] == "ready"
    owners = run(
        fetch(
            pg.app,
            "SELECT count(DISTINCT owner_id) AS n FROM app.datasets WHERE name = 'E-commerce demo'",
        )
    )
    assert owners[0]["n"] >= 1


def test_upload_rate_limit(pg_settings: Callable[..., Settings]) -> None:
    with signed_in(pg_settings(uploads_per_hour=2), with_demo=False) as client:
        codes = [
            client.post(
                f"{API}/datasets/uploads",
                files={"file": ("x.csv", b"a\n1\n", "text/csv")},
                data={"name": f"U{i}"},
            ).status_code
            for i in range(3)
        ]
        assert codes == [201, 201, 429]
        for d in client.get(f"{API}/datasets").json()["items"]:
            client.delete(f"{API}/datasets/{d['id']}")
