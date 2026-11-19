from datetime import datetime

from sqlalchemy import CheckConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PARTNER_STATUSES = ("AVAILABLE", "BUSY", "OFFLINE")


class DeliveryPartner(Base):
    """Simulated rider. BUSY while carrying an order, AVAILABLE when free,
    OFFLINE when the admin takes them off shift. Their current order is the one
    with orders.partner_id = id and status OUT_FOR_DELIVERY."""

    __tablename__ = "delivery_partners"
    __table_args__ = (
        CheckConstraint(
            "status in ('AVAILABLE','BUSY','OFFLINE')", name="ck_delivery_partners_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    status: Mapped[str] = mapped_column(
        String(16), default="AVAILABLE", server_default="AVAILABLE", index=True
    )
    deliveries_count: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
