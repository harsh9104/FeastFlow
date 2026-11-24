"""seed restaurants and menu

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

RESTAURANTS = [
    (1, "Spice Route", "MG Road", "North Indian"),
    (2, "Dosa Junction", "Koramangala", "South Indian"),
    (3, "Wok This Way", "Indiranagar", "Chinese"),
    (4, "Slice Society", "HSR Layout", "Pizza & Fast Food"),
]

# (id, restaurant_id, name, category, is_veg, price, description)
ITEMS = [
    (
        1,
        1,
        "Paneer Butter Masala",
        "Main Course",
        True,
        249,
        "Cottage cheese in a rich tomato gravy",
    ),
    (2, 1, "Chicken Biryani", "Main Course", False, 299, "Dum-cooked basmati with spiced chicken"),
    (3, 1, "Dal Makhani", "Main Course", True, 199, "Slow-cooked black lentils with butter"),
    (4, 1, "Butter Naan", "Breads", True, 49, "Tandoor-baked flatbread"),
    (5, 1, "Gulab Jamun", "Desserts", True, 89, "Two warm milk dumplings in syrup"),
    (6, 2, "Masala Dosa", "Dosa", True, 129, "Crisp dosa with spiced potato filling"),
    (7, 2, "Idli Sambar", "Breakfast", True, 79, "Steamed rice cakes with sambar"),
    (8, 2, "Medu Vada", "Breakfast", True, 69, "Crispy lentil doughnuts"),
    (9, 2, "Rava Dosa", "Dosa", True, 139, "Lacy semolina dosa"),
    (10, 2, "Filter Coffee", "Beverages", True, 49, "Strong South Indian coffee"),
    (11, 3, "Veg Hakka Noodles", "Noodles", True, 179, "Wok-tossed noodles with vegetables"),
    (12, 3, "Chilli Chicken", "Starters", False, 229, "Crispy chicken in chilli sauce"),
    (13, 3, "Veg Manchurian", "Starters", True, 189, "Vegetable balls in Manchurian gravy"),
    (14, 3, "Chicken Fried Rice", "Rice", False, 209, "Egg-fried rice with chicken"),
    (15, 3, "Spring Rolls", "Starters", True, 149, "Four crispy vegetable rolls"),
    (16, 4, "Margherita Pizza", "Pizza", True, 249, "Tomato, mozzarella and basil"),
    (17, 4, "Pepperoni Pizza", "Pizza", False, 349, "Loaded with pepperoni"),
    (18, 4, "Veg Burger", "Burgers", True, 149, "Crispy veg patty with cheese"),
    (19, 4, "French Fries", "Sides", True, 99, "Salted, crisp fries"),
    (20, 4, "Chocolate Shake", "Beverages", True, 129, "Thick chocolate milkshake"),
]


def upgrade() -> None:
    restaurants = sa.table(
        "restaurants",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("area", sa.String),
        sa.column("cuisine", sa.String),
    )
    items = sa.table(
        "menu_items",
        sa.column("id", sa.Integer),
        sa.column("restaurant_id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("is_veg", sa.Boolean),
        sa.column("price", sa.Numeric),
        sa.column("description", sa.Text),
        sa.column("image_key", sa.String),
    )
    op.bulk_insert(
        restaurants,
        [dict(zip(("id", "name", "area", "cuisine"), r, strict=True)) for r in RESTAURANTS],
    )
    op.bulk_insert(
        items,
        [
            {
                "id": i,
                "restaurant_id": r,
                "name": n,
                "category": c,
                "is_veg": v,
                "price": p,
                "description": d,
                # Placeholder SVG uploaded by `python -m app.seed` when SEED_IMAGES=true;
                # replace with real photos from the admin dashboard.
                "image_key": f"menu/{i}.svg",
            }
            for i, r, n, c, v, p, d in ITEMS
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM menu_items WHERE id <= 20")
    op.execute("DELETE FROM restaurants WHERE id <= 4")
