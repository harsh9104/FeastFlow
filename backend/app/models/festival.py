from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RUN_STATUSES = ("RUNNING", "COMPLETED", "CANCELLED", "FAILED")


class FestivalRun(Base):
    """One festival-simulator burst. It runs on whichever API instance received the
    request, but its state lives here so any instance can show progress or cancel it."""

    __tablename__ = "festival_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('RUNNING','COMPLETED','CANCELLED','FAILED')", name="ck_festival_runs_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="RUNNING", server_default="RUNNING")
    requested_orders: Mapped[int]
    prime_percent: Mapped[int]
    duration_seconds: Mapped[int]
    created_orders: Mapped[int] = mapped_column(default=0, server_default="0")
    prime_orders: Mapped[int] = mapped_column(default=0, server_default="0")
    failed_orders: Mapped[int] = mapped_column(default=0, server_default="0")
    instance_id: Mapped[str] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Updated while generating; a RUNNING row with an old heartbeat means its
    # instance died (scale-in, crash) and the run is reported as FAILED.
    heartbeat_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
