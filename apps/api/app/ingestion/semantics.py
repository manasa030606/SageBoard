"""Column semantics: sensitivity (privacy) and semantic role (helps the agent later).

Sensitive columns are detected by name and by value shape. They are stored with
counts only (no samples, no min/max) and their values are masked in previews unless
the owner explicitly reveals them. Owners can change the flag per column.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.ingestion.types import ColumnType

_SENSITIVE_NAME = re.compile(
    r"(^|_)(e_?mail|phone|mobile|tel|ssn|aadhaar|pan|passport|national_id|tax_id|iban|account_number|"
    r"card(_number)?|cvv|password|passwd|secret|token|address|street|postcode|zip(_code)?|dob|"
    r"date_of_birth|birth_?date|first_name|last_name|full_name|surname|ip(_address)?)($|_)"
)
_EMAIL_VALUE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_CURRENCY_NAME = re.compile(r"(price|amount|revenue|cost|total|value|fee|spend|sales|paid|refund)")


def is_sensitive(name: str, samples: Sequence[str] = ()) -> bool:
    if _SENSITIVE_NAME.search(name):
        return True
    present = [s for s in samples if s]
    return bool(present) and all(_EMAIL_VALUE.match(s) for s in present)


def semantic_role(
    name: str,
    column_type: ColumnType,
    *,
    is_key: bool,
    distinct_count: int | None = None,
    row_count: int | None = None,
) -> str | None:
    if is_key or name == "id" or name.endswith("_id") or name in {"sku", "code"}:
        return "identifier"
    if column_type in ("date", "timestamptz"):
        return "time"
    if column_type in ("numeric", "integer", "bigint"):
        return "currency" if _CURRENCY_NAME.search(name) and column_type == "numeric" else "measure"
    if column_type in ("text", "boolean"):
        if distinct_count is not None and row_count and distinct_count <= max(50, row_count // 20):
            return "dimension"
        return "dimension" if column_type == "boolean" else None
    return None
