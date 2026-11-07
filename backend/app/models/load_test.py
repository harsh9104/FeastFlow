from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoadTestRun(Base):
    __tablename__ = "load_test_runs"
    __table_args__ = (
        CheckConstraint("scenario in ('NORMAL','FESTIVAL')", name="ck_lt_scenario"),
        CheckConstraint(
            "status in ('RUNNING','COMPLETED','STOPPED','FAILED')", name="ck_lt_status"
        ),
        # At most one RUNNING row across all app instances.
        Index(
            "ux_one_running_test",
            text("(true)"),
            unique=True,
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    started_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_users: Mapped[int]
    spawn_rate: Mapped[int]
    duration_seconds: Mapped[int]
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    total_requests: Mapped[int | None] = mapped_column(BigInteger)
    failed_requests: Mapped[int | None] = mapped_column(BigInteger)
    avg_response_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    p95_response_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    peak_rps: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    avg_cpu_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    peak_cpu_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    min_instances: Mapped[int | None]
    max_instances: Mapped[int | None]
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    raw_stats: Mapped[dict | None] = mapped_column(JSONB)
