"""restaurant display details and bestseller dishes

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# id: (rating, delivery minutes, cost for two, offer)
DETAILS = {
    1: (4.4, 32, 500, "20% OFF up to ₹100"),
    2: (4.6, 22, 250, "Free filter coffee above ₹299"),
    3: (4.1, 35, 450, "₹75 OFF above ₹399"),
    4: (4.3, 28, 600, "Buy 1 Get 1 on pizzas"),
}
BESTSELLERS = [2, 1, 6, 12, 16]


def upgrade() -> None:
    op.add_column(
        "restaurants", sa.Column("rating", sa.Numeric(2, 1), nullable=False, server_default="4.2")
    )
    op.add_column(
        "restaurants",
        sa.Column("delivery_minutes", sa.Integer, nullable=False, server_default="30"),
    )
    op.add_column(
        "restaurants", sa.Column("cost_for_two", sa.Integer, nullable=False, server_default="400")
    )
    op.add_column("restaurants", sa.Column("offer", sa.String(60)))
    op.add_column(
        "menu_items", sa.Column("is_bestseller", sa.Boolean, nullable=False, server_default="0")
    )

    restaurants = sa.table(
        "restaurants",
        sa.column("id", sa.Integer),
        sa.column("rating", sa.Numeric),
        sa.column("delivery_minutes", sa.Integer),
        sa.column("cost_for_two", sa.Integer),
        sa.column("offer", sa.String),
    )
    for rid, (rating, minutes, cost, offer) in DETAILS.items():
        op.execute(
            restaurants.update()
            .where(restaurants.c.id == rid)
            .values(rating=rating, delivery_minutes=minutes, cost_for_two=cost, offer=offer)
        )
    items = sa.table(
        "menu_items", sa.column("id", sa.Integer), sa.column("is_bestseller", sa.Boolean)
    )
    op.execute(items.update().where(items.c.id.in_(BESTSELLERS)).values(is_bestseller=True))


def downgrade() -> None:
    op.drop_column("menu_items", "is_bestseller")
    for col in ("offer", "cost_for_two", "delivery_minutes", "rating"):
        op.drop_column("restaurants", col)
