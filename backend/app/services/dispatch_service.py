"""Order processing done by the worker (one worker per EC2 instance).

Lifecycle:
  PLACED --(SQS message)--> CONFIRMED --timer--> PREPARING --timer--> AWAITING_PARTNER
  --(free partner)--> OUT_FOR_DELIVERY --timer--> DELIVERED (partner AVAILABLE again)

Many workers can run at once. Every step locks the rows it changes with
SELECT ... FOR UPDATE SKIP LOCKED, so two workers never take the same order or the
same delivery partner; each simply skips rows another worker is holding.
(SQLite in tests ignores the lock clause; the real-MySQL test covers it.)
"""

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utcnow
from app.models.order import Order, OrderEvent
from app.models.partner import DeliveryPartner
from app.services import queue_publisher
from app.services.notification_service import Notice

log = logging.getLogger(__name__)


@dataclass
class StepResult:
    count: int = 0
    notices: list[Notice] = field(default_factory=list)


def _later(now: datetime, seconds: float) -> datetime:
    jitter = get_settings().timer_jitter
    return now + timedelta(seconds=seconds * random.uniform(1 - jitter, 1 + jitter))


def _event(db: Session, order: Order, status: str, now: datetime, note: str | None = None) -> None:
    # Plain insert: appending to order.events would first load the whole timeline.
    db.add(OrderEvent(order_id=order.id, status=status, note=note, created_at=now))


def _notice(order: Order, partner_name: str | None = None) -> Notice:
    return Notice(order.id, order.user_id, order.status, order.is_synthetic, partner_name)


def _locked(stmt):
    return stmt.with_for_update(skip_locked=True)


# ---- step 1: SQS message -> CONFIRMED ---------------------------------------


def parse_message(body: str) -> int | None:
    try:
        return int(json.loads(body)["order_id"])
    except (ValueError, KeyError, TypeError):
        return None


def confirm_order(db: Session, order_id: int, now: datetime | None = None) -> StepResult:
    """Idempotent: SQS can deliver a message twice, but only a PLACED order moves on,
    so a repeat is a harmless no-op. Raises on DB errors so the message is retried."""
    now = now or utcnow()
    s = get_settings()
    res = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == "PLACED")
        .values(
            status="CONFIRMED",
            confirmed_at=now,
            stage_due_at=_later(now, s.confirm_seconds),
            enqueued_at=func.coalesce(Order.enqueued_at, now),
        )
    )
    if res.rowcount == 0:
        db.rollback()
        log.info("order %s already processed or missing; dropping message", order_id)
        return StepResult()
    order = db.get(Order, order_id)
    _event(db, order, "CONFIRMED", now)
    db.commit()
    return StepResult(1, [_notice(order)])


# ---- timer-driven steps ---------------------------------------------------------


def _due(db: Session, status: str, now: datetime) -> list[Order]:
    return list(
        db.scalars(
            _locked(
                select(Order)
                .where(Order.status == status, Order.stage_due_at <= now)
                .order_by(Order.priority.desc(), Order.stage_due_at, Order.id)
                .limit(get_settings().worker_batch_size)
            )
        )
    )


def start_preparing(db: Session, now: datetime | None = None) -> StepResult:
    now = now or utcnow()
    orders = _due(db, "CONFIRMED", now)
    for o in orders:
        o.status, o.preparing_at = "PREPARING", now
        o.stage_due_at = _later(now, get_settings().prep_seconds)
        _event(db, o, "PREPARING", now)
    db.commit()
    return StepResult(len(orders))


def mark_ready(db: Session, now: datetime | None = None) -> StepResult:
    now = now or utcnow()
    orders = _due(db, "PREPARING", now)
    for o in orders:
        o.status, o.ready_at, o.stage_due_at = "AWAITING_PARTNER", now, None
        _event(db, o, "AWAITING_PARTNER", now, "Food is ready, finding a delivery partner")
    db.commit()
    return StepResult(len(orders))


def assign_partners(db: Session, now: datetime | None = None) -> StepResult:
    """Give each free partner the most urgent waiting order: Prime first, then the
    longest-waiting. A standard order waiting more than aging_seconds counts as urgent
    too, so festival-day Prime traffic can't starve it."""
    now = now or utcnow()
    s = get_settings()
    partners = list(
        db.scalars(
            _locked(
                select(DeliveryPartner)
                .where(DeliveryPartner.status == "AVAILABLE")
                # Spread work: the partner with the fewest deliveries goes first.
                .order_by(DeliveryPartner.deliveries_count, DeliveryPartner.id)
                .limit(s.worker_batch_size)
            )
        )
    )
    if not partners:
        db.rollback()
        return StepResult()

    aged_before = now - timedelta(seconds=s.aging_seconds)
    urgent = case((or_(Order.priority == 1, Order.ready_at <= aged_before), 1), else_=0)
    orders = list(
        db.scalars(
            _locked(
                select(Order)
                .where(Order.status == "AWAITING_PARTNER")
                .order_by(urgent.desc(), Order.ready_at, Order.id)
                .limit(len(partners))
            )
        )
    )
    result = StepResult()
    for order, partner in zip(orders, partners, strict=False):
        partner.status = "BUSY"
        order.partner_id, order.assigned_at = partner.id, now
        order.status = "OUT_FOR_DELIVERY"
        order.stage_due_at = _later(now, s.delivery_seconds)
        _event(db, order, "OUT_FOR_DELIVERY", now, f"Picked up by {partner.name}")
        result.count += 1
        result.notices.append(_notice(order, partner.name))
    db.commit()
    return result


def complete_deliveries(db: Session, now: datetime | None = None) -> StepResult:
    now = now or utcnow()
    orders = _due(db, "OUT_FOR_DELIVERY", now)
    result = StepResult()
    for o in orders:
        o.status, o.delivered_at, o.stage_due_at = "DELIVERED", now, None
        _event(db, o, "DELIVERED", now)
        if o.partner_id is not None:
            partner = db.get(DeliveryPartner, o.partner_id, with_for_update=True)
            if partner is not None:
                partner.deliveries_count += 1
                if partner.status == "BUSY":
                    partner.status = "AVAILABLE"
        result.count += 1
        result.notices.append(_notice(o))
    db.commit()
    return result


def tick(db: Session, now: datetime | None = None) -> tuple[dict[str, int], list[Notice]]:
    """One pass over every timer-driven step. Deliveries finish before assignment,
    so a partner freed this tick can take a new order straight away."""
    now = now or utcnow()
    counts, notices = {}, []
    for name, step in (
        ("preparing", start_preparing),
        ("ready", mark_ready),
        ("delivered", complete_deliveries),
        ("assigned", assign_partners),
    ):
        r = step(db, now)
        counts[name] = r.count
        notices.extend(r.notices)
    return counts, notices


# ---- sweeper ------------------------------------------------------------------------


def sweep_unqueued(db: Session, now: datetime | None = None) -> int:
    """Re-send orders whose SQS send failed at checkout (enqueued_at NULL). The wait
    avoids racing the API, which sets enqueued_at right after its own send."""
    now = now or utcnow()
    s = get_settings()
    orders = list(
        db.scalars(
            _locked(
                select(Order)
                .where(
                    Order.status == "PLACED",
                    Order.enqueued_at.is_(None),
                    Order.created_at <= now - timedelta(seconds=s.sweeper_after_seconds),
                )
                .order_by(Order.priority.desc(), Order.id)
                .limit(s.worker_batch_size)
            )
        )
    )
    sent = 0
    for o in orders:
        if queue_publisher.send_order(o.id, o.priority):
            o.enqueued_at = now
            sent += 1
    db.commit()
    if sent:
        log.info("sweeper re-sent %d orders to SQS", sent)
    return sent
