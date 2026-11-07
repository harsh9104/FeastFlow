"""load_test_runs

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "load_test_runs",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("scenario", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_by", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_users", sa.Integer, nullable=False),
        sa.Column("spawn_rate", sa.Integer, nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("total_requests", sa.BigInteger),
        sa.Column("failed_requests", sa.BigInteger),
        sa.Column("avg_response_ms", sa.Numeric(10, 2)),
        sa.Column("p95_response_ms", sa.Numeric(10, 2)),
        sa.Column("peak_rps", sa.Numeric(10, 2)),
        sa.Column("avg_cpu_percent", sa.Numeric(5, 2)),
        sa.Column("peak_cpu_percent", sa.Numeric(5, 2)),
        sa.Column("min_instances", sa.Integer),
        sa.Column("max_instances", sa.Integer),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 4)),
        sa.Column("raw_stats", postgresql.JSONB),
        sa.CheckConstraint("scenario in ('NORMAL','FESTIVAL')", name="ck_lt_scenario"),
        sa.CheckConstraint(
            "status in ('RUNNING','COMPLETED','STOPPED','FAILED')", name="ck_lt_status"
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_one_running_test ON load_test_runs ((true)) WHERE status = 'RUNNING'"
    )


def downgrade() -> None:
    op.drop_table("load_test_runs")
