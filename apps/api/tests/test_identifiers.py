"""Identifier safety: the only strings ever interpolated into SQL are these."""

from __future__ import annotations

import pytest

from app.db.base import uuid7
from app.db.identifiers import (
    UnsafeIdentifierError,
    assert_dataset_schema,
    assert_reader_role,
    new_dataset_identifiers,
    qualified,
    quote_ident,
)
from app.ingestion.identifiers import normalize_identifier


@pytest.mark.parametrize("name", ["orders", "order_items", "_row_id", "c_2024", "a" * 63])
def test_quote_ident_accepts_safe_names(name: str) -> None:
    assert quote_ident(name) == f'"{name}"'


@pytest.mark.parametrize(
    "name",
    [
        "",
        "Orders",  # upper case is normalised before it gets here
        'x"; DROP TABLE users; --',
        "a b",
        "1abc",
        "naïve",
        "a" * 64,
        "orders;",
        "public.orders",
    ],
)
def test_quote_ident_rejects_everything_else(name: str) -> None:
    with pytest.raises(UnsafeIdentifierError):
        quote_ident(name)


def test_qualified_quotes_both_parts() -> None:
    assert qualified("ds_" + "a" * 32, "orders") == f'"ds_{"a" * 32}"."orders"'


def test_dataset_identifiers_are_fresh_and_valid() -> None:
    schema, role = new_dataset_identifiers()
    other, _ = new_dataset_identifiers()
    assert schema != other
    assert assert_dataset_schema(schema) == schema
    assert assert_reader_role(role) == role
    assert role == f"{schema}_r"


@pytest.mark.parametrize("bad", ["public", "app", "ds_xyz", "pg_catalog"])
def test_only_dataset_schemas_pass_the_guard(bad: str) -> None:
    with pytest.raises(UnsafeIdentifierError):
        assert_dataset_schema(bad)
    with pytest.raises(UnsafeIdentifierError):
        assert_reader_role(bad)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Order ID", "order_id"),
        ("  Total Amount ($) ", "total_amount"),
        ("customerName", "customer_name"),
        ("2024 Sales", "c_2024_sales"),
        ("Straße", "strasse"),
        ("Café", "cafe"),
        ("select", "select_col"),
        ("order", "order_col"),
        ("OrderID", "order_id"),
        ("HTTPStatus", "http_status"),
        ("###", "unnamed"),
    ],
)
def test_normalize_identifier(raw: str, expected: str) -> None:
    result = normalize_identifier(raw)
    assert result == expected
    quote_ident(result)  # every normalised name is SQL-safe


def test_normalize_identifier_caps_length() -> None:
    assert len(normalize_identifier("x" * 200)) <= 63


def test_uuid7_is_version_7_and_time_ordered() -> None:
    ids = [uuid7() for _ in range(50)]
    assert all(i.version == 7 for i in ids)
    assert all(i.variant == "specified in RFC 4122" for i in ids)
    timestamps = [i.int >> 80 for i in ids]
    assert timestamps == sorted(timestamps)
