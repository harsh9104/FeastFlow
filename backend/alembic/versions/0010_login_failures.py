"""login_failures (login rate limiting)

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_failures",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_login_failures_email_time", "login_failures", ["email", "created_at"])
    op.create_index("ix_login_failures_ip_time", "login_failures", ["ip", "created_at"])
    op.create_index("ix_login_failures_time", "login_failures", ["created_at"])


def downgrade() -> None:
    op.drop_table("login_failures")
