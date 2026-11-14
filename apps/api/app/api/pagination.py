"""Keyset (cursor) pagination: stable under inserts, no OFFSET scans.

A cursor is an opaque, URL-safe token holding the sort key of the last item returned:
``(timestamp, id)``. Clients pass it back unchanged as ``?cursor=``.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import Query

from app.core.errors import ValidationFailedError

DEFAULT_LIMIT = 25
MAX_LIMIT = 100

LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Page size (max 100)")]
CursorQuery = Annotated[
    str | None, Query(max_length=200, description="`next_cursor` from the previous page")
]


def encode_cursor(at: datetime, item_id: uuid.UUID) -> str:
    raw = json.dumps([at.isoformat(), str(item_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        at, item_id = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(at), uuid.UUID(item_id)
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValidationFailedError(
            "That page link is invalid. Start again from the first page.", code="INVALID_CURSOR"
        ) from exc
