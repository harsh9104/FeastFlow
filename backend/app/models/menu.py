from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    area: Mapped[str] = mapped_column(String(120))
    cuisine: Mapped[str] = mapped_column(String(60))
    is_open: Mapped[bool] = mapped_column(default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    items: Mapped[list["MenuItem"]] = relationship(
        back_populates="restaurant", order_by="MenuItem.id"
    )


class MenuItem(Base):
    __tablename__ = "menu_items"
    __table_args__ = (CheckConstraint("price > 0", name="ck_menu_price"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    is_veg: Mapped[bool] = mapped_column(default=True, server_default="1")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    image_key: Mapped[str | None] = mapped_column(String(255))  # S3 object key, e.g. menu/12.svg
    is_available: Mapped[bool] = mapped_column(default=True, server_default="1")

    restaurant: Mapped[Restaurant] = relationship(back_populates="items")
