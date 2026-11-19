"""restaurants, menu, orders

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

STATUSES = "'PLACED','CONFIRMED','PREPARING','AWAITING_PARTNER','OUT_FOR_DELIVERY','DELIVERED','CANCELLED'"


def upgrade() -> None:
    op.create_table(
        "restaurants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("area", sa.String(120), nullable=False),
        sa.Column("cuisine", sa.String(60), nullable=False),
        sa.Column("is_open", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "menu_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "restaurant_id",
            sa.Integer,
            sa.ForeignKey("restaurants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("is_veg", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("image_key", sa.String(255)),
        sa.Column("is_available", sa.Boolean, nullable=False, server_default="1"),
        sa.CheckConstraint("price > 0", name="ck_menu_price"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "restaurant_id",
            sa.Integer,
            sa.ForeignKey("restaurants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLACED"),
        sa.Column("priority", sa.SmallInteger, nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("delivery_address", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(64)),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.Column("enqueued_at", sa.DateTime),
        sa.Column("confirmed_at", sa.DateTime),
        sa.Column("assigned_at", sa.DateTime),
        sa.Column("delivered_at", sa.DateTime),
        sa.CheckConstraint(f"status in ({STATUSES})", name="ck_orders_status"),
        sa.CheckConstraint("priority in (0,1)", name="ck_orders_priority"),
        sa.CheckConstraint("total_amount >= 0", name="ck_orders_total"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="ux_orders_user_idem"),
    )
    op.create_index("ix_orders_status_priority", "orders", ["status", "priority", "created_at"])
    op.create_index("ix_orders_user_created", "orders", ["user_id", "created_at"])
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "menu_item_id",
            sa.Integer,
            sa.ForeignKey("menu_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_qty"),
    )
    op.create_table(
        "order_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.String(255)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_order_events_order_id", "order_events", ["order_id"])


def downgrade() -> None:
    for table in ("order_events", "order_items", "orders", "menu_items", "restaurants"):
        op.drop_table(table)
