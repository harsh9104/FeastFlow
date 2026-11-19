from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.time import utcnow
from app.models.menu import MenuItem, Restaurant
from app.models.order import Order, OrderEvent, OrderItem
from app.models.user import User
from app.schemas.order import OrderIn, OrderOut
from app.services import queue_publisher

ORDER_LOAD = (
    selectinload(Order.items).selectinload(OrderItem.menu_item),
    selectinload(Order.events),
    selectinload(Order.restaurant),
    selectinload(Order.partner),
    selectinload(Order.user),
)


def _unprocessable(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)


def get_order(db: Session, order_id: int) -> Order | None:
    return db.scalar(select(Order).options(*ORDER_LOAD).where(Order.id == order_id))


def _by_idempotency_key(db: Session, user_id: int, key: str) -> Order | None:
    return db.scalar(
        select(Order)
        .options(*ORDER_LOAD)
        .where(Order.user_id == user_id, Order.idempotency_key == key)
    )


def place_order(
    db: Session, user: User, body: OrderIn, idempotency_key: str | None, synthetic: bool = False
) -> tuple[Order, bool]:
    """Save the order, then send it to SQS. Returns (order, created).
    created=False means the same Idempotency-Key was seen before (a retry)."""
    s = get_settings()
    if idempotency_key and (existing := _by_idempotency_key(db, user.id, idempotency_key)):
        return existing, False

    # Merge duplicate lines (same item added twice) before validating.
    qty: dict[int, int] = defaultdict(int)
    for line in body.items:
        qty[line.menu_item_id] += line.quantity
    if len(qty) > s.max_order_lines:
        raise _unprocessable(f"At most {s.max_order_lines} different items per order")
    if any(q > s.max_item_quantity for q in qty.values()):
        raise _unprocessable(f"At most {s.max_item_quantity} of one item per order")

    menu = {
        m.id: m
        for m in db.scalars(
            select(MenuItem).options(selectinload(MenuItem.restaurant)).where(MenuItem.id.in_(qty))
        )
    }
    missing = sorted(set(qty) - set(menu))
    if missing:
        raise _unprocessable(f"Unknown menu items: {missing}")
    restaurant_ids = {m.restaurant_id for m in menu.values()}
    if len(restaurant_ids) != 1:
        raise _unprocessable("All items must come from the same restaurant")
    restaurant = next(iter(menu.values())).restaurant
    if not restaurant.is_open:
        raise _unprocessable(f"{restaurant.name} is closed right now")
    unavailable = [m.name for m in menu.values() if not m.is_available]
    if unavailable:
        raise _unprocessable(f"Not available right now: {', '.join(unavailable)}")

    # Prices always come from the database, never from the client.
    priority = 1 if user.is_prime else 0
    order = Order(
        user_id=user.id,
        restaurant_id=restaurant.id,
        priority=priority,
        total_amount=sum(menu[i].price * q for i, q in qty.items()),
        delivery_address=body.delivery_address.strip(),
        idempotency_key=idempotency_key,
        is_synthetic=synthetic or user.is_test_user,
        items=[
            OrderItem(menu_item_id=i, quantity=q, unit_price=menu[i].price)
            for i, q in qty.items()
        ],
        events=[OrderEvent(status="PLACED", note="Prime priority" if priority else None)],
    )
    db.add(order)
    try:
        db.commit()
    except IntegrityError:
        # Two retries with the same key raced; the other one won.
        db.rollback()
        if idempotency_key and (existing := _by_idempotency_key(db, user.id, idempotency_key)):
            return existing, False
        raise

    # Commit first, then send: the worker must be able to find the row when the
    # message arrives. If the send fails, enqueued_at stays NULL for the sweeper.
    if queue_publisher.send_order(order.id, priority):
        order.enqueued_at = utcnow()
        db.commit()
    return get_order(db, order.id), True


def list_orders_for_user(
    db: Session, user_id: int, page: int, page_size: int
) -> tuple[list[Order], int]:
    total = db.scalar(select(func.count()).select_from(Order).where(Order.user_id == user_id))
    orders = db.scalars(
        select(Order)
        .options(*ORDER_LOAD)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(orders), total


def to_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        status=order.status,
        priority=order.priority,
        is_prime=order.priority == 1,
        restaurant_id=order.restaurant_id,
        restaurant_name=order.restaurant.name,
        total_amount=order.total_amount,
        delivery_address=order.delivery_address,
        created_at=order.created_at,
        customer_name=order.user.name,
        partner_name=order.partner.name if order.partner else None,
        partner_phone=order.partner.phone if order.partner else None,
        items=[
            {
                "menu_item_id": i.menu_item_id,
                "name": i.menu_item.name,
                "quantity": i.quantity,
                "unit_price": i.unit_price,
            }
            for i in order.items
        ],
        events=order.events,
    )


def list_restaurants(db: Session) -> list[Restaurant]:
    return list(db.scalars(select(Restaurant).order_by(Restaurant.id)))
