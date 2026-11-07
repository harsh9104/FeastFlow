from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.user import LoginIn, RegisterIn, TokenOut, UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    return auth_service.register(
        db, body.full_name, body.email, body.password, body.subscription_tier
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user, token, expires_in = auth_service.login(db, body.email, body.password)
    return TokenOut(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))
