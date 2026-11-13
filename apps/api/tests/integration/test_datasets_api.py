"""Dataset endpoints end-to-end: upload → review → finalize → preview → schema → delete."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import uuid7
from app.db.identifiers import new_dataset_identifiers
from app.main import create_app
from app.seed.demo import export_csv
from tests.integration.conftest import PgUrls, fetch, run

pytestmark = pytest.mark.integration
API = "/api/v1"

SALES_CSV = (
    "Order ID,Order Date,Amount,Region,Customer Email\n"
    '1,2026-01-03,"$1,200.50",West,a@example.com\n'
    "2,2026-01-04,99.10,East,b@example.com\n"
    "3,2026-01-05,,West,c@example.com\n"
)


def upload(
    api: TestClient, content: str | bytes, *, name: str | None = None, filename: str = "sales.csv"
) -> Any:
    data = {"name": name or f"Sales {uuid.uuid4().hex[:6]}"}
    return api.post(
        f"{API}/datasets/uploads", files={"file": (filename, content, "text/csv")}, data=data
    )


@pytest.fixture
def uploaded(api: TestClient) -> Iterator[dict[str, Any]]:
    response = upload(api, SALES_CSV)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    yield body
    api.delete(f"{API}/datasets/{body['dataset']['id']}")


@pytest.fixture
def ready(api: TestClient, uploaded: dict[str, Any]) -> dict[str, Any]:
    response = api.post(
        f"{API}/datasets/{uploaded['dataset']['id']}/finalize", json={"column_types": {}}
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def schema_exists(pg: PgUrls, schema: str) -> bool:
    return bool(run(fetch(pg.owner, "SELECT 1 FROM pg_namespace WHERE nspname = $1", schema)))


# ---------------------------------------------------------------------- upload
def test_upload_returns_a_review_without_loading_anything(
    pg: PgUrls, api: TestClient, uploaded: dict[str, Any]
) -> None:
    assert uploaded["dataset"]["status"] == "pending_review"
    assert uploaded["row_count"] == 3
    types = {c["name"]: c["inferred_type"] for c in uploaded["columns"]}
    assert types == {
        "order_id": "integer",
        "order_date": "date",
        "amount": "numeric",
        "region": "text",
        "customer_email": "text",
    }
    rows = run(
        fetch(
            pg.app,
            "SELECT schema_name FROM app.datasets WHERE id = $1",
            uuid.UUID(uploaded["dataset"]["id"]),
        )
    )
    assert not schema_exists(pg, rows[0]["schema_name"])


def test_invalid_csv_is_rejected_with_issues(api: TestClient) -> None:
    response = upload(api, "Amount,amount\n1,2\n")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "CSV_INVALID"
    assert error["details"]["issues"][0]["code"] == "DUPLICATE_COLUMN"


def test_non_csv_is_rejected(api: TestClient) -> None:
    response = upload(api, b"PK\x03\x04", filename="sales.xlsx")
    assert response.status_code == 415
    assert "CSV UTF-8" in response.json()["error"]["message"]


def test_file_size_limit(pg_settings: Callable[..., Settings], seed: Callable[..., Any]) -> None:
    seed()
    with TestClient(create_app(pg_settings(upload_max_bytes=1024))) as client:
        response = upload(client, "a,b\n" + "1,2\n" * 400)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_duplicate_dataset_name_conflicts(api: TestClient, uploaded: dict[str, Any]) -> None:
    response = upload(api, SALES_CSV, name=uploaded["dataset"]["name"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NAME_TAKEN"


# -------------------------------------------------------------------- finalize
def test_finalize_loads_data_and_builds_the_catalog(
    pg: PgUrls, api: TestClient, ready: dict[str, Any]
) -> None:
    assert ready["status"] == "ready"
    assert ready["total_rows"] == 3
    table = ready["tables"][0]
    columns = {c["column_name"]: c for c in table["columns"]}
    assert columns["customer_email"]["is_sensitive"]
    assert columns["amount"]["data_type"] == "numeric"
    assert schema_exists(
        pg,
        run(
            fetch(
                pg.app, "SELECT schema_name FROM app.datasets WHERE id = $1", uuid.UUID(ready["id"])
            )
        )[0]["schema_name"],
    )

    again = api.post(f"{API}/datasets/{ready['id']}/finalize", json={"column_types": {}})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "DATASET_NOT_PENDING"


def test_type_overrides_are_applied(api: TestClient, uploaded: dict[str, Any]) -> None:
    response = api.post(
        f"{API}/datasets/{uploaded['dataset']['id']}/finalize",
        json={"column_types": {"order_id": "bigint", "region": "text"}},
    )
    assert response.status_code == 200, response.text
    columns = {c["column_name"]: c["data_type"] for c in response.json()["tables"][0]["columns"]}
    assert columns["order_id"] == "bigint"


def test_unknown_override_column_or_type_is_rejected(
    api: TestClient, uploaded: dict[str, Any]
) -> None:
    url = f"{API}/datasets/{uploaded['dataset']['id']}/finalize"
    assert api.post(url, json={"column_types": {"nope": "text"}}).status_code == 422
    assert api.post(url, json={"column_types": {"amount": "money"}}).status_code == 422


def test_too_many_values_failing_the_chosen_type_fails_cleanly(pg: PgUrls, api: TestClient) -> None:
    content = (
        "code,label\n"
        + "".join(f"{i},x\n" for i in range(10))
        + "".join(f"A{i},y\n" for i in range(5))
    )
    review = upload(api, content).json()
    assert {c["name"]: c["inferred_type"] for c in review["columns"]}["code"] == "text"
    dataset_id = review["dataset"]["id"]
    response = api.post(
        f"{API}/datasets/{dataset_id}/finalize", json={"column_types": {"code": "integer"}}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INGESTION_FAILED"
    assert "5 of 15 rows" in error["message"]
    detail = api.get(f"{API}/datasets/{dataset_id}").json()
    assert detail["status"] == "failed"
    assert not schema_exists(
        pg,
        run(
            fetch(
                pg.app, "SELECT schema_name FROM app.datasets WHERE id = $1", uuid.UUID(dataset_id)
            )
        )[0]["schema_name"],
    )
    assert api.delete(f"{API}/datasets/{dataset_id}").status_code == 204


def test_demo_tables_round_trip_through_csv_upload(api: TestClient, tmp_path: Path) -> None:
    """The generator's own CSVs are realistic upload input: types, counts and privacy hold."""
    export_csv(tmp_path, "small")
    expected = {
        "customers": {
            "customer_id": "integer",
            "signup_date": "date",
            "marketing_opt_in": "boolean",
        },
        "orders": {"order_date": "timestamptz", "shipping_fee": "numeric"},
    }
    for table, types in expected.items():
        content = (tmp_path / f"{table}.csv").read_bytes()
        review = upload(api, content, filename=f"{table}.csv").json()
        inferred = {c["name"]: c["inferred_type"] for c in review["columns"]}
        assert {k: inferred[k] for k in types} == types, table
        dataset_id = review["dataset"]["id"]
        try:
            done = api.post(
                f"{API}/datasets/{dataset_id}/finalize", json={"column_types": {}}
            ).json()
            assert done["status"] == "ready"
            assert done["total_rows"] == content.count(b"\n") - 1
            sensitive = {
                c["column_name"] for c in done["tables"][0]["columns"] if c["is_sensitive"]
            }
            if table == "customers":
                assert sensitive == {"first_name", "last_name", "email"}
        finally:
            api.delete(f"{API}/datasets/{dataset_id}")


# --------------------------------------------------------------------- preview
def test_preview_masks_sensitive_columns_by_default(api: TestClient, ready: dict[str, Any]) -> None:
    table = ready["tables"][0]["table_name"]
    body = api.get(f"{API}/datasets/{ready['id']}/tables/{table}/preview").json()
    assert body["masked_columns"] == ["customer_email"]
    assert body["rows"][0] == [1, "2026-01-03", 1200.5, "West", "«redacted»"]
    assert body["rows"][2][2] is None
    assert body["has_more"] is False

    revealed = api.get(
        f"{API}/datasets/{ready['id']}/tables/{table}/preview?reveal_sensitive=true"
    ).json()
    assert revealed["rows"][0][4] == "a@example.com"
    assert revealed["masked_columns"] == []


def test_preview_paginates(api: TestClient, ready: dict[str, Any]) -> None:
    table = ready["tables"][0]["table_name"]
    first = api.get(f"{API}/datasets/{ready['id']}/tables/{table}/preview?limit=2").json()
    second = api.get(f"{API}/datasets/{ready['id']}/tables/{table}/preview?limit=2&offset=2").json()
    assert [r[0] for r in first["rows"]] == [1, 2]
    assert first["has_more"] is True
    assert [r[0] for r in second["rows"]] == [3]
    assert second["has_more"] is False


def test_preview_is_recorded_as_a_query_execution(
    pg: PgUrls, api: TestClient, ready: dict[str, Any]
) -> None:
    table = ready["tables"][0]["table_name"]
    api.get(f"{API}/datasets/{ready['id']}/tables/{table}/preview")
    rows = run(
        fetch(
            pg.app,
            "SELECT origin, guard_status, exec_status, row_count FROM app.query_executions WHERE dataset_id = $1",
            uuid.UUID(ready["id"]),
        )
    )
    assert (rows[-1]["origin"], rows[-1]["guard_status"], rows[-1]["exec_status"]) == (
        "preview",
        "not_applicable",
        "ok",
    )


@pytest.mark.parametrize("table", ["nope", 'x"; DROP TABLE orders; --', "pg_catalog.pg_roles"])
def test_preview_only_serves_catalogued_tables(
    api: TestClient, ready: dict[str, Any], table: str
) -> None:
    response = api.get(f"{API}/datasets/{ready['id']}/tables/{table}/preview")
    assert response.status_code == 404


def test_preview_of_a_pending_dataset_is_refused(api: TestClient, uploaded: dict[str, Any]) -> None:
    response = api.get(f"{API}/datasets/{uploaded['dataset']['id']}/tables/sales/preview")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DATASET_NOT_READY"


# ---------------------------------------------------------------------- schema
def test_schema_catalog_of_the_demo_dataset(api: TestClient) -> None:
    demo = next(
        d for d in api.get(f"{API}/datasets").json()["items"] if d["name"] == "E-commerce demo"
    )
    full = api.get(f"{API}/datasets/{demo['id']}/schema").json()
    tables = {t["name"]: t for t in full["tables"]}
    assert set(tables) == {"customers", "products", "orders", "order_items", "payments"}
    assert tables["orders"]["primary_key"] == ["order_id"]
    assert tables["orders"]["foreign_keys"] == [
        {
            "column": "customer_id",
            "references_table": "customers",
            "references_column": "customer_id",
        }
    ]
    columns = {c["name"]: c for c in tables["customers"]["columns"]}
    assert columns["email"]["samples_redacted"] is True
    assert columns["email"]["sample_values"] == []
    assert "Consumer" in columns["segment"]["sample_values"]
    assert len(full["relationships"]) == 4

    summary = api.get(f"{API}/datasets/{demo['id']}/schema?level=summary").json()
    assert summary["level"] == "summary"
    assert {t["name"] for t in summary["tables"]} == set(tables)

    no_samples = api.get(f"{API}/datasets/{demo['id']}/schema?include_samples=false").json()
    for table in no_samples["tables"]:
        assert all(c["sample_values"] == [] for c in table["columns"])


def test_marking_a_column_sensitive_removes_its_samples(
    api: TestClient, ready: dict[str, Any]
) -> None:
    column = next(c for c in ready["tables"][0]["columns"] if c["column_name"] == "region")
    response = api.patch(
        f"{API}/datasets/{ready['id']}/columns/{column['id']}",
        json={"is_sensitive": True, "description": "Sales region"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["description"] == "Sales region"
    schema = api.get(f"{API}/datasets/{ready['id']}/schema").json()
    region = next(c for c in schema["tables"][0]["columns"] if c["name"] == "region")
    assert region["samples_redacted"] is True
    assert region["sample_values"] == []


# ----------------------------------------------------------- ownership & delete
async def _foreign_dataset(pg: PgUrls) -> tuple[uuid.UUID, uuid.UUID]:
    """Another user's (catalog-only) dataset, created directly as the app role."""
    conn = await asyncpg.connect(PgUrls.dsn(pg.app))
    try:
        async with conn.transaction():
            user = await conn.fetchval(
                "INSERT INTO app.users (id, email, full_name) VALUES ($1, $2, 'Other') RETURNING id",
                uuid7(),
                f"other-{uuid.uuid4().hex[:8]}@example.test",
            )
            connection = await conn.fetchval(
                "INSERT INTO app.database_connections (id, owner_id, name, kind) "
                "VALUES ($1, $2, 'w', 'internal_warehouse') RETURNING id",
                uuid7(),
                user,
            )
            schema, role = new_dataset_identifiers()
            dataset = await conn.fetchval(
                "INSERT INTO app.datasets (id, owner_id, connection_id, name, source_type, schema_name, "
                "reader_role, status) VALUES ($1, $2, $3, 'Theirs', 'upload_csv', $4, $5, 'ready') RETURNING id",
                uuid7(),
                user,
                connection,
                schema,
                role,
            )
        return user, dataset
    finally:
        await conn.close()


def test_other_users_datasets_are_invisible(pg: PgUrls, api: TestClient) -> None:
    user, dataset = run(_foreign_dataset(pg))
    try:
        listed = {d["id"] for d in api.get(f"{API}/datasets").json()["items"]}
        assert str(dataset) not in listed
        for response in (
            api.get(f"{API}/datasets/{dataset}"),
            api.get(f"{API}/datasets/{dataset}/schema"),
            api.get(f"{API}/datasets/{dataset}/tables/x/preview"),
            api.delete(f"{API}/datasets/{dataset}"),
        ):
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "NOT_FOUND"
    finally:
        run(fetch(pg.app, "DELETE FROM app.users WHERE id = $1", user))


def test_delete_drops_the_warehouse_schema_and_role(
    pg: PgUrls, api: TestClient, ready: dict[str, Any]
) -> None:
    info = run(
        fetch(
            pg.app,
            "SELECT schema_name, reader_role FROM app.datasets WHERE id = $1",
            uuid.UUID(ready["id"]),
        )
    )[0]
    assert api.delete(f"{API}/datasets/{ready['id']}").status_code == 204
    assert not schema_exists(pg, info["schema_name"])
    assert not run(
        fetch(pg.owner, "SELECT 1 FROM pg_roles WHERE rolname = $1", info["reader_role"])
    )
    assert api.get(f"{API}/datasets/{ready['id']}").status_code == 404


def test_connections_never_expose_secrets(api: TestClient) -> None:
    body = api.get(f"{API}/connections").json()
    assert body[0]["kind"] == "internal_warehouse"
    assert set(body[0]) == {"id", "name", "kind", "status", "created_at"}


def test_readyz_checks_all_three_database_roles(api: TestClient) -> None:
    checks = api.get(f"{API}/readyz").json()["checks"]
    assert {checks[k]["status"] for k in ("database", "ingest_database", "executor_database")} == {
        "ok"
    }
