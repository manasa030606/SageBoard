"""Build and refresh a dataset's catalog (tables, columns, relationships) in ``app``.

The catalog is always derived from the *live* warehouse schema (introspection) plus
profiles, never from what the client claimed, so it reflects exactly what exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import asyncpg
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Dataset, DatasetColumn, DatasetRelationship, DatasetTable
from app.ingestion.semantics import is_sensitive, semantic_role
from app.ingestion.warehouse import inspect_schema, profile_table


async def rebuild_catalog(
    session: AsyncSession,
    ingest: asyncpg.Connection,
    dataset: Dataset,
    *,
    display_names: Mapping[str, Mapping[str, str]] | None = None,
    inferred_types: Mapping[str, Mapping[str, str]] | None = None,
    table_descriptions: Mapping[str, str] | None = None,
    column_descriptions: Mapping[str, Mapping[str, str]] | None = None,
    sensitive_overrides: Mapping[str, Sequence[str]] | None = None,
) -> int:
    """Replace the dataset's catalog rows from the warehouse. Returns total rows."""
    await session.execute(
        delete(DatasetRelationship).where(DatasetRelationship.dataset_id == dataset.id)
    )
    await session.execute(delete(DatasetTable).where(DatasetTable.dataset_id == dataset.id))
    await session.flush()

    inspected = await inspect_schema(ingest, dataset.schema_name)
    by_name: dict[str, DatasetTable] = {}
    total_rows = 0
    for table in inspected:
        names = (display_names or {}).get(table.name, {})
        # Sensitivity is decided before profiling so sensitive samples are never read.
        sensitive = {c.name for c in table.columns if is_sensitive(c.name)}
        sensitive |= set((sensitive_overrides or {}).get(table.name, []))
        row_count, profiles = await profile_table(
            ingest, dataset.schema_name, table.name, table.columns, sensitive
        )
        # Value-based detection (e.g. an "contact" column full of e-mail addresses).
        late = {
            c.name
            for c in table.columns
            if c.name not in sensitive
            and is_sensitive(
                c.name,
                profiles[c.name].examples + [v["value"] for v in profiles[c.name].top_values],
            )
        }
        for name in late:
            p = profiles[name]
            p.examples, p.top_values = [], []
        sensitive |= late
        total_rows += row_count

        fk_columns = {col for fk in table.foreign_keys for col in fk.columns}
        dt = DatasetTable(
            dataset_id=dataset.id,
            table_name=table.name,
            display_name=table.name.replace("_", " ").capitalize(),
            description=(table_descriptions or {}).get(table.name),
            row_count=row_count,
            primary_key=table.primary_key,
        )
        for c in table.columns:
            profile = profiles[c.name]
            dt.columns.append(
                DatasetColumn(
                    column_name=c.name,
                    display_name=names.get(c.name, c.name),
                    ordinal=c.ordinal,
                    data_type=c.type,
                    inferred_type=(inferred_types or {}).get(table.name, {}).get(c.name),
                    is_nullable=c.nullable,
                    is_primary_key=c.name in table.primary_key,
                    semantic_role=semantic_role(
                        c.name,
                        c.type,
                        is_key=c.name in table.primary_key or c.name in fk_columns,
                        distinct_count=profile.distinct_count,
                        row_count=row_count,
                    ),
                    description=(column_descriptions or {}).get(table.name, {}).get(c.name),
                    is_sensitive=c.name in sensitive,
                    profile=profile.as_dict(),
                )
            )
        session.add(dt)
        by_name[table.name] = dt
    await session.flush()

    for table in inspected:
        for fk in table.foreign_keys:
            target = by_name.get(fk.ref_table)
            if target is None:
                continue
            for col, ref_col in zip(fk.columns, fk.ref_columns, strict=True):
                session.add(
                    DatasetRelationship(
                        dataset_id=dataset.id,
                        from_table_id=by_name[table.name].id,
                        from_column=col,
                        to_table_id=target.id,
                        to_column=ref_col,
                        origin="declared",
                        constraint_name=fk.constraint_name,
                    )
                )
    dataset.total_rows = total_rows
    await session.flush()
    return total_rows
