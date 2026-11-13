"""Supported column types, value parsing and type inference.

One parser is used for both *inference* (which type fits every value?) and *loading*
(convert each cell to a Python value for COPY), so the two can never disagree.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

ColumnType = Literal["integer", "bigint", "numeric", "boolean", "date", "timestamptz", "text"]
SUPPORTED_TYPES: tuple[ColumnType, ...] = (
    "integer",
    "bigint",
    "numeric",
    "boolean",
    "date",
    "timestamptz",
    "text",
)

PG_TYPE: dict[ColumnType, str] = {
    "integer": "integer",
    "bigint": "bigint",
    "numeric": "numeric",
    "boolean": "boolean",
    "date": "date",
    "timestamptz": "timestamptz",
    "text": "text",
}

# Values treated as missing (case-insensitive, after trimming).
NULL_TOKENS = frozenset({"", "na", "n/a", "null", "none", "nan", "-", "#n/a"})

INT32_MAX = 2_147_483_647
_INT = re.compile(r"^[+-]?\d+$")
_NUMERIC = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)?(\.\d+)?$")
_CURRENCY = re.compile(r"^[+-]?[$€£₹]\s?")
_DATE = re.compile(r"^(\d{4})[-/](\d{2})[-/](\d{2})$")
_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:?\d{2})?$"
)
_TRUE = frozenset({"true", "t", "yes", "y"})
_FALSE = frozenset({"false", "f", "no", "n"})

MAX_NUMERIC_DIGITS = 38


def is_missing(raw: str) -> bool:
    return raw.strip().lower() in NULL_TOKENS


def parse_value(column_type: ColumnType, raw: str) -> object:  # noqa: PLR0911, PLR0912 - one branch per type
    """Parse one trimmed, non-missing cell. Raises ValueError if it doesn't fit."""
    value = raw.strip()
    match column_type:
        case "text":
            return value
        case "integer" | "bigint":
            if not _INT.match(value):
                raise ValueError("not a whole number")
            number = int(value)
            limit = INT32_MAX if column_type == "integer" else 9_223_372_036_854_775_807
            if abs(number) > limit:
                raise ValueError(f"out of range for {column_type}")
            return number
        case "numeric":
            cleaned = _CURRENCY.sub(lambda m: m.group(0)[0] if m.group(0)[0] in "+-" else "", value)
            if not _NUMERIC.match(cleaned) or cleaned in {"", "+", "-", "."}:
                raise ValueError("not a number")
            try:
                number_d = Decimal(cleaned.replace(",", ""))
            except InvalidOperation as exc:
                raise ValueError("not a number") from exc
            if len(number_d.as_tuple().digits) > MAX_NUMERIC_DIGITS:
                raise ValueError("too many digits")
            return number_d
        case "boolean":
            lowered = value.lower()
            if lowered in _TRUE:
                return True
            if lowered in _FALSE:
                return False
            raise ValueError("not true/false")
        case "date":
            m = _DATE.match(value)
            if not m:
                raise ValueError("not a date (expected YYYY-MM-DD)")
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        case "timestamptz":
            if not _TIMESTAMP.match(value):
                raise ValueError("not a timestamp (expected ISO 8601)")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise ValueError(f"unsupported type {column_type}")  # pragma: no cover - exhaustive match


class TypeInference:
    """Narrows candidate types as values stream past; picks the most specific survivor."""

    ORDER: tuple[ColumnType, ...] = (
        "boolean",
        "integer",
        "bigint",
        "numeric",
        "date",
        "timestamptz",
    )

    def __init__(self) -> None:
        self.candidates: set[ColumnType] = set(self.ORDER)
        self.seen = 0

    def observe(self, raw: str) -> None:
        if not self.candidates:
            return
        self.seen += 1
        for candidate in list(self.candidates):
            try:
                parse_value(candidate, raw)
            except ValueError:
                self.candidates.discard(candidate)

    def result(self) -> ColumnType:
        if self.seen == 0:
            return "text"
        for candidate in self.ORDER:
            if candidate in self.candidates:
                # A whole-number column that fits in int32 is integer; otherwise bigint.
                return candidate
        return "text"
