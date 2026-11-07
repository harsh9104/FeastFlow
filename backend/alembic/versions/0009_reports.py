"""reports

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("report_type", sa.String(16), nullable=False),
        sa.Column(
            "load_test_run_id",
            sa.BigInteger,
            sa.ForeignKey("load_test_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("s3_key", sa.String(255), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "report_type in ('LOAD_TEST','COST','COMPARISON')", name="ck_reports_type"
        ),
        sa.CheckConstraint("format in ('JSON','CSV','MD')", name="ck_reports_format"),
    )


def downgrade() -> None:
    op.drop_table("reports")
