from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.user import User

# target status -> required current status
TRANSITIONS = {"PREPARING": "PENDING", "COMPLETED": "PREPARING"}

_LOAD = (selectinload(Order.items).selectinload(OrderItem.menu_item),)


def _with_customer(db: Session, order_id: int) -> tuple[Order, str]:
    row = db.execute(
        select(Order, User.full_name)
        .join(User, User.id == Order.user_id)
        .options(*_LOAD)
        .where(Order.id == order_id)
    ).one()
    return row[0], row[1]


def list_queue(db: Session, limit: int) -> list[tuple[Order, str]]:
    rows = db.execute(
        select(Order, User.full_name)
        .join(User, User.id == Order.user_id)
        .options(*_LOAD)
        .where(Order.status == "PENDING")
        .order_by(Order.priority.desc(), Order.created_at.asc(), Order.id.asc())
        .limit(limit)
    ).all()
    return [(r[0], r[1]) for r in rows]


def list_orders(
    db: Session,
    status: str | None,
    priority: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    page: int,
    page_size: int,
) -> tuple[list[tuple[Order, str]], int]:
    conds = []
    if status:
        conds.append(Order.status == status)
    if priority is not None:
        conds.append(Order.priority == priority)
    if date_from:
        conds.append(Order.created_at >= date_from)
    if date_to:
        conds.append(Order.created_at <= date_to)
    total = db.scalar(select(func.count()).select_from(Order).where(*conds))
    rows = db.execute(
        select(Order, User.full_name)
        .join(User, User.id == Order.user_id)
        .options(*_LOAD)
        .where(*conds)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return [(r[0], r[1]) for r in rows], total


def claim_next(db: Session, admin: User) -> tuple[Order, str] | None:
    """Claim the highest-priority, oldest PENDING order. Safe across concurrent admins/instances."""
    next_id = db.scalar(
        select(Order.id)
        .where(Order.status == "PENDING")
        .order_by(Order.priority.desc(), Order.created_at.asc(), Order.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if next_id is None:
        db.rollback()
        return None
    db.execute(
        update(Order)
        .where(Order.id == next_id)
        .values(
            status="PREPARING",
            version=Order.version + 1,
            preparing_at=func.now(),
            updated_at=func.now(),
        )
    )
    db.add(
        OrderStatusHistory(
            order_id=next_id, from_status="PENDING", to_status="PREPARING", changed_by=admin.id
        )
    )
    db.commit()
    return _with_customer(db, next_id)


def transition(
    db: Session, admin: User, order_id: int, to_status: str, version: int
) -> tuple[Order, str]:
    expected_from = TRANSITIONS.get(to_status)
    if expected_from is None:
        raise AppError(422, "INVALID_STATUS", "Target status must be PREPARING or COMPLETED")
    result = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == expected_from, Order.version == version)
        .values(
            status=to_status,
            version=Order.version + 1,
            updated_at=func.now(),
            preparing_at=func.now() if to_status == "PREPARING" else Order.preparing_at,
            completed_at=func.now() if to_status == "COMPLETED" else Order.completed_at,
        )
    )
    if result.rowcount == 0:
        db.rollback()
        current = db.get(Order, order_id)
        if current is None:
            raise AppError(404, "NOT_FOUND", "Order not found")
        if current.status != expected_from:
            raise AppError(
                409,
                "INVALID_TRANSITION",
                f"Order {order_id} cannot move from {current.status} to {to_status}",
            )
        raise AppError(
            409,
            "STALE_VERSION",
            f"Order {order_id} was modified (current version {current.version})",
        )
    db.add(
        OrderStatusHistory(
            order_id=order_id, from_status=expected_from, to_status=to_status, changed_by=admin.id
        )
    )
    db.commit()
    return _with_customer(db, order_id)


def history(db: Session, order_id: int) -> list[OrderStatusHistory]:
    if db.get(Order, order_id) is None:
        raise AppError(404, "NOT_FOUND", "Order not found")
    return list(
        db.scalars(
            select(OrderStatusHistory)
            .where(OrderStatusHistory.order_id == order_id)
            .order_by(OrderStatusHistory.id)
        )
    )


def stats(db: Session, date_from: datetime | None, date_to: datetime | None) -> dict:
    conds = []
    if date_from:
        conds.append(Order.created_at >= date_from)
    if date_to:
        conds.append(Order.created_at <= date_to)
    counts = dict.fromkeys(("PENDING", "PREPARING", "COMPLETED"), 0)
    for status, n in db.execute(
        select(Order.status, func.count()).where(*conds).group_by(Order.status)
    ):
        counts[status] = n
    wait = func.extract("epoch", Order.preparing_at - Order.created_at)
    waits = {
        p: avg
        for p, avg in db.execute(
            select(Order.priority, func.avg(wait))
            .where(Order.preparing_at.is_not(None), *conds)
            .group_by(Order.priority)
        )
    }

    def r(v):
        return None if v is None else round(float(v), 2)

    return {
        "counts_by_status": counts,
        "avg_wait_premium_s": r(waits.get(1)),
        "avg_wait_free_s": r(waits.get(0)),
    }
