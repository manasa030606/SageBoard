"""Dataset lifecycle: upload → review → finalize (load) → preview → delete.

Mentor note — why two steps? Type inference can be wrong (a ZIP code column looks
numeric). The upload step only analyses the file and returns suggested types and
issues; nothing reaches the warehouse until the owner confirms (or overrides) them.

Transactions: loading happens inside ONE warehouse transaction (schema, role, table,
COPY, grants). PostgreSQL DDL — including CREATE SCHEMA and CREATE ROLE — is
transactional, so any failure rolls everything back and leaves no orphaned schema.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailedError,
)
from app.core.logging import get_logger
from app.db.engines import Databases
from app.db.identifiers import new_dataset_identifiers, qualified, quote_ident
from app.db.models import (
    Dataset,
    DatasetColumn,
    DatasetTable,
    IngestionJob,
    QueryExecution,
    User,
)
from app.execution.readonly import ReadOnlyResult, run_readonly
from app.ingestion import uploads
from app.ingestion.csv_validation import (
    MAX_REJECTED_RATIO,
    CsvAnalysis,
    CsvRejected,
    Limits,
    analyze_csv,
    open_csv,
)
from app.ingestion.identifiers import normalize_identifier
from app.ingestion.types import SUPPORTED_TYPES, ColumnType, is_missing, parse_value
from app.ingestion.warehouse import (
    ROW_ID,
    ColumnDef,
    copy_rows,
    create_table,
    drop_schema,
    grant_reader,
    provision_schema,
)
from app.seed.demo import provision_demo
from app.services import audit
from app.services.catalog import rebuild_catalog
from app.services.connections import get_or_create_internal_connection

log = get_logger(__name__)

MASK = "«redacted»"
LOAD_BATCH = 5_000


class RowsRejectedError(Exception):
    def __init__(self, rejected: int, total: int, first: dict[str, Any] | None) -> None:
        super().__init__(f"{rejected} of {total} rows could not be converted")
        self.rejected, self.total, self.first = rejected, total, first


def _require(pool: Any, name: str) -> Any:
    if pool is None:
        raise ServiceUnavailableError(
            f"The {name} database connection is not configured.", details={"connection": name}
        )
    return pool


class DatasetService:
    def __init__(self, session: AsyncSession, databases: Databases, settings: Settings) -> None:
        self.session = session
        self.dbs = databases
        self.settings = settings

    # ------------------------------------------------------------------ reads
    async def list(self, owner: User) -> Sequence[Dataset]:
        result = await self.session.scalars(
            select(Dataset)
            .where(Dataset.owner_id == owner.id)
            .options(selectinload(Dataset.tables))
            .order_by(Dataset.created_at.desc())
        )
        return result.all()

    async def get(self, owner: User, dataset_id: uuid.UUID) -> Dataset:
        dataset = await self.session.scalar(
            select(Dataset)
            .where(Dataset.id == dataset_id, Dataset.owner_id == owner.id)
            .options(
                selectinload(Dataset.tables).selectinload(DatasetTable.columns),
                selectinload(Dataset.relationships),
                selectinload(Dataset.jobs),
            )
            .execution_options(populate_existing=True)
        )
        if dataset is None:  # also covers other users' datasets: never reveal existence
            raise NotFoundError("Dataset not found.")
        return dataset

    # ------------------------------------------------------------------ upload
    async def create_upload(
        self,
        owner: User,
        *,
        source: uploads.AsyncReadable,
        filename: str | None,
        name: str | None,
        description: str | None,
    ) -> tuple[Dataset, IngestionJob, CsvAnalysis]:
        display = uploads.safe_display_name(filename)
        uploads.check_extension(display)
        dataset_name = (name or display.rsplit(".", 1)[0]).strip()[:120] or "Untitled dataset"
        await self._ensure_name_free(owner, dataset_name)

        token, path, size = await uploads.store_upload(
            source, self.settings.upload_dir, self.settings.upload_max_bytes
        )
        try:
            limits = Limits(
                max_rows=self.settings.upload_max_rows, max_columns=self.settings.upload_max_columns
            )
            analysis = await asyncio.to_thread(analyze_csv, path, limits)
        except CsvRejected as rejected:
            uploads.discard(self.settings.upload_dir, token)
            raise ValidationFailedError(
                rejected.issues[0].message,
                code="CSV_INVALID",
                details={"issues": [i.as_dict() for i in rejected.issues]},
            ) from None
        except BaseException:
            uploads.discard(self.settings.upload_dir, token)
            raise

        connection = await get_or_create_internal_connection(self.session, owner)
        schema, role = new_dataset_identifiers()
        dataset = Dataset(
            owner_id=owner.id,
            connection_id=connection.id,
            name=dataset_name,
            description=(description or "").strip()[:2000] or None,
            source_type="upload_csv",
            file_name=display,
            schema_name=schema,
            reader_role=role,
            status="pending_review",
            size_bytes=size,
        )
        self.session.add(dataset)
        await self.session.flush()
        job = IngestionJob(
            dataset_id=dataset.id,
            status="pending",
            file_name=display,
            file_size=size,
            upload_token=token,
            rows_total=analysis.row_count,
            rows_rejected=analysis.rejected_count,
            issues=[i.as_dict() for i in analysis.issues],
            inferred_schema=[
                {**c.as_dict(), "delimiter": analysis.delimiter} for c in analysis.columns
            ],
        )
        self.session.add(job)
        await self.session.commit()
        log.info(
            "upload_received",
            dataset_id=str(dataset.id),
            rows=analysis.row_count,
            columns=len(analysis.columns),
        )
        # Re-read with relationships eager-loaded: async sessions cannot lazy-load later.
        return await self.get(owner, dataset.id), job, analysis

    async def _ensure_name_free(self, owner: User, name: str) -> None:
        taken = await self.session.scalar(
            select(Dataset.id).where(Dataset.owner_id == owner.id, Dataset.name == name)
        )
        if taken:
            raise ConflictError(f"You already have a dataset named “{name}”.", code="NAME_TAKEN")

    # ------------------------------------------------------------------ finalize
    async def finalize(
        self, owner: User, dataset_id: uuid.UUID, type_overrides: Mapping[str, str]
    ) -> Dataset:
        ingest = _require(self.dbs.ingest, "ingest")
        dataset = await self.get(owner, dataset_id)
        if dataset.status != "pending_review":
            raise ConflictError(
                "Only datasets waiting for review can be loaded.", code="DATASET_NOT_PENDING"
            )
        job = next((j for j in dataset.jobs if j.status == "pending" and j.upload_token), None)
        path = (
            uploads.path_for(self.settings.upload_dir, job.upload_token)
            if job and job.upload_token
            else None
        )
        if job is None or path is None or not path.exists():
            raise ConflictError(
                "The uploaded file has expired. Upload it again.", code="UPLOAD_EXPIRED"
            )

        token = job.upload_token
        inferred = {c["name"]: c for c in job.inferred_schema}
        unknown = sorted(set(type_overrides) - set(inferred))
        if unknown:
            raise ValidationFailedError(
                f"Unknown columns: {', '.join(unknown)}.", details={"columns": unknown}
            )
        bad = {k: v for k, v in type_overrides.items() if v not in SUPPORTED_TYPES}
        if bad:
            raise ValidationFailedError(
                f"Unsupported type for {', '.join(bad)}. Supported: {', '.join(SUPPORTED_TYPES)}.",
                details={"columns": bad},
            )
        columns = [
            ColumnDef(name, cast("ColumnType", type_overrides.get(name, meta["inferred_type"])))
            for name, meta in inferred.items()
        ]
        delimiter = next(iter(inferred.values()))["delimiter"]
        table = normalize_identifier(dataset.name)[:50] or "data"

        dataset.status, job.status, job.started_at = "loading", "running", datetime.now(UTC)
        await self.session.commit()

        try:
            async with ingest.acquire() as conn, conn.transaction():
                await provision_schema(conn, dataset.schema_name, dataset.reader_role)
                await create_table(conn, dataset.schema_name, table, columns)
                loaded, rejected, first_bad = await self._load_csv(
                    conn=conn,
                    schema=dataset.schema_name,
                    table=table,
                    columns=columns,
                    path=path,
                    delimiter=delimiter,
                )
                total = loaded + rejected
                if total and rejected / total > MAX_REJECTED_RATIO:
                    raise RowsRejectedError(rejected, total, first_bad)
                await grant_reader(conn, dataset.schema_name, dataset.reader_role)
                await rebuild_catalog(
                    self.session,
                    conn,
                    dataset,
                    display_names={table: {n: m["display_name"] for n, m in inferred.items()}},
                    inferred_types={table: {n: m["inferred_type"] for n, m in inferred.items()}},
                )
                # Commit metadata while the warehouse transaction is still open: if this
                # fails, the warehouse rolls back too and nothing is left half-created.
                dataset.status = "ready"
                dataset.status_reason = (
                    f"{rejected:,} rows were skipped because they didn’t match the column types."
                    if rejected
                    else None
                )
                job.status, job.rows_loaded, job.rows_rejected = (
                    "succeeded",
                    loaded,
                    (job.rows_rejected or 0) + rejected,
                )
                job.finished_at = datetime.now(UTC)
                job.upload_token = None
                audit.record(
                    self.session,
                    "dataset.create",
                    actor_id=owner.id,
                    target_type="dataset",
                    target_id=dataset.id,
                    source="upload_csv",
                    rows=loaded,
                )
                await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            reason = self._failure_reason(exc)
            log.warning(
                "ingestion_failed", dataset_id=str(dataset.id), error_type=type(exc).__name__
            )
            await self._mark_failed(dataset.id, reason)
            uploads.discard(self.settings.upload_dir, token)
            raise ValidationFailedError(reason, code="INGESTION_FAILED") from None

        uploads.discard(self.settings.upload_dir, token)
        log.info("ingestion_succeeded", dataset_id=str(dataset.id), rows=dataset.total_rows)
        return await self.get(owner, dataset.id)

    async def _load_csv(
        self,
        *,
        conn: Any,
        schema: str,
        table: str,
        columns: Sequence[ColumnDef],
        path: Path,
        delimiter: str,
    ) -> tuple[int, int, dict[str, Any] | None]:
        """Parse rows in a worker thread (batch by batch) and COPY them in."""
        types: list[ColumnType] = [c.type for c in columns]
        reader_state: dict[str, Any] = {"rejected": 0, "first": None}
        loaded = 0
        with open_csv(path, delimiter) as (_handle, reader):
            next(reader, None)  # header

            def next_batch() -> list[tuple[Any, ...]]:
                batch: list[tuple[Any, ...]] = []
                for record in reader:
                    if not record or all(not c.strip() for c in record):
                        continue
                    if len(record) != len(types):
                        reader_state["rejected"] += (
                            1  # already reported at upload; skipped again here
                        )
                        continue
                    try:
                        batch.append(
                            tuple(
                                None if is_missing(v) else parse_value(t, v)
                                for t, v in zip(types, record, strict=True)
                            )
                        )
                    except ValueError as exc:
                        reader_state["rejected"] += 1
                        if reader_state["first"] is None:
                            reader_state["first"] = {"line": reader.line_num, "reason": str(exc)}
                    if len(batch) >= LOAD_BATCH:
                        break
                return batch

            while batch := await asyncio.to_thread(next_batch):
                loaded += await copy_rows(conn, schema, table, [c.name for c in columns], batch)
        return loaded, int(reader_state["rejected"]), reader_state["first"]

    @staticmethod
    def _failure_reason(exc: Exception) -> str:
        if isinstance(exc, RowsRejectedError):
            where = (
                f" (first at line {exc.first['line']}: {exc.first['reason']})" if exc.first else ""
            )
            return (
                f"{exc.rejected:,} of {exc.total:,} rows don’t match the chosen column types{where}. "
                "Change the type of that column to text, or fix the values and upload again."
            )
        return "The dataset couldn’t be loaded because of a database error. Nothing was saved; please try again."

    async def _mark_failed(self, dataset_id: uuid.UUID, reason: str) -> None:
        dataset = await self.session.get(Dataset, dataset_id)
        if dataset is None:
            return
        dataset.status, dataset.status_reason = "failed", reason
        job = await self.session.scalar(
            select(IngestionJob)
            .where(IngestionJob.dataset_id == dataset_id)
            .order_by(IngestionJob.created_at.desc())
        )
        if job:
            job.status, job.error, job.finished_at, job.upload_token = (
                "failed",
                reason,
                datetime.now(UTC),
                None,
            )
        await self.session.commit()

    # ------------------------------------------------------------------ updates & delete
    async def update_column(
        self,
        owner: User,
        dataset_id: uuid.UUID,
        column_id: uuid.UUID,
        *,
        description: str | None,
        is_sensitive: bool | None,
    ) -> DatasetColumn:
        dataset = await self.get(owner, dataset_id)
        column = next((c for t in dataset.tables for c in t.columns if c.id == column_id), None)
        if column is None:
            raise NotFoundError("Column not found.")
        if description is not None:
            column.description = description.strip()[:1000] or None
        if is_sensitive is not None:
            column.is_sensitive = is_sensitive
            if is_sensitive:  # forget any stored samples immediately
                column.profile = {
                    **column.profile,
                    "min": None,
                    "max": None,
                    "top_values": [],
                    "examples": [],
                }
        await self.session.commit()
        return column

    async def delete(self, owner: User, dataset_id: uuid.UUID) -> None:
        dataset = await self.get(owner, dataset_id)
        if dataset.status != "pending_review":
            ingest = _require(self.dbs.ingest, "ingest")
            async with ingest.acquire() as conn, conn.transaction():
                await drop_schema(conn, dataset.schema_name, dataset.reader_role)
        for job in dataset.jobs:
            uploads.discard(self.settings.upload_dir, job.upload_token)
        audit.record(
            self.session,
            "dataset.delete",
            actor_id=owner.id,
            target_type="dataset",
            target_id=dataset.id,
            name=dataset.name,
        )
        await self.session.delete(dataset)
        await self.session.commit()

    # ------------------------------------------------------------------ metadata
    async def update(
        self, owner: User, dataset_id: uuid.UUID, *, name: str | None, description: str | None
    ) -> Dataset:
        dataset = await self.get(owner, dataset_id)
        if name is not None:
            cleaned = " ".join(name.split())[:120]
            if not cleaned:
                raise ValidationFailedError("Enter a name.", code="INVALID_NAME")
            if cleaned != dataset.name:
                await self._ensure_name_free(owner, cleaned)
                dataset.name = cleaned
        if description is not None:
            dataset.description = description.strip()[:2000] or None
        await self.session.commit()
        return await self.get(owner, dataset_id)

    async def update_table(
        self, owner: User, dataset_id: uuid.UUID, table_id: uuid.UUID, *, description: str | None
    ) -> DatasetTable:
        dataset = await self.get(owner, dataset_id)
        table = next((t for t in dataset.tables if t.id == table_id), None)
        if table is None:
            raise NotFoundError("Table not found.")
        if description is not None:
            table.description = description.strip()[:1000] or None
        await self.session.commit()
        return table

    async def provision_demo(self, owner: User, *, replace: bool) -> tuple[Dataset, bool]:
        """Load the sample e-commerce dataset into the owner's own isolated schema."""
        ingest = _require(self.dbs.ingest, "ingest")
        result = await provision_demo(
            self.session, ingest, owner, scale=self.settings.demo_dataset_scale, replace=replace
        )
        if result.created:
            audit.record(
                self.session,
                "dataset.create",
                actor_id=owner.id,
                target_type="dataset",
                target_id=result.dataset.id,
                source="demo",
            )
            await self.session.commit()
        return await self.get(owner, result.dataset.id), result.created

    # ------------------------------------------------------------------ preview
    async def preview(
        self,
        owner: User,
        dataset_id: uuid.UUID,
        table_name: str,
        *,
        limit: int,
        offset: int,
        reveal_sensitive: bool,
    ) -> tuple[DatasetTable, ReadOnlyResult]:
        executor = _require(self.dbs.executor, "executor")
        dataset = await self.get(owner, dataset_id)
        if dataset.status != "ready":
            raise ConflictError("This dataset isn’t ready yet.", code="DATASET_NOT_READY")
        table = next((t for t in dataset.tables if t.table_name == table_name), None)
        if table is None:
            raise NotFoundError("Table not found.")
        limit = max(1, min(limit, self.settings.preview_max_rows))
        names = [
            c.column_name for c in table.columns
        ]  # identifiers come from the catalog, not the request
        order = table.primary_key or [ROW_ID]
        sql = (
            f"SELECT {', '.join(quote_ident(n) for n in names)} FROM {qualified(dataset.schema_name, table.table_name)} "  # noqa: S608 - identifiers validated + quoted
            f"ORDER BY {', '.join(quote_ident(n) for n in order)} LIMIT $1 OFFSET $2"
        )
        record = QueryExecution(
            owner_id=owner.id,
            dataset_id=dataset.id,
            origin="preview",
            executed_sql=sql,
            sql_fingerprint=hashlib.sha256(sql.encode()).hexdigest(),
            guard_status="not_applicable",
            exec_status="not_run",
        )
        try:
            result = await run_readonly(
                executor,
                schema=dataset.schema_name,
                reader_role=dataset.reader_role,
                sql=sql,
                params=[limit + 1, max(0, offset)],
                max_rows=limit,
                timeout_ms=self.settings.executor_statement_timeout_ms,
            )
        except Exception as exc:
            record.exec_status, record.error_code = "error", getattr(exc, "sqlstate", None)
            record.error_message = "Preview query failed."
            self.session.add(record)
            await self.session.commit()
            log.warning("preview_failed", dataset_id=str(dataset.id), error_type=type(exc).__name__)
            raise ServiceUnavailableError(
                "The preview could not be loaded. Try again in a moment."
            ) from None
        record.exec_status, record.row_count, record.truncated, record.exec_ms = (
            "ok",
            len(result.rows),
            result.truncated,
            result.exec_ms,
        )
        self.session.add(record)
        await self.session.commit()

        if not reveal_sensitive:
            masked = {i for i, c in enumerate(table.columns) if c.is_sensitive}
            rows = [
                [MASK if i in masked and v is not None else v for i, v in enumerate(row)]
                for row in result.rows
            ]
            result = ReadOnlyResult(result.columns, rows, result.truncated, result.exec_ms)
        return table, result
