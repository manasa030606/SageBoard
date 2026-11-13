"""Deterministic synthetic e-commerce data (customers, products, orders, order_items, payments).

Same ``seed`` + ``scale`` → byte-identical rows, so tests and the evaluation set can
rely on exact answers. Patterns built in (documented for evaluation questions):

- 24 months, Nov 2024 – Oct 2026, ~1% monthly growth, holiday peaks in Nov/Dec,
  a dip in Jan/Feb.
- Six US regions with different growth; the Midwest softens in Q3 2026.
- Repeat customers (a minority place many orders); popular products (Zipf-like).
- Deeper discounts in Nov/Dec; free shipping above $75.
- ~3% of paid orders have a failed card attempt before succeeding; cancelled orders
  have only a failed or voided attempt; returned orders get a refund row.
- No cost/margin data on purpose (the analyst must say it can't compute margin).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.ingestion.warehouse import ColumnDef

START = date(2024, 11, 1)
END = date(2026, 10, 31)
CENT = Decimal("0.01")

SCALES: dict[str, dict[str, int]] = {
    "small": {"customers": 300, "products": 40, "orders_per_day": 3},
    "standard": {"customers": 3_000, "products": 160, "orders_per_day": 32},
}

SEASON = {
    1: 0.80,
    2: 0.78,
    3: 0.92,
    4: 0.95,
    5: 1.0,
    6: 1.02,
    7: 0.98,
    8: 1.01,
    9: 1.04,
    10: 1.08,
    11: 1.25,
    12: 1.42,
}
REGIONS = {
    "Northeast": (["New York", "Boston", "Philadelphia", "Newark"], ["NY", "MA", "PA", "NJ"], 0.24),
    "Southeast": (["Atlanta", "Miami", "Charlotte", "Nashville"], ["GA", "FL", "NC", "TN"], 0.19),
    "Midwest": (["Chicago", "Detroit", "Columbus", "Minneapolis"], ["IL", "MI", "OH", "MN"], 0.17),
    "Southwest": (["Phoenix", "Dallas", "Houston", "Austin"], ["AZ", "TX", "TX", "TX"], 0.14),
    "West": (["Los Angeles", "San Diego", "Denver", "Las Vegas"], ["CA", "CA", "CO", "NV"], 0.18),
    "Pacific Northwest": (
        ["Seattle", "Portland", "Spokane", "Boise"],
        ["WA", "OR", "WA", "ID"],
        0.08,
    ),
}
FIRST = [
    "Aarav",
    "Ana",
    "Ben",
    "Chloe",
    "Daniel",
    "Diya",
    "Elena",
    "Ethan",
    "Farah",
    "Grace",
    "Hana",
    "Ian",
    "Isha",
    "Jack",
    "Julia",
    "Kai",
    "Leo",
    "Lina",
    "Maya",
    "Mohan",
    "Nina",
    "Noah",
    "Omar",
    "Priya",
    "Quinn",
    "Ravi",
    "Rosa",
    "Sam",
    "Sara",
    "Tara",
    "Theo",
    "Uma",
    "Vikram",
    "Wen",
    "Yara",
    "Zoe",
]
LAST = [
    "Ahmed",
    "Brown",
    "Chen",
    "Das",
    "Evans",
    "Fischer",
    "Garcia",
    "Gupta",
    "Hill",
    "Iyer",
    "Jones",
    "Kim",
    "Khan",
    "Lopez",
    "Martin",
    "Nair",
    "Nguyen",
    "Okafor",
    "Patel",
    "Quinn",
    "Rao",
    "Reyes",
    "Singh",
    "Smith",
    "Taylor",
    "Tran",
    "Walker",
    "Wang",
    "Young",
    "Zhang",
]
CATEGORIES = {
    "Home": (
        ["Linen", "Wool", "Cotton", "Stoneware", "Oak", "Woven"],
        ["Duvet Set", "Throw Blanket", "Dinner Set", "Cushion", "Rug", "Lamp"],
        22,
        220,
    ),
    "Kitchen": (
        ["Cast Iron", "Copper", "Ceramic", "Glass", "Bamboo"],
        ["Dutch Oven", "Pour-Over Kit", "Knife Set", "Mixing Bowls", "Cutting Board"],
        14,
        180,
    ),
    "Outdoor": (
        ["Trail", "Summit", "Insulated", "Packable", "Alpine"],
        ["Daypack", "Bottle", "Rain Jacket", "Camp Chair", "Headlamp"],
        18,
        160,
    ),
    "Apparel": (
        ["Merino", "Organic", "Relaxed", "Classic", "Recycled"],
        ["Crew Sweater", "Tee", "Chinos", "Hoodie", "Socks"],
        12,
        130,
    ),
    "Electronics": (
        ["Wireless", "Smart", "Compact", "Portable", "Studio"],
        ["Speaker", "Desk Lamp", "Charger", "Earbuds", "Keyboard"],
        19,
        240,
    ),
    "Beauty": (
        ["Botanical", "Daily", "Gentle", "Mineral", "Night"],
        ["Face Serum", "Cleanser", "Moisturiser", "Sunscreen", "Lip Balm"],
        9,
        70,
    ),
}
SEGMENTS = [("Consumer", 0.76), ("Small business", 0.19), ("Enterprise", 0.05)]
CHANNELS = [("web", 0.58), ("mobile_app", 0.30), ("marketplace", 0.12)]
METHODS = [
    ("card", 0.62),
    ("paypal", 0.18),
    ("apple_pay", 0.12),
    ("gift_card", 0.05),
    ("bank_transfer", 0.03),
]
REGION_TREND = {
    "Northeast": 1.0,
    "Southeast": 1.25,
    "Midwest": 0.9,
    "Southwest": 1.15,
    "West": 1.05,
    "Pacific Northwest": 1.35,
}


@dataclass(frozen=True)
class TableSpec:
    name: str
    description: str
    columns: list[ColumnDef]
    primary_key: list[str]
    foreign_keys: list[tuple[str, str, str]]  # (column, ref_table, ref_column)
    indexes: list[str]


SCHEMA: list[TableSpec] = [
    TableSpec(
        "customers",
        "One row per customer account.",
        [
            ColumnDef("customer_id", "integer", True),
            ColumnDef("first_name", "text", True),
            ColumnDef("last_name", "text", True),
            ColumnDef("email", "text", True),
            ColumnDef("city", "text", True),
            ColumnDef("state", "text", True),
            ColumnDef("region", "text", True),
            ColumnDef("segment", "text", True),
            ColumnDef("signup_date", "date", True),
            ColumnDef("marketing_opt_in", "boolean", True),
        ],
        ["customer_id"],
        [],
        ["region", "segment"],
    ),
    TableSpec(
        "products",
        "Product catalogue. There is no cost or margin information.",
        [
            ColumnDef("product_id", "integer", True),
            ColumnDef("sku", "text", True),
            ColumnDef("name", "text", True),
            ColumnDef("category", "text", True),
            ColumnDef("unit_price", "numeric", True),
            ColumnDef("is_active", "boolean", True),
            ColumnDef("launched_on", "date", True),
        ],
        ["product_id"],
        [],
        ["category"],
    ),
    TableSpec(
        "orders",
        "One row per order. Revenue excludes cancelled orders.",
        [
            ColumnDef("order_id", "integer", True),
            ColumnDef("customer_id", "integer", True),
            ColumnDef("order_date", "timestamptz", True),
            ColumnDef("status", "text", True),
            ColumnDef("channel", "text", True),
            ColumnDef("shipping_fee", "numeric", True),
        ],
        ["order_id"],
        [("customer_id", "customers", "customer_id")],
        ["customer_id", "order_date", "status"],
    ),
    TableSpec(
        "order_items",
        "Line items. Line revenue = quantity × unit_price × (1 − discount).",
        [
            ColumnDef("order_item_id", "integer", True),
            ColumnDef("order_id", "integer", True),
            ColumnDef("product_id", "integer", True),
            ColumnDef("quantity", "integer", True),
            ColumnDef("unit_price", "numeric", True),
            ColumnDef("discount", "numeric", True),
        ],
        ["order_item_id"],
        [("order_id", "orders", "order_id"), ("product_id", "products", "product_id")],
        ["order_id", "product_id"],
    ),
    TableSpec(
        "payments",
        "Payment attempts and refunds. Successful charges have status 'captured'.",
        [
            ColumnDef("payment_id", "integer", True),
            ColumnDef("order_id", "integer", True),
            ColumnDef("method", "text", True),
            ColumnDef("status", "text", True),
            ColumnDef("amount", "numeric", True),
            ColumnDef("paid_at", "timestamptz", True),
        ],
        ["payment_id"],
        [("order_id", "orders", "order_id")],
        ["order_id", "status"],
    ),
]

COLUMN_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "orders": {
        "status": "delivered, shipped, processing, cancelled or returned.",
        "order_date": "When the order was placed (UTC).",
    },
    "order_items": {"discount": "Fraction between 0 and 0.4 (0.1 = 10% off)."},
    "payments": {
        "status": "captured, failed, voided or refunded. Refund rows repeat the refunded amount."
    },
    "customers": {"segment": "Consumer, Small business or Enterprise."},
}


def _pick(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    return rng.choices([w[0] for w in weighted], weights=[w[1] for w in weighted])[0]


def _money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def generate(  # noqa: PLR0912, PLR0915 - a linear, readable simulation script
    scale: str = "standard", seed: int = 20261113
) -> dict[str, list[tuple[Any, ...]]]:
    if scale not in SCALES:
        raise ValueError(f"Unknown scale {scale!r}; choose one of {', '.join(SCALES)}")
    cfg = SCALES[scale]
    rng = random.Random(seed)

    # -- customers ------------------------------------------------------------
    customers: list[tuple[Any, ...]] = []
    customer_regions: list[str] = []
    region_names = list(REGIONS)
    region_weights = [REGIONS[r][2] for r in region_names]
    for cid in range(1, cfg["customers"] + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        region = rng.choices(region_names, weights=region_weights)[0]
        cities, states, _ = REGIONS[region]
        idx = rng.randrange(len(cities))
        signup = START - timedelta(days=int(rng.expovariate(1 / 500)))
        signup = min(max(signup, date(2019, 1, 1)), END)
        customers.append(
            (
                cid,
                first,
                last,
                f"{first.lower()}.{last.lower()}{cid}@example.com",
                cities[idx],
                states[idx],
                region,
                _pick(rng, SEGMENTS),
                signup,
                rng.random() < 0.41,
            )
        )
        customer_regions.append(region)
    # Repeat-purchase propensity: a minority of customers order often.
    customer_weight = [rng.paretovariate(1.6) for _ in customers]
    by_region: dict[str, list[int]] = {r: [] for r in REGIONS}
    for i, region in enumerate(customer_regions):
        by_region[region].append(i)

    # -- products -------------------------------------------------------------
    products: list[tuple[Any, ...]] = []
    prices: list[Decimal] = []
    names_seen: set[str] = set()
    cat_names = list(CATEGORIES)
    for pid in range(1, cfg["products"] + 1):
        category = cat_names[(pid - 1) % len(cat_names)]
        adjectives, nouns, lo, hi = CATEGORIES[category]
        name = f"{rng.choice(adjectives)} {rng.choice(nouns)}"
        while name in names_seen:
            name = f"{name} {rng.choice(['II', 'Plus', 'Mini', 'Pro', 'Max'])}"
        names_seen.add(name)
        # Retail-style prices ending in .99, skewed towards the cheaper end of the range.
        price = max(
            Decimal(int(lo + (hi - lo) * rng.betavariate(1.6, 3.2))) + Decimal("0.99"),
            Decimal("4.99"),
        )
        prices.append(price)
        products.append(
            (
                pid,
                f"{category[:2].upper()}-{1000 + pid}",
                name,
                category,
                price,
                rng.random() > 0.06,
                START - timedelta(days=rng.randrange(0, 900)),
            )
        )
    popularity = [1 / (rank**0.9) for rank in range(1, len(products) + 1)]
    rng.shuffle(popularity)

    # -- orders, items, payments ---------------------------------------------
    orders: list[tuple[Any, ...]] = []
    items: list[tuple[Any, ...]] = []
    payments: list[tuple[Any, ...]] = []
    order_id = item_id = payment_id = 0
    total_days = (END - START).days + 1
    for day_index in range(total_days):
        day = START + timedelta(days=day_index)
        months_in = (day.year - START.year) * 12 + day.month - START.month
        weekday = 1.08 if day.weekday() in (5, 6) else 0.97
        expected = cfg["orders_per_day"] * SEASON[day.month] * (1 + 0.0105 * months_in) * weekday
        n_orders = max(0, int(rng.gauss(expected, expected**0.5)))
        age_days = (END - day).days
        for _ in range(n_orders):
            # Region mix drifts by region trend; Midwest softens in Q3 2026.
            region_bias = [
                REGIONS[r][2]
                * (REGION_TREND[r] ** (months_in / 24))
                * (0.88 if r == "Midwest" and day >= date(2026, 7, 1) else 1.0)
                for r in region_names
            ]
            region = rng.choices(region_names, weights=region_bias)[0]
            pool = by_region[region] or list(range(len(customers)))
            cust_index = rng.choices(pool, weights=[customer_weight[i] for i in pool])[0]
            order_id += 1
            placed = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(
                seconds=rng.randrange(6 * 3600, 23 * 3600)
            )
            if age_days <= 2:
                status = "processing"
            elif age_days <= 6:
                status = rng.choices(["shipped", "processing"], weights=[0.8, 0.2])[0]
            else:
                status = rng.choices(
                    ["delivered", "cancelled", "returned"], weights=[0.93, 0.03, 0.04]
                )[0]

            holiday = day.month in (11, 12)
            discount_choices = [
                Decimal("0"),
                Decimal("0.05"),
                Decimal("0.10"),
                Decimal("0.15"),
                Decimal("0.20"),
            ]
            discount_weights = (
                [0.55, 0.15, 0.15, 0.10, 0.05] if holiday else [0.75, 0.10, 0.09, 0.04, 0.02]
            )
            subtotal = Decimal("0")
            for _ in range(min(6, 1 + int(rng.expovariate(1 / 1.3)))):
                p_index = rng.choices(range(len(products)), weights=popularity)[0]
                quantity = rng.choices([1, 2, 3, 4], weights=[0.72, 0.19, 0.06, 0.03])[0]
                drift = Decimal(str(round(1 + 0.04 * months_in / 24 + rng.uniform(-0.01, 0.01), 4)))
                unit_price = _money(prices[p_index] * drift)
                discount = rng.choices(discount_choices, weights=discount_weights)[0]
                item_id += 1
                items.append((item_id, order_id, p_index + 1, quantity, unit_price, discount))
                subtotal += unit_price * quantity * (1 - discount)
            shipping = Decimal("0.00") if subtotal >= 75 else Decimal("6.99")
            orders.append(
                (order_id, cust_index + 1, placed, status, _pick(rng, CHANNELS), shipping)
            )

            amount = _money(subtotal + shipping)
            method = _pick(rng, METHODS)
            paid_at = placed + timedelta(minutes=rng.randrange(1, 15))
            if status == "cancelled":
                payment_id += 1
                payments.append(
                    (
                        payment_id,
                        order_id,
                        method,
                        rng.choice(["failed", "voided"]),
                        amount,
                        paid_at,
                    )
                )
                continue
            if method == "card" and rng.random() < 0.05:
                payment_id += 1
                payments.append((payment_id, order_id, method, "failed", amount, paid_at))
                paid_at += timedelta(minutes=rng.randrange(1, 30))
            payment_id += 1
            payments.append((payment_id, order_id, method, "captured", amount, paid_at))
            if status == "returned":
                payment_id += 1
                payments.append(
                    (
                        payment_id,
                        order_id,
                        method,
                        "refunded",
                        amount,
                        paid_at + timedelta(days=rng.randrange(5, 25)),
                    )
                )

    return {
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_items": items,
        "payments": payments,
    }


def checksum(data: dict[str, list[tuple[Any, ...]]]) -> str:
    """Stable fingerprint of generated data (used by determinism tests and the seed log)."""
    digest = hashlib.sha256()
    for table in sorted(data):
        for row in data[table]:
            digest.update(repr(row).encode())
    return digest.hexdigest()
