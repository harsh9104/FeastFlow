from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_customer
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import TierIn, UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me/subscription", response_model=UserOut)
def change_my_tier(
    body: TierIn, user: User = Depends(require_customer), db: Session = Depends(get_db)
):
    return auth_service.set_tier(db, user, body.subscription_tier)
