from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.order import OrderIn, OrderListOut, OrderOut
from app.services import order_service

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=status.HTTP_202_ACCEPTED)
def place_order(
    body: OrderIn,
    response: Response,
    idempotency_key: str | None = Header(default=None, max_length=64),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """202: the order is saved and queued; a worker confirms it asynchronously.
    Send the same Idempotency-Key when retrying to avoid a duplicate order (200)."""
    if user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins can't place orders")
    order, created = order_service.place_order(db, user, body, idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK
    return order_service.to_out(order)


@router.get("", response_model=OrderListOut)
def my_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    orders, total = order_service.list_orders_for_user(db, user.id, page, page_size)
    return {"total": total, "items": [order_service.to_out(o) for o in orders]}


@router.get("/{order_id}", response_model=OrderOut)
def order_detail(
    order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    order = order_service.get_order(db, order_id)
    # 404 rather than 403 for other people's orders, so ids can't be probed.
    if order is None or (order.user_id != user.id and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order_service.to_out(order)
