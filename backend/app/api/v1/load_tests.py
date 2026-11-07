from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.load_test import LoadTestRun
from app.models.user import User
from app.services import load_test_service as svc

router = APIRouter(prefix="/api/v1/admin/load-tests", tags=["load-tests"])


class StartIn(BaseModel):
    scenario: Literal["NORMAL", "FESTIVAL"]
    # Optional overrides, handy for short local runs.
    users: int | None = Field(default=None, ge=1, le=500)
    duration_s: int | None = Field(default=None, ge=10, le=3600)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    scenario: str
    status: str
    target_users: int
    spawn_rate: int
    duration_seconds: int
    started_at: datetime
    ended_at: datetime | None
    total_requests: int | None
    failed_requests: int | None
    avg_response_ms: float | None
    p95_response_ms: float | None
    peak_rps: float | None
    avg_cpu_percent: float | None
    peak_cpu_percent: float | None
    min_instances: int | None
    max_instances: int | None
    estimated_cost_usd: float | None


class RunDetail(BaseModel):
    run: RunOut
    live_stats: dict | None


class RunPage(BaseModel):
    items: list[RunOut]
    page: int
    page_size: int
    total: int


def _out(r: LoadTestRun) -> RunOut:
    return RunOut.model_validate(r)


@router.get("/scenarios")
def list_scenarios(_: User = Depends(require_admin)):
    return svc.scenarios()


@router.post("", status_code=202)
def start(body: StartIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    run = svc.start(db, admin, body.scenario, body.users, body.duration_s)
    return {"run_id": run.id, "status": run.status}


@router.get("", response_model=RunPage)
def history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows, total = svc.list_runs(db, page, page_size)
    return RunPage(items=[_out(r) for r in rows], page=page, page_size=page_size, total=total)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    run, live = svc.get_with_live(db, run_id)
    return RunDetail(run=_out(run), live_stats=live)


@router.post("/{run_id}/stop", response_model=RunDetail)
def stop_run(run_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return RunDetail(run=_out(svc.stop(db, run_id)), live_stats=None)
