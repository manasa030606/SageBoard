"""Database connection metadata. Never returns hosts, users or secrets."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ConnectionServiceDep, CurrentUser
from app.schemas.datasets import ConnectionOut
from app.schemas.errors import ErrorResponse

router = APIRouter(tags=["connections"])


@router.get(
    "/connections",
    response_model=list[ConnectionOut],
    responses={401: {"model": ErrorResponse}},
    summary="Your database connections (no secrets)",
)
async def list_connections(user: CurrentUser, service: ConnectionServiceDep) -> list[ConnectionOut]:
    return [ConnectionOut.model_validate(c) for c in await service.list(user)]
