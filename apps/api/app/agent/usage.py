"""Daily model-call accounting (free-tier protection, D50).

Every model call is recorded live in ``agent_node_runs.llm_calls``, so counting them
gives today's usage, including runs still in progress. "Today" starts at midnight
Pacific time, when Google's free-tier daily quotas reset.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentNodeRun

QUOTA_TZ = ZoneInfo("America/Los_Angeles")


def quota_day_start(now: datetime | None = None) -> datetime:
    local = (now or datetime.now(UTC)).astimezone(QUOTA_TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def seconds_until_reset(now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    nxt = quota_day_start(current) + timedelta(days=1)
    return max(1, int((nxt - current.astimezone(QUOTA_TZ)).total_seconds()))


async def model_calls_today(db: AsyncSession, now: datetime | None = None) -> int:
    total = await db.scalar(
        select(func.coalesce(func.sum(func.jsonb_array_length(AgentNodeRun.llm_calls)), 0)).where(
            AgentNodeRun.started_at >= quota_day_start(now)
        )
    )
    return int(total or 0)
