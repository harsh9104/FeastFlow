from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import LoginIn, RegisterIn, TokenOut, UserOut
from app.services import notification_service, user_service

router = APIRouter(prefix="/api", tags=["auth"])


def _token_for(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_token(user.id, user.role, user.is_prime),
        user=UserOut.model_validate(user),
    )


@router.post("/auth/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    user = user_service.register(db, body.name, body.email, body.password)
    # Best effort: AWS emails a confirmation link; order updates start once it's clicked.
    notification_service.subscribe_email(user.id, user.email)
    return _token_for(user)


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    return _token_for(user_service.authenticate(db, body.email, body.password))


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/prime/subscribe", response_model=TokenOut)
def subscribe_prime(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns a fresh token so the UI shows the Prime badge straight away."""
    return _token_for(user_service.subscribe_prime(db, user))


@router.post("/prime/cancel", response_model=TokenOut)
def cancel_prime(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _token_for(user_service.cancel_prime(db, user))
