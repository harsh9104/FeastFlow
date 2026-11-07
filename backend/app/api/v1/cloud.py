from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.services import metrics_service as ms

router = APIRouter(prefix="/api/v1/admin/cloud", tags=["cloud"])


@router.get("/metrics")
def metrics(
    range: str = Query("1h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ms.get_metrics(db, range)


@router.get("/instances")
def instances(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return ms.get_provider().instances(db)


@router.get("/scaling-activities")
def scaling_activities(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return ms.get_provider().scaling_activities(db)


@router.get("/alarms")
def alarms(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return ms.get_provider().alarms(db)
