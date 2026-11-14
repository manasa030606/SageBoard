"""Agent runs: node trace table and result columns on analysis sessions.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analysis_sessions", sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema="app")
    op.add_column("analysis_sessions", sa.Column("llm_provider", sa.String(length=32), nullable=True), schema="app")
    op.add_column("analysis_sessions", sa.Column("llm_model", sa.String(length=120), nullable=True), schema="app")
    op.create_table(
        "agent_node_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_session_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("node", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("llm_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('succeeded', 'failed', 'degraded')", name=op.f("ck_agent_node_runs_status")),
        sa.ForeignKeyConstraint(["analysis_session_id"], ["app.analysis_sessions.id"], name=op.f("fk_agent_node_runs_analysis_session_id_analysis_sessions"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["app.users.id"], name=op.f("fk_agent_node_runs_owner_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_node_runs")),
        schema="app",
    )
    op.create_index("uq_agent_node_runs_session_seq", "agent_node_runs", ["analysis_session_id", "seq"], unique=True, schema="app")


def downgrade() -> None:
    op.drop_index("uq_agent_node_runs_session_seq", table_name="agent_node_runs", schema="app")
    op.drop_table("agent_node_runs", schema="app")
    op.drop_column("analysis_sessions", "llm_model", schema="app")
    op.drop_column("analysis_sessions", "llm_provider", schema="app")
    op.drop_column("analysis_sessions", "result", schema="app")
