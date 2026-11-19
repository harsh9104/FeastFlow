from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import LOCKED_PASSWORD_HASH, hash_password, verify_password
from app.core.time import utcnow
from app.models.user import User

# Checked when the email is unknown, so login takes the same time whether or not
# the account exists (stops attackers discovering registered emails by timing).
_DUMMY_HASH = hash_password("timing-equaliser")


def register(db: Session, name: str, email: str, password: str) -> User:
    user = User(name=name.strip(), email=email.lower(), password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return user


def subscribe_prime(db: Session, user: User) -> User:
    """Mock payment. Renewing early adds the new period on top of the time left."""
    start = user.prime_expires_at if user.is_prime else utcnow()
    user.prime_expires_at = start + timedelta(days=get_settings().prime_plan_days)
    db.commit()
    db.refresh(user)
    return user


def cancel_prime(db: Session, user: User) -> User:
    if user.is_prime:
        user.prime_expires_at = utcnow()
        db.commit()
        db.refresh(user)
    return user


def ensure_admin(db: Session) -> bool:
    """Create the configured admin if missing. Safe to run on every boot. True if created."""
    s = get_settings()
    if db.scalar(select(User).where(User.email == s.admin_email.lower())):
        return False
    db.add(
        User(
            name="Admin",
            email=s.admin_email.lower(),
            password_hash=hash_password(s.admin_password),
            role="ADMIN",
        )
    )
    try:
        db.commit()
    except IntegrityError:  # another EC2 instance seeded it at the same moment
        db.rollback()
        return False
    return True


PRIME_FOREVER = datetime(2099, 1, 1)


def loadtest_email(i: int) -> str:
    return f"customer{i:04d}@{get_settings().loadtest_email_domain}"


def ensure_test_users(db: Session) -> int:
    """Create the festival/load-test customers if missing, and set their password from
    LOADTEST_PASSWORD (or lock them when it's unset). Safe on every boot and on several
    instances at once. Returns how many were created."""
    s = get_settings()
    # One bcrypt hash shared by all of them: hashing 200 times would add ~1 min to boot.
    pw_hash = hash_password(s.loadtest_password) if s.loadtest_password else LOCKED_PASSWORD_HASH
    existing = set(db.scalars(select(User.email).where(User.is_test_user.is_(True))))
    prime_count = round(s.loadtest_users * s.loadtest_prime_percent / 100)
    created = 0
    for i in range(1, s.loadtest_users + 1):
        email = loadtest_email(i)
        if email in existing:
            continue
        db.add(
            User(
                name=f"Festival Customer {i}",
                email=email,
                password_hash=pw_hash,
                is_test_user=True,
                prime_expires_at=PRIME_FOREVER if i <= prime_count else None,
            )
        )
        created += 1
    try:
        db.commit()
    except IntegrityError:  # another instance seeded at the same moment
        db.rollback()
        created = 0
    # ORM update (not a raw table update) so User objects already loaded in this
    # session see the new hash too.
    db.execute(update(User).where(User.is_test_user.is_(True)).values(password_hash=pw_hash))
    db.commit()
    return created
