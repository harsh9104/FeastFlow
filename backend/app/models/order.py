from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MenuItem(Base):
    __tablename__ = "menu_items"
    __table_args__ = (CheckConstraint("price > 0", name="ck_menu_price"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    image_key: Mapped[str | None] = mapped_column(String(255))
    is_available: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status in ('PENDING','PREPARING','COMPLETED')", name="ck_orders_status"),
        CheckConstraint("priority in (0,1)", name="ck_orders_priority"),
        CheckConstraint("tier_at_order in ('FREE','PREMIUM')", name="ck_orders_tier"),
        CheckConstraint("total_amount >= 0", name="ck_orders_total"),
        Index("ix_orders_queue", "status", text("priority DESC"), "created_at"),
        Index("ix_orders_user_created", "user_id", text("created_at DESC")),
        Index(
            "ux_orders_user_idem",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    priority: Mapped[int] = mapped_column(SmallInteger)
    tier_at_order: Mapped[str] = mapped_column(String(16))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1, server_default=text("1"))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    preparing_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    history: Mapped[list["OrderStatusHistory"]] = relationship(
        order_by="OrderStatusHistory.id", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity between 1 and 20", name="ck_order_items_qty"),
        UniqueConstraint("order_id", "menu_item_id", name="uq_order_items_order_menu"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id", ondelete="RESTRICT"))
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    order: Mapped[Order] = relationship(back_populates="items")
    menu_item: Mapped[MenuItem] = relationship()


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    __table_args__ = (Index("ix_history_order_changed", "order_id", "changed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
