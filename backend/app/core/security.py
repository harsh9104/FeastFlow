from datetime import timedelta

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.time import utcnow

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int, role: str, is_prime: bool) -> str:
    s = get_settings()
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,
        # For the UI only. The server re-reads Prime from the database on every
        # request, so an old token can never grant priority after expiry.
        "prime": is_prime,
        "iat": now,
        "exp": now + timedelta(minutes=s.jwt_expire_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    return int(payload["sub"])
