"""menu_items, orders, order_items, order_status_history

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_ts = dict(nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "menu_items",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("image_key", sa.String(255)),
        sa.Column("is_available", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), **_ts),
        sa.Column("updated_at", sa.DateTime(timezone=True), **_ts),
        sa.CheckConstraint("price > 0", name="ck_menu_price"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("priority", sa.SmallInteger, nullable=False),
        sa.Column("tier_at_order", sa.String(16), nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), **_ts),
        sa.Column("updated_at", sa.DateTime(timezone=True), **_ts),
        sa.Column("preparing_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status in ('PENDING','PREPARING','COMPLETED')", name="ck_orders_status"
        ),
        sa.CheckConstraint("priority in (0,1)", name="ck_orders_priority"),
        sa.CheckConstraint("tier_at_order in ('FREE','PREMIUM')", name="ck_orders_tier"),
        sa.CheckConstraint("total_amount >= 0", name="ck_orders_total"),
    )
    op.create_index("ix_orders_queue", "orders", ["status", sa.text("priority DESC"), "created_at"])
    op.create_index("ix_orders_user_created", "orders", ["user_id", sa.text("created_at DESC")])
    op.create_index(
        "ux_orders_user_idem",
        "orders",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "order_id",
            sa.BigInteger,
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "menu_item_id",
            sa.BigInteger,
            sa.ForeignKey("menu_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint("quantity between 1 and 20", name="ck_order_items_qty"),
        sa.UniqueConstraint("order_id", "menu_item_id", name="uq_order_items_order_menu"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "order_id",
            sa.BigInteger,
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(16)),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("changed_by", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), **_ts),
    )
    op.create_index("ix_history_order_changed", "order_status_history", ["order_id", "changed_at"])


def downgrade() -> None:
    op.drop_table("order_status_history")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("menu_items")
