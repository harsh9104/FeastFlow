"""app_metrics (local metrics provider)

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_metrics",
        sa.Column("instance_id", sa.String(64), primary_key=True),
        sa.Column("worker", sa.Integer, primary_key=True),
        sa.Column("minute", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("request_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_5xx", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_sum_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("p50_ms", sa.Float),
        sa.Column("p90_ms", sa.Float),
        sa.Column("cpu_pct", sa.Float),
        sa.Column("mem_pct", sa.Float),
    )
    op.create_index("ix_app_metrics_minute", "app_metrics", ["minute"])


def downgrade() -> None:
    op.drop_table("app_metrics")
