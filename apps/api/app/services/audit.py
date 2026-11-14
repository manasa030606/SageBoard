"""Security audit trail (app.audit_log). Writes join the caller's transaction."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import AuditLog

log = get_logger("audit")


def record(
    session: AsyncSession,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | str | None = None,
    ip: str | None = None,
    **meta: Any,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            ip=ip,
            meta=meta,
        )
    )
    log.info(
        "audit",
        action=action,
        actor_id=str(actor_id) if actor_id else None,
        target_id=str(target_id) if target_id else None,
    )
