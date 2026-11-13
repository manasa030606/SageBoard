"""The synthetic e-commerce generator: determinism, integrity and business rules."""

from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.seed.demo import export_csv
from app.seed.ecommerce import END, SCHEMA, START, checksum, generate

Data = dict[str, list[tuple[Any, ...]]]


@pytest.fixture(scope="module")
def small() -> Data:
    return generate("small")


def column(table: str, name: str) -> int:
    spec = next(s for s in SCHEMA if s.name == table)
    return [c.name for c in spec.columns].index(name)


def test_same_seed_same_data(small: Data) -> None:
    assert checksum(generate("small")) == checksum(small)


def test_different_seed_different_data(small: Data) -> None:
    assert checksum(generate("small", seed=1)) != checksum(small)


def test_unknown_scale_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown scale"):
        generate("huge")


def test_rows_match_the_declared_columns(small: Data) -> None:
    for spec in SCHEMA:
        assert small[spec.name], f"{spec.name} is empty"
        assert {len(r) for r in small[spec.name]} == {len(spec.columns)}


def test_primary_keys_are_unique(small: Data) -> None:
    for spec in SCHEMA:
        idx = [column(spec.name, c) for c in spec.primary_key]
        keys = [tuple(r[i] for i in idx) for r in small[spec.name]]
        assert len(keys) == len(set(keys)), spec.name


def test_every_foreign_key_resolves(small: Data) -> None:
    for spec in SCHEMA:
        for col, ref_table, ref_col in spec.foreign_keys:
            parents = {r[column(ref_table, ref_col)] for r in small[ref_table]}
            children = {r[column(spec.name, col)] for r in small[spec.name]}
            assert children <= parents, f"{spec.name}.{col} → {ref_table}.{ref_col}"


def test_orders_fall_inside_the_simulated_window(small: Data) -> None:
    dates = [r[column("orders", "order_date")].date() for r in small["orders"]]
    assert min(dates) >= START
    assert max(dates) <= END


def test_every_order_has_items_and_valid_amounts(small: Data) -> None:
    with_items = {r[column("order_items", "order_id")] for r in small["order_items"]}
    assert with_items == {r[column("orders", "order_id")] for r in small["orders"]}
    for r in small["order_items"]:
        assert r[column("order_items", "quantity")] >= 1
        assert Decimal(0) <= r[column("order_items", "discount")] < Decimal(1)
    for r in small["products"]:
        assert r[column("products", "unit_price")] >= Decimal("4.99")


def test_payment_statuses_are_from_the_documented_set(small: Data) -> None:
    statuses = Counter(r[column("payments", "status")] for r in small["payments"])
    assert set(statuses) <= {"captured", "failed", "voided", "refunded"}
    assert statuses["captured"] > sum(v for k, v in statuses.items() if k != "captured")


def test_categorical_columns_have_realistic_spread(small: Data) -> None:
    regions = Counter(r[column("customers", "region")] for r in small["customers"])
    categories = Counter(r[column("products", "category")] for r in small["products"])
    assert len(regions) == 6
    assert len(categories) == 6
    assert min(regions.values()) > 0


def test_export_csv_writes_one_file_per_table(tmp_path: Path, small: Data) -> None:
    paths = export_csv(tmp_path, "small")
    assert [p.name for p in paths] == [f"{s.name}.csv" for s in SCHEMA]
    with (tmp_path / "orders.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == [c.name for c in next(s for s in SCHEMA if s.name == "orders").columns]
    assert len(rows) - 1 == len(small["orders"])
