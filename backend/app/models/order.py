from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.menu import MenuItem, Restaurant
from app.models.partner import DeliveryPartner
from app.models.user import User

ORDER_STATUSES = (
    "PLACED",  # saved, message sent (or about to be) to SQS
    "CONFIRMED",  # a worker picked it up
    "PREPARING",
    "AWAITING_PARTNER",  # food ready, no delivery partner free yet
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "CANCELLED",
)
_status_list = ",".join(f"'{s}'" for s in ORDER_STATUSES)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(f"status in ({_status_list})", name="ck_orders_status"),
        CheckConstraint("priority in (0,1)", name="ck_orders_priority"),
        CheckConstraint("total_amount >= 0", name="ck_orders_total"),
        # MySQL allows many NULLs in a unique index, so orders without a key never clash.
        UniqueConstraint("user_id", "idempotency_key", name="ux_orders_user_idem"),
        Index("ix_orders_status_priority", "status", "priority", "created_at"),
        Index("ix_orders_user_created", "user_id", "created_at"),
        # The worker's ticker looks up "orders in status X whose timer is due".
        Index("ix_orders_status_due", "status", "stage_due_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="PLACED", server_default="PLACED")
    priority: Mapped[int] = mapped_column(SmallInteger)  # 1 = Prime at the time of ordering
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    delivery_address: Mapped[str] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    is_synthetic: Mapped[bool] = mapped_column(default=False, server_default="0")  # festival sim
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    # NULL means the SQS send failed; P3's sweeper re-sends these.
    enqueued_at: Mapped[datetime | None]
    confirmed_at: Mapped[datetime | None]
    preparing_at: Mapped[datetime | None]
    ready_at: Mapped[datetime | None]  # food ready, waiting for / handed to a partner
    assigned_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
    # When the current stage's simulated timer runs out (see dispatch_service).
    stage_due_at: Mapped[datetime | None]
    partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("delivery_partners.id", ondelete="SET NULL")
    )

    restaurant: Mapped[Restaurant] = relationship()
    partner: Mapped[DeliveryPartner | None] = relationship()
    user: Mapped[User] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    events: Mapped[list["OrderEvent"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderEvent.id"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_items_qty"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id", ondelete="RESTRICT"))
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # price when ordered

    order: Mapped[Order] = relationship(back_populates="items")
    menu_item: Mapped[MenuItem] = relationship()


class OrderEvent(Base):
    """One row per status change: the timeline shown on both dashboards."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="events")
