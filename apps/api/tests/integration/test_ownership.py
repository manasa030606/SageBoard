"""User-level ownership: one user can never see or change another user's resources.

The route list comes from the OpenAPI document, so a new route with an id in its path
is tested automatically (and the test fails if it has a parameter we can't fill).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import PgUrls, signed_in
from tests.integration.test_workspace_api import ask, finish_session, new_conversation
from tests.test_api_contract import EXPECTED_OPERATIONS

pytestmark = pytest.mark.integration
API = "/api/v1"
BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("PATCH", "/datasets/{dataset_id}"): {"name": "Stolen"},
    ("PATCH", "/datasets/{dataset_id}/tables/{table_id}"): {"description": "x"},
    ("PATCH", "/datasets/{dataset_id}/columns/{column_id}"): {"is_sensitive": False},
    ("POST", "/datasets/{dataset_id}/finalize"): {"column_types": {}},
    ("PATCH", "/conversations/{conversation_id}"): {"title": "x"},
    ("POST", "/conversations/{conversation_id}/sessions"): {"question": "Leak?"},
    ("PATCH", "/reports/{report_id}"): {"title": "x"},
}


def owner_resources(pg: PgUrls, a: TestClient) -> dict[str, str]:
    dataset = next(
        d for d in a.get(f"{API}/datasets").json()["items"] if d["name"] == "E-commerce demo"
    )
    detail = a.get(f"{API}/datasets/{dataset['id']}").json()
    table = next(t for t in detail["tables"] if t["table_name"] == "customers")
    convo = new_conversation(a)
    session_id = ask(a, convo["id"], "Revenue by region?")["session"]["id"]
    finish_session(pg, session_id)
    report = a.post(f"{API}/reports", json={"analysis_session_id": session_id}).json()
    return {
        "dataset_id": dataset["id"],
        "table_id": table["id"],
        "table_name": table["table_name"],
        "column_id": table["columns"][0]["id"],
        "conversation_id": convo["id"],
        "session_id": session_id,
        "report_id": report["id"],
    }


def test_other_users_resources_are_404_on_every_route(
    pg: PgUrls, pg_settings: Callable[..., Settings]
) -> None:
    with signed_in(pg_settings()) as a, signed_in(pg_settings(), with_demo=False) as b:
        ids = owner_resources(pg, a)
        spec = b.app.openapi()  # type: ignore[attr-defined]
        checked = 0
        for path, item in spec["paths"].items():
            params = re.findall(r"{(\w+)}", path)
            if not params:
                continue
            for method in item:
                route = path.removeprefix(API)
                missing = [p for p in params if p not in ids]
                assert not missing, f"don't know how to fill {missing} for {route}"
                url = path.format(**ids)
                response = b.request(
                    method.upper(), url, json=BODIES.get((method.upper(), route), {})
                )
                assert response.status_code == 404, (
                    f"{method.upper()} {route} → {response.status_code}"
                )
                assert response.json()["error"]["code"] == "NOT_FOUND"
                checked += 1
        assert checked == sum(1 for _, path in EXPECTED_OPERATIONS if "{" in path)

        # Lists never include someone else's items …
        for path in (
            "/datasets",
            "/conversations",
            "/history/sessions",
            "/history/queries",
            "/reports",
        ):
            assert b.get(f"{API}{path}").json()["items"] == [], path
        assert b.get(f"{API}/connections").json() == []
        # … filters with someone else's ids return nothing rather than leaking
        assert (
            b.get(f"{API}/conversations", params={"dataset_id": ids["dataset_id"]}).json()["items"]
            == []
        )
        assert (
            b.get(f"{API}/history/queries", params={"dataset_id": ids["dataset_id"]}).json()[
                "items"
            ]
            == []
        )
        # … and B can't start work on A's dataset or report A's session.
        assert (
            b.post(f"{API}/conversations", json={"dataset_id": ids["dataset_id"]}).status_code
            == 404
        )
        assert (
            b.post(f"{API}/reports", json={"analysis_session_id": ids["session_id"]}).status_code
            == 404
        )

        # A's data is untouched by B's attempts.
        assert a.get(f"{API}/datasets/{ids['dataset_id']}").json()["name"] == "E-commerce demo"
        assert a.get(f"{API}/reports/{ids['report_id']}").status_code == 200


def test_each_user_gets_an_isolated_copy_of_the_demo(
    pg: PgUrls, pg_settings: Callable[..., Settings]
) -> None:
    with signed_in(pg_settings()) as a, signed_in(pg_settings()) as b:
        da = a.get(f"{API}/datasets").json()["items"][0]["id"]
        db = b.get(f"{API}/datasets").json()["items"][0]["id"]
        assert da != db
        assert b.get(f"{API}/datasets/{da}").status_code == 404
        assert a.get(f"{API}/datasets/{db}/tables/orders/preview").status_code == 404
