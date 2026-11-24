"""Restaurant / dispatch dashboard API: live order board, delivery partners, stats."""

import logging
from datetime import timedelta

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core import aws
from app.core.config import get_settings
from app.core.time import utcnow
from app.db.session import get_db
from app.models.order import ORDER_STATUSES, Order
from app.models.partner import PARTNER_STATUSES, DeliveryPartner
from app.models.user import User
from app.schemas.order import OrderListOut
from app.schemas.partner import PartnerIn, PartnerOut, PartnerStatusIn
from app.services import order_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

ACTIVE = ("PLACED", "CONFIRMED", "PREPARING", "AWAITING_PARTNER", "OUT_FOR_DELIVERY")


# ---- order board -------------------------------------------------------------


@router.get("/orders", response_model=OrderListOut)
def order_board(
    status_filter: str = Query("ACTIVE", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """status=ACTIVE (default) lists open orders Prime-first, oldest first, the same
    order the worker serves them in. Any single status, or ALL, lists newest first."""
    if status_filter == "ACTIVE":
        conds, order_by = [Order.status.in_(ACTIVE)], (Order.priority.desc(), Order.created_at)
    elif status_filter == "ALL":
        conds, order_by = [], (Order.created_at.desc(),)
    elif status_filter in ORDER_STATUSES:
        conds, order_by = [Order.status == status_filter], (Order.created_at.desc(),)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status")
    total = db.scalar(select(func.count()).select_from(Order).where(*conds))
    orders = db.scalars(
        select(Order)
        .options(*order_service.ORDER_LOAD)
        .where(*conds)
        .order_by(*order_by, Order.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"total": total, "items": [order_service.to_out(o) for o in orders]}


# ---- delivery partners -------------------------------------------------------


def _partner_out(db: Session, partners: list[DeliveryPartner]) -> list[PartnerOut]:
    ids = [p.id for p in partners]
    current = dict(
        db.execute(
            select(Order.partner_id, Order.id).where(
                Order.partner_id.in_(ids), Order.status == "OUT_FOR_DELIVERY"
            )
        ).all()
    )
    out = []
    for p in partners:
        item = PartnerOut.model_validate(p)
        item.current_order_id = current.get(p.id)
        out.append(item)
    return out


@router.get("/partners", response_model=list[PartnerOut])
def list_partners(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    partners = list(db.scalars(select(DeliveryPartner).order_by(DeliveryPartner.id)))
    return _partner_out(db, partners)


@router.post("/partners", response_model=PartnerOut, status_code=status.HTTP_201_CREATED)
def add_partner(body: PartnerIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    partner = DeliveryPartner(name=body.name.strip(), phone=body.phone)
    db.add(partner)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Phone number already used") from None
    db.refresh(partner)
    return _partner_out(db, [partner])[0]


@router.patch("/partners/{partner_id}", response_model=PartnerOut)
def set_partner_status(
    partner_id: int,
    body: PartnerStatusIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Put a partner on or off shift. Not allowed mid-delivery; the worker frees
    them when the delivery finishes."""
    partner = db.get(DeliveryPartner, partner_id, with_for_update=True)
    if partner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
    if partner.status == "BUSY":
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Partner is on a delivery")
    partner.status = body.status
    db.commit()
    return _partner_out(db, [partner])[0]


# ---- stats for the dashboard header -----------------------------------------------


def _queue_depths() -> dict:
    s = get_settings()
    out = {}
    for label, name in (("prime", s.sqs_prime_queue), ("standard", s.sqs_standard_queue)):
        try:
            attrs = aws.sqs().get_queue_attributes(
                QueueUrl=aws.queue_url(name),
                AttributeNames=[
                    "ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible",
                ],
            )["Attributes"]
            out[label] = {
                "waiting": int(attrs["ApproximateNumberOfMessages"]),
                "in_flight": int(attrs["ApproximateNumberOfMessagesNotVisible"]),
            }
        except (BotoCoreError, ClientError) as exc:
            log.warning("queue depth unavailable for %s: %s", name, exc)
            out[label] = None
    return out


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


@router.get("/dispatch/stats")
def dispatch_stats(
    window_minutes: int = Query(15, ge=1, le=1440),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    by_status = dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).all())
    partners = dict(
        db.execute(
            select(DeliveryPartner.status, func.count()).group_by(DeliveryPartner.status)
        ).all()
    )

    # Prime vs standard waiting times for recent orders: the key festival-day number.
    since = utcnow() - timedelta(minutes=window_minutes)
    rows = db.execute(
        select(
            Order.priority,
            Order.created_at,
            Order.confirmed_at,
            Order.ready_at,
            Order.assigned_at,
            Order.delivered_at,
        )
        .where(Order.created_at >= since)
        .limit(20000)
    ).all()
    waits = {p: {"confirm": [], "partner": [], "total": []} for p in (0, 1)}
    for pr, created, confirmed, ready, assigned, delivered in rows:
        if confirmed:
            waits[pr]["confirm"].append((confirmed - created).total_seconds())
        if ready and assigned:
            waits[pr]["partner"].append((assigned - ready).total_seconds())
        if delivered:
            waits[pr]["total"].append((delivered - created).total_seconds())

    def summary(p: int) -> dict:
        return {
            "orders": sum(1 for r in rows if r[0] == p),
            "avg_seconds_to_confirm": _avg(waits[p]["confirm"]),
            "avg_seconds_waiting_for_partner": _avg(waits[p]["partner"]),
            "avg_seconds_to_deliver": _avg(waits[p]["total"]),
        }

    return {
        "queues": _queue_depths(),
        "orders_by_status": {s: by_status.get(s, 0) for s in ORDER_STATUSES},
        "partners": {s: partners.get(s, 0) for s in PARTNER_STATUSES},
        "window_minutes": window_minutes,
        "prime": summary(1),
        "standard": summary(0),
    }
