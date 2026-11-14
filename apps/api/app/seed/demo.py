"""Seed the demo user and the "E-commerce demo" dataset.

Usage (from apps/api):

    uv run python -m app.seed                      # standard scale, idempotent
    uv run python -m app.seed --scale small        # fast, for tests
    uv run python -m app.seed --replace            # drop and rebuild the demo dataset
    uv run python -m app.seed --csv-out ./demo_csv # also export the tables as CSV files

The demo dataset is loaded with the same warehouse primitives as uploads (isolated
schema, SELECT-only reader role, COPY), plus real PRIMARY KEY / FOREIGN KEY
constraints and indexes so the schema service can report relationships.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import asyncpg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.engines import Databases, open_databases
from app.db.identifiers import new_dataset_identifiers, qualified, quote_ident
from app.db.models import Dataset, User
from app.ingestion.warehouse import (
    copy_rows,
    create_table,
    drop_schema,
    grant_reader,
    provision_schema,
)
from app.seed.ecommerce import COLUMN_DESCRIPTIONS, SCHEMA, checksum, generate
from app.services.catalog import rebuild_catalog
from app.services.connections import get_or_create_internal_connection

DEMO_DATASET_NAME = "E-commerce demo"
DEMO_DESCRIPTION = (
    "Synthetic online retailer, Nov 2024 – Oct 2026: customers, products, orders, order items and payments "
    "across six US regions. Generated deterministically for demos and evaluation."
)


@dataclass
class SeedResult:
    user: User
    dataset: Dataset
    created: bool
    row_counts: dict[str, int]
    checksum: str | None


async def ensure_demo_user(session: AsyncSession, email: str) -> User:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        user = User(email=email.lower(), full_name="Demo Analyst")
        session.add(user)
        await session.flush()
    return user


async def load_demo_tables(
    conn: asyncpg.Connection, schema: str, data: dict[str, list[tuple[object, ...]]]
) -> None:
    for spec in SCHEMA:
        await create_table(
            conn, schema, spec.name, spec.columns, primary_key=spec.primary_key, with_row_id=False
        )
    for spec in SCHEMA:  # load parents before children
        await copy_rows(conn, schema, spec.name, [c.name for c in spec.columns], data[spec.name])
    for spec in SCHEMA:
        for column, ref_table, ref_column in spec.foreign_keys:
            await conn.execute(
                f"ALTER TABLE {qualified(schema, spec.name)} ADD CONSTRAINT {quote_ident(f'fk_{spec.name}_{column}')} "
                f"FOREIGN KEY ({quote_ident(column)}) REFERENCES {qualified(schema, ref_table)} ({quote_ident(ref_column)})"
            )
        for column in spec.indexes:
            await conn.execute(
                f"CREATE INDEX {quote_ident(f'ix_{spec.name}_{column}')} ON {qualified(schema, spec.name)} ({quote_ident(column)})"
            )
        await conn.execute(f"ANALYZE {qualified(schema, spec.name)}")


async def provision_demo(
    session: AsyncSession,
    ingest: asyncpg.Pool,
    user: User,
    *,
    scale: str = "standard",
    replace: bool = False,
    seed: int = 20261113,
) -> SeedResult:
    """Give ``user`` their own copy of the demo dataset (own schema and reader role).

    Idempotent: a ready copy is returned as-is unless ``replace``. Commits on success.
    """
    existing = await session.scalar(
        select(Dataset).where(Dataset.owner_id == user.id, Dataset.name == DEMO_DATASET_NAME)
    )
    if existing and existing.status == "ready" and not replace:
        await session.commit()
        return SeedResult(user, existing, False, {}, None)
    if existing:
        if existing.status != "pending_review":
            async with ingest.acquire() as conn, conn.transaction():
                await drop_schema(conn, existing.schema_name, existing.reader_role)
        await session.delete(existing)
        await session.flush()

    connection = await get_or_create_internal_connection(session, user)
    schema, role = new_dataset_identifiers()
    dataset = Dataset(
        owner_id=user.id,
        connection_id=connection.id,
        name=DEMO_DATASET_NAME,
        description=DEMO_DESCRIPTION,
        source_type="demo",
        schema_name=schema,
        reader_role=role,
        status="loading",
    )
    session.add(dataset)
    await session.flush()

    data = await asyncio.to_thread(generate, scale, seed)
    async with ingest.acquire() as conn, conn.transaction():
        await provision_schema(conn, schema, role)
        await load_demo_tables(conn, schema, data)
        await grant_reader(conn, schema, role)
        await rebuild_catalog(
            session,
            conn,
            dataset,
            table_descriptions={s.name: s.description for s in SCHEMA},
            column_descriptions=COLUMN_DESCRIPTIONS,
        )
        dataset.status = "ready"
        await session.commit()
    return SeedResult(user, dataset, True, {k: len(v) for k, v in data.items()}, checksum(data))


async def seed_demo(
    databases: Databases,
    settings: Settings,
    *,
    scale: str = "standard",
    replace: bool = False,
    seed: int = 20261113,
) -> SeedResult:
    """CLI path: create the demo user (used by AUTH_MODE=demo) and provision their copy."""
    if databases.sessions is None or databases.ingest is None:
        raise RuntimeError("DATABASE_URL and INGEST_DATABASE_URL must be configured to seed.")
    async with databases.sessions() as session:
        user = await ensure_demo_user(session, settings.demo_user_email)
        return await provision_demo(
            session, databases.ingest, user, scale=scale, replace=replace, seed=seed
        )


def export_csv(directory: Path, scale: str, seed: int = 20261113) -> list[Path]:
    """Write the generated tables as CSV files (useful for trying the upload flow)."""
    directory.mkdir(parents=True, exist_ok=True)
    data = generate(scale, seed)
    written = []
    for spec in SCHEMA:
        path = directory / f"{spec.name}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([c.name for c in spec.columns])
            for row in data[spec.name]:
                writer.writerow([v.isoformat() if hasattr(v, "isoformat") else v for v in row])
        written.append(path)
    return written


async def _main(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.csv_out:
        for path in export_csv(Path(args.csv_out), args.scale):
            print(f"wrote {path}")
    databases = await open_databases(settings)
    try:
        result = await seed_demo(databases, settings, scale=args.scale, replace=args.replace)
    finally:
        await databases.close()
    if result.created:
        counts = ", ".join(f"{k}={v:,}" for k, v in result.row_counts.items())
        print(f"✓ Seeded “{DEMO_DATASET_NAME}” for {result.user.email}: {counts}")
        print(
            f"  schema {result.dataset.schema_name} · checksum {result.checksum[:12] if result.checksum else '-'}"
        )
    else:
        print(
            f"✓ “{DEMO_DATASET_NAME}” already exists for {result.user.email} (use --replace to rebuild)"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed", description="Seed Sageboard demo data."
    )
    parser.add_argument("--scale", choices=["small", "standard"], default="standard")
    parser.add_argument("--replace", action="store_true", help="drop and rebuild the demo dataset")
    parser.add_argument(
        "--csv-out", help="also write the demo tables as CSV files to this directory"
    )
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
