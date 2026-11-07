from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.errors import AppError
from app.db.session import get_db
from app.models.load_test import LoadTestRun
from app.models.report import Report
from app.models.user import User
from app.services import cost_service, report_service

router = APIRouter(tags=["costs-reports"])
MAX_WINDOW = timedelta(days=31)


@router.get("/api/v1/admin/costs/rates")
def rates(_: User = Depends(require_admin)):
    return {
        "region": cost_service.RATE_TABLE["region"],
        "effective_date": cost_service.RATE_TABLE["effective_date"],
        "note": cost_service.RATE_TABLE["note"],
        "rates": cost_service.RATE_TABLE["rates"],
        "assumptions": cost_service.RATE_TABLE["assumptions"],
    }


@router.get("/api/v1/admin/costs/estimate")
def estimate(
    run_id: int | None = None,
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    requests = None
    if run_id is not None:
        run = db.get(LoadTestRun, run_id)
        if run is None:
            raise AppError(404, "NOT_FOUND", "Load test run not found")
        start, end = run.started_at, run.ended_at or datetime.now(UTC)
        requests = run.total_requests
    else:
        end = date_to or datetime.now(UTC)
        start = date_from or end - timedelta(hours=1)
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        if end <= start:
            raise AppError(422, "INVALID_PERIOD", "'to' must be after 'from'")
        if end - start > MAX_WINDOW:
            raise AppError(422, "INVALID_PERIOD", "Period is limited to 31 days")
    result = cost_service.estimate(db, start, end, requests=requests)
    if run_id is not None:
        result["run_id"] = run_id
    return result


class ReportIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    report_type: Literal["LOAD_TEST", "COST", "COMPARISON"]
    format: Literal["JSON", "CSV", "MD"] = "JSON"
    run_ids: list[int] | None = Field(default=None, max_length=2)
    date_from: datetime | None = Field(default=None, alias="from")
    date_to: datetime | None = Field(default=None, alias="to")


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    report_type: str
    load_test_run_id: int | None
    s3_key: str
    format: str
    created_at: datetime


@router.post("/api/v1/admin/reports", status_code=201)
def create_report(
    body: ReportIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    r = report_service.create_report(
        db, admin, body.report_type, body.format, body.run_ids, body.date_from, body.date_to
    )
    return {"report_id": r.id, "s3_key": r.s3_key, "format": r.format, "report_type": r.report_type}


@router.get("/api/v1/admin/reports")
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(Report))
    rows = db.scalars(
        select(Report).order_by(Report.id.desc()).limit(page_size).offset((page - 1) * page_size)
    ).all()
    return {
        "items": [ReportOut.model_validate(r) for r in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/api/v1/admin/reports/{report_id}/download")
def download(report_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if report is None:
        raise AppError(404, "NOT_FOUND", "Report not found")
    return {"url": report_service.download_url(report), "expires_in": report_service.URL_TTL}


@router.get("/api/v1/reports/file", include_in_schema=False)
def report_file(t: str, db: Session = Depends(get_db)):
    """Target of the signed link returned by /download when reports are stored locally."""
    report, data = report_service.read_via_token(db, t)
    name = report.s3_key.rsplit("/", 1)[-1]
    return Response(
        data,
        media_type=report_service.MIME[report.format],
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
