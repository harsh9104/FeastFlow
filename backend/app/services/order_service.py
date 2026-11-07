from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.models.order import MenuItem, Order, OrderItem, OrderStatusHistory
from app.models.user import User


def _find_idempotent(db: Session, user_id: int, key: str) -> Order | None:
    return db.scalar(
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.menu_item))
        .where(Order.user_id == user_id, Order.idempotency_key == key)
    )


def create_order(
    db: Session, user: User, lines: list[tuple[int, int]], notes: str | None, idem_key: str | None
) -> tuple[Order, bool]:
    """Returns (order, created). created=False means an idempotent replay."""
    if idem_key:
        existing = _find_idempotent(db, user.id, idem_key)
        if existing:
            return existing, False

    # Merge duplicate lines.
    merged: dict[int, int] = {}
    for item_id, qty in lines:
        merged[item_id] = merged.get(item_id, 0) + qty
    if any(q > 20 for q in merged.values()):
        raise AppError(422, "QUANTITY_EXCEEDED", "Maximum quantity per item is 20")

    menu = {
        m.id: m for m in db.scalars(select(MenuItem).where(MenuItem.id.in_(merged.keys()))).all()
    }
    bad = [i for i in merged if i not in menu or not menu[i].is_available]
    if bad:
        raise AppError(
            422, "ITEM_UNAVAILABLE", "Some items are unavailable", {"menu_item_ids": sorted(bad)}
        )

    order = Order(
        user_id=user.id,
        status="PENDING",
        priority=1 if user.subscription_tier == "PREMIUM" else 0,
        tier_at_order=user.subscription_tier,
        notes=notes,
        idempotency_key=idem_key,
        total_amount=Decimal("0"),
    )
    total = Decimal("0")
    for item_id, qty in merged.items():
        price = menu[item_id].price
        line = price * qty
        total += line
        order.items.append(
            OrderItem(menu_item_id=item_id, quantity=qty, unit_price=price, line_total=line)
        )
    order.total_amount = total
    order.history.append(
        OrderStatusHistory(from_status=None, to_status="PENDING", changed_by=user.id)
    )
    db.add(order)
    try:
        db.commit()  # order + items + first history row in one transaction
    except IntegrityError:
        db.rollback()
        if idem_key:
            existing = _find_idempotent(db, user.id, idem_key)
            if existing:
                return existing, False
        raise
    return _load(db, order.id), True


def _load(db: Session, order_id: int) -> Order:
    return db.scalars(
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.history),
        )
        .where(Order.id == order_id)
    ).one()


def list_orders(
    db: Session, user: User, status: str | None, page: int, page_size: int
) -> tuple[list[Order], int]:
    q = select(Order).where(Order.user_id == user.id)
    if status:
        q = q.where(Order.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(
        q.options(selectinload(Order.items).selectinload(OrderItem.menu_item))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return list(rows), total


def get_order(db: Session, user: User, order_id: int) -> Order:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if order is None:  # also covers other users' orders: no existence leak
        raise AppError(404, "NOT_FOUND", "Order not found")
    return _load(db, order_id)
