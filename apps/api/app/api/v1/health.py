"""Health endpoints. Thin: delegate everything to HealthService."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import HealthServiceDep
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz(service: HealthServiceDep) -> HealthResponse:
    return service.liveness()


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "A dependency is not ready"}},
)
async def readyz(service: HealthServiceDep, response: Response) -> ReadinessResponse:
    result = await service.readiness()
    if result.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
