"""Dataset, schema, preview and connection endpoints. Thin: parse → service → schema."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DatasetServiceDep, SessionDep
from app.db.models import DatabaseConnection
from app.schemas.catalog import SchemaCatalog
from app.schemas.datasets import (
    ColumnOut,
    ColumnPatch,
    ConnectionOut,
    DatasetDetail,
    DatasetPage,
    DatasetSummary,
    FinalizeRequest,
    InferredColumn,
    PreviewColumn,
    PreviewResponse,
    UploadIssue,
    UploadReview,
)
from app.schemas.errors import ErrorResponse
from app.services.schema_catalog import build_catalog

router = APIRouter(tags=["datasets"])
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (404, 409, 413, 415, 422, 503)
}


@router.get("/datasets", response_model=DatasetPage, summary="List your datasets")
async def list_datasets(user: CurrentUser, service: DatasetServiceDep) -> DatasetPage:
    return DatasetPage(items=[DatasetSummary.build(d) for d in await service.list(user)])


@router.post(
    "/datasets/uploads",
    response_model=UploadReview,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
    summary="Upload a CSV for review (nothing is loaded yet)",
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


@router.get(
    "/connections",
    response_model=list[ConnectionOut],
    summary="Your database connections (no secrets)",
)
async def list_connections(user: CurrentUser, session: SessionDep) -> list[ConnectionOut]:
    rows = await session.scalars(
        select(DatabaseConnection)
        .where(DatabaseConnection.owner_id == user.id)
        .order_by(DatabaseConnection.created_at)
    )
    return [ConnectionOut.model_validate(c) for c in rows]
