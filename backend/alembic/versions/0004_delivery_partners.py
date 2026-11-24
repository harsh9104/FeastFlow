"""delivery partners and worker timers

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

FIRST = [
    "Arjun",
    "Priya",
    "Rahul",
    "Sneha",
    "Vikram",
    "Ananya",
    "Karan",
    "Meera",
    "Rohit",
    "Divya",
    "Aditya",
    "Pooja",
    "Sanjay",
    "Kavya",
    "Nikhil",
    "Isha",
    "Manish",
    "Riya",
    "Suresh",
    "Neha",
]
LAST = ["Sharma", "Patel", "Reddy", "Iyer", "Singh", "Nair", "Gupta", "Joshi", "Rao", "Mehta"]


def upgrade() -> None:
    op.create_table(
        "delivery_partners",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="AVAILABLE"),
        sa.Column("deliveries_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status in ('AVAILABLE','BUSY','OFFLINE')", name="ck_delivery_partners_status"
        ),
    )
    op.create_index("ix_delivery_partners_status", "delivery_partners", ["status"])

    op.add_column("orders", sa.Column("preparing_at", sa.DateTime))
    op.add_column("orders", sa.Column("ready_at", sa.DateTime))
    op.add_column("orders", sa.Column("stage_due_at", sa.DateTime))
    op.add_column("orders", sa.Column("partner_id", sa.Integer))
    op.create_foreign_key(
        "fk_orders_partner",
        "orders",
        "delivery_partners",
        ["partner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_orders_status_due", "orders", ["status", "stage_due_at"])

    partners = sa.table(
        "delivery_partners",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("phone", sa.String),
    )
    op.bulk_insert(
        partners,
        [
            {
                "id": i + 1,
                "name": f"{first} {LAST[i % len(LAST)]}",
                "phone": f"+91900000{i + 1:04d}",
            }
            for i, first in enumerate(FIRST)
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_orders_status_due", "orders")
    op.drop_constraint("fk_orders_partner", "orders", type_="foreignkey")
    for col in ("partner_id", "stage_due_at", "ready_at", "preparing_at"):
        op.drop_column("orders", col)
    op.drop_table("delivery_partners")
