"""Turn arbitrary CSV headers into safe, readable PostgreSQL column names."""

from __future__ import annotations

import re
import unicodedata

# A conservative subset of SQL reserved words that would be confusing as column names.
RESERVED = frozenset(
    [
        "all",
        "and",
        "any",
        "array",
        "as",
        "asc",
        "between",
        "both",
        "case",
        "cast",
        "check",
        "collate",
        "column",
        "constraint",
        "create",
        "current_date",
        "current_time",
        "current_timestamp",
        "current_user",
        "default",
        "deferrable",
        "desc",
        "distinct",
        "do",
        "else",
        "end",
        "except",
        "false",
        "fetch",
        "for",
        "foreign",
        "from",
        "grant",
        "group",
        "having",
        "in",
        "initially",
        "intersect",
        "into",
        "is",
        "join",
        "lateral",
        "leading",
        "left",
        "like",
        "limit",
        "localtime",
        "localtimestamp",
        "natural",
        "not",
        "null",
        "offset",
        "on",
        "only",
        "or",
        "order",
        "outer",
        "primary",
        "references",
        "returning",
        "right",
        "select",
        "session_user",
        "some",
        "symmetric",
        "table",
        "then",
        "to",
        "trailing",
        "true",
        "union",
        "unique",
        "user",
        "using",
        "variadic",
        "when",
        "where",
        "window",
        "with",
    ]
)
MAX_LEN = 63


def normalize_identifier(raw: str) -> str:
    """'Order Date (UTC)' → 'order_date_utc'; 'Größe' → 'grosse'; '2024 sales' → 'c_2024_sales'."""
    text = (
        unicodedata.normalize("NFKD", raw.replace("ß", "ss"))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    # Split camelCase / PascalCase: customerName → customer_Name, OrderID → Order_ID.
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    text = re.sub(r"_+", "_", text)
    if not text:
        text = "unnamed"
    if text[0].isdigit():
        text = f"c_{text}"
    if text in RESERVED:
        text = f"{text}_col"
    if text.startswith("_"):  # reserved for internal columns such as _row_id
        text = f"c{text}"
    return text[:MAX_LEN].rstrip("_")
