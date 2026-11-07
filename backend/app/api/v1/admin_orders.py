from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.v1.orders import to_out
from app.db.session import get_db
from app.models.order import Order
from app.models.user import User
from app.schemas.order import OrderOut
from app.services import queue_service

router = APIRouter(prefix="/api/v1/admin/orders", tags=["admin-orders"])


class AdminOrderOut(OrderOut):
    customer: str


class AdminOrderPage(BaseModel):
    items: list[AdminOrderOut]
    page: int
    page_size: int
    total: int


class StatusIn(BaseModel):
    status: Literal["PREPARING", "COMPLETED"]
    version: int = Field(ge=1)


class HistoryRow(BaseModel):
    from_status: str | None
    to_status: str
    changed_by: int
    changed_at: datetime


class StatsOut(BaseModel):
    counts_by_status: dict[str, int]
    avg_wait_premium_s: float | None
    avg_wait_free_s: float | None


def _admin_out(pair: tuple[Order, str]) -> AdminOrderOut:
    order, customer = pair
    return AdminOrderOut(**to_out(order).model_dump(), customer=customer)


@router.get("", response_model=AdminOrderPage)
def list_orders(
    status: Literal["PENDING", "PREPARING", "COMPLETED"] | None = None,
    priority: int | None = Query(None, ge=0, le=1),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows, total = queue_service.list_orders(
        db, status, priority, date_from, date_to, page, page_size
    )
    return AdminOrderPage(
        items=[_admin_out(r) for r in rows], page=page, page_size=page_size, total=total
    )


@router.get("/queue")
def queue(
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {"items": [_admin_out(r) for r in queue_service.list_queue(db, limit)]}


@router.post("/queue/next", response_model=AdminOrderOut, responses={204: {"description": "Empty"}})
def claim_next(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    pair = queue_service.claim_next(db, admin)
    if pair is None:
        return Response(status_code=204)
    return _admin_out(pair)


@router.get("/stats", response_model=StatsOut)
def stats(
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return queue_service.stats(db, date_from, date_to)


@router.patch("/{order_id}/status", response_model=AdminOrderOut)
def change_status(
    order_id: int,
    body: StatusIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _admin_out(queue_service.transition(db, admin, order_id, body.status, body.version))


@router.get("/{order_id}/history", response_model=list[HistoryRow])
def history(order_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [
        HistoryRow(
            from_status=h.from_status,
            to_status=h.to_status,
            changed_by=h.changed_by,
            changed_at=h.changed_at,
        )
        for h in queue_service.history(db, order_id)
    ]
