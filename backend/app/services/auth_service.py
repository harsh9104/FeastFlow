from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import create_token, hash_password, verify_password
from app.models.user import User
from app.services import login_limiter

# Valid hash used to keep login timing similar when the email is unknown.
_DUMMY_HASH = hash_password("dummy-password")


def register(db: Session, full_name: str, email: str, password: str, tier: str) -> User:
    email = email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise AppError(409, "EMAIL_TAKEN", "Email is already registered")
    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        subscription_tier=tier,
        role="CUSTOMER",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "Email is already registered") from None
    return user


def login(db: Session, email: str, password: str, ip: str) -> tuple[User, str, int]:
    email = email.lower()
    # Unknown emails are counted too, so lockouts don't reveal which accounts exist.
    login_limiter.check(db, email, ip)
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        login_limiter.record_failure(db, email, ip)
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid email or password")
    login_limiter.clear_email(db, email)
    token, expires_in = create_token(user)
    return user, token, expires_in


def set_tier(db: Session, user: User, tier: str) -> User:
    user.subscription_tier = tier
    db.commit()
    return user
