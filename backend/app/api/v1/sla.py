from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.services import sla_service

router = APIRouter(prefix="/api/v1/admin/sla", tags=["sla"])


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)


@router.get("/availability")
def availability(
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Availability for the period (default: last 24 h) measured against the SLA target."""
    end = _aware(date_to) if date_to else datetime.now(UTC)
    start = _aware(date_from) if date_from else end - timedelta(hours=24)
    return sla_service.availability(db, start, end)
