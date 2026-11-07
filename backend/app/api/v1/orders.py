from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_customer
from app.db.session import get_db
from app.models.order import Order
from app.models.user import User
from app.schemas.order import (
    HistoryOut,
    OrderCreateIn,
    OrderDetailOut,
    OrderItemOut,
    OrderOut,
    OrderPage,
)
from app.services import order_service

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def to_out(o: Order) -> OrderOut:
    return OrderOut(
        id=o.id,
        status=o.status,
        priority=o.priority,
        tier_at_order=o.tier_at_order,
        total_amount=o.total_amount,
        notes=o.notes,
        version=o.version,
        created_at=o.created_at,
        items=[
            OrderItemOut(
                menu_item_id=i.menu_item_id,
                name=i.menu_item.name,
                quantity=i.quantity,
                unit_price=i.unit_price,
                line_total=i.line_total,
            )
            for i in o.items
        ],
    )


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    body: OrderCreateIn,
    response: Response,
    idempotency_key: str | None = Header(default=None, max_length=64),
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    order, created = order_service.create_order(
        db, user, [(i.menu_item_id, i.quantity) for i in body.items], body.notes, idempotency_key
    )
    if not created:
        response.status_code = 200
    return to_out(order)


@router.get("", response_model=OrderPage)
def list_orders(
    status: Literal["PENDING", "PREPARING", "COMPLETED"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    rows, total = order_service.list_orders(db, user, status, page, page_size)
    return OrderPage(items=[to_out(o) for o in rows], page=page, page_size=page_size, total=total)


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order(order_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    o = order_service.get_order(db, user, order_id)
    return OrderDetailOut(
        **to_out(o).model_dump(),
        history=[HistoryOut.model_validate(h) for h in o.history],
    )
