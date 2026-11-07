from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

ALGO = "HS256"


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user) -> tuple[str, int]:
    s = get_settings()
    expires_in = s.jwt_expire_minutes * 60
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "tier": user.subscription_tier,
        "exp": datetime.now(UTC) + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGO), expires_in


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGO])
