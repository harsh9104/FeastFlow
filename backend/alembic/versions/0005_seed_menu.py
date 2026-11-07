"""seed menu items

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ITEMS = [
    ("Paneer Tikka", "Char-grilled cottage cheese with spices", "Starters", "8.50", "paneer-tikka"),
    ("Veg Spring Rolls", "Crispy rolls with vegetable filling", "Starters", "6.00", "spring-rolls"),
    ("Samosa Plate", "Two crisp samosas with chutney", "Starters", "4.50", "samosa"),
    ("Butter Chicken", "Creamy tomato curry with chicken", "Mains", "12.50", "butter-chicken"),
    ("Dal Makhani", "Slow-cooked black lentils", "Mains", "9.50", "dal-makhani"),
    ("Veg Biryani", "Fragrant rice with vegetables", "Mains", "10.00", "veg-biryani"),
    ("Margherita Pizza", "Tomato, mozzarella and basil", "Mains", "11.00", "margherita"),
    ("Garlic Naan", "Tandoor-baked garlic flatbread", "Breads", "2.50", "garlic-naan"),
    ("Butter Roti", "Whole-wheat flatbread", "Breads", "1.80", "roti"),
    ("Gulab Jamun", "Milk dumplings in sugar syrup", "Desserts", "4.00", "gulab-jamun"),
    ("Mango Lassi", "Chilled yogurt mango drink", "Drinks", "3.80", "mango-lassi"),
    ("Masala Chai", "Spiced milk tea", "Drinks", "2.20", "chai"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for name, desc, cat, price, slug in ITEMS:
        conn.execute(
            sa.text(
                "INSERT INTO menu_items (name, description, category, price, image_key) "
                "VALUES (:n, :d, :c, :p, :k) ON CONFLICT (name) DO NOTHING"
            ),
            {"n": name, "d": desc, "c": cat, "p": price, "k": f"menu/{slug}.jpg"},
        )


def downgrade() -> None:
    op.execute("DELETE FROM menu_items WHERE image_key LIKE 'menu/%'")
