from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.errors import AppError
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import TierIn, UserOut, UserPage
from app.services import auth_service

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])


@router.get("", response_model=UserPage)
def list_users(
    tier: Literal["FREE", "PREMIUM"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = select(User)
    if tier:
        q = q.where(User.subscription_tier == tier)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(User.id).limit(page_size).offset((page - 1) * page_size)).all()
    return UserPage(items=rows, page=page, page_size=page_size, total=total)


@router.patch("/{user_id}/subscription", response_model=UserOut)
def change_tier(
    user_id: int,
    body: TierIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "NOT_FOUND", "User not found")
    return auth_service.set_tier(db, user, body.subscription_tier)
