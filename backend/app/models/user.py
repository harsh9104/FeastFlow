from datetime import datetime

from sqlalchemy import CheckConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role in ('CUSTOMER','ADMIN')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="CUSTOMER", server_default="CUSTOMER")
    # Prime is active while this is in the future. There is no separate is_prime
    # column, so the flag can never go stale after a subscription runs out.
    prime_expires_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    @property
    def is_prime(self) -> bool:
        return self.prime_expires_at is not None and self.prime_expires_at > utcnow()

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"
