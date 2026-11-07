from datetime import datetime

from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoginFailure(Base):
    """One failed login. Counted per email and per client IP to rate-limit /auth/login."""

    __tablename__ = "login_failures"
    __table_args__ = (
        Index("ix_login_failures_email_time", "email", "created_at"),
        Index("ix_login_failures_ip_time", "ip", "created_at"),
        Index("ix_login_failures_time", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    ip: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
