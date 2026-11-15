"""Reports: saved snapshots of finished analysis sessions, with Markdown and PDF export."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, ReportServiceDep, csrf_protect
from app.api.pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery
from app.schemas.common import Page
from app.schemas.errors import ErrorResponse
from app.schemas.reports import Fidelity, ReportCreate, ReportDetail, ReportPatch, ReportSummary

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(csrf_protect)])
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)
}


def _detail(report: Any, service: Any) -> ReportDetail:
    detail = ReportDetail.model_validate(report)
    detail.fidelity = Fidelity.model_validate(service.fidelity(report))
    return detail


@router.get(
    "", response_model=Page[ReportSummary], responses=ERRORS, summary="Your reports, newest first"
)
async def list_reports(
    user: CurrentUser,
    service: ReportServiceDep,
    analysis_session_id: Annotated[
        uuid.UUID | None, Query(description="Only reports saved from this analysis")
    ] = None,
    limit: LimitQuery = DEFAULT_LIMIT,
    cursor: CursorQuery = None,
) -> Page[ReportSummary]:
    rows, next_cursor = await service.list(
        user, limit=limit, cursor=cursor, analysis_session_id=analysis_session_id
    )
    return Page(items=[ReportSummary.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post(
    "",
    response_model=ReportDetail,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
    summary="Save a finished analysis session as a report",
)
async def create_report(
    body: ReportCreate, user: CurrentUser, service: ReportServiceDep
) -> ReportDetail:
    report = await service.create(
        user, analysis_session_id=body.analysis_session_id, title=body.title
    )
    return _detail(report, service)


@router.get("/{report_id}", response_model=ReportDetail, responses=ERRORS, summary="One report")
async def get_report(
    report_id: uuid.UUID, user: CurrentUser, service: ReportServiceDep
) -> ReportDetail:
    return _detail(await service.get(user, report_id), service)


@router.patch(
    "/{report_id}", response_model=ReportDetail, responses=ERRORS, summary="Edit title or summary"
)
async def patch_report(
    report_id: uuid.UUID, body: ReportPatch, user: CurrentUser, service: ReportServiceDep
) -> ReportDetail:
    report = await service.update(user, report_id, title=body.title, summary=body.summary)
    return _detail(report, service)


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERRORS,
    summary="Delete a report",
)
async def delete_report(
    report_id: uuid.UUID, user: CurrentUser, service: ReportServiceDep
) -> Response:
    await service.delete(user, report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{report_id}/export.md",
    responses={**ERRORS, 200: {"content": {"text/markdown": {}}, "description": "Markdown file"}},
    summary="Download the report as Markdown",
)
async def export_report(
    report_id: uuid.UUID, user: CurrentUser, service: ReportServiceDep
) -> Response:
    filename, markdown = await service.export_markdown(user, report_id)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/{report_id}/export.pdf",
    responses={**ERRORS, 200: {"content": {"application/pdf": {}}, "description": "PDF file"}},
    summary="Download the report as a PDF",
)
async def export_report_pdf(
    report_id: uuid.UUID, user: CurrentUser, service: ReportServiceDep
) -> Response:
    filename, pdf = await service.export_pdf(user, report_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
