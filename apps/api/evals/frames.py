"""Independent ground truth: the seeded generator's rows, queried with plain Python.

The expected answer for every evaluation question is computed here, *not* with SQL, so a
mistake in a reference query cannot hide behind the same mistake in the expectation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import cached_property
from typing import Any

from app.seed.ecommerce import SCHEMA, generate

Row = dict[str, Any]


class Frames:
    """The five demo tables as lists of dicts, plus the joined order-line view."""

    def __init__(self, scale: str = "standard", seed: int = 20261113) -> None:
        data = generate(scale, seed)
        self.scale = scale
        self.t: dict[str, list[Row]] = {
            spec.name: [
                dict(zip((c.name for c in spec.columns), r, strict=True)) for r in data[spec.name]
            ]
            for spec in SCHEMA
        }
        self.customers = self.t["customers"]
        self.products = self.t["products"]
        self.orders = self.t["orders"]
        self.items = self.t["order_items"]
        self.payments = self.t["payments"]
        self._order = {o["order_id"]: o for o in self.orders}
        self._product = {p["product_id"]: p for p in self.products}
        self._customer = {c["customer_id"]: c for c in self.customers}

    def order(self, order_id: int) -> Row:
        return self._order[order_id]

    def customer_of(self, order: Row) -> Row:
        return self._customer[order["customer_id"]]

    @cached_property
    def lines(self) -> list[Row]:
        """Order lines of non-cancelled orders, joined to order, product and customer."""
        out = []
        for it in self.items:
            o = self._order[it["order_id"]]
            if o["status"] == "cancelled":
                continue
            p, c = self._product[it["product_id"]], self._customer[o["customer_id"]]
            when: datetime = o["order_date"]
            out.append(
                {
                    "rev": it["quantity"] * it["unit_price"] * (1 - it["discount"]),
                    "month": when.strftime("%Y-%m"),
                    "year": when.year,
                    "quarter": f"{when.year}-Q{(when.month - 1) // 3 + 1}",
                    "half": f"{when.year}-H{1 if when.month <= 6 else 2}",
                    "category": p["category"],
                    "product": p["name"],
                    "region": c["region"],
                    "segment": c["segment"],
                    "channel": o["channel"],
                }
            )
        return out


def total(rows: Iterable[Row], key: str = "rev") -> Decimal:
    return sum((r[key] for r in rows), Decimal(0))


def group_sum(rows: Iterable[Row], by: str, key: str = "rev") -> dict[Any, Decimal]:
    out: dict[Any, Decimal] = defaultdict(Decimal)
    for r in rows:
        out[r[by]] += r[key]
    return dict(out)


def group_count(rows: Iterable[Row], by: str) -> dict[Any, int]:
    out: dict[Any, int] = defaultdict(int)
    for r in rows:
        out[r[by]] += 1
    return dict(out)


def ranked(d: dict[Any, Any], n: int | None = None) -> list[tuple[Any, Any]]:
    """Descending by value, ties broken by key ascending (the reference SQL does the same)."""
    items = sorted(d.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return items[:n] if n else items


def rnd(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


Truth = Callable[[Frames], list[tuple[Any, ...]]]
