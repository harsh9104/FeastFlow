from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.time import utcnow
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/api/admin/users", tags=["admin"])


@router.get("")
def list_users(
    prime_only: bool = False,
    include_test_users: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    conds = [User.prime_expires_at > utcnow()] if prime_only else []
    if not include_test_users:
        conds.append(User.is_test_user.is_(False))
    total = db.scalar(select(func.count()).select_from(User).where(*conds))
    users = db.scalars(
        select(User).where(*conds).order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"total": total, "items": [UserOut.model_validate(u) for u in users]}
