"""Print the `app` schema as Markdown tables, straight from the SQLAlchemy models.

Regenerates the table reference in docs/DATABASE_DESIGN.md so the doc can't drift:

    uv run python scripts/schema_reference.py > /tmp/tables.md
"""

from __future__ import annotations

import sys

from sqlalchemy import CheckConstraint, Column, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql

import app.db.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import APP_SCHEMA, Base

ORDER = [
    "users",
    "refresh_tokens",
    "audit_log",
    "database_connections",
    "datasets",
    "dataset_tables",
    "dataset_columns",
    "dataset_relationships",
    "ingestion_jobs",
    "conversations",
    "messages",
    "analysis_sessions",
    "agent_node_runs",
    "query_executions",
    "reports",
]
DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]


def _default(column: Column[object]) -> str:
    arg = column.server_default.arg  # type: ignore[union-attr]
    if isinstance(arg, str):
        return arg
    return "now()" if "now" in repr(arg) else str(getattr(arg, "text", arg))


def _constraints(column: Column[object]) -> str:
    bits: list[str] = []
    if column.primary_key:
        bits.append("PK")
    for fk in column.foreign_keys:
        deferred = (
            " DEFERRABLE INITIALLY DEFERRED" if fk.constraint and fk.constraint.deferrable else ""
        )
        bits.append(
            f"FK → {fk.column.table.name}.{fk.column.name} ON DELETE {fk.ondelete or 'NO ACTION'}{deferred}"
        )
    if not column.nullable and not column.primary_key:
        bits.append("NOT NULL")
    if column.unique:
        bits.append("UNIQUE")
    if column.server_default is not None:
        bits.append(f"DEFAULT {_default(column)}")
    return ", ".join(bits)


def _extras(table: Table) -> list[str]:
    lines: list[str] = []
    for con in sorted(table.constraints, key=lambda c: str(c.name)):
        if isinstance(con, CheckConstraint):
            lines.append(f"CHECK `{con.name}`: `{con.sqltext}`")
        elif isinstance(con, UniqueConstraint):
            lines.append(f"UNIQUE `{con.name}` ({', '.join(c.name for c in con.columns)})")
    for ix in sorted(table.indexes, key=lambda i: str(i.name)):
        cols = ", ".join(getattr(e, "name", None) or str(e) for e in ix.expressions)
        where = ix.dialect_options["postgresql"].get("where")
        suffix = f" WHERE `{where}`" if where is not None else ""
        lines.append(f"{'UNIQUE ' if ix.unique else ''}INDEX `{ix.name}` ({cols}){suffix}")
    return lines


def render() -> str:
    out: list[str] = []
    for name in ORDER:
        table = Base.metadata.tables[f"{APP_SCHEMA}.{name}"]
        out += [f"**{name}**", "", "| Column | Type | Constraints |", "|---|---|---|"]
        out += [
            f"| {c.name} | {c.type.compile(DIALECT).lower()} | {_constraints(c)} |"
            for c in table.columns
        ]
        extras = _extras(table)
        if extras:
            out += ["", *(f"- {e}" for e in extras)]
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.write(render() + "\n")
