"""festival runs and load-test customers

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_test_user", sa.Boolean, nullable=False, server_default="0")
    )
    op.create_index("ix_users_is_test_user", "users", ["is_test_user"])
    op.create_table(
        "festival_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="RUNNING"),
        sa.Column("requested_orders", sa.Integer, nullable=False),
        sa.Column("prime_percent", sa.Integer, nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=False),
        sa.Column("created_orders", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prime_orders", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_orders", sa.Integer, nullable=False, server_default="0"),
        sa.Column("instance_id", sa.String(64), nullable=False),
        sa.Column("error", sa.String(255)),
        sa.Column(
            "created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("heartbeat_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime),
        sa.CheckConstraint(
            "status in ('RUNNING','COMPLETED','CANCELLED','FAILED')", name="ck_festival_runs_status"
        ),
    )
    # Test customers are created by `python -m app.seed` (the password comes from the
    # environment, so it can't live in a migration).


def downgrade() -> None:
    op.drop_table("festival_runs")
    op.drop_index("ix_users_is_test_user", "users")
    op.drop_column("users", "is_test_user")
