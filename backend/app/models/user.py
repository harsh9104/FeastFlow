from datetime import datetime

from sqlalchemy import CheckConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role in ('CUSTOMER','ADMIN')", name="ck_users_role"),
        CheckConstraint("subscription_tier in ('FREE','PREMIUM')", name="ck_users_tier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="CUSTOMER", server_default="CUSTOMER")
    subscription_tier: Mapped[str] = mapped_column(
        String(16), default="FREE", server_default="FREE"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
