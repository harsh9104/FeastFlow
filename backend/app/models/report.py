from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("report_type in ('LOAD_TEST','COST','COMPARISON')", name="ck_reports_type"),
        CheckConstraint("format in ('JSON','CSV','MD')", name="ck_reports_format"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(16))
    load_test_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("load_test_runs.id", ondelete="SET NULL")
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    s3_key: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
