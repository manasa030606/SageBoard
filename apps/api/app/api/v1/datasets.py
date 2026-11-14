"""Dataset, upload, metadata, schema and preview endpoints. Thin: parse → service → schema.

Every route takes ``CurrentUser`` and every service query filters by its id, so another
user's dataset is always a 404. State-changing routes are CSRF-checked (router-wide).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DatasetServiceDep, csrf_protect, upload_rate_limit
from app.schemas.catalog import SchemaCatalog
from app.schemas.datasets import (
    ColumnOut,
    ColumnPatch,
    DatasetDetail,
    DatasetPage,
    DatasetPatch,
    DatasetSummary,
    DemoProvisioned,
    FinalizeRequest,
    InferredColumn,
    IngestionJobOut,
    PreviewColumn,
    PreviewResponse,
    TableOut,
    TablePatch,
    UploadIssue,
    UploadReview,
)
from app.schemas.errors import ErrorResponse
from app.services.schema_catalog import build_catalog

router = APIRouter(tags=["datasets"], dependencies=[Depends(csrf_protect)])
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 415, 422, 429, 503)
}


@router.get("/datasets", response_model=DatasetPage, responses=ERRORS, summary="List your datasets")
async def list_datasets(user: CurrentUser, service: DatasetServiceDep) -> DatasetPage:
    return DatasetPage(items=[DatasetSummary.build(d) for d in await service.list(user)])


@router.post(
    "/datasets/uploads",
    response_model=UploadReview,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
    summary="Upload a CSV for review (nothing is loaded yet)",
    dependencies=[Depends(upload_rate_limit())],
)
async def upload_dataset(
    user: CurrentUser,
    service: DatasetServiceDep,
    file: Annotated[UploadFile, File(description="UTF-8 CSV, up to the configured size limit")],
    name: Annotated[str | None, Form(max_length=120)] = None,
    description: Annotated[str | None, Form(max_length=2000)] = None,
) -> UploadReview:
    dataset, _job, analysis = await service.create_upload(
        user, source=file, filename=file.filename, name=name, description=description
    )
    return UploadReview(
        dataset=DatasetSummary.build(dataset),
        row_count=analysis.row_count,
        rejected_count=analysis.rejected_count,
        rejected_samples=analysis.rejected_rows[:20],
        columns=[InferredColumn(**c.as_dict()) for c in analysis.columns],
        issues=[UploadIssue(**i.as_dict()) for i in analysis.issues],
    )


@router.post(
    "/datasets/{dataset_id}/finalize",
    response_model=DatasetDetail,
    responses=ERRORS,
    summary="Confirm column types and load the dataset",
)
async def finalize_dataset(
    dataset_id: uuid.UUID, body: FinalizeRequest, user: CurrentUser, service: DatasetServiceDep
) -> DatasetDetail:
    return DatasetDetail.build(await service.finalize(user, dataset_id, dict(body.column_types)))


@router.get(
    "/datasets/{dataset_id}",
    response_model=DatasetDetail,
    responses=ERRORS,
    summary="Dataset with tables and columns",
)
async def get_dataset(
    dataset_id: uuid.UUID, user: CurrentUser, service: DatasetServiceDep
) -> DatasetDetail:
    return DatasetDetail.build(await service.get(user, dataset_id))


@router.get(
    "/datasets/{dataset_id}/schema",
    response_model=SchemaCatalog,
    responses=ERRORS,
    summary="Schema metadata: tables, columns, types, keys, relationships, samples (privacy-controlled)",
)
async def get_schema(
    dataset_id: uuid.UUID,
    user: CurrentUser,
    service: DatasetServiceDep,
    level: Literal["summary", "full"] = "full",
    include_samples: bool = True,
) -> SchemaCatalog:
    return build_catalog(
        await service.get(user, dataset_id), level=level, include_samples=include_samples
    )


@router.get(
    "/datasets/{dataset_id}/tables/{table_name}/preview",
    response_model=PreviewResponse,
    responses=ERRORS,
    summary="First rows of a table (read-only; sensitive columns masked unless revealed)",
)
async def preview_table(  # noqa: PLR0917 - FastAPI path/query parameters
    dataset_id: uuid.UUID,
    table_name: str,
    user: CurrentUser,
    service: DatasetServiceDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000_000)] = 0,
    reveal_sensitive: bool = False,
) -> PreviewResponse:
    table, result = await service.preview(
        user, dataset_id, table_name, limit=limit, offset=offset, reveal_sensitive=reveal_sensitive
    )
    masked = [] if reveal_sensitive else [c.column_name for c in table.columns if c.is_sensitive]
    return PreviewResponse(
        table=table.table_name,
        columns=[
            PreviewColumn(name=c.column_name, data_type=c.data_type, is_sensitive=c.is_sensitive)
            for c in table.columns
        ],
        rows=result.rows,
        limit=min(limit, service.settings.preview_max_rows),
        offset=offset,
        has_more=result.truncated,
        masked_columns=masked,
        exec_ms=result.exec_ms,
    )


@router.patch(
    "/datasets/{dataset_id}/columns/{column_id}",
    response_model=ColumnOut,
    responses=ERRORS,
    summary="Edit a column's description or sensitivity",
)
async def patch_column(
    dataset_id: uuid.UUID,
    column_id: uuid.UUID,
    body: ColumnPatch,
    user: CurrentUser,
    service: DatasetServiceDep,
) -> ColumnOut:
    column = await service.update_column(
        user, dataset_id, column_id, description=body.description, is_sensitive=body.is_sensitive
    )
    return ColumnOut.build(column)


@router.delete(
    "/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERRORS,
    summary="Delete a dataset and its data",
)
async def delete_dataset(
    dataset_id: uuid.UUID, user: CurrentUser, service: DatasetServiceDep
) -> Response:
    await service.delete(user, dataset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/datasets/demo",
    response_model=DemoProvisioned,
    responses=ERRORS,
    summary="Load the sample e-commerce dataset into your account (idempotent)",
)
async def provision_demo_dataset(
    user: CurrentUser, service: DatasetServiceDep, response: Response, replace: bool = False
) -> DemoProvisioned:
    dataset, created = await service.provision_demo(user, replace=replace)
    if created:
        response.status_code = status.HTTP_201_CREATED
    return DemoProvisioned(dataset=DatasetDetail.build(dataset), created=created)


@router.patch(
    "/datasets/{dataset_id}",
    response_model=DatasetDetail,
    responses=ERRORS,
    summary="Rename or describe a dataset",
)
async def patch_dataset(
    dataset_id: uuid.UUID, body: DatasetPatch, user: CurrentUser, service: DatasetServiceDep
) -> DatasetDetail:
    dataset = await service.update(user, dataset_id, name=body.name, description=body.description)
    return DatasetDetail.build(dataset)


@router.patch(
    "/datasets/{dataset_id}/tables/{table_id}",
    response_model=TableOut,
    responses=ERRORS,
    summary="Describe a table (descriptions help the agent later)",
)
async def patch_table(
    dataset_id: uuid.UUID,
    table_id: uuid.UUID,
    body: TablePatch,
    user: CurrentUser,
    service: DatasetServiceDep,
) -> TableOut:
    table = await service.update_table(user, dataset_id, table_id, description=body.description)
    return TableOut.build(table)


@router.get(
    "/datasets/{dataset_id}/jobs",
    response_model=list[IngestionJobOut],
    responses=ERRORS,
    summary="Ingestion jobs for a dataset (each upload and load attempt)",
)
async def list_jobs(
    dataset_id: uuid.UUID, user: CurrentUser, service: DatasetServiceDep
) -> list[IngestionJobOut]:
    dataset = await service.get(user, dataset_id)
    jobs = sorted(dataset.jobs, key=lambda j: j.created_at, reverse=True)
    return [IngestionJobOut.model_validate(j) for j in jobs]
