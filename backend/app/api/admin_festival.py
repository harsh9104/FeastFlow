"""Festival-day controls: the in-app order burst and the Locust load generator."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.services import festival_service, locust_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


class FestivalRunIn(BaseModel):
    orders: int = Field(ge=1)
    duration_seconds: int = Field(ge=0, le=1800)
    prime_percent: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _cap(self):
        cap = get_settings().festival_max_orders
        if self.orders > cap:
            raise ValueError(f"orders must be at most {cap}")
        return self


class FestivalRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    requested_orders: int
    prime_percent: int
    duration_seconds: int
    created_orders: int
    prime_orders: int
    failed_orders: int
    instance_id: str
    error: str | None
    started_at: datetime
    finished_at: datetime | None


@router.get("/festival/runs", response_model=list[FestivalRunOut])
def festival_runs(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return festival_service.list_runs(db)


@router.post("/festival/runs", response_model=FestivalRunOut, status_code=status.HTTP_202_ACCEPTED)
def start_festival_run(
    body: FestivalRunIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    run = festival_service.create_run(
        db, admin, body.orders, body.duration_seconds, body.prime_percent
    )
    festival_service.start_in_background(run.id)
    return run


@router.post("/festival/runs/{run_id}/cancel", response_model=FestivalRunOut)
def cancel_festival_run(
    run_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return festival_service.cancel_run(db, run_id)


class LoadTestIn(BaseModel):
    profile: Literal["normal", "festival"]


@router.get("/loadtest")
def loadtest_status(_: User = Depends(require_admin)):
    return locust_service.status_()


@router.post("/loadtest/start")
def loadtest_start(body: LoadTestIn, _: User = Depends(require_admin)):
    return locust_service.start(body.profile)


@router.post("/loadtest/stop")
def loadtest_stop(_: User = Depends(require_admin)):
    return locust_service.stop()
