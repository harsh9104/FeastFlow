from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppMetric(Base):
    """Per-minute metrics written by each app worker (local metrics provider)."""

    __tablename__ = "app_metrics"
    __table_args__ = (Index("ix_app_metrics_minute", "minute"),)

    instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    worker: Mapped[int] = mapped_column(primary_key=True)
    minute: Mapped[datetime] = mapped_column(primary_key=True)
    request_count: Mapped[int] = mapped_column(default=0)
    error_5xx: Mapped[int] = mapped_column(default=0)
    latency_sum_ms: Mapped[float] = mapped_column(default=0.0)
    p50_ms: Mapped[float | None]
    p90_ms: Mapped[float | None]
    cpu_pct: Mapped[float | None]
    mem_pct: Mapped[float | None]
